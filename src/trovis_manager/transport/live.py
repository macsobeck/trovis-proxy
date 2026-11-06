"""Optional adapter for ``modbus-connection`` TCP and serial backends."""

from __future__ import annotations

from typing import Any


class LiveTransport:
    def __init__(self, connection: Any, unit_id: int, transport_name: str) -> None:
        self._connection = connection
        self._unit = connection.for_unit(unit_id)
        self.unit_id = unit_id
        self.transport_name = transport_name

    @classmethod
    def tcp(
        cls,
        host: str,
        port: int,
        unit_id: int,
        timeout: float,
        connect_delay: float = 0.0,
    ) -> LiveTransport:
        try:
            from modbus_connection import ModbusTcpParams
            from modbus_connection.tmodbus import ModbusConnection
        except ImportError as exc:
            raise RuntimeError("install the 'live' extra for real Modbus access") from exc
        connection = ModbusConnection(
            ModbusTcpParams(host=host, port=port),
            timeout=timeout,
            connect_delay=connect_delay,
        )
        return cls(connection, unit_id, "tcp")

    @classmethod
    def serial(
        cls,
        device: str,
        unit_id: int,
        timeout: float,
        baudrate: int = 19200,
        connect_delay: float = 0.0,
    ) -> LiveTransport:
        try:
            from modbus_connection import ModbusSerialParams
            from modbus_connection.tmodbus import ModbusConnection
        except ImportError as exc:
            raise RuntimeError("install the 'live' extra for real Modbus access") from exc
        connection = ModbusConnection(
            ModbusSerialParams(device=device, baudrate=baudrate),
            timeout=timeout,
            connect_delay=connect_delay,
        )
        return cls(connection, unit_id, "serial")

    @classmethod
    def rtu_over_tcp(
        cls,
        host: str,
        port: int,
        unit_id: int,
        timeout: float,
        baudrate: int = 19200,
        connect_delay: float = 0.0,
    ) -> LiveTransport:
        """Use an RTU-framed serial stream exposed as ``socket://``."""
        try:
            from modbus_connection import ModbusSerialParams
            from modbus_connection.tmodbus import ModbusConnection
        except ImportError as exc:
            raise RuntimeError("install the 'live' extra for real Modbus access") from exc
        connection = ModbusConnection(
            ModbusSerialParams(
                device=f"socket://{host}:{port}",
                baudrate=baudrate,
            ),
            timeout=timeout,
            connect_delay=connect_delay,
        )
        return cls(connection, unit_id, "rtu-tcp")

    @property
    def connected(self) -> bool:
        return bool(self._connection.connected)

    async def connect(self) -> None:
        await self._connection.connect()

    async def disconnect(self) -> None:
        await self._connection.disconnect()

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        return await self._unit.read_holding_registers(address, count)

    async def read_coils(self, address: int, count: int) -> list[bool]:
        return await self._unit.read_coils(address, count)
