from __future__ import annotations

import unittest

from trovis_manager.codec import decode_words
from trovis_manager.models import DataPointDefinition, TransportAddress


def definition(**overrides: object) -> DataPointDefinition:
    values: dict[str, object] = {
        "id": "test.value",
        "label": "Test",
        "group": "Test",
        "transport": TransportAddress(type="holding_register", address=0),
        "datatype": "uint16",
    }
    values.update(overrides)
    return DataPointDefinition.model_validate(values)


class CodecTests(unittest.TestCase):
    def test_unsigned_scaling(self) -> None:
        raw, value = decode_words(definition(scale=0.1), [195])
        self.assertEqual(raw, 195)
        self.assertEqual(value, 19.5)

    def test_signed_value(self) -> None:
        raw, value = decode_words(definition(datatype="int16", signed=True, scale=0.1), [0xFFCE])
        self.assertEqual(raw, -50)
        self.assertEqual(value, -5)

    def test_enum(self) -> None:
        raw, value = decode_words(definition(enum={"2": "standby"}), [2])
        self.assertEqual(raw, 2)
        self.assertEqual(value, "standby")

    def test_sentinel(self) -> None:
        self.assertEqual(decode_words(definition(sentinel=0x7FFF), [0x7FFF]), (0x7FFF, None))

    def test_uint32(self) -> None:
        self.assertEqual(
            decode_words(definition(datatype="uint32"), [0x0003, 0xB5EB]),
            (243179, 243179),
        )
