"""Read definitions through a connection manager and build stable snapshots."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from trovis_manager.catalog import RegisterCatalog
from trovis_manager.codec import decode_words
from trovis_manager.models import (
    CommunicationError,
    ConfigurationSection,
    ConfigurationSnapshot,
    ControllerIdentity,
    DataPoint,
    DataPointDefinition,
    ReadResult,
    SnapshotStatus,
    TimeProgram,
)
from trovis_manager.transport.connection import ConnectionManager


class FirmwareMismatchError(RuntimeError):
    pass


def _count(definition: DataPointDefinition) -> int:
    return 2 if definition.datatype == "uint32" else 1


class ConfigurationService:
    def __init__(self, manager: ConnectionManager, catalog: RegisterCatalog) -> None:
        self.manager = manager
        self.catalog = catalog

    async def identify(self) -> ControllerIdentity:
        model = await self.read("controller.model")
        firmware = await self.read("controller.firmware")
        system = await self.read("controller.system_code")
        unit = await self.read("communication.station_address")
        hardware = await self.read("controller.hardware_version")
        serial = await self.read("controller.serial_number")
        serial_raw = await self.read("controller.serial_number_raw")
        values = [model, firmware, system, unit]
        if any(not result.successful for result in values):
            failure = next(result.error for result in values if result.error is not None)
            raise RuntimeError(f"controller identification failed: {failure.message}")
        assert model.data_point and firmware.data_point and system.data_point and unit.data_point
        firmware_number = float(firmware.data_point.value)
        return ControllerIdentity(
            model=str(model.data_point.value),
            firmware=f"{firmware_number:05.2f}.00",
            hardware_version=(
                str(hardware.data_point.value)
                if hardware.successful and hardware.data_point is not None
                else None
            ),
            serial_number=(
                str(serial.data_point.value)
                if serial.successful and serial.data_point is not None
                else getattr(self.manager.transport, "serial_number_override", None)
            ),
            serial_number_raw=(
                int(serial_raw.data_point.value)
                if serial_raw.successful and serial_raw.data_point is not None
                else None
            ),
            system_code=f"{float(system.data_point.value):.1f}",
            modbus_unit_id=int(unit.data_point.value),
        )

    async def read(self, data_point_id: str) -> ReadResult:
        definition = self.catalog.get(data_point_id)
        if not definition.readable or definition.transport.address is None:
            return ReadResult(
                error=CommunicationError(
                    operation="read",
                    data_point_id=definition.id,
                    kind="not_readable",
                    message="no verified read mapping is available",
                )
            )
        try:
            if definition.transport.type == "coil":
                raw_bits = await self.manager.read_coils(definition.transport.address, 1)
                raw, value = int(raw_bits[0]), bool(raw_bits[0])
                function_code = 1
            else:
                words = await self.manager.read_holding_registers(
                    definition.transport.address, _count(definition)
                )
                raw, value = decode_words(definition, words)
                function_code = 3
            self.manager.annotate_last_trace(
                function_code=function_code,
                address=definition.transport.address,
                count=_count(definition),
                decoded_response={definition.id: value},
            )
            return ReadResult(data_point=self._point(definition, raw, value))
        except Exception as exc:
            return ReadResult(
                error=CommunicationError(
                    operation="read",
                    data_point_id=definition.id,
                    kind=type(exc).__name__,
                    message=str(exc),
                    attempts=self.manager.settings.retries + 1,
                )
            )

    async def read_group(self, group: str) -> list[ReadResult]:
        definitions = [item for item in self.catalog.group(group) if item.readable]
        results: dict[str, ReadResult] = {}
        for block in self._safe_blocks(definitions):
            await self._read_block(block, results)
        return [results[item.id] for item in definitions]

    @staticmethod
    def _safe_blocks(
        definitions: Iterable[DataPointDefinition], max_registers: int = 50
    ) -> list[list[DataPointDefinition]]:
        ordered = sorted(
            (item for item in definitions if item.transport.address is not None),
            key=lambda item: (item.transport.type, item.transport.address or 0),
        )
        blocks: list[list[DataPointDefinition]] = []
        for definition in ordered:
            if not blocks:
                blocks.append([definition])
                continue
            prior = blocks[-1][-1]
            start = blocks[-1][0].transport.address or 0
            prior_end = (prior.transport.address or 0) + _count(prior)
            current = definition.transport.address or 0
            same_space = definition.transport.type == prior.transport.type
            within_limit = current + _count(definition) - start <= max_registers
            if same_space and current == prior_end and within_limit:
                blocks[-1].append(definition)
            else:
                blocks.append([definition])
        return blocks

    async def _read_block(
        self, block: list[DataPointDefinition], results: dict[str, ReadResult]
    ) -> None:
        if len(block) == 1:
            results[block[0].id] = await self.read(block[0].id)
            return
        start = block[0].transport.address
        assert start is not None
        end = (block[-1].transport.address or 0) + _count(block[-1])
        try:
            if block[0].transport.type == "coil":
                raw_values = await self.manager.read_coils(start, end - start)
            else:
                raw_values = await self.manager.read_holding_registers(start, end - start)
            decoded: dict[str, object] = {}
            for definition in block:
                offset = (definition.transport.address or start) - start
                if definition.transport.type == "coil":
                    raw, value = int(raw_values[offset]), bool(raw_values[offset])
                else:
                    words = raw_values[offset : offset + _count(definition)]
                    raw, value = decode_words(definition, words)
                results[definition.id] = ReadResult(
                    data_point=self._point(definition, raw, value)
                )
                decoded[definition.id] = value
            self.manager.annotate_last_trace(
                function_code=1 if block[0].transport.type == "coil" else 3,
                address=start,
                count=end - start,
                decoded_response=decoded,
            )
        except Exception:
            # A failed block is retried point-by-point to preserve a partial snapshot.
            for definition in block:
                results[definition.id] = await self.read(definition.id)

    @staticmethod
    def _point(definition: DataPointDefinition, raw: object, value: object) -> DataPoint:
        return DataPoint(
            id=definition.id,
            label=definition.label,
            group=definition.group,
            co=definition.co,
            function=definition.function,
            value=value,
            raw_value=raw,
            datatype=definition.datatype,
            scale=definition.scale,
            unit=definition.unit,
            minimum=definition.minimum,
            maximum=definition.maximum,
            enum=definition.enum,
            readable=definition.readable,
            writable=definition.writable,
            active=None,
            source=definition.source,
            confidence=definition.confidence,
            value_kind=definition.value_kind,
        )

    async def read_config(
        self,
        expected_firmware: str = "03.09",
        identity: ControllerIdentity | None = None,
    ) -> ConfigurationSnapshot:
        identity = identity or await self.identify()
        errors: list[CommunicationError] = []
        if not identity.firmware.startswith(expected_firmware):
            errors.append(
                CommunicationError(
                    operation="identify",
                    kind=FirmwareMismatchError.__name__,
                    message=f"expected FW {expected_firmware}.xx, got {identity.firmware}",
                )
            )
        sections: list[ConfigurationSection] = []
        grouped: dict[str, list[DataPointDefinition]] = defaultdict(list)
        for definition in self.catalog.readable():
            if definition.group != "Controller":
                grouped[definition.group].append(definition)
        time_programs: list[TimeProgram] = getattr(self.manager.transport, "time_programs", [])
        for group in grouped:
            group_results = await self.read_group(group)
            points = [
                result.data_point
                for result in group_results
                if result.data_point is not None
            ]
            errors.extend(result.error for result in group_results if result.error is not None)
            programs = [
                program
                for program in time_programs
                if program.id.startswith(group.casefold())
            ]
            if group == "Zirkulation":
                programs = [
                    program
                    for program in time_programs
                    if program.id.startswith("circulation")
                ]
            sections.append(
                ConfigurationSection(
                    id=group.casefold().replace(" ", "_"),
                    label=group,
                    data_points=points,
                    time_programs=programs,
                )
            )
        circulation = [
            program for program in time_programs if program.id.startswith("circulation")
        ]
        if circulation:
            sections.append(
                ConfigurationSection(
                    id="circulation",
                    label="Zirkulation",
                    time_programs=circulation,
                )
            )
        return ConfigurationSnapshot(
            controller=identity,
            firmware=identity.firmware,
            serial_number=identity.serial_number,
            system_code=identity.system_code,
            modbus_unit_id=identity.modbus_unit_id,
            status=SnapshotStatus.PARTIAL if errors else SnapshotStatus.COMPLETE,
            configuration=sections,
            errors=errors,
        )
