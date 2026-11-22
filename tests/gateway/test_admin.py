from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from trovis_gateway.admin.server import AdminServer
from trovis_gateway.config import InfrastructureSettings
from trovis_gateway.metrics import GatewayMetrics
from trovis_gateway.store import ConfigStore


class AdminTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ConfigStore(Path(self.temporary.name) / "config.json")
        settings = InfrastructureSettings(
            listen_host="0.0.0.0",
            listen_port=7112,
            admin_host="127.0.0.1",
            admin_port=0,
            config_path=self.store.path,
        )
        self.server = AdminServer(
            settings,
            self.store,
            GatewayMetrics(),
            asyncio.get_running_loop(),
        )
        self.server.start()
        self.base = f"http://127.0.0.1:{self.server.bound_port}"

    async def asyncTearDown(self) -> None:
        await asyncio.to_thread(self.server.close)
        self.temporary.cleanup()

    async def fetch(self, path: str, payload: dict[str, object] | None = None) -> tuple[int, str]:
        def request() -> tuple[int, str]:
            data = json.dumps(payload).encode() if payload is not None else None
            method = "POST" if payload is not None else "GET"
            req = urllib.request.Request(
                self.base + path,
                data=data,
                method=method,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.read().decode()

        return await asyncio.to_thread(request)

    async def test_api_masks_key_and_keeps_listener_out_of_profile(self) -> None:
        status, _ = await self.fetch(
            "/api/profiles",
            {
                "name": "Admin Test",
                "transport": "modbus_tcp",
                "host": "127.0.0.1",
                "address_preference": "ipv4",
                "access_key": "secret-value",
            },
        )
        self.assertEqual(status, 201)
        _, body = await self.fetch("/api/config")
        document = json.loads(body)
        profile = document["profiles"][0]
        self.assertEqual(profile["access_key"], "")
        self.assertTrue(profile["access_key_configured"])
        self.assertEqual(profile["address_preference"], "ipv4")
        reloaded = ConfigStore(self.store.path).load()
        assert reloaded.profiles
        self.assertEqual(reloaded.profiles[0].address_preference, "ipv4")
        self.assertNotIn("secret-value", body)
        self.assertNotIn("listen_port", profile)
        self.assertNotIn("compatibility", profile)
        self.assertEqual(profile["timing"]["max_connection_age_s"], 25)
        self.assertEqual(profile["timing"]["client_burst_idle_s"], 0.8)
        self.assertEqual(profile["timing"]["total_request_timeout_s"], 16)
        _, status_body = await self.fetch("/api/status")
        self.assertNotIn("secret-value", status_body)
        self.assertEqual(json.loads(status_body)["version"], "1.2.1")

    async def test_forwarding_state_can_be_changed_and_is_reported(self) -> None:
        status, body = await self.fetch(
            "/api/forwarding",
            {"enabled": False},
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["forwarding_enabled"])

        _, status_body = await self.fetch("/api/status")
        state = json.loads(status_body)
        self.assertFalse(state["forwarding_enabled"])
        self.assertNotIn("disabled_request_policy", state)
        self.assertNotIn("buffer_retention_s", state)

        _, config_body = await self.fetch("/api/config")
        self.assertFalse(json.loads(config_body)["forwarding_enabled"])

    async def test_ui_has_controller_editor_but_no_downstream_editor(self) -> None:
        _, html = await self.fetch("/")
        self.assertIn('<html lang="en">', html)
        self.assertIn("TROVIS Modbus Proxy", html)
        self.assertNotIn("TROVIS Proxy Gateway", html)
        self.assertNotIn("TROVIS Communication Gateway", html)
        self.assertIn("Modbus Proxy status", html)
        self.assertNotIn("Gateway status", html)
        self.assertIn("Controller connection", html)
        self.assertIn('<h2>Modbus Proxy</h2>', html)
        self.assertNotIn('<h2>Gateway</h2>', html)
        self.assertIn("Design by macsobeck", html)
        self.assertIn('<span id="release-version">Release 1.2.1</span>', html)
        self.assertIn("TROVIS-VIEW Listener", html)
        self.assertIn('class="parameter-row"', html)
        self.assertIn('class="parameter-label"', html)
        self.assertIn('class="parameter-value"', html)
        self.assertNotIn('id="fc01-translation-enabled"', html)
        self.assertNotIn('id="fc01-address-offset"', html)
        self.assertIn('id="max-connection-age"', html)
        self.assertIn('id="client-burst-idle"', html)
        self.assertIn('id="forwarding-toggle"', html)
        self.assertNotIn('id="disabled-request-policy"', html)
        self.assertNotIn('id="buffer-retention"', html)
        self.assertIn('id="timing-preset"', html)
        self.assertIn('id="address-preference"', html)
        self.assertIn('<option value="system">System order (default)</option>', html)
        self.assertIn('<option value="ipv4">Prefer IPv4</option>', html)
        self.assertIn('<option value="ipv6">Prefer IPv6</option>', html)
        self.assertIn('<option value="fast">Fast</option>', html)
        self.assertIn('<option value="standard">Standard (recommended)</option>', html)
        self.assertIn('<option value="reliable">Reliable</option>', html)
        self.assertIn('<option value="custom">Custom</option>', html)
        self.assertNotIn("<details", html)
        self.assertNotIn('id="listen-port"', html)
        self.assertNotIn('id="downstream-unit-id"', html)
