from __future__ import annotations

import asyncio
import unittest

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
        self.assertEqual(received, b"")
