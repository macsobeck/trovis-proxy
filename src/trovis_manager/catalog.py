"""Load the firmware-specific register catalog kept in ``reference/``."""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path

from .models import DataPointDefinition


def default_matrix_path() -> Path:
    override = os.environ.get("TROVIS_MATRIX_PATH")
    if override:
        return Path(override)
    checkout = Path(__file__).resolve().parents[2] / "reference" / "fw309-register-matrix.json"
    if checkout.exists():
        return checkout
    return Path(str(files("trovis_manager").joinpath("data/fw309-register-matrix.json")))


class RegisterCatalog:
    def __init__(self, definitions: list[DataPointDefinition]) -> None:
        self._by_id = {definition.id: definition for definition in definitions}
        if len(self._by_id) != len(definitions):
            raise ValueError("duplicate data-point ID in register matrix")

    @classmethod
    def load(cls, path: Path | None = None) -> RegisterCatalog:
        payload = json.loads((path or default_matrix_path()).read_text(encoding="utf-8"))
        kinds = payload.get("value_kind_by_group", {})
        definitions: list[DataPointDefinition] = []
        for item in payload["data_points"]:
            enriched = dict(item)
            enriched.setdefault("value_kind", kinds.get(item["group"], "unknown"))
            definitions.append(DataPointDefinition.model_validate(enriched))
        return cls(definitions)

    def get(self, data_point_id: str) -> DataPointDefinition:
        try:
            return self._by_id[data_point_id]
        except KeyError as exc:
            raise KeyError(f"unknown data point: {data_point_id}") from exc

    def group(self, group: str) -> list[DataPointDefinition]:
        return [item for item in self._by_id.values() if item.group.casefold() == group.casefold()]

    def readable(self) -> list[DataPointDefinition]:
        return [item for item in self._by_id.values() if item.readable]

    @property
    def definitions(self) -> list[DataPointDefinition]:
        return list(self._by_id.values())
