"""Style-preserving source trace for one standard table row."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Optional

from .legacy_constants import GRAY, GREEN, YELLOW
from .models import Row
from .standard_contract import TOKEN_RENAMES


def build_standard_trace(row: Row, ref: dict, headers: dict, start: int, end: int,
                         raw_dates: dict, external_key: str) -> dict:
    rgb, style_class = _row_fill(row, start, end)
    formulas = [cell.ref for column, cell in row.cells.items()
                if start <= column <= end and cell.formula]
    values = {cell.ref: cell.raw_value for column, cell in row.cells.items()
              if start <= column <= end and cell.raw_value != ""}
    return {
        "source_ref": ref, "disposition": "mapped", "row_hidden": row.hidden,
        "hidden_columns": sorted(column for column in range(start, end + 1)
                                 if row.cell(column) and row.cell(column).column_hidden),
        "fill_rgb": rgb, "style_class": style_class,
        "row_hash": hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest(),
        "raw_dates": raw_dates,
        "field_disposition": {field: f"mapped:{TOKEN_RENAMES.get(field, field)}"
                              for field in headers.values()},
        "target_entity_keys": [external_key], "formula_cells": formulas,
        "match_method": "external_key", "match_confidence": "exact",
    }


def _row_fill(row: Row, start: int, end: int) -> tuple[Optional[str], str]:
    colors = Counter(cell.style.fill_rgb for column, cell in row.cells.items()
                     if start <= column <= end and cell.style.fill_rgb)
    rgb = colors.most_common(1)[0][0] if colors else None
    if rgb in GREEN:
        return rgb, "green"
    if rgb in YELLOW:
        return rgb, "yellow"
    if rgb in GRAY:
        return rgb, "gray"
    return (rgb, "none") if not rgb or rgb == "FFFFFFFF" else (rgb, "other")
