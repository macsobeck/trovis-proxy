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


class ModbusResponseError(ValueError):
    """The upstream response cannot belong to the current request."""


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


def validate_response_pdu(request_pdu: bytes, response_pdu: bytes) -> None:
    """Validate the protocol fields that correlate a response with its request.

    Read responses do not contain the requested address, so this cannot prove correlation for two
    identical reads. It does detect the first function or shape mismatch in a shifted stream. The
    caller must then discard the connection before processing any further response.
    """
    if not request_pdu:
        raise ModbusResponseError("empty Modbus request PDU")
    if not response_pdu:
        raise ModbusResponseError("empty Modbus response PDU")

    request_function = request_pdu[0]
    response_function = response_pdu[0]
    exception_function = request_function | 0x80
    if response_function == exception_function:
        if len(response_pdu) != 2:
            raise ModbusResponseError("invalid Modbus exception response length")
        return
    if response_function != request_function:
        raise ModbusResponseError(
            "unexpected Modbus response function "
            f"0x{response_function:02X}; expected 0x{request_function:02X}"
        )

    if request_function in READ_FUNCTIONS:
        if len(request_pdu) < 5:
            raise ModbusResponseError("malformed Modbus read request")
        if len(response_pdu) < 2:
            raise ModbusResponseError("short Modbus read response")
        quantity = int.from_bytes(request_pdu[3:5], "big")
        expected_byte_count = (
            (quantity + 7) // 8 if request_function in {0x01, 0x02} else quantity * 2
        )
        byte_count = response_pdu[1]
        if byte_count != expected_byte_count:
            raise ModbusResponseError(
                "unexpected Modbus response byte count "
                f"{byte_count}; expected {expected_byte_count}"
            )
        if len(response_pdu) != byte_count + 2:
            raise ModbusResponseError("Modbus response length does not match byte count")
        return

    if request_function in {0x05, 0x06}:
        if len(request_pdu) < 5 or response_pdu != request_pdu[:5]:
            raise ModbusResponseError("Modbus single-write response does not echo request")
        return

    if request_function in {0x0F, 0x10} and (
        len(request_pdu) < 5
        or len(response_pdu) != 5
        or response_pdu[1:5] != request_pdu[1:5]
    ):
        raise ModbusResponseError("Modbus multiple-write response does not echo address and count")


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
