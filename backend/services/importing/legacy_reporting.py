"""Source trace, style evidence and canonical summary projection."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Optional

from .legacy_constants import GRAY, GREEN, YELLOW
from .models import Row


class ReportingMixin:
    def add_trace(self, sheet: str, row: Row, disposition: str, field_map: dict,
                  target_keys: list[str], raw_dates: Optional[dict] = None,
                  match_method: str = "none", confidence: str = "none") -> None:
        rgb, style_class = representative_fill(row, len(field_map) or None)
        values = {cell.ref: cell.raw_value for cell in row.cells.values() if cell.raw_value != ""}
        digest = hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.source_trace.append({
            "source_ref": self.source_ref(sheet, row.number), "disposition": disposition,
            "row_hidden": row.hidden, "hidden_columns": sorted(
                cell.column for cell in row.cells.values() if cell.column_hidden),
            "fill_rgb": rgb, "style_class": style_class, "row_hash": digest,
            "raw_dates": raw_dates or {}, "field_disposition": field_map,
            "target_entity_keys": target_keys, "match_method": match_method,
            "match_confidence": confidence,
        })

    def finalize(self) -> dict:
        mapped = {"mapped", "mapped_with_issues"}
        style_counts = Counter(item["style_class"] for item in self.source_trace
                               if item["disposition"] in mapped)
        issue_counts = Counter(item["severity"] for item in self.issues)
        return {
            "format": "JPT-XLSX-1.0-canonical", "dataset_id": self.dataset_id,
            "source_hash": self.workbook.source_hash,
            "source": {"filename": self.workbook.source_name, "kind": "legacy-europe-squad-v1"},
            "entities": self.entities, "source_trace": self.source_trace,
            "issues": self.issues, "member_name_tokens": sorted(
                self._members.values(), key=lambda item: item["username_token"]),
            "summary": {
                "source_rows": self.source_counts,
                "total_source_rows": sum(self.source_counts.values()),
                "entity_counts": {name: len(items) for name, items in self.entities.items()},
                "issues": dict(issue_counts), "style_rows": dict(style_counts),
                "won_fulfillment": dict(self.won_fulfillment_rows),
                "can_import": issue_counts.get("blocker", 0) == 0,
            },
        }


def representative_fill(row: Row, max_column: Optional[int] = None) -> tuple[Optional[str], str]:
    colors = Counter(
        cell.style.fill_rgb for cell in row.cells.values()
        if cell.style.fill_rgb and (max_column is None or cell.column <= max_column)
    )
    rgb = colors.most_common(1)[0][0] if colors else None
    if rgb in GREEN:
        return rgb, "green"
    if rgb in YELLOW:
        return rgb, "yellow"
    if rgb in GRAY:
        return rgb, "gray"
    return (rgb, "none") if not rgb or rgb == "FFFFFFFF" else (rgb, "other")
