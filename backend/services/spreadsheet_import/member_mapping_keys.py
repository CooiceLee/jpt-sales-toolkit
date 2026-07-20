"""Backward-compatible keys for purpose-specific member resolutions."""

from __future__ import annotations


def member_mapping_key(source_name: str, purpose: str) -> str:
    return f"{source_name}::{purpose}"


def manual_member_target(
    manual: dict[str, str], source_name: str, purpose: str, raw_names: set[str]
) -> str | None:
    purpose_keys = [
        member_mapping_key(source_name, purpose),
        *(member_mapping_key(raw, purpose) for raw in sorted(raw_names)),
    ]
    legacy_keys = [source_name, *sorted(raw_names)]
    return next((manual[key] for key in [*purpose_keys, *legacy_keys] if key in manual), None)
