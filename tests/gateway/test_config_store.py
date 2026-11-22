from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path

from trovis_gateway.config import ControllerProfile, GatewayConfig
from trovis_gateway.store import ConfigStore


class ConfigStoreTests(unittest.TestCase):
    def test_forwarding_state_is_persisted_across_profile_updates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            store = ConfigStore(path)

            self.assertTrue(store.forwarding_enabled())
            store.set_forwarding_enabled(False)
            store.upsert_profile(
                {
                    "name": "Plant A",
                    "transport": "modbus_tcp",
                    "host": "127.0.0.1",
                }
            )

            reloaded = ConfigStore(path)
            reloaded.load()
            self.assertFalse(reloaded.forwarding_enabled())
            public = reloaded.public_document()
            self.assertFalse(public["forwarding_enabled"])
            self.assertNotIn("disabled_request_policy", public)
            self.assertNotIn("buffer_retention_s", public)

    def test_secret_is_persisted_but_redacted_from_public_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            store = ConfigStore(path)
            profile = store.upsert_profile(
                {
                    "name": "Plant A",
                    "transport": "modbus_tcp",
                    "host": "127.0.0.1",
                    "access_key": "very-secret",
                }
            )

            public = store.public_document()["profiles"][0]
            persisted = json.loads(path.read_text(encoding="utf-8"))["profiles"][0]
            self.assertEqual(public["access_key"], "")
            self.assertTrue(public["access_key_configured"])
            self.assertEqual(persisted["access_key"], "very-secret")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            store.upsert_profile(
                {**public, "name": "Plant A revised", "access_key": ""},
                profile.id,
            )
            self.assertEqual(
                store.active_profile().access_key.get_secret_value(),
                "very-secret",
            )

    def test_profile_can_change_controller_without_device_fields(self) -> None:
        first = ControllerProfile(name="First", host="192.0.2.1")
        second = ControllerProfile(
            name="Second",
            transport="serial_rtu",
            serial={"device": "/dev/ttyUSB9"},
            upstream_unit_id=12,
        )
        config = GatewayConfig(active_profile_id=second.id, profiles=[first, second])
        self.assertEqual(config.active_profile().target_label(), "/dev/ttyUSB9")
        fields = set(ControllerProfile.model_fields)
        self.assertFalse(fields & {"model", "firmware", "downstream_host", "listen_port"})

    def test_legacy_fc01_compatibility_is_removed_on_load_and_upsert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "forwarding_enabled": False,
                        "disabled_request_policy": "buffer_all",
                        "buffer_retention_s": 600,
                        "active_profile_id": "legacy",
                        "profiles": [
                            {
                                "id": "legacy",
                                "name": "Legacy",
                                "host": "192.0.2.1",
                                "compatibility": {
                                    "fc01_address_translation_enabled": True,
                                    "fc01_address_offset": 1024,
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            store = ConfigStore(path)

            loaded = store.load()
            public = store.public_document()["profiles"][0]
            persisted = json.loads(path.read_text(encoding="utf-8"))["profiles"][0]

            self.assertEqual(public["address_preference"], "system")
            self.assertEqual(loaded.active_profile().timing.max_connection_age_s, 25)
            self.assertEqual(loaded.active_profile().timing.client_burst_idle_s, 0.8)
            self.assertEqual(loaded.active_profile().timing.total_request_timeout_s, 16)
            self.assertNotIn("compatibility", ControllerProfile.model_fields)
            self.assertNotIn("compatibility", public)
            self.assertNotIn("compatibility", persisted)
            persisted_document = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("disabled_request_policy", persisted_document)
            self.assertNotIn("buffer_retention_s", persisted_document)
            self.assertFalse(store.forwarding_enabled())

            store.upsert_profile(
                {
                    **public,
                    "compatibility": {
                        "fc01_address_translation_enabled": True,
                        "fc01_address_offset": 1024,
                    },
                },
                "legacy",
            )
            persisted = json.loads(path.read_text(encoding="utf-8"))["profiles"][0]
            self.assertNotIn("compatibility", persisted)
