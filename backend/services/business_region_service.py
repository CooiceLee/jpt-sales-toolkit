"""Canonical business-region definitions for member assignment and lead filtering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class InvalidBusinessRegionError(ValueError):
    """Raised when an account or filter uses an unsupported business region."""


class BusinessRegionService:
    """Load and normalize the five owner-account business regions."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or (
            Path(__file__).resolve().parents[2] / "config" / "regions.json"
        )
        with self.config_path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        self.definitions = payload.get("business_regions") or []
        self._aliases: dict[str, str] = {}
        self._definitions_by_code: dict[str, dict] = {}
        for definition in self.definitions:
            code = str(definition["code"]).strip()
            self._definitions_by_code[code] = definition
            values = [code, *(definition.get("aliases") or [])]
            for value in values:
                self._aliases[self._key(value)] = code

    @staticmethod
    def _key(value: object) -> str:
        return str(value or "").strip().casefold()

    def normalize(self, value: object, *, allow_none: bool = True) -> Optional[str]:
        key = self._key(value)
        if not key and allow_none:
            return None
        code = self._aliases.get(key)
        if not code:
            raise InvalidBusinessRegionError(f"Unsupported business region: {value}")
        return code

    def aliases_for(self, value: object) -> tuple[str, ...]:
        code = self.normalize(value, allow_none=False)
        definition = self._definitions_by_code[code]
        values = [code, *(definition.get("aliases") or [])]
        return tuple(dict.fromkeys(self._key(item) for item in values if self._key(item)))


_SERVICE: Optional[BusinessRegionService] = None


def get_business_region_service() -> BusinessRegionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = BusinessRegionService()
    return _SERVICE


def normalize_business_region(value: object, *, allow_none: bool = True) -> Optional[str]:
    return get_business_region_service().normalize(value, allow_none=allow_none)
