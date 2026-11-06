"""Serialized, transport-neutral forwarding to the configured controller."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from time import monotonic
from typing import Any

from .config import ControllerProfile, TransportType
from .metrics import GatewayMetrics
from .protocol import (
    PduKind,
    classify_pdu,
    decode_rtu_adu,
    encode_rtu_adu,
    encode_tcp_adu,
    read_tcp_adu,
)
from .trace import GatewayTrace


class UpstreamRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        sent: bool,
        timed_out: bool = False,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.sent = sent
        self.timed_out = timed_out
        self.retryable = retryable


class UpstreamBackend(ABC):
    def __init__(self, profile: ControllerProfile) -> None:
        self.profile = profile

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def exchange(self, transaction_id: int, pdu: bytes) -> bytes: ...


class ModbusTcpBackend(UpstreamBackend):
    def __init__(self, profile: ControllerProfile) -> None:
        super().__init__(profile)
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def connect(self) -> None:
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.profile.host, self.profile.port),
                self.profile.timing.connect_timeout_s,
            )
            if self.profile.timing.connect_settle_delay_s:
                await asyncio.sleep(self.profile.timing.connect_settle_delay_s)
        except Exception as exc:
            await self.close()
            raise UpstreamRequestError(str(exc), sent=False, timed_out=_timeout(exc)) from exc

    async def close(self) -> None:
        writer, self.writer, self.reader = self.writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def exchange(self, transaction_id: int, pdu: bytes) -> bytes:
        if self.reader is None or self.writer is None:
            raise UpstreamRequestError("upstream is not connected", sent=False)
        sent = False
        try:
            self.writer.write(
                encode_tcp_adu(transaction_id, self.profile.upstream_unit_id, pdu)
            )
            sent = True
            await self.writer.drain()
            response = await asyncio.wait_for(
                read_tcp_adu(self.reader),
                self.profile.timing.response_timeout_s,
            )
            if response.transaction_id != transaction_id:
                raise ValueError("upstream transaction ID mismatch")
            if response.unit_id != self.profile.upstream_unit_id:
                raise ValueError("upstream unit ID mismatch")
            return response.pdu
        except Exception as exc:
            raise UpstreamRequestError(
                str(exc), sent=sent, timed_out=_timeout(exc), retryable=_transport_failure(exc)
            ) from exc


class RtuOverTcpBackend(UpstreamBackend):
    def __init__(self, profile: ControllerProfile) -> None:
        super().__init__(profile)
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def connect(self) -> None:
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.profile.host, self.profile.port),
                self.profile.timing.connect_timeout_s,
            )
            if self.profile.timing.connect_settle_delay_s:
                await asyncio.sleep(self.profile.timing.connect_settle_delay_s)
        except Exception as exc:
            await self.close()
            raise UpstreamRequestError(str(exc), sent=False, timed_out=_timeout(exc)) from exc

    async def close(self) -> None:
        writer, self.writer, self.reader = self.writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def exchange(self, transaction_id: int, pdu: bytes) -> bytes:
        del transaction_id
        if self.reader is None or self.writer is None:
            raise UpstreamRequestError("upstream is not connected", sent=False)
        sent = False
        try:
            self.writer.write(encode_rtu_adu(self.profile.upstream_unit_id, pdu))
            sent = True
            await self.writer.drain()
            frame = await _read_rtu_response(
                self.reader,
                pdu[0],
                self.profile.timing.response_timeout_s,
            )
            return decode_rtu_adu(frame, self.profile.upstream_unit_id)
        except Exception as exc:
            raise UpstreamRequestError(
                str(exc), sent=sent, timed_out=_timeout(exc), retryable=_transport_failure(exc)
            ) from exc


class SerialRtuBackend(UpstreamBackend):
    def __init__(self, profile: ControllerProfile) -> None:
        super().__init__(profile)
        self.port: Any = None

    @property
    def connected(self) -> bool:
        return bool(self.port is not None and self.port.is_open)

    async def connect(self) -> None:
        try:
            import serial
        except ImportError as exc:
            raise UpstreamRequestError(
                "Serial RTU requires the 'serial' project extra",
                sent=False,
            ) from exc

        def open_port() -> Any:
            return serial.Serial(
                port=self.profile.serial.device,
                baudrate=self.profile.serial.baudrate,
                bytesize=self.profile.serial.data_bits,
                parity=self.profile.serial.parity,
                stopbits=self.profile.serial.stop_bits,
                timeout=self.profile.timing.response_timeout_s,
                write_timeout=self.profile.timing.connect_timeout_s,
            )

        try:
            self.port = await asyncio.wait_for(
                asyncio.to_thread(open_port),
                self.profile.timing.connect_timeout_s,
            )
            if self.profile.timing.connect_settle_delay_s:
                await asyncio.sleep(self.profile.timing.connect_settle_delay_s)
        except Exception as exc:
            await self.close()
            raise UpstreamRequestError(str(exc), sent=False, timed_out=_timeout(exc)) from exc

    async def close(self) -> None:
        port, self.port = self.port, None
        if port is not None:
            try:
                await asyncio.to_thread(port.close)
            except Exception:
                pass

    async def exchange(self, transaction_id: int, pdu: bytes) -> bytes:
        del transaction_id
        if self.port is None:
            raise UpstreamRequestError("upstream is not connected", sent=False)
        sent = False

        def transact() -> bytes:
            nonlocal sent
            self.port.reset_input_buffer()
            sent = True
            self.port.write(encode_rtu_adu(self.profile.upstream_unit_id, pdu))
            self.port.flush()
            return _read_rtu_serial(self.port, pdu[0])

        try:
            frame = await asyncio.to_thread(transact)
            return decode_rtu_adu(frame, self.profile.upstream_unit_id)
        except Exception as exc:
            raise UpstreamRequestError(
                str(exc), sent=sent, timed_out=_timeout(exc), retryable=_transport_failure(exc)
            ) from exc


def _timeout(error: BaseException) -> bool:
    return isinstance(error, TimeoutError) or "timeout" in type(error).__name__.casefold()


def _transport_failure(error: BaseException) -> bool:
    return isinstance(
        error,
        (TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError),
    )


async def _read_rtu_response(
    reader: asyncio.StreamReader,
    request_function: int,
    timeout: float,
) -> bytes:
    del request_function
    prefix = await asyncio.wait_for(reader.readexactly(2), timeout)
    response_function = prefix[1]
    if response_function & 0x80:
        return prefix + await asyncio.wait_for(reader.readexactly(3), timeout)
    if response_function in {0x01, 0x02, 0x03, 0x04}:
        byte_count = await asyncio.wait_for(reader.readexactly(1), timeout)
        return prefix + byte_count + await asyncio.wait_for(
            reader.readexactly(byte_count[0] + 2),
            timeout,
        )
    if response_function in {0x05, 0x06, 0x0F, 0x10}:
        return prefix + await asyncio.wait_for(reader.readexactly(6), timeout)
    chunks = [prefix]
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(256), min(timeout, 0.05))
        except TimeoutError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _read_rtu_serial(port: Any, request_function: int) -> bytes:
    del request_function
    prefix = port.read(2)
    if len(prefix) != 2:
        raise TimeoutError("serial response timeout")
    response_function = prefix[1]
    if response_function & 0x80:
        remainder = port.read(3)
    elif response_function in {0x01, 0x02, 0x03, 0x04}:
        byte_count = port.read(1)
        if len(byte_count) != 1:
            raise TimeoutError("serial byte-count timeout")
        remainder = byte_count + port.read(byte_count[0] + 2)
    elif response_function in {0x05, 0x06, 0x0F, 0x10}:
        remainder = port.read(6)
    else:
        chunks: list[bytes] = []
        while chunk := port.read(256):
            chunks.append(chunk)
        remainder = b"".join(chunks)
    return prefix + remainder


def _backend(profile: ControllerProfile) -> UpstreamBackend:
    if profile.transport == TransportType.MODBUS_TCP:
        return ModbusTcpBackend(profile)
    if profile.transport == TransportType.RTU_OVER_TCP:
        return RtuOverTcpBackend(profile)
    return SerialRtuBackend(profile)


class UpstreamRouter:
    """One serialized request boundary for the active controller profile."""

    def __init__(self, metrics: GatewayMetrics, trace: GatewayTrace) -> None:
        self.metrics = metrics
        self.trace = trace
        self._lock = asyncio.Lock()
        self._backend: UpstreamBackend | None = None
        self._fingerprint: tuple[object, ...] | None = None
        self._last_request_at = 0.0
        self._last_failure_at = 0.0
        self._ever_connected = False

    async def close(self) -> None:
        if self._backend is not None:
            await self._backend.close()
        self._backend = None
        self._fingerprint = None
        self.metrics.set("upstream_connected", False)

    async def request(
        self,
        *,
        transaction_id: int,
        downstream_unit_id: int,
        pdu: bytes,
        profile: ControllerProfile,
    ) -> bytes:
        self.metrics.increment("queue_depth")
        try:
            await self._lock.acquire()
        finally:
            self.metrics.increment("queue_depth", -1)
        try:
            try:
                return await asyncio.wait_for(
                    self._request_locked(
                        transaction_id=transaction_id,
                        downstream_unit_id=downstream_unit_id,
                        pdu=pdu,
                        profile=profile,
                    ),
                    profile.timing.total_request_timeout_s,
                )
            except TimeoutError as exc:
                self.metrics.increment("timeouts")
                await self.close()
                self.trace.emit(
                    "UPSTREAM RX",
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    upstream_unit_id=profile.upstream_unit_id,
                    pdu=pdu,
                    exception=exc,
                )
                raise UpstreamRequestError(
                    "total request timeout",
                    sent=True,
                    timed_out=True,
                ) from exc
        finally:
            self._lock.release()

    async def _request_locked(
        self,
        *,
        transaction_id: int,
        downstream_unit_id: int,
        pdu: bytes,
        profile: ControllerProfile,
    ) -> bytes:
        kind = classify_pdu(pdu)
        max_retries = profile.retry.read_retries if kind == PduKind.READ else 0
        if kind == PduKind.WRITE:
            max_retries = profile.retry.write_retries
        for attempt in range(max_retries + 1):
            try:
                await self._ensure_backend(profile)
                await self._pace(profile)
                started = monotonic()
                self.trace.emit(
                    "UPSTREAM TX",
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    upstream_unit_id=profile.upstream_unit_id,
                    pdu=pdu,
                    retry=attempt,
                )
                assert self._backend is not None
                response = await self._backend.exchange(transaction_id, pdu)
                self._last_request_at = monotonic()
                self.trace.emit(
                    "UPSTREAM RX",
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    upstream_unit_id=profile.upstream_unit_id,
                    pdu=response,
                    duration_ms=(monotonic() - started) * 1000,
                    retry=attempt,
                )
                return response
            except UpstreamRequestError as exc:
                if exc.timed_out:
                    self.metrics.increment("timeouts")
                self.trace.emit(
                    "UPSTREAM RX",
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    upstream_unit_id=profile.upstream_unit_id,
                    pdu=pdu,
                    retry=attempt,
                    exception=exc,
                )
                self._last_failure_at = monotonic()
                await self.close()
                can_retry_read = (
                    kind == PduKind.READ and exc.retryable and attempt < max_retries
                )
                can_retry_unsent_write = (
                    kind == PduKind.WRITE
                    and exc.retryable
                    and not exc.sent
                    and attempt < max_retries
                )
                if not (can_retry_read or can_retry_unsent_write):
                    raise
                self.metrics.increment("retries")
        raise AssertionError("unreachable retry loop")

    async def _ensure_backend(self, profile: ControllerProfile) -> None:
        fingerprint = profile.connection_fingerprint()
        if self._fingerprint != fingerprint:
            await self.close()
            self._backend = _backend(profile)
            self._fingerprint = fingerprint
        assert self._backend is not None
        if self._backend.connected:
            return
        since_failure = monotonic() - self._last_failure_at
        if self._last_failure_at and since_failure < profile.timing.reconnect_delay_s:
            await asyncio.sleep(profile.timing.reconnect_delay_s - since_failure)
        await self._backend.connect()
        if self._ever_connected:
            self.metrics.increment("reconnects")
        self._ever_connected = True
        self.metrics.set("upstream_connected", True)
        self.metrics.set("upstream_target", profile.target_label())

    async def _pace(self, profile: ControllerProfile) -> None:
        wait = profile.timing.minimum_request_interval_s - (
            monotonic() - self._last_request_at
        )
        if wait > 0:
            await asyncio.sleep(wait)
