"""Atomic, permission-restricted profile persistence with secret redaction."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from .config import ControllerProfile, GatewayConfig


def _profile_storage(profile: ControllerProfile) -> dict[str, Any]:
    payload = profile.model_dump(mode="json", exclude={"access_key"})
    payload["access_key"] = (
        profile.access_key.get_secret_value() if profile.access_key is not None else None
    )
    return payload


def public_profile(profile: ControllerProfile) -> dict[str, Any]:
    payload = profile.model_dump(mode="json", exclude={"access_key"})
    payload["access_key"] = ""
    payload["access_key_configured"] = bool(
        profile.access_key and profile.access_key.get_secret_value()
    )
    return payload


class ConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._config = GatewayConfig()

    def load(self) -> GatewayConfig:
        with self._lock:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                self._config = GatewayConfig.model_validate(payload)
            return self.snapshot()

    def snapshot(self) -> GatewayConfig:
        with self._lock:
            return GatewayConfig.model_validate(self._config.model_dump())

    def public_document(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": self._config.schema_version,
                "active_profile_id": self._config.active_profile_id,
                "profiles": [public_profile(profile) for profile in self._config.profiles],
            }

    def active_profile(self) -> ControllerProfile | None:
        with self._lock:
            profile = self._config.active_profile()
            return ControllerProfile.model_validate(profile.model_dump()) if profile else None

    def upsert_profile(
        self,
        payload: dict[str, Any],
        profile_id: str | None = None,
    ) -> ControllerProfile:
        with self._lock:
            existing = next(
                (profile for profile in self._config.profiles if profile.id == profile_id),
                None,
            )
            candidate = dict(payload)
            candidate.pop("access_key_configured", None)
            clear_secret = bool(candidate.pop("clear_access_key", False))
            submitted_secret = candidate.pop("access_key", None)
            if profile_id is not None:
                candidate["id"] = profile_id
            if clear_secret:
                candidate["access_key"] = None
            elif submitted_secret:
                candidate["access_key"] = SecretStr(str(submitted_secret))
            elif existing is not None:
                candidate["access_key"] = existing.access_key
            profile = ControllerProfile.model_validate(candidate)
            profiles = [item for item in self._config.profiles if item.id != profile.id]
            profiles.append(profile)
            active_id = self._config.active_profile_id
            if active_id is None:
                active_id = profile.id
            self._config = GatewayConfig(
                schema_version=self._config.schema_version,
                active_profile_id=active_id,
                profiles=profiles,
            )
            self._save_locked()
            return ControllerProfile.model_validate(profile.model_dump())

    def delete_profile(self, profile_id: str) -> None:
        with self._lock:
            profiles = [profile for profile in self._config.profiles if profile.id != profile_id]
            if len(profiles) == len(self._config.profiles):
                raise KeyError("profile not found")
            active_id = self._config.active_profile_id
            if active_id == profile_id:
                active_id = profiles[0].id if profiles else None
            self._config = GatewayConfig(
                schema_version=self._config.schema_version,
                active_profile_id=active_id,
                profiles=profiles,
            )
            self._save_locked()

    def activate_profile(self, profile_id: str) -> None:
        with self._lock:
            if not any(profile.id == profile_id for profile in self._config.profiles):
                raise KeyError("profile not found")
            self._config.active_profile_id = profile_id
            self._save_locked()

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self._config.schema_version,
            "active_profile_id": self._config.active_profile_id,
            "profiles": [_profile_storage(profile) for profile in self._config.profiles],
        }
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=self.path.parent,
            text=True,
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
