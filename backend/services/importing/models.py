"""Small immutable OOXML workbook models used by import adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass(frozen=True)
class StyleInfo:
    fill_rgb: Optional[str] = None
    pattern_type: Optional[str] = None
    number_format: Optional[str] = None


@dataclass(frozen=True)
class Cell:
    ref: str
    row: int
    column: int
    value: Any
    raw_value: str
    data_type: Optional[str]
    style_id: int
    style: StyleInfo
    formula: Optional[str] = None
    column_hidden: bool = False


@dataclass
class Row:
    number: int
    hidden: bool
    cells: Dict[int, Cell] = field(default_factory=dict)

    def cell(self, column: int) -> Optional[Cell]:
        return self.cells.get(column)

    def value(self, column: int, default: Any = "") -> Any:
        cell = self.cell(column)
        return default if cell is None else cell.value

    def nonempty(self) -> bool:
        return any(str(cell.value or "").strip() for cell in self.cells.values())


@dataclass(frozen=True)
class Table:
    name: str
    display_name: str
    ref: str
    sheet_name: str
    columns: List[str]


@dataclass
class Sheet:
    name: str
    part_name: str
    rows: Dict[int, Row]
    hidden_columns: Set[int] = field(default_factory=set)
    tables: List[Table] = field(default_factory=list)

    def row(self, number: int) -> Row:
        return self.rows.get(number, Row(number=number, hidden=False))


@dataclass
class Workbook:
    source_name: str
    source_hash: str
    date_1904: bool
    sheets: Dict[str, Sheet]
    tables: Dict[str, Table]
