"""In-memory FW 3.09 controller with deterministic failure injection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


class MockModbusException(RuntimeError):
    pass


class MockConnectionLoss(ConnectionError):
    pass


@dataclass(slots=True)
class MockFailurePlan:
    timeouts: int = 0
    connection_losses: int = 0
    exception_addresses: set[int] = field(default_factory=set)
    missing_addresses: set[int] = field(default_factory=set)


class MockTransport:
    def __init__(
        self,
        holding: dict[int, int] | None = None,
        coils: dict[int, bool] | None = None,
        failures: MockFailurePlan | None = None,
    ) -> None:
        self.holding = holding or {}
        self.coils = coils or {}
        self.failures = failures or MockFailurePlan()
        self._connected = False
        self.unit_id = 247
        self.transport_name = "mock"
        self.read_calls: list[tuple[str, int, int]] = []

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def _before_read(self, address: int) -> None:
        if not self._connected:
            raise MockConnectionLoss("mock connection is closed")
        if self.failures.timeouts:
            self.failures.timeouts -= 1
            await asyncio.sleep(3600)
        if self.failures.connection_losses:
            self.failures.connection_losses -= 1
            self._connected = False
            raise MockConnectionLoss("injected connection loss")
        if address in self.failures.exception_addresses:
            raise MockModbusException(f"injected Modbus exception at address {address}")

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        self.read_calls.append(("holding_register", address, count))
        await self._before_read(address)
        values: list[int] = []
        for current in range(address, address + count):
            if current in self.failures.missing_addresses or current not in self.holding:
                raise MockModbusException(f"illegal data address {current}")
            values.append(self.holding[current])
        return values

    async def read_coils(self, address: int, count: int) -> list[bool]:
        self.read_calls.append(("coil", address, count))
        await self._before_read(address)
        values: list[bool] = []
        for current in range(address, address + count):
            if current in self.failures.missing_addresses or current not in self.coils:
                raise MockModbusException(f"illegal data address {current}")
            values.append(self.coils[current])
        return values
