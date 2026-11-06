"""Atomic JSON snapshot persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from trovis_manager.models import ConfigurationSnapshot


def _atomic_write_text(payload: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            if not payload.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def save_snapshot(snapshot: ConfigurationSnapshot, path: Path) -> None:
    _atomic_write_text(snapshot.model_dump_json(indent=2), path)


def save_json_document(payload: object, path: Path) -> None:
    _atomic_write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        path,
    )


def load_snapshot(path: Path) -> ConfigurationSnapshot:
    return ConfigurationSnapshot.model_validate(json.loads(path.read_text(encoding="utf-8")))
