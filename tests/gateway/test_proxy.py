from __future__ import annotations

import asyncio
import json
import socket
import sys
import tempfile
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from trovis_gateway.metrics import GatewayMetrics
from trovis_gateway.protocol import (
    ModbusTcpAdu,
    decode_rtu_adu,
    encode_rtu_adu,
    encode_tcp_adu,
    read_tcp_adu,
)
from trovis_gateway.proxy import ModbusProxy
from trovis_gateway.store import ConfigStore
from trovis_gateway.trace import GatewayTrace
from trovis_gateway.upstream import UpstreamRouter

Handler = Callable[[ModbusTcpAdu, asyncio.StreamWriter], Awaitable[None]]


class FakeController:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[ModbusTcpAdu] = []
        self.server: asyncio.Server | None = None

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)

    @property
    def port(self) -> int:
        assert self.server and self.server.sockets
        return int(self.server.sockets[0].getsockname()[1])

    async def close(self) -> None:
        assert self.server
        self.server.close()
        await self.server.wait_closed()

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await read_tcp_adu(reader)
            self.requests.append(request)
            await self.handler(request, writer)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ConfigStore(Path(self.temporary.name) / "config.json")
        self.metrics = GatewayMetrics()
        self.router = UpstreamRouter(self.metrics, GatewayTrace())
        self.proxy = ModbusProxy(
            host="127.0.0.1",
            port=0,
            store=self.store,
            router=self.router,
            metrics=self.metrics,
            trace=GatewayTrace(),
        )
        self.controllers: list[FakeController] = []
        self.raw_servers: list[asyncio.Server] = []

    async def asyncTearDown(self) -> None:
        await self.proxy.close()
        for controller in self.controllers:
            await controller.close()
        for server in self.raw_servers:
            server.close()
            await server.wait_closed()
        self.temporary.cleanup()

    async def start_controller(self, handler: Handler) -> FakeController:
        controller = FakeController(handler)
        await controller.start()
        self.controllers.append(controller)
        return controller

    async def request(self, pdu: bytes, *, unit_id: int = 7) -> ModbusTcpAdu:
        reader, writer = await asyncio.open_connection("127.0.0.1", self.proxy.bound_port)
        writer.write(encode_tcp_adu(101, unit_id, pdu))
        await writer.drain()
        try:
            return await asyncio.wait_for(read_tcp_adu(reader), 2)
        finally:
            writer.close()
            await writer.wait_closed()

    async def configure(self, controller: FakeController, **overrides: object) -> None:
        values: dict[str, object] = {
            "name": "Fake",
            "transport": "modbus_tcp",
            "host": "127.0.0.1",
            "port": controller.port,
            "upstream_unit_id": 12,
            "timing": {
                "connect_timeout_s": 0.2,
                "response_timeout_s": 0.08,
                "total_request_timeout_s": 1,
                "minimum_request_interval_s": 0,
                "connect_settle_delay_s": 0,
                "reconnect_delay_s": 0,
            },
        }
        values.update(overrides)
        self.store.upsert_profile(values)
        await self.proxy.start()

    async def start_rtu_controller(
        self,
        handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
        **overrides: object,
    ) -> None:
        async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                await handler(reader, writer)
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except ConnectionError:
                    pass

        server = await asyncio.start_server(client, "127.0.0.1", 0)
        self.raw_servers.append(server)
        assert server.sockets
        profile: dict[str, object] = {
            "name": "RTU bridge",
            "transport": "rtu_over_tcp",
            "host": "127.0.0.1",
            "port": server.sockets[0].getsockname()[1],
            "upstream_unit_id": 12,
            "timing": {
                "response_timeout_s": 0.2,
                "total_request_timeout_s": 1,
                "minimum_request_interval_s": 0,
                "client_burst_idle_s": 0,
                "connect_settle_delay_s": 0,
                "reconnect_delay_s": 0,
                "max_connection_age_s": 0,
            },
            "retry": {"read_retries": 1, "write_retries": 3},
        }
        self.store.upsert_profile({**profile, **overrides})
        await self.proxy.start()

    def set_total_timeout(self, seconds: float) -> None:
        profile = self.store.active_profile()
        assert profile is not None
        payload = profile.model_dump()
        payload["timing"]["total_request_timeout_s"] = seconds
        self.store.upsert_profile(payload, profile.id)

    async def test_unit_id_translation_and_vendor_pdu_are_opaque(self) -> None:
        async def echo(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            writer.write(encode_tcp_adu(request.transaction_id, request.unit_id, request.pdu))
            await writer.drain()

        controller = await self.start_controller(echo)
        await self.configure(controller)
        pdu = bytes.fromhex("41deadbeef")
        response = await self.request(pdu, unit_id=93)
        self.assertEqual(response.pdu, pdu)
        self.assertEqual(response.unit_id, 93)
        self.assertEqual(controller.requests[0].unit_id, 12)

    async def test_read_disconnect_is_retried(self) -> None:
        async def close_then_answer(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            if len(controller.requests) == 1:
                return
            writer.write(
                encode_tcp_adu(
                    request.transaction_id,
                    request.unit_id,
                    bytes.fromhex("0302002a"),
                )
            )
            await writer.drain()

        controller = await self.start_controller(close_then_answer)
        await self.configure(controller, retry={"read_retries": 1, "write_retries": 0})
        response = await self.request(bytes.fromhex("0300000001"))
        self.assertEqual(response.pdu, bytes.fromhex("0302002a"))
        self.assertEqual(len(controller.requests), 2)
        self.assertEqual(self.metrics.snapshot()["retries"], 1)

    async def test_expired_tcp_connection_is_replaced_before_next_write(self) -> None:
        connections: list[list[bytes]] = []

        async def persistent_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            requests: list[bytes] = []
            connections.append(requests)
            try:
                while True:
                    request = await read_tcp_adu(reader)
                    requests.append(request.pdu)
                    writer.write(
                        encode_tcp_adu(
                            request.transaction_id,
                            request.unit_id,
                            request.pdu,
                        )
                    )
                    await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(persistent_client, "127.0.0.1", 0)
        self.raw_servers.append(server)
        assert server.sockets
        port = int(server.sockets[0].getsockname()[1])
        self.store.upsert_profile(
            {
                "name": "Connection lifetime",
                "transport": "modbus_tcp",
                "host": "127.0.0.1",
                "port": port,
                "upstream_unit_id": 12,
                "timing": {
                    "connect_timeout_s": 0.2,
                    "response_timeout_s": 0.2,
                    "total_request_timeout_s": 1,
                    "minimum_request_interval_s": 0,
                    "connect_settle_delay_s": 0,
                    "reconnect_delay_s": 0.01,
                    "max_connection_age_s": 0.02,
                },
            }
        )
        await self.proxy.start()

        first_write = bytes.fromhex("06009006c4")
        second_write = bytes.fromhex("0600041732")
        await self.request(first_write)
        await asyncio.sleep(0.03)
        response = await self.request(second_write)

        self.assertEqual(response.pdu, second_write)
        self.assertEqual(connections, [[first_write], [second_write]])
        self.assertEqual(self.metrics.snapshot()["reconnects"], 1)

    async def test_fc01_is_forwarded_unchanged(self) -> None:
        async def echo(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            writer.write(
                encode_tcp_adu(
                    request.transaction_id,
                    request.unit_id,
                    bytes.fromhex("01020000"),
                )
            )
            await writer.drain()

        controller = await self.start_controller(echo)
        await self.configure(controller)

        await self.request(bytes.fromhex("0100000009"))

        self.assertEqual(controller.requests[0].pdu, bytes.fromhex("0100000009"))

    async def test_scheduled_rtu_renewal_waits_for_client_sequence_boundary(self) -> None:
        connections: list[list[bytes]] = []
        start_read = bytes.fromhex("0300000001")
        device_data = bytes.fromhex("0300010001")
        poll = bytes.fromhex("0400000001")
        device_value = bytes.fromhex("0302002a")
        poll_value = bytes.fromhex("0402002b")

        async def adapter(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            requests: list[bytes] = []
            connections.append(requests)
            while True:
                request = decode_rtu_adu(await reader.readexactly(8), 12)
                if request == device_data and (not requests or requests[-1] != start_read):
                    response = bytes.fromhex("8304")
                else:
                    response = poll_value if request == poll else device_value
                requests.append(request)
                writer.write(encode_rtu_adu(12, response))
                await writer.drain()

        await self.start_rtu_controller(
            adapter,
            timing={
                "max_connection_age_s": 5,
                "client_burst_idle_s": 0.25,
                "response_timeout_s": 0.5,
                "total_request_timeout_s": 2,
                "minimum_request_interval_s": 0,
                "reconnect_delay_s": 0,
                "connect_settle_delay_s": 0,
            },
        )
        reader, writer = await asyncio.open_connection("127.0.0.1", self.proxy.bound_port)
        polling: asyncio.Task[ModbusTcpAdu] | None = None

        async def read(transaction: int, pdu: bytes) -> bytes:
            writer.write(encode_tcp_adu(transaction, 7, pdu))
            await writer.drain()
            return (await asyncio.wait_for(read_tcp_adu(reader), 1)).pdu

        try:
            self.assertEqual(await read(1, start_read), device_value)
            self.assertEqual(await read(2, device_data), device_value)
            self.assertEqual((await self.request(poll)).pdu, poll_value)

            self.assertEqual(await read(3, start_read), device_value)
            polling = asyncio.create_task(self.request(poll))
            async with asyncio.timeout(0.2):
                while self.metrics.snapshot()["queue_depth"] != 1:
                    await asyncio.sleep(0.001)

            # Age only the upstream connection while the second client waits.
            self.router._connected_at -= 5
            self.assertEqual(await read(4, device_data), device_value)
            self.assertEqual(self.metrics.snapshot()["reconnects"], 0)

            self.assertEqual((await polling).pdu, poll_value)
            self.assertEqual(
                connections, [[start_read, device_data, poll, start_read, device_data], [poll]]
            )
            self.assertEqual(self.metrics.snapshot()["reconnects"], 1)
        finally:
            writer.close()
            await writer.wait_closed()
            if polling is not None and not polling.done():
                polling.cancel()
                await asyncio.gather(polling, return_exceptions=True)

    async def test_write_timeout_after_send_is_not_retried(self) -> None:
        async def never_answer(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            await asyncio.sleep(0.2)

        controller = await self.start_controller(never_answer)
        await self.configure(controller, retry={"read_retries": 0, "write_retries": 3})
        with self.assertLogs("trovis_gateway.modbus", level="WARNING") as logs:
            response = await self.request(bytes.fromhex("0600010001"))
        self.assertIn("Modbus TCP response exceeded the configured timeout", logs.output[0])
        self.assertIn('"duration_ms":', logs.output[0])
        self.assertEqual(response.pdu, bytes.fromhex("860b"))
        await asyncio.sleep(0.05)
        self.assertEqual(len(controller.requests), 1)

    async def test_rtu_over_tcp_translates_between_adu_formats(self) -> None:
        received: list[bytes] = []

        async def raw_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                frame = await reader.readexactly(8)
                received.append(frame)
                writer.write(encode_rtu_adu(12, bytes.fromhex("0302002a")))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(raw_client, "127.0.0.1", 0)
        self.raw_servers.append(server)
        assert server.sockets
        port = int(server.sockets[0].getsockname()[1])
        self.store.upsert_profile(
            {
                "name": "RTU bridge",
                "transport": "rtu_over_tcp",
                "host": "127.0.0.1",
                "port": port,
                "upstream_unit_id": 12,
                "timing": {
                    "connect_timeout_s": 0.2,
                    "response_timeout_s": 0.2,
                    "total_request_timeout_s": 1,
                    "minimum_request_interval_s": 0,
                    "connect_settle_delay_s": 0,
                    "reconnect_delay_s": 0,
                },
            }
        )
        await self.proxy.start()

        response = await self.request(bytes.fromhex("0300000001"), unit_id=93)

        self.assertEqual(response.unit_id, 93)
        self.assertEqual(response.pdu, bytes.fromhex("0302002a"))
        self.assertEqual(decode_rtu_adu(received[0], 12), bytes.fromhex("0300000001"))

    async def test_rtu_response_mismatch_reconnects_before_retrying_read(self) -> None:
        connections = 0
        received: list[bytes] = []

        async def raw_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            nonlocal connections
            connections += 1
            connection = connections
            try:
                frame = await reader.readexactly(8)
                received.append(frame)
                if connection == 1:
                    writer.write(
                        encode_rtu_adu(12, bytes.fromhex("030c15c500000000000000000000"))
                        + encode_rtu_adu(12, bytes.fromhex("010101"))
                    )
                else:
                    writer.write(encode_rtu_adu(12, bytes.fromhex("010100")))
                await writer.drain()
                await reader.read()
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        server = await asyncio.start_server(raw_client, "127.0.0.1", 0)
        self.raw_servers.append(server)
        assert server.sockets
        port = int(server.sockets[0].getsockname()[1])
        self.store.upsert_profile(
            {
                "name": "RTU resynchronization",
                "transport": "rtu_over_tcp",
                "host": "127.0.0.1",
                "port": port,
                "upstream_unit_id": 12,
                "timing": {
                    "connect_timeout_s": 0.2,
                    "response_timeout_s": 0.2,
                    "total_request_timeout_s": 1,
                    "minimum_request_interval_s": 0,
                    "connect_settle_delay_s": 0,
                    "reconnect_delay_s": 0,
                    "max_connection_age_s": 0,
                },
                "retry": {"read_retries": 1, "write_retries": 0},
            }
        )
        await self.proxy.start()

        with self.assertLogs("trovis_gateway.modbus", level="WARNING") as logs:
            response = await self.request(bytes.fromhex("01003b0001"))
        event = json.loads(logs.records[0].getMessage())
        self.assertEqual(event["downstream_client_id"], 1)
        self.assertEqual(event["function_code"], 1)
        self.assertEqual(event["address"], 59)
        self.assertEqual(event["count_or_value"], 1)
        self.assertEqual(event["response_function_code"], 3)
        self.assertEqual(event["response_byte_count"], 12)
        self.assertNotIn("pdu_hex", event)

        self.assertEqual(response.pdu, bytes.fromhex("010100"))
        self.assertEqual(connections, 2)
        self.assertEqual(len(received), 2)
        self.assertEqual(self.metrics.snapshot()["retries"], 1)
        self.assertEqual(self.metrics.snapshot()["reconnects"], 1)

    async def test_idle_coil_reply_is_not_reused_for_a_different_coil(self) -> None:
        inject = asyncio.Event()
        injected = asyncio.Event()
        connections: list[list[bytes]] = []
        pump_on = bytes.fromhex("010101")
        pump_off = bytes.fromhex("010100")
        request_up = bytes.fromhex("0100380001")
        request_slp = bytes.fromhex("01003b0001")

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            requests: list[bytes] = []
            connections.append(requests)
            first_connection = len(connections) == 1
            while True:
                request = decode_rtu_adu(await reader.readexactly(8), 12)
                requests.append(request)
                response = pump_on if request == request_up else pump_off
                writer.write(encode_rtu_adu(12, response))
                await writer.drain()
                if first_connection and len(requests) == 1:
                    await inject.wait()
                    writer.write(encode_rtu_adu(12, pump_on))
                    await writer.drain()
                    injected.set()

        await self.start_rtu_controller(controller)

        try:
            self.assertEqual((await self.request(request_up)).pdu, pump_on)
        finally:
            inject.set()
        await asyncio.wait_for(injected.wait(), 1)
        await asyncio.sleep(0.02)
        self.assertEqual((await self.request(request_slp)).pdu, pump_off)
        self.assertEqual(connections, [[request_up], [request_slp]])

    async def test_multiple_clients_keep_values_with_periodic_stale_rtu_replies(self) -> None:
        # The two coils share the same response shape. The register's stale value is
        # also structurally valid for a single-register read.
        cases = [
            (bytes.fromhex("0100380001"), bytes.fromhex("010101"), bytes.fromhex("010100")),
            (bytes.fromhex("01003b0001"), bytes.fromhex("010100"), bytes.fromhex("010101")),
            (bytes.fromhex("0304280001"), bytes.fromhex("03020008"), bytes.fromhex("030201c5")),
        ]
        replies = {request: (correct, stale) for request, correct, stale in cases}
        forwarded = 0
        injected = 0

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal forwarded, injected
            while True:
                request = decode_rtu_adu(await reader.readexactly(8), 12)
                correct, stale = replies[request]
                forwarded += 1
                frame = encode_rtu_adu(12, correct)
                if forwarded % 7 == 0:
                    injected += 1
                    writer.write(encode_rtu_adu(12, stale) + frame)
                else:
                    writer.write(frame[:3])
                    await writer.drain()
                    await asyncio.sleep(0.001)
                    writer.write(frame[3:])
                await writer.drain()

        async def poll(unit_id: int, offset: int) -> None:
            reader, writer = await asyncio.open_connection("127.0.0.1", self.proxy.bound_port)
            try:
                for index in range(40):
                    request, expected, _ = cases[(index + offset) % len(cases)]
                    writer.write(encode_tcp_adu(index, unit_id, request))
                    await writer.drain()
                    response = await asyncio.wait_for(read_tcp_adu(reader), 2)
                    self.assertEqual(response, ModbusTcpAdu(index, unit_id, expected))
            finally:
                writer.close()
                await writer.wait_closed()

        await self.start_rtu_controller(controller)
        async with asyncio.TaskGroup() as clients:
            for index in range(3):
                clients.create_task(poll(7 + index, index))

        self.assertGreaterEqual(injected, 10)
        self.assertEqual(forwarded, 120 + injected)
        self.assertEqual(self.metrics.snapshot()["retries"], injected)
        self.assertEqual(self.metrics.snapshot()["reconnects"], injected)

    async def test_rtu_write_with_extra_reply_is_not_repeated(self) -> None:
        received: list[bytes] = []

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            while True:
                request = decode_rtu_adu(await reader.readexactly(8), 12)
                received.append(request)
                if request[0] == 0x06:
                    reply = encode_rtu_adu(12, request)
                    writer.write(reply + reply)
                else:
                    writer.write(encode_rtu_adu(12, bytes.fromhex("0302002a")))
                await writer.drain()

        await self.start_rtu_controller(controller)
        write = bytes.fromhex("0600010001")
        read = bytes.fromhex("0300000001")

        self.assertEqual((await self.request(write)).pdu, bytes.fromhex("860b"))
        self.assertEqual((await self.request(read)).pdu, bytes.fromhex("0302002a"))
        self.assertEqual(received, [write, read])
        self.assertEqual(self.metrics.snapshot()["retries"], 0)

    async def test_rtu_vendor_reply_can_span_tcp_chunks(self) -> None:
        request = bytes.fromhex("4101020304")
        response = bytes.fromhex("41060504030201")

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            self.assertEqual(decode_rtu_adu(await reader.readexactly(8), 12), request)
            frame = encode_rtu_adu(12, response)
            writer.write(frame[:4])
            await writer.drain()
            await asyncio.sleep(0.005)
            writer.write(frame[4:])
            await writer.drain()
            await reader.read()

        await self.start_rtu_controller(controller)
        self.assertEqual((await self.request(request)).pdu, response)

    async def test_rtu_response_timeout_applies_to_the_entire_frame(self) -> None:
        completed = asyncio.Event()

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.readexactly(8)
            frame = encode_rtu_adu(12, bytes.fromhex("0302002a"))
            try:
                await asyncio.sleep(0.06)
                writer.write(frame[:2])
                await writer.drain()
                await asyncio.sleep(0.06)
                writer.write(frame[2:])
                await writer.drain()
            finally:
                completed.set()

        await self.start_rtu_controller(
            controller,
            timing={
                "response_timeout_s": 0.1,
                "connect_settle_delay_s": 0,
                "reconnect_delay_s": 0,
            },
            retry={"read_retries": 0},
        )
        response = await self.request(bytes.fromhex("0300000001"))
        await asyncio.wait_for(completed.wait(), 1)
        self.assertEqual(response.pdu, bytes.fromhex("830b"))
        self.assertEqual(self.metrics.snapshot()["timeouts"], 1)

    async def test_queue_timeout_does_not_cancel_active_request_or_send_expired_write(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        read = bytes.fromhex("0300000001")
        reply = bytes.fromhex("0302002a")
        write = bytes.fromhex("0600010001")

        async def controller(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            started.set()
            await release.wait()
            writer.write(encode_tcp_adu(request.transaction_id, request.unit_id, reply))
            await writer.drain()

        fake = await self.start_controller(controller)
        await self.configure(
            fake,
            timing={"response_timeout_s": 1, "total_request_timeout_s": 1.5},
        )
        active = asyncio.create_task(self.request(read))
        try:
            await asyncio.wait_for(started.wait(), 1)
            self.set_total_timeout(0.12)
            expired = await self.request(write)
            self.assertEqual(expired, ModbusTcpAdu(101, 7, bytes.fromhex("860b")))
            self.assertFalse(active.done())
            self.assertEqual(self.metrics.snapshot()["queue_depth"], 0)
        finally:
            release.set()
            result = await active
        self.assertEqual(result.pdu, reply)
        self.assertEqual([request.pdu for request in fake.requests], [read])
        self.assertEqual(self.metrics.snapshot()["timeouts"], 1)

    async def test_wait_in_queue_reduces_time_available_for_controller_reply(self) -> None:
        active_started = asyncio.Event()
        release = asyncio.Event()
        second_started = asyncio.Event()
        completed = asyncio.Event()
        first = bytes.fromhex("0300000001")
        second = bytes.fromhex("0300010001")
        reply = bytes.fromhex("0302002a")
        received: list[bytes] = []

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            while True:
                request = decode_rtu_adu(await reader.readexactly(8), 12)
                received.append(request)
                if request == first:
                    active_started.set()
                    await release.wait()
                else:
                    second_started.set()
                    await asyncio.sleep(0.28)
                    completed.set()
                writer.write(encode_rtu_adu(12, reply))
                await writer.drain()

        await self.start_rtu_controller(
            controller,
            timing={
                "response_timeout_s": 1,
                "total_request_timeout_s": 1.5,
                "connect_settle_delay_s": 0,
                "minimum_request_interval_s": 0,
                "client_burst_idle_s": 0,
            },
        )
        first_request = asyncio.create_task(self.request(first))
        try:
            await asyncio.wait_for(active_started.wait(), 1)
            self.set_total_timeout(0.36)
            queued = asyncio.create_task(self.request(second))
            async with asyncio.timeout(1):
                while not self.metrics.snapshot()["queue_depth"]:
                    await asyncio.sleep(0.001)
            await asyncio.sleep(0.16)
        finally:
            release.set()
        self.assertEqual((await first_request).pdu, reply)
        self.assertEqual((await queued).pdu, bytes.fromhex("830b"))
        self.assertTrue(second_started.is_set())
        self.assertFalse(completed.is_set())
        await asyncio.wait_for(completed.wait(), 1)
        self.assertEqual(received, [first, second])

    async def test_total_timeout_reconnects_and_discards_late_coil_reply_before_next_send(
        self,
    ) -> None:
        first_sent = asyncio.Event()
        connection_times: list[float] = []
        requests: list[bytes] = []
        loop = asyncio.get_running_loop()
        late_at = 0.0
        next_sent_at = 0.0
        up = bytes.fromhex("0100380001")
        slp = bytes.fromhex("01003b0001")
        pump_off = bytes.fromhex("010100")

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal late_at, next_sent_at
            connection_times.append(loop.time())
            if len(connection_times) == 1:
                requests.append(decode_rtu_adu(await reader.readexactly(8), 12))
                first_sent.set()
            else:
                await asyncio.sleep(0.035)
                writer.write(encode_rtu_adu(12, bytes.fromhex("010101")))
                await writer.drain()
                late_at = loop.time()
                requests.append(decode_rtu_adu(await reader.readexactly(8), 12))
                next_sent_at = loop.time()
                writer.write(encode_rtu_adu(12, pump_off))
                await writer.drain()
            await reader.read()

        await self.start_rtu_controller(
            controller,
            timing={
                "total_request_timeout_s": 0.2,
                "response_timeout_s": 1,
                "reconnect_delay_s": 0.2,
                "connect_settle_delay_s": 0.07,
                "client_burst_idle_s": 0,
                "max_connection_age_s": 0,
            },
        )
        first = asyncio.create_task(self.request(up))
        await asyncio.wait_for(first_sent.wait(), 1)
        self.set_total_timeout(1.2)
        queued = asyncio.create_task(self.request(slp, unit_id=9))

        self.assertEqual((await first).pdu, bytes.fromhex("810b"))
        expired_at = loop.time()
        self.assertEqual(await queued, ModbusTcpAdu(101, 9, pump_off))
        self.assertEqual(requests, [up, slp])
        self.assertGreaterEqual(connection_times[1] - expired_at, 0.15)
        self.assertGreaterEqual(next_sent_at - late_at, 0.06)
        self.assertEqual(self.metrics.snapshot()["reconnects"], 1)

    async def test_serial_timeout_waits_for_old_worker_before_opening_a_new_port(self) -> None:
        old_read_finished = Event()
        old = Mock(is_open=True)
        fresh = Mock(is_open=True)

        def blocked_read(_size: int) -> bytes:
            old_read_finished.wait(2)
            return b""

        write = bytes.fromhex("0600010001")
        read = bytes.fromhex("0300000001")
        reply = bytes.fromhex("0302002a")
        frame = encode_rtu_adu(12, reply)
        old.read.side_effect = blocked_read
        fresh.read.side_effect = [frame[:2], frame[2:3], frame[3:]]
        self.store.upsert_profile(
            {
                "name": "Serial bridge",
                "transport": "serial_rtu",
                "upstream_unit_id": 12,
                "serial": {"device": "/dev/test-modbus"},
                "timing": {
                    "total_request_timeout_s": 0.14,
                    "connect_settle_delay_s": 0,
                    "reconnect_delay_s": 0,
                },
                "retry": {"write_retries": 3},
            }
        )
        await self.proxy.start()
        open_serial = Mock(side_effect=[old, fresh])
        with patch.dict(sys.modules, {"serial": Mock(Serial=open_serial)}):
            try:
                self.assertEqual((await self.request(write)).pdu, bytes.fromhex("860b"))
                self.assertEqual((await self.request(read)).pdu, bytes.fromhex("830b"))
                self.assertEqual(open_serial.call_count, 1)
                old.write.assert_called_once_with(encode_rtu_adu(12, write))
                old.close.assert_called_once()
            finally:
                old_read_finished.set()
            self.set_total_timeout(1)
            self.assertEqual((await self.request(read)).pdu, reply)
            self.assertEqual(open_serial.call_count, 2)
            fresh.write.assert_called_once_with(encode_rtu_adu(12, read))

    async def test_persistent_rtu_input_expires_without_sending_the_queued_write(self) -> None:
        connections = 0
        unexpected_request = asyncio.Event()
        recovery_closed = asyncio.Event()
        response = encode_rtu_adu(12, bytes.fromhex("010101"))

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal connections
            connections += 1
            if connections == 1:
                await reader.readexactly(8)
                await reader.read()
                return

            incoming = asyncio.create_task(reader.read(1))
            try:
                while not incoming.done():
                    writer.write(response)
                    await writer.drain()
                    await asyncio.sleep(0.012)
            finally:
                if not incoming.done():
                    incoming.cancel()
                elif not incoming.cancelled() and incoming.exception() is None:
                    if incoming.result():
                        unexpected_request.set()
                await asyncio.gather(incoming, return_exceptions=True)
                recovery_closed.set()

        await self.start_rtu_controller(
            controller,
            timing={
                "total_request_timeout_s": 0.22,
                "response_timeout_s": 1,
                "reconnect_delay_s": 0,
                "connect_settle_delay_s": 0,
            },
        )
        self.assertEqual((await self.request(bytes.fromhex("0100380001"))).pdu, b"\x81\x0b")
        result = await self.request(bytes.fromhex("0600010001"))
        await asyncio.wait_for(recovery_closed.wait(), 1)

        self.assertEqual(result.pdu, b"\x86\x0b")
        self.assertEqual(connections, 2)
        self.assertFalse(unexpected_request.is_set())
        self.assertEqual(self.metrics.snapshot()["reconnects"], 0)

    async def test_changing_address_preference_reopens_live_rtu_connection(self) -> None:
        expected = bytes.fromhex("0302002a")

        async def controller(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            while True:
                await reader.readexactly(8)
                writer.write(encode_rtu_adu(12, expected))
                await writer.drain()

        await self.start_rtu_controller(
            controller, host="trovis.example.test", address_preference="ipv4"
        )
        profile = self.store.active_profile()
        assert profile is not None
        tcp = (socket.SOCK_STREAM, socket.IPPROTO_TCP, "")
        addresses = [
            (socket.AF_INET6, *tcp, ("::1", profile.port, 0, 0)),
            (socket.AF_INET, *tcp, ("127.0.0.1", profile.port)),
        ]
        attempts: list[int] = []
        loop = asyncio.get_running_loop()
        real_connect = loop.sock_connect

        async def connect(connection: socket.socket, address: tuple) -> None:
            if address[1] == profile.port:
                attempts.append(connection.family)
                if connection.family == socket.AF_INET6:
                    raise ConnectionError("simulated unavailable IPv6")
            await real_connect(connection, address)

        request = bytes.fromhex("0300000001")
        with (
            patch("trovis_gateway.tcp.socket.getaddrinfo", return_value=addresses) as lookup,
            patch.object(loop, "sock_connect", side_effect=connect),
        ):
            self.assertEqual((await self.request(request)).pdu, expected)
            self.store.upsert_profile(
                {**profile.model_dump(), "address_preference": "ipv6"}, profile.id
            )
            self.assertEqual((await self.request(request)).pdu, expected)

        self.assertEqual(attempts, [socket.AF_INET, socket.AF_INET6, socket.AF_INET])
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(self.metrics.snapshot()["reconnects"], 1)

    async def test_client_read_sequences_do_not_interleave(self) -> None:
        upstream_order: list[bytes] = []

        async def persistent_client(
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            try:
                while True:
                    request = await read_tcp_adu(reader)
                    upstream_order.append(request.pdu)
                    response_pdu = (
                        bytes.fromhex("0302002a")
                        if request.pdu[0] == 0x03
                        else bytes.fromhex("0402002b")
                    )
                    writer.write(
                        encode_tcp_adu(
                            request.transaction_id,
                            request.unit_id,
                            response_pdu,
                        )
                    )
                    await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(persistent_client, "127.0.0.1", 0)
        self.raw_servers.append(server)
        assert server.sockets
        port = int(server.sockets[0].getsockname()[1])
        self.store.upsert_profile(
            {
                "name": "Multi-client arbitration",
                "transport": "modbus_tcp",
                "host": "127.0.0.1",
                "port": port,
                "upstream_unit_id": 12,
                "timing": {
                    "connect_timeout_s": 0.2,
                    "response_timeout_s": 0.2,
                    "total_request_timeout_s": 1,
                    "minimum_request_interval_s": 0,
                    "client_burst_idle_s": 0.05,
                    "connect_settle_delay_s": 0,
                    "reconnect_delay_s": 0,
                    "max_connection_age_s": 0,
                },
            }
        )
        await self.proxy.start()
        reader_a, writer_a = await asyncio.open_connection(
            "127.0.0.1", self.proxy.bound_port
        )
        reader_b, writer_b = await asyncio.open_connection(
            "127.0.0.1", self.proxy.bound_port
        )
        first_a = bytes.fromhex("0300000001")
        second_a = bytes.fromhex("0300010001")
        first_b = bytes.fromhex("0400000001")

        writer_a.write(encode_tcp_adu(1, 7, first_a))
        await writer_a.drain()
        self.assertEqual((await read_tcp_adu(reader_a)).pdu, bytes.fromhex("0302002a"))

        writer_b.write(encode_tcp_adu(2, 7, first_b))
        await writer_b.drain()
        response_b = asyncio.create_task(read_tcp_adu(reader_b))
        for _ in range(50):
            if self.metrics.snapshot()["queue_depth"] == 1:
                break
            await asyncio.sleep(0.002)
        self.assertEqual(self.metrics.snapshot()["queue_depth"], 1)

        writer_a.write(encode_tcp_adu(3, 7, second_a))
        await writer_a.drain()
        self.assertEqual((await read_tcp_adu(reader_a)).pdu, bytes.fromhex("0302002a"))
        self.assertFalse(response_b.done())
        self.assertEqual(
            (await asyncio.wait_for(response_b, 0.5)).pdu,
            bytes.fromhex("0402002b"),
        )
        self.assertEqual(upstream_order, [first_a, second_a, first_b])

        writer_a.close()
        writer_b.close()
        await writer_a.wait_closed()
        await writer_b.wait_closed()

    async def test_no_profile_returns_gateway_exception(self) -> None:
        await self.proxy.start()
        response = await self.request(bytes.fromhex("0300000001"))
        self.assertEqual(response.pdu, bytes.fromhex("830b"))

    async def test_paused_proxy_rejects_requests_without_forwarding(self) -> None:
        async def echo(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            writer.write(encode_tcp_adu(request.transaction_id, request.unit_id, request.pdu))
            await writer.drain()

        controller = await self.start_controller(echo)
        await self.configure(controller)
        self.store.set_forwarding_enabled(False)

        response = await self.request(bytes.fromhex("0300000001"))

        self.assertEqual(response.pdu, bytes.fromhex("830b"))
        self.assertEqual(controller.requests, [])

    async def test_active_request_finishes_and_queued_write_is_rejected(self) -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        async def delayed_echo(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            started.set()
            await release.wait()
            writer.write(
                encode_tcp_adu(
                    request.transaction_id,
                    request.unit_id,
                    bytes.fromhex("0302002a"),
                )
            )
            await writer.drain()

        controller = await self.start_controller(delayed_echo)
        await self.configure(controller)
        active_pdu = bytes.fromhex("0300000001")
        queued_write = bytes.fromhex("0600010001")
        active = asyncio.create_task(self.request(active_pdu))
        await asyncio.wait_for(started.wait(), 0.5)
        queued = asyncio.create_task(self.request(queued_write))
        for _ in range(50):
            if self.metrics.snapshot()["queue_depth"] == 1:
                break
            await asyncio.sleep(0.002)
        self.assertEqual(self.metrics.snapshot()["queue_depth"], 1)

        self.store.set_forwarding_enabled(False)
        release.set()
        active_response = await asyncio.wait_for(active, 1)
        queued_response = await asyncio.wait_for(queued, 1)

        self.assertEqual(active_response.pdu, bytes.fromhex("0302002a"))
        self.assertEqual(queued_response.pdu, bytes.fromhex("860b"))
        self.assertEqual([request.pdu for request in controller.requests], [active_pdu])
