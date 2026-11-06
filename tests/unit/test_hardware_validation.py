from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trovis_manager.catalog import RegisterCatalog
from trovis_manager.configuration import ConfigurationService
from trovis_manager.controller import golden_mock_transport
from trovis_manager.hardware import HardwareValidator, UnsupportedControllerError
from trovis_manager.hardware.golden import compare_snapshots, compare_to_golden
from trovis_manager.hardware.models import (
    ConsistencyStatus,
    GoldenStatus,
    ValidationOutcome,
)
from trovis_manager.transport import ConnectionManager, ConnectionSettings, MockFailurePlan


def validator(
    failures: MockFailurePlan | None = None,
) -> tuple[HardwareValidator, object, ConnectionManager, RegisterCatalog]:
    transport = golden_mock_transport(failures)
    manager = ConnectionManager(
        transport,
        ConnectionSettings(
            timeout=0.01,
            inter_request_delay=0,
            retries=1,
            retry_backoff=0,
            trace_enabled=True,
        ),
    )
    catalog = RegisterCatalog.load()
    service = ConfigurationService(manager, catalog)
    return HardwareValidator(service, manager, catalog), transport, manager, catalog


class HardwareValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_gate_reads_hardware_version(self) -> None:
        check, _, _, _ = validator()
        identity = await check.identify_gate()
        self.assertEqual(identity.hardware_version, "110")
        self.assertEqual(identity.serial_number, "243179")
        self.assertEqual(identity.serial_number_raw, 12345)

    async def test_identity_gate_aborts_before_configuration_read(self) -> None:
        check, transport, _, _ = validator()
        transport.holding[2] = 254  # type: ignore[attr-defined]
        with self.assertRaises(UnsupportedControllerError):
            await check.read_once()
        calls = transport.read_calls  # type: ignore[attr-defined]
        addresses = {address for _, address, _ in calls}
        self.assertNotIn(1000, addresses)
        self.assertNotIn(1799, addresses)

    async def test_mock_endurance_writes_complete_reports_but_never_passes(self) -> None:
        check, _, _, _ = validator()
        with tempfile.TemporaryDirectory() as directory:
            output, summary = await check.endurance_read(
                runs=3,
                pause_s=0,
                output_root=Path(directory),
            )
            self.assertEqual(summary.outcome, ValidationOutcome.FAIL)
            self.assertEqual(summary.complete_snapshots, 3)
            self.assertEqual(summary.golden_differences, 0)
            self.assertIn("mock execution", " ".join(summary.reasons))
            for name in (
                "consistency-report.json",
                "consistency-report.md",
                "golden-comparison.json",
                "golden-comparison.md",
                "validation-summary.json",
                "validation-summary.md",
                "modbus-trace.json",
                "modbus-trace.jsonl",
            ):
                self.assertTrue((output / name).is_file(), name)
            trace = json.loads((output / "modbus-trace.json").read_text())
            self.assertTrue(any(item["decoded_response"] for item in trace))
            self.assertTrue(all("function_code" in item for item in trace))

    async def test_timeout_recovers_and_next_read_completes(self) -> None:
        check, _, _, _ = validator(MockFailurePlan(timeouts=1))
        with tempfile.TemporaryDirectory() as directory:
            output, summary = await check.endurance_read(
                runs=2,
                pause_s=0,
                output_root=Path(directory),
            )
            runs = json.loads((output / "runs.json").read_text())
            self.assertEqual(summary.complete_snapshots, 2)
            self.assertEqual(runs[0]["metrics"]["timeouts"], 1)
            self.assertEqual(runs[0]["metrics"]["retries"], 1)
            self.assertGreaterEqual(runs[0]["metrics"]["reconnects"], 1)
            self.assertEqual(runs[1]["snapshot_status"], "complete")

    async def test_runtime_change_is_expected_not_configuration_inconsistency(self) -> None:
        check, transport, _, catalog = validator()
        first = await check.read_once()
        transport.holding[9] = 75  # type: ignore[attr-defined]
        second = await check.read_once()
        records = {item.data_point_id: item for item in compare_snapshots([first, second], catalog)}
        self.assertEqual(records["sensor.af1"].status, ConsistencyStatus.CHANGED_EXPECTED)
        self.assertEqual(records["rk1.heating_curve.slope"].status, ConsistencyStatus.STABLE)

    async def test_golden_comparison_matches_mapped_configuration(self) -> None:
        check, _, _, catalog = validator()
        snapshot = await check.read_once()
        comparison = compare_to_golden(snapshot, catalog)
        mapped = [item for item in comparison if item.data_point_id == "rk1.room.day"]
        self.assertEqual(mapped[0].status, GoldenStatus.MATCH)
        self.assertFalse(any(item.status == GoldenStatus.DIFFERENT for item in comparison))
