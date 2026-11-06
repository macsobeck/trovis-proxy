"""Serialized, bounded, retrying access to a single Modbus connection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Awaitable, Callable, TypeVar

from .base import Transport
from .metrics import RequestMetrics, RequestTrace

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ConnectionSettings:
    timeout: float = 1.0
    inter_request_delay: float = 0.05
    retries: int = 2
    retry_backoff: float = 0.1
    trace_enabled: bool = False


class ConnectionManager:
    def __init__(self, transport: Transport, settings: ConnectionSettings | None = None) -> None:
        self.transport = transport
        self.settings = settings or ConnectionSettings()
        self._lock = asyncio.Lock()
        self._last_request = 0.0
        self._ever_connected = False
        self.metrics = RequestMetrics()
        self.trace: list[RequestTrace] = []
        self.trace_context: dict[str, object] = {}
        self._trace_sequence = 0

    async def _connect(self) -> None:
        was_connected_before = self._ever_connected
        await asyncio.wait_for(self.transport.connect(), self.settings.timeout)
        self._ever_connected = True
        if was_connected_before:
            self.metrics.reconnects += 1

    async def connect(self) -> None:
        async with self._lock:
            if not self.transport.connected:
                await self._connect()

    async def disconnect(self) -> None:
        async with self._lock:
            await asyncio.wait_for(self.transport.disconnect(), self.settings.timeout)

    async def _request(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        function_code: int,
        address: int,
        count: int,
    ) -> T:
        async with self._lock:
            self.metrics.requests += 1
            loop = asyncio.get_running_loop()
            wait = self.settings.inter_request_delay - (loop.time() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            last_error: Exception | None = None
            for attempt in range(self.settings.retries + 1):
                self.metrics.attempts += 1
                if attempt:
                    self.metrics.retries += 1
                started = monotonic()
                try:
                    if not self.transport.connected:
                        await self._connect()
                    result = await asyncio.wait_for(operation(), self.settings.timeout)
                    self._last_request = loop.time()
                    self._record_trace(
                        function_code=function_code,
                        address=address,
                        count=count,
                        duration_ms=(monotonic() - started) * 1000,
                        retry=attempt,
                        raw_response=result if isinstance(result, list) else None,
                    )
                    return result
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    last_error = exc
                    self._classify_error(exc)
                    self._record_trace(
                        function_code=function_code,
                        address=address,
                        count=count,
                        duration_ms=(monotonic() - started) * 1000,
                        retry=attempt,
                        exception=exc,
                    )
                    try:
                        await asyncio.wait_for(self.transport.disconnect(), self.settings.timeout)
                    except Exception:
                        pass
                    if attempt < self.settings.retries:
                        await asyncio.sleep(self.settings.retry_backoff * (2**attempt))
            assert last_error is not None
            raise last_error

    def _classify_error(self, error: Exception) -> None:
        name = type(error).__name__.casefold()
        if isinstance(error, TimeoutError) or "timeout" in name:
            self.metrics.timeouts += 1
        elif isinstance(error, ConnectionError) or "connection" in name:
            self.metrics.connection_losses += 1
        else:
            self.metrics.modbus_exceptions += 1

    def _record_trace(
        self,
        *,
        function_code: int,
        address: int,
        count: int,
        duration_ms: float,
        retry: int,
        raw_response: list[int | bool] | None = None,
        exception: Exception | None = None,
    ) -> None:
        if not self.settings.trace_enabled:
            return
        self._trace_sequence += 1
        self.trace.append(
            RequestTrace.now(
                sequence=self._trace_sequence,
                function_code=function_code,
                address=address,
                count=count,
                duration_ms=duration_ms,
                retry=retry,
                raw_response=raw_response,
                exception=exception,
                context=self.trace_context,
            )
        )

    def annotate_last_trace(
        self,
        *,
        function_code: int,
        address: int,
        count: int,
        decoded_response: dict[str, object],
    ) -> None:
        if not self.settings.trace_enabled:
            return
        for entry in reversed(self.trace):
            if (
                entry.function_code == function_code
                and entry.address == address
                and entry.count == count
                and entry.exception is None
                and entry.decoded_response is None
            ):
                entry.decoded_response = dict(decoded_response)
                return

    def reset_metrics(self) -> None:
        self.metrics = RequestMetrics()

    def metrics_snapshot(self) -> RequestMetrics:
        return self.metrics.copy()

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        return await self._request(
            lambda: self.transport.read_holding_registers(address, count),
            function_code=3,
            address=address,
            count=count,
        )

    async def read_coils(self, address: int, count: int) -> list[bool]:
        return await self._request(
            lambda: self.transport.read_coils(address, count),
            function_code=1,
            address=address,
            count=count,
        )
