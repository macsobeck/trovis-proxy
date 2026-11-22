"""Serialized, transport-neutral forwarding to the configured controller."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from threading import Event
from time import monotonic
from typing import Any

from .config import ControllerProfile, TransportType
from .metrics import GatewayMetrics
from .protocol import (
    ModbusResponseError,
    PduKind,
    classify_pdu,
    decode_rtu_adu,
    encode_rtu_adu,
    encode_tcp_adu,
    read_tcp_adu,
    validate_response_pdu,
)
from .tcp import TcpAddressCache, open_tcp_connection
from .trace import GatewayTrace

MIN_RTU_RECOVERY_QUIET_S = 0.05
logger = logging.getLogger(__name__)


class UpstreamRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        sent: bool,
        timed_out: bool = False,
        retryable: bool = True,
        response_pdu: bytes | None = None,
    ) -> None:
        super().__init__(message)
        self.sent = sent
        self.timed_out = timed_out
        self.retryable = retryable
        self.response_pdu = response_pdu


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
    def __init__(self, profile: ControllerProfile, address_cache: TcpAddressCache) -> None:
        super().__init__(profile)
        self.address_cache = address_cache
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def connect(self) -> None:
        try:
            self.reader, self.writer, _ = await open_tcp_connection(
                self.profile.host,
                self.profile.port,
                self.profile.timing.connect_timeout_s,
                address_preference=self.profile.address_preference,
                address_cache=self.address_cache,
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
        response_pdu: bytes | None = None
        try:
            self.writer.write(
                encode_tcp_adu(transaction_id, self.profile.upstream_unit_id, pdu)
            )
            sent = True
            await self.writer.drain()
            try:
                async with asyncio.timeout(self.profile.timing.response_timeout_s):
                    response = await read_tcp_adu(self.reader)
            except TimeoutError as exc:
                raise TimeoutError("Modbus TCP response exceeded the configured timeout") from exc
            response_pdu = response.pdu
            if response.transaction_id != transaction_id:
                raise ModbusResponseError("upstream transaction ID mismatch")
            if response.unit_id != self.profile.upstream_unit_id:
                raise ModbusResponseError("upstream unit ID mismatch")
            validate_response_pdu(pdu, response_pdu)
            return response_pdu
        except Exception as exc:
            raise UpstreamRequestError(
                str(exc),
                sent=sent,
                timed_out=_timeout(exc),
                retryable=_transport_failure(exc),
                response_pdu=response_pdu,
            ) from exc


class RtuOverTcpBackend(UpstreamBackend):
    def __init__(
        self,
        profile: ControllerProfile,
        address_cache: TcpAddressCache,
        *,
        resynchronize: bool = False,
    ) -> None:
        super().__init__(profile)
        self.address_cache = address_cache
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.resynchronize = resynchronize

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()

    async def connect(self) -> None:
        try:
            self.reader, self.writer, _ = await open_tcp_connection(
                self.profile.host,
                self.profile.port,
                self.profile.timing.connect_timeout_s,
                address_preference=self.profile.address_preference,
                address_cache=self.address_cache,
            )
            settle_s = self.profile.timing.connect_settle_delay_s
            if self.resynchronize:
                await self._wait_for_quiet(max(settle_s, MIN_RTU_RECOVERY_QUIET_S))
            elif settle_s:
                await asyncio.sleep(settle_s)
        except Exception as exc:
            await self.close()
            raise UpstreamRequestError(str(exc), sent=False, timed_out=_timeout(exc)) from exc

    async def _wait_for_quiet(self, quiet_s: float) -> None:
        assert self.reader is not None
        # No request has been sent on this connection. Discard any reply to a previous exchange
        # and restart the quiet interval. The router enforces the overall request deadline.
        while True:
            try:
                async with asyncio.timeout(quiet_s):
                    data = await self.reader.read(4096)
            except TimeoutError:
                return
            if not data:
                raise ConnectionError("RTU connection closed during resynchronization")
            # A continuously readable stream must still let the request deadline run.
            await asyncio.sleep(0)

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
        response_pdu: bytes | None = None
        try:
            await _check_rtu_stream_boundary(self.reader, before_request=True)
            self.writer.write(encode_rtu_adu(self.profile.upstream_unit_id, pdu))
            sent = True
            await self.writer.drain()
            frame = await _read_rtu_response(
                self.reader,
                self.profile.timing.response_timeout_s,
            )
            try:
                response_pdu = decode_rtu_adu(frame, self.profile.upstream_unit_id)
            except ValueError as exc:
                raise ModbusResponseError(str(exc)) from exc
            validate_response_pdu(pdu, response_pdu)
            await _check_rtu_stream_boundary(self.reader, before_request=False)
            return response_pdu
        except Exception as exc:
            raise UpstreamRequestError(
                str(exc),
                sent=sent,
                timed_out=_timeout(exc),
                retryable=_transport_failure(exc),
                response_pdu=response_pdu,
            ) from exc


class SerialRtuBackend(UpstreamBackend):
    def __init__(self, profile: ControllerProfile) -> None:
        super().__init__(profile)
        self.port: Any = None
        self._opening: asyncio.Task[Any] | None = None
        self._transacting: asyncio.Task[bytes] | None = None

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
            self._opening = asyncio.create_task(asyncio.to_thread(open_port))
            self.port = await asyncio.wait_for(
                asyncio.shield(self._opening),
                self.profile.timing.connect_timeout_s,
            )
            self._opening = None
            if self.profile.timing.connect_settle_delay_s:
                await asyncio.sleep(self.profile.timing.connect_settle_delay_s)
        except Exception as exc:
            raise UpstreamRequestError(str(exc), sent=False, timed_out=_timeout(exc)) from exc

    async def close(self) -> None:
        port, self.port = self.port, None
        opening, self._opening = self._opening, None
        transacting, self._transacting = self._transacting, None
        # A serial worker can outlive the caller's deadline. Close its port and
        # join it before the router is allowed to open another serial exchange.
        if opening is not None:
            try:
                port = await opening
            except Exception:
                pass
        if port is not None:
            try:
                await asyncio.to_thread(port.close)
            except Exception:
                pass
        if transacting is not None:
            try:
                await transacting
            except Exception:
                pass

    async def exchange(self, transaction_id: int, pdu: bytes) -> bytes:
        del transaction_id
        port = self.port
        if port is None:
            raise UpstreamRequestError("upstream is not connected", sent=False)
        sent = False
        response_pdu: bytes | None = None
        cancelled = Event()

        def transact() -> bytes:
            nonlocal sent
            port.reset_input_buffer()
            if cancelled.is_set():
                raise OSError("serial exchange cancelled before send")
            sent = True
            port.write(encode_rtu_adu(self.profile.upstream_unit_id, pdu))
            port.flush()
            return _read_rtu_serial(port)

        transacting = asyncio.create_task(asyncio.to_thread(transact))
        self._transacting = transacting
        try:
            frame = await asyncio.shield(transacting)
            try:
                response_pdu = decode_rtu_adu(frame, self.profile.upstream_unit_id)
            except ValueError as exc:
                raise ModbusResponseError(str(exc)) from exc
            validate_response_pdu(pdu, response_pdu)
            return response_pdu
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except Exception as exc:
            raise UpstreamRequestError(
                str(exc),
                sent=sent,
                timed_out=_timeout(exc),
                retryable=_transport_failure(exc),
                response_pdu=response_pdu,
            ) from exc
        finally:
            if transacting.done():
                self._transacting = None


def _timeout(error: BaseException) -> bool:
    return isinstance(error, TimeoutError) or "timeout" in type(error).__name__.casefold()


def _transport_failure(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            ModbusResponseError,
            TimeoutError,
            asyncio.IncompleteReadError,
            ConnectionError,
            OSError,
        ),
    )


async def _check_rtu_stream_boundary(
    reader: asyncio.StreamReader,
    *,
    before_request: bool,
) -> None:
    # Allow ready socket callbacks to deliver their bytes, then check without
    # adding a fixed wait to every Modbus request.
    await asyncio.sleep(0)
    try:
        async with asyncio.timeout(0):
            data = await reader.read(1)
    except TimeoutError:
        return
    if data:
        phase = "before request" if before_request else "after response"
        raise ModbusResponseError(f"unexpected RTU stream data {phase}")
    if before_request:
        raise ConnectionError("RTU connection closed before request")


async def _read_rtu_response(
    reader: asyncio.StreamReader,
    timeout: float,
) -> bytes:
    try:
        async with asyncio.timeout(timeout):
            return await _read_rtu_frame(reader)
    except TimeoutError as exc:
        raise TimeoutError("RTU response exceeded the configured timeout") from exc


async def _read_rtu_frame(reader: asyncio.StreamReader) -> bytes:
    prefix = await reader.readexactly(2)
    response_function = prefix[1]
    if response_function & 0x80:
        return prefix + await reader.readexactly(3)
    if response_function in {0x01, 0x02, 0x03, 0x04}:
        byte_count = await reader.readexactly(1)
        return prefix + byte_count + await reader.readexactly(byte_count[0] + 2)
    if response_function in {0x05, 0x06, 0x0F, 0x10}:
        return prefix + await reader.readexactly(6)
    chunks = [prefix]
    while True:
        try:
            chunk = await asyncio.wait_for(reader.read(256), 0.05)
        except TimeoutError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def _read_rtu_serial(port: Any) -> bytes:
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


def _backend(
    profile: ControllerProfile, address_cache: TcpAddressCache, *, resynchronize: bool
) -> UpstreamBackend:
    if profile.transport == TransportType.MODBUS_TCP:
        return ModbusTcpBackend(profile, address_cache)
    if profile.transport == TransportType.RTU_OVER_TCP:
        return RtuOverTcpBackend(profile, address_cache, resynchronize=resynchronize)
    return SerialRtuBackend(profile)


class UpstreamRouter:
    """Serialized request boundary with short-lived downstream client affinity."""

    def __init__(self, metrics: GatewayMetrics, trace: GatewayTrace) -> None:
        self.metrics = metrics
        self.trace = trace
        self._lock = asyncio.Lock()
        self._client_condition = asyncio.Condition()
        self._client_owner: int | None = None
        self._client_owner_active = False
        self._client_owner_last_completed_at = 0.0
        self._client_waiters: deque[int] = deque()
        self._client_waiter_ids: set[int] = set()
        self._backend: UpstreamBackend | None = None
        self._address_cache = TcpAddressCache()
        self._closing_backend: asyncio.Task[None] | None = None
        self._rtu_recovery_targets: set[tuple[str, int]] = set()
        self._fingerprint: tuple[object, ...] | None = None
        self._last_request_at = 0.0
        self._last_failure_at = 0.0
        self._connected_at = 0.0
        self._ever_connected = False

    async def close(self) -> None:
        self._begin_backend_close()
        closing = self._closing_backend
        if closing is not None:
            await asyncio.shield(closing)
            if self._closing_backend is closing:
                self._closing_backend = None

    def _begin_backend_close(self) -> None:
        backend, self._backend = self._backend, None
        if backend is not None:
            self._closing_backend = asyncio.create_task(backend.close())
        self._fingerprint = None
        self._connected_at = 0.0
        self.metrics.set("upstream_connected", False)

    def _fail_backend(self, profile: ControllerProfile) -> None:
        self._last_failure_at = monotonic()
        if profile.transport == TransportType.RTU_OVER_TCP:
            self._rtu_recovery_targets.add((profile.host, profile.port))
        self._begin_backend_close()

    async def request(
        self,
        *,
        client_id: int,
        transaction_id: int,
        downstream_unit_id: int,
        pdu: bytes,
        profile: ControllerProfile,
        forwarding_allowed: Callable[[], bool] | None = None,
    ) -> bytes:
        if forwarding_allowed is not None and not forwarding_allowed():
            raise UpstreamRequestError(
                "forwarding is disabled",
                sent=False,
                retryable=False,
            )
        self.metrics.increment("queue_depth")
        turn_acquired = False
        lock_acquired = False
        deadline = asyncio.get_running_loop().time() + profile.timing.total_request_timeout_s
        try:
            async with asyncio.timeout_at(deadline):
                try:
                    continues_sequence = await self._acquire_client_turn(
                        client_id,
                        profile.timing.client_burst_idle_s,
                    )
                    turn_acquired = True
                    await self._lock.acquire()
                    lock_acquired = True
                finally:
                    self.metrics.increment("queue_depth", -1)
                if forwarding_allowed is not None and not forwarding_allowed():
                    raise UpstreamRequestError(
                        "forwarding is disabled",
                        sent=False,
                        retryable=False,
                    )
                return await self._request_locked(
                    client_id=client_id,
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    pdu=pdu,
                    profile=profile,
                    deadline=deadline,
                    continues_sequence=continues_sequence,
                )
        except TimeoutError as exc:
            self.metrics.increment("timeouts")
            stage = "during upstream processing" if lock_acquired else "in the request queue"
            error = UpstreamRequestError(
                f"total request timeout {stage}",
                sent=lock_acquired,
                timed_out=True,
                retryable=False,
            )
            self.trace.emit(
                "UPSTREAM RX" if lock_acquired else "QUEUE TIMEOUT",
                client_id=client_id,
                transaction_id=transaction_id,
                downstream_unit_id=downstream_unit_id,
                upstream_unit_id=profile.upstream_unit_id,
                pdu=pdu,
                exception=error,
            )
            raise error from exc
        finally:
            if lock_acquired:
                self._lock.release()
            if turn_acquired:
                await self._complete_client_turn(client_id)

    async def release_client(self, client_id: int) -> None:
        """Release affinity immediately when a downstream connection closes."""
        async with self._client_condition:
            self._remove_waiter(client_id)
            if self._client_owner == client_id:
                self._client_owner = None
                self._client_owner_active = False
                self._client_owner_last_completed_at = 0.0
            self._client_condition.notify_all()

    async def _acquire_client_turn(self, client_id: int, idle_s: float) -> bool:
        """Acquire the turn and report whether the client is extending its current sequence."""
        async with self._client_condition:
            if self._client_owner != client_id:
                self._append_waiter(client_id)
            try:
                while True:
                    now = monotonic()
                    owner_idle = (
                        self._client_owner is not None
                        and not self._client_owner_active
                    )
                    if owner_idle and (
                        idle_s == 0
                        or now - self._client_owner_last_completed_at >= idle_s
                    ):
                        previous_owner = self._client_owner
                        self._client_owner = None
                        if previous_owner == client_id:
                            self._append_waiter(client_id)

                    if self._client_owner == client_id:
                        self._client_owner_active = True
                        return True

                    if self._client_owner is None:
                        self._append_waiter(client_id)
                        if self._client_waiters[0] == client_id:
                            self._client_waiters.popleft()
                            self._client_waiter_ids.remove(client_id)
                            self._client_owner = client_id
                            self._client_owner_active = True
                            return False

                    timeout: float | None = None
                    if self._client_owner is not None and not self._client_owner_active:
                        timeout = max(
                            0,
                            idle_s - (monotonic() - self._client_owner_last_completed_at),
                        )
                    if timeout is None:
                        await self._client_condition.wait()
                    else:
                        try:
                            await asyncio.wait_for(
                                self._client_condition.wait(),
                                timeout,
                            )
                        except TimeoutError:
                            pass
            except BaseException:
                self._remove_waiter(client_id)
                self._client_condition.notify_all()
                raise

    async def _complete_client_turn(self, client_id: int) -> None:
        async with self._client_condition:
            if self._client_owner == client_id:
                self._client_owner_active = False
                self._client_owner_last_completed_at = monotonic()
            self._client_condition.notify_all()

    def _append_waiter(self, client_id: int) -> None:
        if client_id not in self._client_waiter_ids:
            self._client_waiters.append(client_id)
            self._client_waiter_ids.add(client_id)

    def _remove_waiter(self, client_id: int) -> None:
        if client_id not in self._client_waiter_ids:
            return
        self._client_waiter_ids.remove(client_id)
        self._client_waiters.remove(client_id)

    async def _request_locked(
        self,
        *,
        client_id: int,
        transaction_id: int,
        downstream_unit_id: int,
        pdu: bytes,
        profile: ControllerProfile,
        deadline: float,
        continues_sequence: bool,
    ) -> bytes:
        kind = classify_pdu(pdu)
        max_retries = profile.retry.read_retries if kind == PduKind.READ else 0
        if kind == PduKind.WRITE:
            max_retries = profile.retry.write_retries
        for attempt in range(max_retries + 1):
            started: float | None = None
            try:
                await self._ensure_backend(profile, continues_sequence=continues_sequence)
                await self._pace(profile)
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError
                started = monotonic()
                self.trace.emit(
                    "UPSTREAM TX",
                    client_id=client_id,
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    upstream_unit_id=profile.upstream_unit_id,
                    pdu=pdu,
                    retry=attempt,
                )
                assert self._backend is not None
                try:
                    response = await self._backend.exchange(transaction_id, pdu)
                except asyncio.CancelledError:
                    self._fail_backend(profile)
                    raise
                self._last_request_at = monotonic()
                self.trace.emit(
                    "UPSTREAM RX",
                    client_id=client_id,
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    upstream_unit_id=profile.upstream_unit_id,
                    pdu=pdu,
                    response_pdu=response,
                    duration_ms=(monotonic() - started) * 1000,
                    retry=attempt,
                )
                return response
            except UpstreamRequestError as exc:
                if exc.timed_out:
                    self.metrics.increment("timeouts")
                self.trace.emit(
                    "UPSTREAM RX",
                    client_id=client_id,
                    transaction_id=transaction_id,
                    downstream_unit_id=downstream_unit_id,
                    upstream_unit_id=profile.upstream_unit_id,
                    pdu=pdu,
                    response_pdu=exc.response_pdu,
                    duration_ms=(monotonic() - started) * 1000 if started is not None else None,
                    retry=attempt,
                    exception=exc,
                )
                self._fail_backend(profile)
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

    async def _ensure_backend(
        self, profile: ControllerProfile, *, continues_sequence: bool
    ) -> None:
        fingerprint = profile.connection_fingerprint()
        rtu_target = (profile.host, profile.port)
        resynchronize = rtu_target in self._rtu_recovery_targets
        if self._fingerprint != fingerprint:
            await self.close()
            self._backend = _backend(profile, self._address_cache, resynchronize=resynchronize)
            self._fingerprint = fingerprint
        assert self._backend is not None
        if self._backend.connected:
            max_age = profile.timing.max_connection_age_s
            age = monotonic() - self._connected_at
            connection_expired = (
                profile.transport in {TransportType.MODBUS_TCP, TransportType.RTU_OVER_TCP}
                and max_age > 0
                and self._connected_at > 0
                and age >= max_age
            )
            if not connection_expired or continues_sequence:
                return
            logger.info(
                "Renewing upstream TCP connection between client sequences (age %.1f s)", age
            )
            await self.close()
            if profile.timing.reconnect_delay_s:
                await asyncio.sleep(profile.timing.reconnect_delay_s)
            self._backend = _backend(profile, self._address_cache, resynchronize=resynchronize)
            self._fingerprint = fingerprint
        since_failure = monotonic() - self._last_failure_at
        if self._last_failure_at and since_failure < profile.timing.reconnect_delay_s:
            await asyncio.sleep(profile.timing.reconnect_delay_s - since_failure)
        try:
            await self._backend.connect()
        except asyncio.CancelledError:
            self._fail_backend(profile)
            raise
        if profile.transport == TransportType.RTU_OVER_TCP:
            self._rtu_recovery_targets.discard(rtu_target)
        self._connected_at = monotonic()
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
