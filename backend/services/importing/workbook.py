"""Dependency-free OOXML workbook reader for import analysis."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict

from .archive import SafeXlsxArchive
from .exceptions import ImportWorkbookError
from .models import Sheet, Table, Workbook
from .ooxml_parts import (DOC_REL, MAIN, column_index, read_relationships,
                          read_shared_strings)
from .ooxml_sheet import parse_rows, parse_tables
from .styles import parse_styles


def read_workbook(content: bytes, filename: str) -> Workbook:
    archive = SafeXlsxArchive(content, filename)
    workbook_part = "xl/workbook.xml"
    root = ET.fromstring(archive.read(workbook_part))
    workbook_props = root.find(MAIN + "workbookPr")
    date_1904 = bool(workbook_props is not None and
                     workbook_props.get("date1904") in {"1", "true", "True"})
    rels = read_relationships(archive, workbook_part)
    shared = read_shared_strings(archive)
    styles = parse_styles(archive.read("xl/styles.xml", required=False))
    sheets: Dict[str, Sheet] = {}
    tables: Dict[str, Table] = {}
    sheets_node = root.find(MAIN + "sheets")
    if sheets_node is None:
        raise ImportWorkbookError("Workbook contains no worksheets")
    for sheet_node in sheets_node.findall(MAIN + "sheet"):
        name = sheet_node.get("name", "")
        part_name = rels.get(sheet_node.get(DOC_REL + "id", ""))
        if not name or not part_name:
            raise ImportWorkbookError("Workbook contains a broken worksheet relationship")
        sheet_root = ET.fromstring(archive.read(part_name))
        rows, hidden_columns = parse_rows(sheet_root, shared, styles)
        sheet_tables = parse_tables(archive, name, part_name, sheet_root)
        sheets[name] = Sheet(name, part_name, rows, hidden_columns, sheet_tables)
        for table in sheet_tables:
            key = (table.name or table.display_name).lower()
            if not key or key in tables:
                raise ImportWorkbookError(f"Duplicate or unnamed Excel table on sheet: {name}")
            tables[key] = table
    return Workbook(filename, archive.source_hash, date_1904, sheets, tables)


__all__ = ["column_index", "read_workbook"]
