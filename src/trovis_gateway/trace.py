"""Structured, side-aware Modbus trace logging without secret material."""

from __future__ import annotations

import json
import logging
from typing import Any

from .protocol import describe_pdu


class GatewayTrace:
    def __init__(self, enabled: bool = False, logger: logging.Logger | None = None) -> None:
        self.enabled = enabled
        self.logger = logger or logging.getLogger("trovis_gateway.modbus")

    def emit(
        self,
        direction: str,
        *,
        transaction_id: int,
        downstream_unit_id: int,
        upstream_unit_id: int | None,
        pdu: bytes,
        duration_ms: float | None = None,
        retry: int = 0,
        exception: BaseException | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "event": direction,
            "transaction_id": transaction_id,
            "downstream_unit_id": downstream_unit_id,
            "upstream_unit_id": upstream_unit_id,
            **describe_pdu(pdu),
            "retry": retry,
        }
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms, 3)
        if exception is not None:
            event["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
            }
        if self.enabled:
            event["pdu_hex"] = pdu.hex()
            self.logger.info(json.dumps(event, separators=(",", ":"), default=str))
        elif exception is not None:
            self.logger.warning(json.dumps(event, separators=(",", ":"), default=str))
