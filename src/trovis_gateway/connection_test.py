"""Transport-only controller reachability checks; no Modbus request is generated."""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from typing import Any

from .config import ControllerProfile, TransportType
from .tcp import TcpConnectionTiming, open_tcp_connection


async def test_connection(profile: ControllerProfile) -> dict[str, Any]:
    started = monotonic()
    if profile.transport == TransportType.SERIAL_RTU:
        exists = Path(profile.serial.device).exists()
        return {
            "ok": exists,
            "transport": profile.transport.value,
            "target": profile.target_label(),
            "upstream_unit_id": profile.upstream_unit_id,
            "latency_ms": round((monotonic() - started) * 1000, 3),
            "modbus_test": "not_performed",
            "detail": (
                "Serial device exists; no protocol request was sent."
                if exists
                else "Serial device does not exist."
            ),
        }

    writer: asyncio.StreamWriter | None = None
    timing = TcpConnectionTiming()
    result: dict[str, Any] = {
        "transport": profile.transport.value,
        "target": profile.target_label(),
        "upstream_unit_id": profile.upstream_unit_id,
        "modbus_test": "not_performed",
    }
    try:
        _, writer, resolved_target = await open_tcp_connection(
            profile.host,
            profile.port,
            profile.timing.connect_timeout_s,
            address_preference=profile.address_preference,
            timing=timing,
        )
        result.update(
            ok=True,
            resolved_target=resolved_target,
            detail=(
                f"TCP connection established via {resolved_target}; "
                "no Modbus request was sent."
            ),
        )
    except Exception as exc:
        result.update(ok=False, detail=str(exc) or type(exc).__name__)
    finally:
        result["latency_ms"] = round((monotonic() - started) * 1000, 3)
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
    if timing.dns_ms is not None:
        result["dns_latency_ms"] = round(timing.dns_ms, 3)
    if timing.tcp_ms is not None:
        result["tcp_latency_ms"] = round(timing.tcp_ms, 3)
    return result
