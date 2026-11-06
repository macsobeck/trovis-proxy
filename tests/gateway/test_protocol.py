from __future__ import annotations

import asyncio
import unittest

from trovis_gateway.protocol import (
    PduKind,
    classify_pdu,
    decode_rtu_adu,
    encode_rtu_adu,
    encode_tcp_adu,
    read_tcp_adu,
)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_and_rtu_frames_round_trip(self) -> None:
        pdu = bytes.fromhex("0300100002")
        reader = asyncio.StreamReader()
        reader.feed_data(encode_tcp_adu(31, 7, pdu))
        reader.feed_eof()
        adu = await read_tcp_adu(reader)
        self.assertEqual((adu.transaction_id, adu.unit_id, adu.pdu), (31, 7, pdu))
        self.assertEqual(decode_rtu_adu(encode_rtu_adu(12, pdu), 12), pdu)

    async def test_known_and_vendor_functions_are_classified_without_parsing(self) -> None:
        self.assertEqual(classify_pdu(bytes.fromhex("0100000001")), PduKind.READ)
        self.assertEqual(classify_pdu(bytes.fromhex("1000000001020001")), PduKind.WRITE)
        self.assertEqual(classify_pdu(bytes.fromhex("41deadbeef")), PduKind.OTHER)
