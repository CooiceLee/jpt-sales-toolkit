"""Safe OOXML relationship, shared-string, and cell primitives."""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict

from .archive import SafeXlsxArchive
from .exceptions import ImportWorkbookError, UnsafeWorkbookError

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


def column_index(reference: str) -> int:
    match = CELL_REF.match(reference.upper())
    if not match:
        raise ImportWorkbookError(f"Invalid cell reference: {reference}")
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - 64
    return result


def resolve_part(base_part: str, target: str) -> str:
    target = target.replace("\\", "/")
    if target.startswith("/"):
        resolved = posixpath.normpath(target.lstrip("/"))
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base_part), target))
    if resolved.startswith("../") or resolved == "..":
        raise UnsafeWorkbookError(f"Unsafe OOXML relationship target: {target}")
    return resolved


def relationships_part(part_name: str) -> str:
    directory, filename = posixpath.split(part_name)
    return posixpath.join(directory, "_rels", filename + ".rels")


def read_relationships(archive: SafeXlsxArchive, owner_part: str) -> Dict[str, str]:
    payload = archive.read(relationships_part(owner_part), required=False)
    if not payload:
        return {}
    root = ET.fromstring(payload)
    return {
        item.get("Id", ""): resolve_part(owner_part, item.get("Target", ""))
        for item in root.findall(PKG_REL + "Relationship")
        if item.get("Id") and item.get("Target")
    }


def read_shared_strings(archive: SafeXlsxArchive) -> list[str]:
    payload = archive.read("xl/sharedStrings.xml", required=False)
    if not payload:
        return []
    root = ET.fromstring(payload)
    return ["".join(node.text or "" for node in item.iter(MAIN + "t"))
            for item in root.findall(MAIN + "si")]


def cell_value(cell: ET.Element, shared: list[str]) -> tuple[Any, str]:
    cell_type = cell.get("t")
    value_node = cell.find(MAIN + "v")
    raw = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "inlineStr":
        value = "".join(node.text or "" for node in cell.iter(MAIN + "t"))
        return value, value
    if cell_type == "s" and raw:
        try:
            value = shared[int(raw)]
        except (ValueError, IndexError) as exc:
            raise ImportWorkbookError(f"Invalid shared-string index: {raw}") from exc
        return value, value
    if cell_type == "b":
        return raw == "1", raw
    return raw, raw
