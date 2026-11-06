"""Narrow read-only transport contract; deliberately contains no write method."""

from __future__ import annotations

from typing import Protocol


class Transport(Protocol):
    @property
    def connected(self) -> bool: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def read_holding_registers(self, address: int, count: int) -> list[int]: ...

    async def read_coils(self, address: int, count: int) -> list[bool]: ...
