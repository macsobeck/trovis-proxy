"""Golden-reference and repeated-snapshot comparisons."""

from __future__ import annotations

import json
import math
import os
from importlib.resources import files
from pathlib import Path
from typing import Any

from trovis_manager.catalog import RegisterCatalog
from trovis_manager.models import ConfigurationSnapshot

from .models import (
    ConsistencyRecord,
    ConsistencyStatus,
    GoldenComparisonRecord,
    GoldenStatus,
)


def _reference_path(name: str, environment_name: str) -> Path:
    override = os.environ.get(environment_name)
    if override:
        return Path(override)
    checkout = Path(__file__).resolve().parents[3] / "reference" / name
    if checkout.exists():
        return checkout
    return Path(str(files("trovis_manager").joinpath(f"data/{name}")))


def default_golden_path() -> Path:
    return _reference_path("fw309_anlage21.json", "TROVIS_GOLDEN_PATH")


def default_mapping_path() -> Path:
    return _reference_path("golden-comparison-map.json", "TROVIS_GOLDEN_MAP_PATH")


def _flatten(value: Any, prefix: str, result: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten(child, f"{prefix}.{key}" if prefix else key, result)
    else:
        result[prefix] = value


def flatten_golden(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    _flatten(payload["controller"], "controller", result)
    for co, section in payload["configuration_options"].items():
        for function in section["functions"]:
            base = f"configuration_options.{co}.functions.{function['function']}"
            result[f"{base}.state"] = function["state"]
            if "parameters" in function:
                _flatten(function["parameters"], f"{base}.parameters", result)
    _flatten(payload["parameters"], "parameters", result)
    for name, program in payload["time_programs"].items():
        result[f"time_programs.{name}"] = program
    _flatten(payload["observed_values"], "observed_values", result)
    return result


def _snapshot_values(snapshot: ConfigurationSnapshot) -> dict[str, Any]:
    values: dict[str, Any] = {
        "controller.model": snapshot.controller.model,
        "controller.firmware": snapshot.controller.firmware,
        "controller.hardware_version": snapshot.controller.hardware_version,
        "controller.serial_number": snapshot.controller.serial_number,
        "controller.serial_number_raw": snapshot.controller.serial_number_raw,
        "controller.system_code": snapshot.controller.system_code,
        "communication.station_address": snapshot.controller.modbus_unit_id,
    }
    for section in snapshot.configuration:
        for point in section.data_points:
            values[point.id] = point.value
    return values


def _equal(reference: Any, controller: Any) -> bool:
    if isinstance(controller, bool) and isinstance(reference, str):
        controller = "ON" if controller else "OFF"
    if isinstance(reference, (int, float)) and isinstance(controller, (int, float)):
        return math.isclose(float(reference), float(controller), rel_tol=0, abs_tol=1e-9)
    return reference == controller


def compare_to_golden(
    snapshot: ConfigurationSnapshot,
    catalog: RegisterCatalog,
    golden_path: Path | None = None,
    mapping_path: Path | None = None,
) -> list[GoldenComparisonRecord]:
    golden = flatten_golden(
        json.loads((golden_path or default_golden_path()).read_text(encoding="utf-8"))
    )
    mappings = json.loads(
        (mapping_path or default_mapping_path()).read_text(encoding="utf-8")
    )["mappings"]
    by_path = {item["golden_path"]: item["data_point_id"] for item in mappings}
    snapshot_values = _snapshot_values(snapshot)
    records: list[GoldenComparisonRecord] = []
    mapped_ids: set[str] = set()
    for path, reference in golden.items():
        data_point_id = by_path.get(path)
        if data_point_id is None:
            records.append(
                GoldenComparisonRecord(
                    parameter=path,
                    reference_value=reference,
                    status=GoldenStatus.NOT_MAPPED,
                    confidence="UNKNOWN",
                )
            )
            continue
        mapped_ids.add(data_point_id)
        definition = catalog.get(data_point_id)
        controller = snapshot_values.get(data_point_id)
        if definition.value_kind == "runtime":
            status = GoldenStatus.RUNTIME_ONLY
        elif controller is None:
            status = GoldenStatus.NOT_READABLE
        elif _equal(reference, controller):
            status = GoldenStatus.MATCH
        else:
            status = GoldenStatus.DIFFERENT
        causes: list[str] = []
        if status == GoldenStatus.DIFFERENT:
            causes = [
                "controller configuration changed",
                "register mapping or scaling is wrong",
                "firmware-specific semantics differ",
                "TROVIS-VIEW reference is stale",
            ]
        records.append(
            GoldenComparisonRecord(
                parameter=path,
                data_point_id=data_point_id,
                reference_value=reference,
                controller_value=controller,
                status=status,
                confidence=definition.confidence,
                possible_causes=causes,
            )
        )
    for definition in catalog.definitions:
        if definition.id not in mapped_ids:
            controller = snapshot_values.get(definition.id)
            status = (
                GoldenStatus.RUNTIME_ONLY
                if definition.value_kind == "runtime"
                else GoldenStatus.NOT_MAPPED
            )
            records.append(
                GoldenComparisonRecord(
                    parameter=definition.id,
                    data_point_id=definition.id,
                    controller_value=controller,
                    status=status,
                    confidence=definition.confidence,
                )
            )
    return records


def _point_values(snapshot: ConfigurationSnapshot) -> dict[str, Any]:
    return _snapshot_values(snapshot)


def compare_snapshots(
    snapshots: list[ConfigurationSnapshot], catalog: RegisterCatalog
) -> list[ConsistencyRecord]:
    maps = [_point_values(snapshot) for snapshot in snapshots]
    records: list[ConsistencyRecord] = []
    for definition in catalog.definitions:
        values = [mapping.get(definition.id) for mapping in maps]
        if not snapshots or any(value is None for value in values):
            status = ConsistencyStatus.UNREADABLE
        elif all(_equal(values[0], value) for value in values[1:]):
            status = ConsistencyStatus.STABLE
        elif definition.value_kind == "runtime":
            status = ConsistencyStatus.CHANGED_EXPECTED
        elif definition.value_kind == "configuration":
            status = ConsistencyStatus.INCONSISTENT
        else:
            status = ConsistencyStatus.UNKNOWN
        records.append(
            ConsistencyRecord(
                data_point_id=definition.id,
                label=definition.label,
                value_kind=definition.value_kind,
                status=status,
                values=values,
            )
        )
    for schedule_id, label in (
        ("rk1.schedule", "Heating schedule"),
        ("dhw.schedule", "DHW schedule"),
        ("circulation.schedule", "Circulation schedule"),
    ):
        values: list[Any] = []
        for snapshot in snapshots:
            found = None
            for section in snapshot.configuration:
                for program in section.time_programs:
                    if program.id == schedule_id:
                        found = program.model_dump(mode="json")
            values.append(found)
        if not snapshots or any(value is None for value in values):
            status = ConsistencyStatus.UNREADABLE
        elif all(value == values[0] for value in values[1:]):
            status = ConsistencyStatus.STABLE
        else:
            status = ConsistencyStatus.INCONSISTENT
        records.append(
            ConsistencyRecord(
                data_point_id=schedule_id,
                label=label,
                value_kind="configuration",
                status=status,
                values=values,
            )
        )
    return records
