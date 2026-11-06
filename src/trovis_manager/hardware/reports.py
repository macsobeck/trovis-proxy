"""Persist hardware-validation JSON and compact Markdown reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel

from trovis_manager.storage.json_store import save_json_document

from .models import (
    ConsistencyRecord,
    GoldenComparisonRecord,
    HardwareRunRecord,
    HardwareValidationSummary,
)


def _cell(value: object) -> str:
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    return rendered.replace("|", "\\|").replace("\n", " ")


def save_models(path: Path, models: Iterable[BaseModel]) -> None:
    save_json_document([item.model_dump(mode="json") for item in models], path)


def write_consistency_reports(path: Path, records: list[ConsistencyRecord]) -> None:
    save_models(path / "consistency-report.json", records)
    lines = [
        "# Consistency Report",
        "",
        "| Data point | Kind | Status | Values |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| `{item.data_point_id}` | {item.value_kind} | {item.status} | {_cell(item.values)} |"
        for item in records
    )
    (path / "consistency-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_golden_reports(path: Path, records: list[GoldenComparisonRecord]) -> None:
    save_models(path / "golden-comparison.json", records)
    lines = [
        "# Golden Reference Comparison",
        "",
        "| Parameter | TROVIS-VIEW | Controller | Status | Confidence |",
        "|---|---|---|---|---|",
    ]
    lines.extend(
        f"| `{item.parameter}` | {_cell(item.reference_value)} | "
        f"{_cell(item.controller_value)} | {item.status} | {item.confidence} |"
        for item in records
    )
    (path / "golden-comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_reports(
    path: Path,
    summary: HardwareValidationSummary,
    runs: list[HardwareRunRecord],
) -> None:
    save_json_document(summary.model_dump(mode="json"), path / "validation-summary.json")
    save_models(path / "runs.json", runs)
    lines = [
        "# Read-only Hardware Validation",
        "",
        f"- Outcome: **{summary.outcome}**",
        f"- Execution mode: `{summary.execution_mode}`",
        f"- Reads: {summary.completed_reads}/{summary.requested_reads}",
        f"- Complete/partial/failed: {summary.complete_snapshots}/"
        f"{summary.partial_snapshots}/{summary.failed_reads}",
        f"- Error rate: {summary.error_rate:.4f}",
        f"- Reconnects: {summary.reconnects}",
        f"- Golden matches/differences: {summary.golden_matches}/"
        f"{summary.golden_differences}",
        "",
        "## Reasons",
        "",
    ]
    lines.extend(f"- {reason}" for reason in summary.reasons)
    lines.extend(
        [
            "",
            "## Runs",
            "",
            "| Run | Duration | Requests | Retries | Timeouts | Exceptions | "
            "Reconnects | Snapshot |",
            "|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    lines.extend(
        f"| {run.run} | {run.duration_s:.3f}s | {run.metrics.requests} | "
        f"{run.metrics.retries} | {run.metrics.timeouts} | "
        f"{run.metrics.modbus_exceptions} | {run.metrics.reconnects} | "
        f"{run.snapshot_status or 'FAILED'} |"
        for run in runs
    )
    (path / "validation-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
