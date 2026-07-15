"""OOXML worksheet rows, hidden columns, and Excel table relationships."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict

from .archive import SafeXlsxArchive
from .exceptions import ImportWorkbookError
from .models import Cell, Row, StyleInfo, Table
from .ooxml_parts import (DOC_REL, MAIN, cell_value, column_index,
                          read_relationships)


def hidden_columns(root: ET.Element) -> set[int]:
    hidden: set[int] = set()
    columns = root.find(MAIN + "cols")
    if columns is None:
        return hidden
    for item in columns.findall(MAIN + "col"):
        if item.get("hidden") not in {"1", "true", "True"}:
            continue
        hidden.update(range(int(item.get("min", "0")), int(item.get("max", "0")) + 1))
    return hidden


def parse_rows(root: ET.Element, shared: list[str],
               styles: list[StyleInfo]) -> tuple[Dict[int, Row], set[int]]:
    hidden = hidden_columns(root)
    rows: Dict[int, Row] = {}
    for row_node in root.iter(MAIN + "row"):
        number = int(row_node.get("r", "0"))
        if number <= 0:
            continue
        row = Row(number, row_node.get("hidden") in {"1", "true", "True"})
        for cell_node in row_node.findall(MAIN + "c"):
            reference = cell_node.get("r", "")
            column = column_index(reference)
            style_id = int(cell_node.get("s", "0"))
            style = styles[style_id] if style_id < len(styles) else StyleInfo()
            value, raw = cell_value(cell_node, shared)
            formula_node = cell_node.find(MAIN + "f")
            row.cells[column] = Cell(
                ref=reference, row=number, column=column, value=value, raw_value=raw,
                data_type=cell_node.get("t"), style_id=style_id, style=style,
                formula=formula_node.text if formula_node is not None else None,
                column_hidden=column in hidden,
            )
        rows[number] = row
    return rows, hidden


def parse_tables(archive: SafeXlsxArchive, sheet_name: str, sheet_part: str,
                 sheet_root: ET.Element) -> list[Table]:
    rels = read_relationships(archive, sheet_part)
    result: list[Table] = []
    table_parts = sheet_root.find(MAIN + "tableParts")
    if table_parts is None:
        return result
    for item in table_parts.findall(MAIN + "tablePart"):
        part_name = rels.get(item.get(DOC_REL + "id", ""))
        if not part_name:
            raise ImportWorkbookError(f"Broken table relationship on sheet: {sheet_name}")
        root = ET.fromstring(archive.read(part_name))
        columns_node = root.find(MAIN + "tableColumns")
        columns = [] if columns_node is None else [
            node.get("name", "") for node in columns_node.findall(MAIN + "tableColumn")
        ]
        result.append(Table(
            name=root.get("name", ""), display_name=root.get("displayName", ""),
            ref=root.get("ref", ""), sheet_name=sheet_name, columns=columns,
        ))
    return result
