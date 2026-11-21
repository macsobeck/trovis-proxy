from __future__ import annotations

import asyncio
import socket
import unittest
from unittest.mock import patch

from trovis_gateway.config import ControllerProfile
from trovis_gateway.connection_test import test_connection as check_connection


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
            result = await check_connection(
                ControllerProfile(
                    name="Connection test",
                    transport="modbus_tcp",
                    host="127.0.0.1",
                    port=port,
                    upstream_unit_id=12,
                )
            )
            await asyncio.sleep(0)
        finally:
            server.close()
            await server.wait_closed()

        self.assertTrue(result["ok"])
        self.assertEqual(result["upstream_unit_id"], 12)
        self.assertEqual(result["modbus_test"], "not_performed")
        self.assertEqual(result["resolved_target"], f"127.0.0.1:{port}")
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
