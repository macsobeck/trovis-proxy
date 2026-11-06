from __future__ import annotations

import asyncio
import unittest

from trovis_manager.catalog import RegisterCatalog
from trovis_manager.configuration import ConfigurationService
from trovis_manager.controller import golden_mock_transport
from trovis_manager.models import SnapshotStatus
from trovis_manager.transport import (
    ConnectionManager,
    ConnectionSettings,
    MockFailurePlan,
    MockTransport,
)


def service(failures: MockFailurePlan | None = None) -> tuple[ConfigurationService, object]:
    transport = golden_mock_transport(failures)
    manager = ConnectionManager(
        transport,
        ConnectionSettings(timeout=0.01, inter_request_delay=0, retries=1, retry_backoff=0),
    )
    return ConfigurationService(manager, RegisterCatalog.load()), transport


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_detection(self) -> None:
        reader, _ = service()
        identity = await reader.identify()
        self.assertEqual(identity.model, "TROVIS 5573-1")
        self.assertEqual(identity.firmware, "03.09.00")
        self.assertEqual(identity.modbus_unit_id, 247)

    async def test_read_group_uses_safe_blocks(self) -> None:
        reader, transport = service()
        results = await reader.read_group("DHW")
        self.assertTrue(all(item.successful for item in results))
        self.assertLess(len(transport.read_calls), len(results))  # type: ignore[attr-defined]

    async def test_timeout_terminates(self) -> None:
        reader, _ = service(MockFailurePlan(timeouts=2))
        result = await asyncio.wait_for(reader.read("rk1.flow.maximum"), 0.1)
        self.assertFalse(result.successful)
        self.assertEqual(result.error.kind, "TimeoutError")  # type: ignore[union-attr]

    async def test_cancellation_propagates(self) -> None:
        transport = golden_mock_transport(MockFailurePlan(timeouts=1))
        manager = ConnectionManager(
            transport,
            ConnectionSettings(timeout=1, inter_request_delay=0, retries=0),
        )
        reader = ConfigurationService(manager, RegisterCatalog.load())
        task = asyncio.create_task(reader.read("rk1.flow.maximum"))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_requests_are_serialized(self) -> None:
        class InstrumentedTransport(MockTransport):
            def __init__(self) -> None:
                super().__init__(holding={1: 1, 2: 2})
                self.active = 0
                self.maximum_active = 0

            async def read_holding_registers(self, address: int, count: int) -> list[int]:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
                try:
                    await asyncio.sleep(0.01)
                    return await super().read_holding_registers(address, count)
                finally:
                    self.active -= 1

        transport = InstrumentedTransport()
        manager = ConnectionManager(
            transport,
            ConnectionSettings(timeout=0.1, inter_request_delay=0, retries=0),
        )
        await asyncio.gather(
            manager.read_holding_registers(1, 1),
            manager.read_holding_registers(2, 1),
        )
        self.assertEqual(transport.maximum_active, 1)

    async def test_retry_after_connection_loss(self) -> None:
        reader, transport = service(MockFailurePlan(connection_losses=1))
        result = await reader.read("rk1.flow.maximum")
        self.assertTrue(result.successful)
        self.assertEqual(result.data_point.value, 70)  # type: ignore[union-attr]
        manager = reader.manager
        self.assertEqual(manager.metrics.connection_losses, 1)
        self.assertEqual(manager.metrics.retries, 1)
        self.assertEqual(manager.metrics.reconnects, 1)
        self.assertTrue(transport.connected)  # type: ignore[attr-defined]

    async def test_partial_snapshot(self) -> None:
        reader, _ = service(MockFailurePlan(missing_addresses={1002}))
        snapshot = await reader.read_config()
        self.assertEqual(snapshot.status, SnapshotStatus.PARTIAL)
        self.assertTrue(any(error.data_point_id == "rk1.room.day" for error in snapshot.errors))
        points = {point.id for section in snapshot.configuration for point in section.data_points}
        self.assertIn("rk1.room.night", points)

    async def test_firmware_mismatch(self) -> None:
        reader, transport = service()
        transport.holding[2] = 254  # type: ignore[attr-defined]
        snapshot = await reader.read_config()
        self.assertEqual(snapshot.status, SnapshotStatus.PARTIAL)
        self.assertTrue(any(error.kind == "FirmwareMismatchError" for error in snapshot.errors))

    async def test_snapshot_serialization_round_trip(self) -> None:
        reader, _ = service()
        snapshot = await reader.read_config()
        restored = type(snapshot).model_validate_json(snapshot.model_dump_json())
        self.assertEqual(restored, snapshot)
