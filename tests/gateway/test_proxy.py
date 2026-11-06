from __future__ import annotations

import asyncio
import tempfile
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path

from trovis_gateway.config import ControllerProfile
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
        response = await read_tcp_adu(reader)
        writer.close()
        await writer.wait_closed()
        return response

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

    async def test_write_timeout_after_send_is_not_retried(self) -> None:
        async def never_answer(request: ModbusTcpAdu, writer: asyncio.StreamWriter) -> None:
            await asyncio.sleep(0.2)

        controller = await self.start_controller(never_answer)
        await self.configure(controller, retry={"read_retries": 0, "write_retries": 3})
        response = await self.request(bytes.fromhex("0600010001"))
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

    async def test_no_profile_returns_gateway_exception(self) -> None:
        await self.proxy.start()
        response = await self.request(bytes.fromhex("0300000001"))
        self.assertEqual(response.pdu, bytes.fromhex("830b"))
