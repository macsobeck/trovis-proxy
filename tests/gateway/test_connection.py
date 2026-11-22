from __future__ import annotations

import asyncio
import socket
import unittest
from unittest.mock import AsyncMock, patch

from trovis_gateway.config import ControllerProfile
from trovis_gateway.connection_test import test_connection as check_connection
from trovis_gateway.tcp import (
    AddressInfo,
    TcpAddressCache,
    TcpConnectError,
    TcpConnectTimeout,
    open_tcp_connection,
)


class TcpAddressCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_background_dns_refresh_does_not_block_reconnect(self) -> None:
        old = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.1", 502))]
        new = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.2", 502))]
        refresh_started = asyncio.Event()
        release_refresh = asyncio.Event()
        calls = 0

        async def resolve(_host: str, _port: int) -> list[AddressInfo]:
            nonlocal calls
            calls += 1
            if calls == 1:
                return old
            refresh_started.set()
            await release_refresh.wait()
            return new

        cache = TcpAddressCache()
        host = "controller.example.test"
        with (
            patch("trovis_gateway.tcp._resolve_addresses", side_effect=resolve),
            patch("trovis_gateway.tcp.DNS_REFRESH_INTERVAL_S", 0),
        ):
            self.assertEqual(await cache.get(host, 502), (old, False))
            try:
                self.assertEqual(await asyncio.wait_for(cache.get(host, 502), 0.2), (old, True))
                await asyncio.wait_for(refresh_started.wait(), 0.2)
                self.assertEqual(await asyncio.wait_for(cache.get(host, 502), 0.2), (old, True))
                self.assertEqual(calls, 2)
            finally:
                release_refresh.set()
            # A failed cached connection joins the refresh already in progress.
            self.assertEqual((await cache.get(host, 502, failed=old))[0], new)
            self.assertEqual(calls, 2)

    async def test_failed_cached_address_is_replaced_by_new_dns_result(self) -> None:
        old = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.1", 502))]
        new = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.2", 502))]
        cache = TcpAddressCache()
        host = "controller.example.test"
        resolver = AsyncMock(side_effect=[old, new])
        connect = AsyncMock(
            side_effect=[
                (None, None, "192.0.2.1:502"),
                TcpConnectError(),
                (None, None, "192.0.2.2:502"),
            ]
        )

        with (
            patch("trovis_gateway.tcp._resolve_addresses", resolver),
            patch("trovis_gateway.tcp._connect_addresses", connect),
        ):
            first = await open_tcp_connection(host, 502, 3, address_cache=cache)
            second = await open_tcp_connection(host, 502, 3, address_cache=cache)

        self.assertEqual(first[2], "192.0.2.1:502")
        self.assertEqual(second[2], "192.0.2.2:502")
        self.assertEqual([call.args[-1] for call in connect.await_args_list], [old, old, new])
        self.assertEqual(resolver.await_count, 2)

    async def test_expired_dns_cache_waits_for_new_result(self) -> None:
        old = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.1", 502))]
        new = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.2", 502))]
        cache = TcpAddressCache()
        host = "controller.example.test"
        with (
            patch("trovis_gateway.tcp.DNS_CACHE_MAX_AGE_S", 0),
            patch("trovis_gateway.tcp._resolve_addresses", side_effect=[old, new]) as lookup,
        ):
            self.assertEqual(await cache.get(host, 502), (old, False))
            self.assertEqual(await cache.get(host, 502), (new, False))
            self.assertEqual(lookup.await_count, 2)

    async def test_reconnect_refreshes_dns_when_cached_address_hangs(self) -> None:
        server = await asyncio.start_server(lambda _reader, writer: writer.close(), "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            tcp = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "")
            old = [(*tcp, ("127.0.0.2", port))]
            new = [(*tcp, ("127.0.0.1", port))]
            loop = asyncio.get_running_loop()
            real_connect = loop.sock_connect
            attempts: list[str] = []

            async def connect(connection: socket.socket, address: tuple) -> None:
                attempts.append(address[0])
                if address[0] == "127.0.0.2":
                    await asyncio.Future()
                await real_connect(connection, address)

            cache = TcpAddressCache()
            host = "controller.example.test"
            with (
                patch("trovis_gateway.tcp._resolve_addresses", side_effect=[old, new]),
                patch.object(loop, "sock_connect", side_effect=connect),
            ):
                await cache.get(host, port)
                _, writer, target = await open_tcp_connection(host, port, 0.3, address_cache=cache)
                writer.close()
                await writer.wait_closed()
            self.assertEqual(attempts, ["127.0.0.2", "127.0.0.1"])
            self.assertEqual(target, f"127.0.0.1:{port}")
            self.assertEqual(await cache.get(host, port), (new, True))

    async def test_switching_controller_does_not_reuse_previous_dns_addresses(self) -> None:
        first = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.1", 502))]
        second = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("192.0.2.2", 502))]
        cache = TcpAddressCache()
        with patch("trovis_gateway.tcp._resolve_addresses", side_effect=[first, second]) as lookup:
            self.assertEqual(await cache.get("first.example.test", 502), (first, False))
            self.assertEqual(await cache.get("second.example.test", 502), (second, False))
            self.assertEqual(await cache.get("second.example.test", 502), (second, True))
        self.assertEqual(lookup.await_count, 2)


class ConnectionTestTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_check_sends_no_modbus_request(self) -> None:
        received = bytearray()

        async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            received.extend(await reader.read())
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(client, "127.0.0.1", 0)
        try:
            assert server.sockets
            port = int(server.sockets[0].getsockname()[1])
            with patch("trovis_gateway.tcp.socket.getaddrinfo") as resolve:
                result = await check_connection(
                    ControllerProfile(
                        name="Connection test",
                        transport="modbus_tcp",
                        host="127.0.0.1",
                        port=port,
                        upstream_unit_id=12,
                    )
                )
                resolve.assert_not_called()
            await asyncio.sleep(0)
        finally:
            server.close()
            await server.wait_closed()

        self.assertTrue(result["ok"])
        self.assertEqual(result["upstream_unit_id"], 12)
        self.assertEqual(result["modbus_test"], "not_performed")
        self.assertEqual(result["resolved_target"], f"127.0.0.1:{port}")
        self.assertIn("tcp_latency_ms", result)
        self.assertNotIn("dns_latency_ms", result)
        self.assertEqual(received, b"")

    async def test_dns_name_is_resolved_before_tcp_connect(self) -> None:
        async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.read()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(client, "127.0.0.1", 0)
        try:
            assert server.sockets
            port = int(server.sockets[0].getsockname()[1])
            address = (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", port),
            )
            with patch("trovis_gateway.tcp.socket.getaddrinfo", return_value=[address]):
                result = await check_connection(
                    ControllerProfile(
                        name="DNS connection test",
                        transport="rtu_over_tcp",
                        host="trovis.example.test",
                        port=port,
                        upstream_unit_id=247,
                    )
                )
        finally:
            server.close()
            await server.wait_closed()

        self.assertTrue(result["ok"])
        self.assertEqual(result["target"], f"trovis.example.test:{port}")
        self.assertEqual(result["resolved_target"], f"127.0.0.1:{port}")
        self.assertIn(f"via 127.0.0.1:{port}", result["detail"])
        self.assertIn("dns_latency_ms", result)
        self.assertIn("tcp_latency_ms", result)

    async def test_dns_error_is_reported_without_tcp_attempt(self) -> None:
        with patch(
            "trovis_gateway.tcp.socket.getaddrinfo",
            side_effect=socket.gaierror(socket.EAI_NONAME, "Name not known"),
        ):
            result = await check_connection(
                ControllerProfile(name="Missing host", host="missing.example.test")
            )
        self.assertFalse(result["ok"])
        self.assertIn("could not resolve", result["detail"])
        self.assertIn("dns_latency_ms", result)
        self.assertNotIn("tcp_latency_ms", result)

    async def test_slow_dns_uses_the_same_connection_budget(self) -> None:
        async def resolve(_host: str, _port: int) -> list[AddressInfo]:
            return await asyncio.Future()

        with patch("trovis_gateway.tcp._resolve_addresses", side_effect=resolve):
            result = await asyncio.wait_for(
                check_connection(
                    ControllerProfile(
                        name="Slow lookup", host="slow.example.test",
                        timing={"connect_timeout_s": 0.1},
                    )
                ),
                timeout=0.5,
            )
        self.assertFalse(result["ok"])
        self.assertIn("DNS resolution for slow.example.test timed out", result["detail"])
        self.assertNotIn("tcp_latency_ms", result)

    async def test_all_tcp_attempts_share_the_remaining_time_after_dns(self) -> None:
        target = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "")
        addresses = [(*target, (f"127.0.0.{number}", 502)) for number in range(1, 5)]

        async def resolve(_host: str, _port: int) -> list[AddressInfo]:
            await asyncio.sleep(0.07)
            return addresses

        async def connect(_connection: socket.socket, _address: tuple) -> None:
            await asyncio.Future()

        loop = asyncio.get_running_loop()
        with (
            patch("trovis_gateway.tcp._resolve_addresses", side_effect=resolve),
            patch.object(loop, "sock_connect", side_effect=connect) as attempts,
        ):
            with self.assertRaises(TcpConnectTimeout):
                await asyncio.wait_for(
                    open_tcp_connection("controller.example.test", 502, 0.25),
                    timeout=0.5,
                )
        self.assertEqual(attempts.await_count, len(addresses))

    async def test_address_preference_and_fast_sequential_fallback(self) -> None:
        async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.read()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(client, "127.0.0.1", 0)
        async with server:
            assert server.sockets
            port = server.sockets[0].getsockname()[1]
            tcp = (socket.SOCK_STREAM, socket.IPPROTO_TCP, "")
            ipv4 = (socket.AF_INET, *tcp, ("127.0.0.1", port))
            ipv6 = (socket.AF_INET6, *tcp, ("::1", port, 0, 0))
            other_ipv6 = (socket.AF_INET6, *tcp, ("::2", port, 0, 0))
            loop = asyncio.get_running_loop()
            real_connect = loop.sock_connect
            attempts: list[socket.socket] = []

            async def connect(connection: socket.socket, address: tuple) -> None:
                self.assertTrue(all(sock.fileno() == -1 for sock in attempts))
                attempts.append(connection)
                if connection.family == socket.AF_INET6:
                    await asyncio.Future()  # Simulate IPv6 without a network response.
                await real_connect(connection, address)

            for preference, addresses, expected in (
                ("system", [ipv6, other_ipv6, ipv4], [socket.AF_INET6, socket.AF_INET]),
                ("ipv4", [ipv6, ipv4], [socket.AF_INET]),
                ("ipv6", [ipv4, ipv6], [socket.AF_INET6, socket.AF_INET]),
                ("ipv6", [ipv4], [socket.AF_INET]),
            ):
                with self.subTest(preference=preference, addresses=addresses):
                    attempts.clear()
                    with (
                        patch("trovis_gateway.tcp.socket.getaddrinfo", return_value=addresses),
                        patch.object(loop, "sock_connect", side_effect=connect),
                    ):
                        result = await asyncio.wait_for(
                            check_connection(
                                ControllerProfile(
                                    name="Dual-stack bridge",
                                    host="trovis.example.test",
                                    port=port,
                                    address_preference=preference,
                                    timing={"connect_timeout_s": 3},
                                )
                            ),
                            timeout=1.2,
                        )

                    self.assertEqual([entry.family for entry in attempts], expected)
                    self.assertTrue(result["ok"])
                    self.assertEqual(result["resolved_target"], f"127.0.0.1:{port}")
