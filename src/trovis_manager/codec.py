"""Decode Modbus words according to register-matrix metadata."""

from __future__ import annotations

from typing import Any

from .models import DataPointDefinition


def decode_words(definition: DataPointDefinition, words: list[int]) -> tuple[Any, Any]:
    if not words:
        raise ValueError("empty Modbus response")
    raw: int | list[int]
    if definition.datatype == "uint32":
        if len(words) < 2:
            raise ValueError("uint32 requires two registers")
        raw = (words[0] << 16) | words[1]
    else:
        raw = words[0]
        if not 0 <= raw <= 0xFFFF:
            raise ValueError(f"word outside uint16 range: {raw}")

    if definition.sentinel is not None and raw == definition.sentinel:
        return raw, None
    if definition.datatype == "bool":
        return raw, bool(raw)
    if definition.datatype == "int16" or definition.signed:
        if raw >= 0x8000:
            raw -= 0x10000

    enum_value = definition.enum.get(str(raw))
    if enum_value is not None:
        return raw, enum_value
    value: Any = raw * definition.scale
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return raw, value
