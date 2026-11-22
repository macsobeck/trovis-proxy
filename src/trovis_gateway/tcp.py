"""Explicit DNS resolution followed by a numeric TCP connection."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from itertools import zip_longest
from typing import Any

from .config import AddressPreference

DNS_RESOLUTION_TIMEOUT_S = 10.0
ADDRESS_FALLBACK_DELAY_S = 0.3
DNS_REFRESH_INTERVAL_S = 60.0
DNS_CACHE_MAX_AGE_S = 120.0
DNS_REFRESH_RETRY_S = 10.0
AddressInfo = tuple[int, int, int, str, tuple[Any, ...]]

logger = logging.getLogger(__name__)


class DnsResolutionError(OSError):
    """The configured host could not be resolved to a TCP endpoint."""


class DnsResolutionTimeout(DnsResolutionError, TimeoutError):
    """The deadline expired while resolving the configured host."""


class TcpConnectError(OSError):
    """All resolved TCP endpoints rejected or timed out the connection."""


class TcpConnectTimeout(TcpConnectError, TimeoutError):
    """The available TCP connection time was used up."""


@dataclass
class TcpConnectionTiming:
    dns_ms: float | None = None
    tcp_ms: float | None = None


class TcpAddressCache:
    """Share DNS results across reconnects for one active controller."""

    def __init__(self) -> None:
        self._target: tuple[str, int] | None = None
        self._addresses: list[AddressInfo] = []
        self._refresh_at = 0.0
        self._expires_at = 0.0
        self._lookup: asyncio.Task[list[AddressInfo]] | None = None

    async def get(
        self, host: str, port: int, *, failed: list[AddressInfo] | None = None
    ) -> tuple[list[AddressInfo], bool]:
        target = (host, port)
        if target != self._target:
            if self._lookup is not None:
                self._lookup.cancel()
            self._target = target
            self._addresses = []
            self._lookup = None
        now = asyncio.get_running_loop().time()
        if failed is self._addresses:
            self._addresses = []
        if self._addresses and now < self._expires_at:
            if now >= self._refresh_at and self._lookup is None:
                self._start_lookup(host, port)
            return self._addresses, True
        lookup = self._lookup or self._start_lookup(host, port)
        return await asyncio.shield(lookup), False

    def _start_lookup(self, host: str, port: int) -> asyncio.Task[list[AddressInfo]]:
        task = asyncio.create_task(_resolve_addresses(host, port))
        task.add_done_callback(self._finish_lookup)
        self._lookup = task
        return task

    def _finish_lookup(self, task: asyncio.Task[list[AddressInfo]]) -> None:
        if task is not self._lookup:
            if not task.cancelled():
                task.exception()
            return
        self._lookup = None
        now = asyncio.get_running_loop().time()
        try:
            self._addresses = task.result()
        except asyncio.CancelledError:
            return
        except OSError:
            self._refresh_at = now + DNS_REFRESH_RETRY_S
        else:
            self._refresh_at = now + DNS_REFRESH_INTERVAL_S
            self._expires_at = now + DNS_CACHE_MAX_AGE_S


async def open_tcp_connection(
    host: str,
    port: int,
    connect_timeout_s: float,
    *,
    address_preference: AddressPreference = "system",
    address_cache: TcpAddressCache | None = None,
    timing: TcpConnectionTiming | None = None,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, str]:
    """Resolve and open one upstream connection within a shared deadline."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + connect_timeout_s
    if timing is None:
        timing = TcpConnectionTiming()

    async def resolve(
        failed: list[AddressInfo] | None = None,
    ) -> tuple[list[AddressInfo], bool]:
        started = loop.time()
        cached = False
        try:
            async with asyncio.timeout_at(deadline):
                if address_cache is None:
                    return await _resolve_addresses(host, port), False
                addresses, cached = await address_cache.get(host, port, failed=failed)
                return addresses, cached
        except TimeoutError as exc:
            raise DnsResolutionTimeout(f"DNS resolution for {host} timed out") from exc
        finally:
            elapsed_ms = (loop.time() - started) * 1000
            timing.dns_ms = (timing.dns_ms or 0) + elapsed_ms
            logger.debug("DNS lookup for %s took %.3f ms (cached=%s)", host, elapsed_ms, cached)

    async def connect(
        tcp_deadline: float,
        addresses: list[AddressInfo],
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, str]:
        started = loop.time()
        try:
            return await _connect_addresses(host, port, tcp_deadline, address_preference, addresses)
        finally:
            timing.tcp_ms = (timing.tcp_ms or 0) + (loop.time() - started) * 1000

    literal = _numeric_address(host, port)
    if literal is not None:
        return await connect(deadline, [literal])

    addresses, cached = await resolve()
    if not cached:
        return await connect(deadline, addresses)

    # Leave time to re-resolve and connect if a cached address has gone away.
    cached_deadline = (loop.time() + deadline) / 2
    try:
        return await connect(cached_deadline, addresses)
    except TcpConnectError as exc:
        refreshed, _ = await resolve(failed=addresses)
        if refreshed == addresses and not isinstance(exc, TcpConnectTimeout):
            raise
        return await connect(deadline, refreshed)


