"""FW 03.09.00 / system 2.1 mock values from the Golden Sample."""

from __future__ import annotations

from trovis_manager.models import Confidence, TimeInterval, TimeProgram
from trovis_manager.transport.mock import MockFailurePlan, MockTransport


def _daily(program_id: str, label: str, start: str, end: str) -> TimeProgram:
    interval = [TimeInterval(start=start, end=end)]
    return TimeProgram(
        id=program_id,
        label=label,
        days={day: interval for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
        source=["golden-pdf", "tro55xx-correlation"],
        confidence=Confidence.VERIFIED,
    )


def golden_mock_transport(failures: MockFailurePlan | None = None) -> MockTransport:
    transport = MockTransport(
        holding={
            0: 55731,
            1: 21,
            2: 309,
            3: 110,
            5: 12345,
            9: 64,
            12: 411,
            16: 311,
            22: 483,
            142: 247,
            1000: 700,
            1001: 300,
            1002: 195,
            1003: 170,
            1005: 10,
            1006: 0,
            1008: 12,
            1009: 0,
            1010: 650,
            1011: 650,
            1064: 2,
            1065: 130,
            1066: 25,
            1067: 0,
            1799: 540,
            1800: 550,
            1801: 230,
            1802: 80,
            1803: 250,
            1804: 40,
            1806: 400,
            1827: 630,
        },
        coils={1024: False, 1025: True, 1026: True, 1035: True},
        failures=failures,
    )
    # The upstream single-register serial mapping cannot encode 243179. Keep
    # that Golden value as mock metadata until the live width is verified.
    transport.serial_number_override = "243179"  # type: ignore[attr-defined]
    transport.time_programs = [  # type: ignore[attr-defined]
        _daily("rk1.schedule", "Heizkreis Rk1", "06:15", "22:45"),
        _daily("dhw.schedule", "Trinkwasser", "05:00", "06:30"),
        _daily("circulation.schedule", "Zirkulationspumpe", "00:00", "24:00"),
    ]
    return transport
