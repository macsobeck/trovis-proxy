"""Transport-only controller reachability checks; no Modbus request is generated."""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from typing import Any

from .config import ControllerProfile, TransportType


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
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(profile.host, profile.port),
            profile.timing.connect_timeout_s,
        )
        return {
            "ok": True,
            "transport": profile.transport.value,
            "target": profile.target_label(),
            "upstream_unit_id": profile.upstream_unit_id,
            "latency_ms": round((monotonic() - started) * 1000, 3),
            "modbus_test": "not_performed",
            "detail": "TCP connection established; no Modbus request was sent.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "transport": profile.transport.value,
            "target": profile.target_label(),
            "upstream_unit_id": profile.upstream_unit_id,
            "latency_ms": round((monotonic() - started) * 1000, 3),
            "modbus_test": "not_performed",
            "detail": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
