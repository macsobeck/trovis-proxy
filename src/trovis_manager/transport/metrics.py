"""Per-request communication metrics and optional diagnostic trace records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class RequestMetrics:
    requests: int = 0
    attempts: int = 0
    retries: int = 0
    timeouts: int = 0
    modbus_exceptions: int = 0
    connection_losses: int = 0
    reconnects: int = 0

    def copy(self) -> RequestMetrics:
        return replace(self)

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class RequestTrace:
    sequence: int
    timestamp: str
    function_code: int
    address: int
    count: int
    duration_ms: float
    retry: int
    raw_response: list[int | bool] | None = None
    decoded_response: dict[str, Any] | None = None
    exception: dict[str, str] | None = None
    context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(
        cls,
        *,
        sequence: int,
        function_code: int,
        address: int,
        count: int,
        duration_ms: float,
        retry: int,
        raw_response: list[int | bool] | None = None,
        exception: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> RequestTrace:
        error = None
        if exception is not None:
            error = {"type": type(exception).__name__, "message": str(exception)}
        return cls(
            sequence=sequence,
            timestamp=datetime.now(timezone.utc).isoformat(),
            function_code=function_code,
            address=address,
            count=count,
            duration_ms=round(duration_ms, 3),
            retry=retry,
            raw_response=raw_response,
            exception=error,
            context=dict(context or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
