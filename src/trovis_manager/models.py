"""Stable internal models for definitions, reads, and configuration backups."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Confidence(StrEnum):
    VERIFIED = "VERIFIED"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class SnapshotStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"


class TransportAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    address: int | None = None
    reference: str | None = None
    read_function_code: int | None = None
    write_function_code: int | None = None


class DataPointDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    group: str
    co: str | None = None
    function: str | None = None
    subparameter: str | None = None
    transport: TransportAddress
    datatype: str
    signed: bool = False
    bit: int | None = None
    scale: float = 1.0
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    enum: dict[str, Any] = Field(default_factory=dict)
    sentinel: int | None = None
    readable: bool = True
    writable: bool = False
    write_protection: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    firmware: list[str] = Field(default_factory=lambda: ["3.09.xx"])
    source: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    notes: str | None = None
    value_kind: str = "unknown"
    hardware_verified: bool = False
    verified_controller_firmware: str | None = None
    hardware_verification_date: str | None = None
    hardware_test_reference: str | None = None


class DataPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    group: str
    co: str | None = None
    function: str | None = None
    value: Any = None
    raw_value: Any = None
    datatype: str
    scale: float = 1.0
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    enum: dict[str, Any] = Field(default_factory=dict)
    readable: bool = True
    writable: bool = False
    active: bool | None = None
    source: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.UNKNOWN
    value_kind: str = "unknown"


class TimeInterval(BaseModel):
    start: str
    end: str


class TimeProgram(BaseModel):
    id: str
    label: str
    days: dict[str, list[TimeInterval]]
    source: list[str] = Field(default_factory=list)
    confidence: Confidence


class ControllerIdentity(BaseModel):
    manufacturer: str = "SAMSON"
    model: str
    firmware: str
    hardware_version: str | None = None
    serial_number: str | None = None
    serial_number_raw: int | None = None
    system_code: str
    modbus_unit_id: int = Field(ge=1, le=247)


class CommunicationError(BaseModel):
    operation: str
    data_point_id: str | None = None
    kind: str
    message: str
    attempts: int = 1


class ReadResult(BaseModel):
    data_point: DataPoint | None = None
    error: CommunicationError | None = None

    @property
    def successful(self) -> bool:
        return self.data_point is not None and self.error is None


class ConfigurationSection(BaseModel):
    id: str
    label: str
    data_points: list[DataPoint] = Field(default_factory=list)
    time_programs: list[TimeProgram] = Field(default_factory=list)


class ConfigurationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    controller: ControllerIdentity
    firmware: str
    serial_number: str | None
    system_code: str
    modbus_unit_id: int
    status: SnapshotStatus
    configuration: list[ConfigurationSection]
    errors: list[CommunicationError] = Field(default_factory=list)
