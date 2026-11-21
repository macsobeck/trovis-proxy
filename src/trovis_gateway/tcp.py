"""Explicit DNS resolution followed by a numeric TCP connection."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Sequence
from typing import Any

DNS_RESOLUTION_TIMEOUT_S = 10.0
AddressInfo = tuple[int, int, int, str, tuple[Any, ...]]


class DnsResolutionError(OSError):
    """The configured host could not be resolved to a TCP endpoint."""


class TcpConnectError(OSError):
    """All resolved TCP endpoints rejected or timed out the connection."""


async def open_tcp_connection(
    host: str,
    port: int,
    connect_timeout_s: float,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, str]:
    """Resolve *host* first, then connect without another hostname lookup."""
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
        raise TimeoutError(
            f"DNS resolution for {host} exceeded {DNS_RESOLUTION_TIMEOUT_S:g} seconds"
        ) from exc
    except Exception as exc:
        detail = str(exc) or type(exc).__name__
        raise DnsResolutionError(f"could not resolve {host}: {detail}") from exc

    endpoints = _unique_endpoints(addresses)
    if not endpoints:
        raise DnsResolutionError(f"no TCP address found for {host}")

    failures: list[str] = []
    errors: list[Exception] = []
    loop = asyncio.get_running_loop()
    for family, socktype, protocol, _, sockaddr in endpoints:
        target = _format_target(sockaddr)
        connection = socket.socket(family, socktype, protocol)
        connection.setblocking(False)
        try:
            await asyncio.wait_for(
                loop.sock_connect(connection, sockaddr),
                connect_timeout_s,
            )
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            reader, writer = await asyncio.open_connection(sock=connection)
            return reader, writer, target
        except Exception as exc:
            connection.close()
            errors.append(exc)
            detail = str(exc) or type(exc).__name__
            failures.append(f"{target}: {type(exc).__name__}: {detail}")

    message = f"could not connect to {host}:{port} via " + "; ".join(failures)
    if errors and all(isinstance(error, TimeoutError) for error in errors):
        raise TimeoutError(message) from errors[-1]
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
