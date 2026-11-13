"""Thread-safe operational state shared by the Modbus Proxy and status API."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class MetricValues:
    downstream_clients: int = 0
    queue_depth: int = 0
    requests: int = 0
    timeouts: int = 0
    retries: int = 0
    reconnects: int = 0
    upstream_connected: bool = False
    upstream_target: str | None = None


class GatewayMetrics:
    def __init__(self) -> None:
        self._values = MetricValues()
        self._lock = threading.RLock()

    def increment(self, field: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self._values, field, getattr(self._values, field) + amount)

    def set(self, field: str, value: Any) -> None:
        with self._lock:
            setattr(self._values, field, value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._values)
