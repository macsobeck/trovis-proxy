"""Device-neutral Modbus framing and PDU classification."""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass
from enum import StrEnum

MAX_MODBUS_PDU = 253


class PduKind(StrEnum):
    READ = "read"
    WRITE = "write"
    OTHER = "other"


READ_FUNCTIONS = frozenset({0x01, 0x02, 0x03, 0x04})
WRITE_FUNCTIONS = frozenset({0x05, 0x06, 0x0F, 0x10})


@dataclass(frozen=True, slots=True)
class ModbusTcpAdu:
    transaction_id: int
    unit_id: int
    pdu: bytes

    @property
    def function_code(self) -> int:
        return self.pdu[0]

    def encode(self, *, unit_id: int | None = None, pdu: bytes | None = None) -> bytes:
        actual_unit = self.unit_id if unit_id is None else unit_id
        actual_pdu = self.pdu if pdu is None else pdu
        return encode_tcp_adu(self.transaction_id, actual_unit, actual_pdu)


def classify_pdu(pdu: bytes) -> PduKind:
    if not pdu:
        return PduKind.OTHER
    if pdu[0] in READ_FUNCTIONS:
        return PduKind.READ
    if pdu[0] in WRITE_FUNCTIONS:
        return PduKind.WRITE
    return PduKind.OTHER


def describe_pdu(pdu: bytes) -> dict[str, int | str | None]:
    function_code = pdu[0] if pdu else None
    address = None
    count = None
    if len(pdu) >= 5 and function_code in READ_FUNCTIONS | WRITE_FUNCTIONS:
        address = int.from_bytes(pdu[1:3], "big")
        count = int.from_bytes(pdu[3:5], "big")
    return {
        "function_code": function_code,
        "kind": classify_pdu(pdu).value,
        "address": address,
        "count_or_value": count,
    }


def encode_tcp_adu(transaction_id: int, unit_id: int, pdu: bytes) -> bytes:
    if not pdu or len(pdu) > MAX_MODBUS_PDU:
        raise ValueError("invalid Modbus PDU length")
    return struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1, unit_id) + pdu


async def read_tcp_adu(reader: asyncio.StreamReader) -> ModbusTcpAdu:
    header = await reader.readexactly(7)
    transaction_id, protocol_id, length, unit_id = struct.unpack(">HHHB", header)
    if protocol_id != 0:
        raise ValueError("unsupported Modbus protocol identifier")
    if length < 2 or length > MAX_MODBUS_PDU + 1:
        raise ValueError("invalid Modbus TCP length")
    pdu = await reader.readexactly(length - 1)
    return ModbusTcpAdu(transaction_id=transaction_id, unit_id=unit_id, pdu=pdu)


def exception_pdu(request_pdu: bytes, exception_code: int) -> bytes:
    function_code = request_pdu[0] if request_pdu else 0
    return bytes((function_code | 0x80, exception_code))


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def encode_rtu_adu(unit_id: int, pdu: bytes) -> bytes:
    payload = bytes((unit_id,)) + pdu
    return payload + crc16(payload).to_bytes(2, "little")


def decode_rtu_adu(frame: bytes, expected_unit_id: int) -> bytes:
    if len(frame) < 5:
        raise ValueError("short Modbus RTU frame")
    payload, received_crc = frame[:-2], int.from_bytes(frame[-2:], "little")
    if crc16(payload) != received_crc:
        raise ValueError("invalid Modbus RTU CRC")
    if payload[0] != expected_unit_id:
        raise ValueError("unexpected Modbus RTU unit ID")
    return payload[1:]
