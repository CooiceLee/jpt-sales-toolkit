"""Stable non-mutating preflight report projection."""

from __future__ import annotations


def build_preflight_report(canonical: dict) -> dict:
    return {
        "format": canonical["format"], "dataset_id": canonical["dataset_id"],
        "source_hash": canonical["source_hash"], "source": canonical["source"],
        "summary": canonical["summary"], "issues": canonical["issues"],
        "source_trace": canonical["source_trace"],
    }