def _numeric_address(host: str, port: int) -> AddressInfo | None:
    try:
        address = ip_address(host)
    except ValueError:
        return None
    if isinstance(address, IPv6Address):
        ip, _, scope = host.partition("%")
        scope_id = 0
        try:
            if scope:
                scope_id = int(scope) if scope.isdecimal() else socket.if_nametoindex(scope)
        except OSError as exc:
            raise TcpConnectError(f"TCP connection to [{host}]:{port}: {exc}") from exc
        sockaddr = (ip, port, 0, scope_id)
        return (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (host, port))


async def _resolve_addresses(host: str, port: int) -> list[AddressInfo]:
    try:
        addresses = await asyncio.wait_for(
            asyncio.to_thread(
                socket.getaddrinfo,
                host,
                port,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
            ),
            DNS_RESOLUTION_TIMEOUT_S,
        )
    except TimeoutError as exc:
        raise DnsResolutionTimeout(
            f"DNS resolution for {host} exceeded {DNS_RESOLUTION_TIMEOUT_S:g} seconds"
        ) from exc
    except OSError as exc:
        detail = str(exc) or type(exc).__name__
        raise DnsResolutionError(f"could not resolve {host}: {detail}") from exc

    endpoints = _unique_endpoints(addresses)
    if not endpoints:
        raise DnsResolutionError(f"no TCP address found for {host}")
    return endpoints


async def _connect_addresses(
    host: str,
    port: int,
    deadline: float,
    address_preference: AddressPreference,
    addresses: list[AddressInfo],
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, str]:
    preferred_family = {"ipv4": socket.AF_INET, "ipv6": socket.AF_INET6}.get(
        address_preference, addresses[0][0]
    )
    preferred = [address for address in addresses if address[0] == preferred_family]
    alternate = [address for address in addresses if address[0] != preferred_family]
    endpoints = [
        address
        for pair in zip_longest(preferred, alternate)
        for address in pair
        if address is not None
    ]

    failures: list[str] = []
    errors: list[Exception] = []
    loop = asyncio.get_running_loop()
    for index, (family, socktype, protocol, _, sockaddr) in enumerate(endpoints):
        target = _format_target(sockaddr)
        started = loop.time()
        if started >= deadline:
            break
        # Share the remaining budget so later addresses still get a chance.
        timeout_s = (deadline - started) / (len(endpoints) - index)
        if index + 1 < len(endpoints) and endpoints[index + 1][0] != family:
            timeout_s = min(timeout_s, ADDRESS_FALLBACK_DELAY_S)
        connection: socket.socket | None = None
        try:
            connection = socket.socket(family, socktype, protocol)
            connection.setblocking(False)
            async with asyncio.timeout_at(min(started + timeout_s, deadline)):
                await loop.sock_connect(connection, sockaddr)
                connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                reader, writer = await asyncio.open_connection(sock=connection)
            connection = None  # Ownership has transferred to the stream.
            logger.debug(
                "TCP connection to %s established in %.3f ms",
                target, (loop.time() - started) * 1000,
            )
            return reader, writer, target
        except OSError as exc:
            errors.append(exc)
            detail = str(exc) or type(exc).__name__
            failures.append(f"{target}: {detail}")
            logger.debug(
                "TCP connection to %s failed after %.3f ms (%s)",
                target, (loop.time() - started) * 1000, detail,
            )
        finally:
            if connection is not None:
                connection.close()

    message = f"TCP connection to {_format_target((host, port))}"
    if failures:
        message += " failed via " + "; ".join(failures)
    if loop.time() >= deadline or all(isinstance(error, TimeoutError) for error in errors):
        raise TcpConnectTimeout(f"{message} (TCP timeout)") from (errors[-1] if errors else None)
    raise TcpConnectError(message) from errors[-1]


def _unique_endpoints(addresses: Sequence[AddressInfo]) -> list[AddressInfo]:
    unique: list[AddressInfo] = []
    seen: set[tuple[int, tuple[Any, ...]]] = set()
    for address in addresses:
        key = (address[0], address[4])
        if key in seen:
            continue
        seen.add(key)
        unique.append(address)
    return unique


def _format_target(sockaddr: tuple[Any, ...]) -> str:
    host, port = str(sockaddr[0]), int(sockaddr[1])
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
