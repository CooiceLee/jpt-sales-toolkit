"""
Country normalization and region lookup helpers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class CountryService:
    """Resolve country codes, display names, regions, and center coordinates."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path(__file__).parents[2] / "config" / "regions.json"
        self.lookup = self._load_lookup()

    def _load_lookup(self) -> dict:
        lookup = {
            "countries": {},
            "name_to_code": {},
            "aliases": {
                "UK": "GB",
                "U.K.": "GB",
                "UAE": "AE",
                "USA": "US",
                "U.S.A.": "US",
                "UNITED STATES OF AMERICA": "US",
            },
        }
        if not self.config_path.exists():
            return lookup

        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        for region_code, region in data.get("regions", {}).items():
            for code, country in region.get("countries", {}).items():
                item = {**country, "region": region_code, "code": code}
                lookup["countries"][code.upper()] = item
                for name in (country.get("name"), country.get("name_cn"), code):
                    if name:
                        lookup["name_to_code"][str(name).strip().lower()] = code.upper()
        return lookup

    def country_code(self, value: Optional[str]) -> Optional[str]:
        """Normalize a country code/name to the configured country code."""
        if not value:
            return None
        raw = str(value).strip()
        if not raw:
            return None
        upper = raw.upper()
        aliases = self.lookup.get("aliases", {})
        if upper in aliases:
            return aliases[upper]
        if upper in self.lookup.get("countries", {}):
            return upper
        return self.lookup.get("name_to_code", {}).get(raw.lower(), upper)

    def center(self, value: Optional[str]) -> Optional[dict]:
        code = self.country_code(value)
        if not code:
            return None
        return self.lookup.get("countries", {}).get(code)

    def region(self, value: Optional[str]) -> Optional[str]:
        country = self.center(value)
        return country.get("region") if country else None

    def display_name(self, value: Optional[str]) -> Optional[str]:
        country = self.center(value)
        if country:
            return country.get("name")
        return str(value).strip() if value else None

    def normalize_customer_payload(self, payload: dict, fill_region: bool = True) -> dict:
        """Normalize customer country/region fields before persistence."""
        if "country" not in payload:
            return payload

        normalized_country = self.display_name(payload.get("country"))
        if normalized_country:
            payload["country"] = normalized_country

        if fill_region and not payload.get("region"):
            region = self.region(normalized_country)
            if region:
                payload["region"] = region
        return payload
