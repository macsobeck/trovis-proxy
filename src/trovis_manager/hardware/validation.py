"""Conservative read-only validation against a real FW 03.09 controller."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from trovis_manager.catalog import RegisterCatalog
from trovis_manager.configuration import ConfigurationService
from trovis_manager.models import ConfigurationSnapshot, ControllerIdentity, SnapshotStatus
from trovis_manager.storage import save_json_document, save_snapshot
from trovis_manager.transport import ConnectionManager

from .golden import compare_snapshots, compare_to_golden
from .models import (
    CommunicationMetrics,
    ConsistencyRecord,
    ConsistencyStatus,
    GoldenComparisonRecord,
    GoldenStatus,
    HardwareRunRecord,
    HardwareValidationSummary,
    ValidationOutcome,
)
from .reports import write_consistency_reports, write_golden_reports, write_summary_reports


class UnsupportedControllerError(RuntimeError):
    """Raised before configuration reads when the identity gate fails."""


class HardwareExpectations:
    model = "TROVIS 5573-1"
    firmware_prefix = "03.09."
    system_code = "2.1"
    unit_id = 247


class HardwareValidator:
    def __init__(
        self,
        service: ConfigurationService,
        manager: ConnectionManager,
        catalog: RegisterCatalog,
        expectations: HardwareExpectations | None = None,
    ) -> None:
        self.service = service
        self.manager = manager
        self.catalog = catalog
        self.expectations = expectations or HardwareExpectations()

    @property
    def execution_mode(self) -> str:
        return str(getattr(self.manager.transport, "transport_name", "unknown"))

    async def identify_gate(self) -> ControllerIdentity:
        identity = await self.service.identify()
        failures: list[str] = []
        if identity.model != self.expectations.model:
            failures.append(f"model {identity.model!r} is unsupported")
        if not identity.firmware.startswith(self.expectations.firmware_prefix):
            failures.append(f"firmware {identity.firmware!r} is unsupported")
        if identity.system_code != self.expectations.system_code:
            failures.append(f"system {identity.system_code!r} is not 2.1")
        if identity.modbus_unit_id != self.expectations.unit_id:
            failures.append(f"reported unit ID {identity.modbus_unit_id} is not 247")
        target_unit = getattr(self.manager.transport, "unit_id", None)
        if target_unit is not None and target_unit != self.expectations.unit_id:
            failures.append(f"transport target unit ID {target_unit} is not 247")
        if failures:
            raise UnsupportedControllerError("; ".join(failures))
        return identity

    async def read_once(self) -> ConfigurationSnapshot:
        identity = await self.identify_gate()
        return await self.service.read_config(identity=identity)

    def _missing(self, snapshot: ConfigurationSnapshot) -> list[str]:
        present = {
            point.id
            for section in snapshot.configuration
            for point in section.data_points
        }
        expected = {
            item.id
            for item in self.catalog.readable()
            if item.group != "Controller"
        }
        return sorted(expected - present)

    async def _run(
        self,
        number: int,
        output_dir: Path,
    ) -> tuple[HardwareRunRecord, ConfigurationSnapshot | None]:
        self.manager.reset_metrics()
        self.manager.trace_context = {"run": number}
        started_at = datetime.now(timezone.utc)
        started = monotonic()
        snapshot: ConfigurationSnapshot | None = None
        identity: ControllerIdentity | None = None
        error: str | None = None
        snapshot_file: str | None = None
        try:
            identity = await self.identify_gate()
            snapshot = await self.service.read_config(identity=identity)
            relative = Path("snapshots") / f"run-{number:03d}.json"
            save_snapshot(snapshot, output_dir / relative)
            snapshot_file = str(relative)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        ended_at = datetime.now(timezone.utc)
        metrics = CommunicationMetrics.model_validate(
            self.manager.metrics_snapshot().as_dict()
        )
        missing = self._missing(snapshot) if snapshot is not None else []
        record = HardwareRunRecord(
            run=number,
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            duration_s=round(monotonic() - started, 6),
            metrics=metrics,
            data_points_read=(
                sum(len(section.data_points) for section in snapshot.configuration)
                if snapshot is not None
                else 0
            ),
            missing_data_points=missing,
            snapshot_status=snapshot.status if snapshot is not None else None,
            controller=identity,
            snapshot_file=snapshot_file,
            error=error,
        )
        return record, snapshot

    @staticmethod
    def _output_directory(root: Path) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        path = root / stamp
        path.mkdir(parents=True, exist_ok=False)
        return path

    async def endurance_read(
        self,
        *,
        runs: int = 20,
        pause_s: float = 2.0,
        output_root: Path = Path("hardware-validation"),
    ) -> tuple[Path, HardwareValidationSummary]:
        if runs < 1:
            raise ValueError("runs must be at least 1")
        if pause_s < 0:
            raise ValueError("pause must not be negative")
        output_dir = self._output_directory(output_root)
        trace_start = len(self.manager.trace)
        run_records: list[HardwareRunRecord] = []
        snapshots: list[ConfigurationSnapshot] = []
        for number in range(1, runs + 1):
            record, snapshot = await self._run(number, output_dir)
            run_records.append(record)
            if snapshot is not None:
                snapshots.append(snapshot)
            if record.error and "UnsupportedControllerError" in record.error:
                break
            if number < runs and pause_s:
                await asyncio.sleep(pause_s)

        consistency = compare_snapshots(snapshots, self.catalog)
        golden: list[GoldenComparisonRecord] = []
        if snapshots:
            golden = compare_to_golden(snapshots[-1], self.catalog)
        summary = self._summary(runs, run_records, consistency, golden)
        write_consistency_reports(output_dir, consistency)
        write_golden_reports(output_dir, golden)
        write_summary_reports(output_dir, summary, run_records)
        self._write_trace(output_dir, trace_start)
        self._write_verification_candidates(output_dir, summary, consistency, golden)
        return output_dir, summary

    def _summary(
        self,
        requested: int,
        runs: list[HardwareRunRecord],
        consistency: list[ConsistencyRecord],
        golden: list[GoldenComparisonRecord],
    ) -> HardwareValidationSummary:
        complete = sum(run.snapshot_status == SnapshotStatus.COMPLETE for run in runs)
        partial = sum(run.snapshot_status == SnapshotStatus.PARTIAL for run in runs)
        failed = sum(run.snapshot_status is None for run in runs)
        totals = CommunicationMetrics()
        for run in runs:
            for field in type(totals).model_fields:
                setattr(totals, field, getattr(totals, field) + getattr(run.metrics, field))
        errors = totals.timeouts + totals.modbus_exceptions + totals.connection_losses
        error_rate = errors / totals.attempts if totals.attempts else 0.0
        counts = Counter(record.status.value for record in golden)
        inconsistent = sum(
            item.status == ConsistencyStatus.INCONSISTENT
            and item.value_kind == "configuration"
            for item in consistency
        )
        reasons: list[str] = []
        if self.execution_mode == "mock":
            reasons.append("mock execution cannot prove real-hardware readiness")
        if requested < 20:
            reasons.append("fewer than 20 reads were requested")
        if len(runs) != requested:
            reasons.append("the run sequence aborted before all requested reads")
        if complete != requested:
            reasons.append("not every requested read produced a complete snapshot")
        if inconsistent:
            reasons.append(f"{inconsistent} configuration points were inconsistent")
        if counts[GoldenStatus.DIFFERENT.value]:
            reasons.append("one or more mapped values differ from the Golden Reference")
        if not runs or any(run.controller is None for run in runs):
            reasons.append("controller identity was not available for every run")
        elif any(run.controller.serial_number is None for run in runs if run.controller):
            reasons.append("serial number remains unreadable/UNKNOWN")
        outcome = ValidationOutcome.PASS if not reasons else ValidationOutcome.FAIL
        confidence = Counter(item.confidence.value for item in self.catalog.definitions)
        return HardwareValidationSummary(
            outcome=outcome,
            execution_mode=self.execution_mode,
            requested_reads=requested,
            completed_reads=len(runs),
            complete_snapshots=complete,
            partial_snapshots=partial,
            failed_reads=failed,
            error_rate=round(error_rate, 6),
            reconnects=totals.reconnects,
            golden_matches=counts[GoldenStatus.MATCH.value],
            golden_differences=counts[GoldenStatus.DIFFERENT.value],
            not_readable=counts[GoldenStatus.NOT_READABLE.value],
            not_mapped=counts[GoldenStatus.NOT_MAPPED.value],
            runtime_only=counts[GoldenStatus.RUNTIME_ONLY.value],
            inconsistent_configuration_points=inconsistent,
            reasons=reasons,
            matrix_confidence_counts=dict(sorted(confidence.items())),
        )

    def _write_trace(self, output_dir: Path, start: int) -> None:
        entries = [entry.as_dict() for entry in self.manager.trace[start:]]
        if not entries:
            return
        save_json_document(entries, output_dir / "modbus-trace.json")
        lines = "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in entries)
        (output_dir / "modbus-trace.jsonl").write_text(lines + "\n", encoding="utf-8")

    def _write_verification_candidates(
        self,
        output_dir: Path,
        summary: HardwareValidationSummary,
        consistency: list[ConsistencyRecord],
        golden: list[GoldenComparisonRecord],
    ) -> None:
        stable = {
            item.data_point_id
            for item in consistency
            if item.status == ConsistencyStatus.STABLE
        }
        matched = {
            item.data_point_id
            for item in golden
            if item.status == GoldenStatus.MATCH and item.data_point_id is not None
        }
        eligible = sorted(stable & matched) if summary.outcome == ValidationOutcome.PASS else []
        payload = {
            "automatic_promotion": False,
            "note": "Candidates require human review; this file never changes matrix confidence.",
            "validation_outcome": summary.outcome,
            "eligible_data_points": eligible,
        }
        save_json_document(payload, output_dir / "matrix-verification-candidates.json")
