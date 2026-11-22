"""Structured, side-aware Modbus trace logging without secret material."""

from __future__ import annotations

import json
import logging
from typing import Any

from .protocol import READ_FUNCTIONS, describe_pdu


class GatewayTrace:
    def __init__(self, enabled: bool = False, logger: logging.Logger | None = None) -> None:
        self.enabled = enabled
        self.logger = logger or logging.getLogger("trovis_gateway.modbus")

    def emit(
        self,
        direction: str,
        *,
        client_id: int,
        transaction_id: int,
        downstream_unit_id: int,
        upstream_unit_id: int | None,
        pdu: bytes,
        response_pdu: bytes | None = None,
        duration_ms: float | None = None,
        retry: int = 0,
        exception: BaseException | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "event": direction,
            "downstream_client_id": client_id,
            "transaction_id": transaction_id,
            "downstream_unit_id": downstream_unit_id,
            "upstream_unit_id": upstream_unit_id,
            **describe_pdu(pdu),
            "retry": retry,
        }
        if response_pdu:
            event["response_function_code"] = response_pdu[0]
            if len(response_pdu) >= 2 and response_pdu[0] in READ_FUNCTIONS:
                event["response_byte_count"] = response_pdu[1]
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms, 3)
        if exception is not None:
            event["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
            }
        if self.enabled:
            event["pdu_hex"] = (response_pdu if response_pdu is not None else pdu).hex()
            self.logger.info(json.dumps(event, separators=(",", ":"), default=str))
        elif exception is not None:
            self.logger.warning(json.dumps(event, separators=(",", ":"), default=str))
