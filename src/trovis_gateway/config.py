"""Persistent controller-profile and infrastructure configuration models."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


DEFAULT_LISTEN_PORT = 7112


class TransportType(StrEnum):
    MODBUS_TCP = "modbus_tcp"
    RTU_OVER_TCP = "rtu_over_tcp"
    SERIAL_RTU = "serial_rtu"


class TimingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connect_timeout_s: float = Field(default=3.0, gt=0, le=120)
    response_timeout_s: float = Field(default=2.0, gt=0, le=120)
    total_request_timeout_s: float = Field(default=8.0, gt=0, le=300)
    minimum_request_interval_s: float = Field(default=0.1, ge=0, le=30)
    connect_settle_delay_s: float = Field(default=0.25, ge=0, le=30)
    reconnect_delay_s: float = Field(default=1.0, ge=0, le=120)


class RetrySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read_retries: int = Field(default=2, ge=0, le=10)
    write_retries: int = Field(default=0, ge=0, le=3)


class SerialSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: str = ""
    baudrate: int = Field(default=19200, ge=300, le=4_000_000)
    data_bits: Literal[7, 8] = 8
    parity: Literal["N", "E", "O"] = "N"
    stop_bits: Literal[1, 2] = 1


class ControllerProfile(BaseModel):
    """Only the Gateway → controller side of the connection."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    transport: TransportType = TransportType.RTU_OVER_TCP
    host: str = Field(default="", max_length=253)
    port: int = Field(default=502, ge=1, le=65535)
    upstream_unit_id: int = Field(default=247, ge=1, le=247)
    access_key: SecretStr | None = Field(default=None, repr=False)
    key_mode: Literal["pass-through"] = "pass-through"
    timing: TimingSettings = Field(default_factory=TimingSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    serial: SerialSettings = Field(default_factory=SerialSettings)

    @model_validator(mode="after")
    def validate_endpoint(self) -> ControllerProfile:
        if self.transport in {TransportType.MODBUS_TCP, TransportType.RTU_OVER_TCP}:
            if not self.host.strip():
                raise ValueError("host is required for TCP transports")
        elif not self.serial.device.strip():
            raise ValueError("serial device is required for Serial RTU")
        return self

    def connection_fingerprint(self) -> tuple[object, ...]:
        return (
            self.transport,
            self.host,
            self.port,
            self.upstream_unit_id,
            self.serial.device,
            self.serial.baudrate,
            self.serial.data_bits,
            self.serial.parity,
            self.serial.stop_bits,
            self.timing.connect_timeout_s,
            self.timing.response_timeout_s,
            self.timing.connect_settle_delay_s,
        )

    def target_label(self) -> str:
        if self.transport == TransportType.SERIAL_RTU:
            return self.serial.device
        return f"{self.host}:{self.port}"


class GatewayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    active_profile_id: str | None = None
    profiles: list[ControllerProfile] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_profiles(self) -> GatewayConfig:
        identifiers = [profile.id for profile in self.profiles]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("profile IDs must be unique")
        if self.active_profile_id is not None and self.active_profile_id not in identifiers:
            raise ValueError("active profile does not exist")
        return self

    def active_profile(self) -> ControllerProfile | None:
        return next(
            (profile for profile in self.profiles if profile.id == self.active_profile_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class InfrastructureSettings:
    listen_host: str = "0.0.0.0"
    listen_port: int = DEFAULT_LISTEN_PORT
    admin_host: str = "127.0.0.1"
    admin_port: int = 8080
    config_path: Path = Path("/data/config.json")
    trace_modbus: bool = False

    @classmethod
    def from_environment(cls) -> InfrastructureSettings:
        return cls(
            listen_host=os.environ.get("LISTEN_ADDRESS", "0.0.0.0"),
            listen_port=int(os.environ.get("LISTEN_PORT", str(DEFAULT_LISTEN_PORT))),
            admin_host=os.environ.get("ADMIN_ADDRESS", "127.0.0.1"),
            admin_port=int(os.environ.get("ADMIN_PORT", "8080")),
            config_path=Path(os.environ.get("GATEWAY_CONFIG_PATH", "/data/config.json")),
            trace_modbus=os.environ.get("MODBUS_TRACE", "0").casefold()
            in {"1", "true", "yes", "on"},
        )
