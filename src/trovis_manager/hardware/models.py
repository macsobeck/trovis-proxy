"""Models for read-only hardware validation artifacts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from trovis_manager.models import Confidence, ControllerIdentity, SnapshotStatus


class ConsistencyStatus(StrEnum):
    STABLE = "STABLE"
    CHANGED_EXPECTED = "CHANGED_EXPECTED"
    INCONSISTENT = "INCONSISTENT"
    UNREADABLE = "UNREADABLE"
    UNKNOWN = "UNKNOWN"


class GoldenStatus(StrEnum):
    MATCH = "MATCH"
    DIFFERENT = "DIFFERENT"
    NOT_READABLE = "NOT_READABLE"
    NOT_MAPPED = "NOT_MAPPED"
    RUNTIME_ONLY = "RUNTIME_ONLY"


class ValidationOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class CommunicationMetrics(BaseModel):
    requests: int = 0
    attempts: int = 0
    retries: int = 0
    timeouts: int = 0
    modbus_exceptions: int = 0
    connection_losses: int = 0
    reconnects: int = 0


class HardwareRunRecord(BaseModel):
    run: int
    started_at: str
    ended_at: str
    duration_s: float
    metrics: CommunicationMetrics
    data_points_read: int
    missing_data_points: list[str] = Field(default_factory=list)
    snapshot_status: SnapshotStatus | None = None
    controller: ControllerIdentity | None = None
    snapshot_file: str | None = None
    error: str | None = None


class ConsistencyRecord(BaseModel):
    data_point_id: str
    label: str
    value_kind: str
    status: ConsistencyStatus
    values: list[Any]


class GoldenComparisonRecord(BaseModel):
    parameter: str
    data_point_id: str | None = None
    reference_value: Any = None
    controller_value: Any = None
    status: GoldenStatus
    confidence: Confidence
    possible_causes: list[str] = Field(default_factory=list)


class HardwareValidationSummary(BaseModel):
    outcome: ValidationOutcome
    execution_mode: str
    requested_reads: int
    completed_reads: int
    complete_snapshots: int
    partial_snapshots: int
    failed_reads: int
    error_rate: float
    reconnects: int
    golden_matches: int
    golden_differences: int
    not_readable: int
    not_mapped: int
    runtime_only: int
    inconsistent_configuration_points: int
    reasons: list[str] = Field(default_factory=list)
    matrix_confidence_counts: dict[str, int] = Field(default_factory=dict)
