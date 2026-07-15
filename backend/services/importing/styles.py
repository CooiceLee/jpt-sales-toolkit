"""Tolerant OOXML style parsing, including malformed empty fill nodes."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from .models import StyleInfo

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

BUILTIN_FORMATS = {
    0: "General", 1: "0", 2: "0.00", 9: "0%", 10: "0.00%",
    14: "mm-dd-yy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy",
    18: "h:mm AM/PM", 19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss",
    22: "m/d/yy h:mm", 45: "mm:ss", 46: "[h]:mm:ss", 47: "mmss.0",
}


def _visible_fill(fill: ET.Element) -> tuple[Optional[str], Optional[str]]:
    pattern = fill.find(MAIN + "patternFill")
    if pattern is None:
        return None, None
    pattern_type = pattern.get("patternType")
    if pattern_type != "solid":
        return None, pattern_type
    color = pattern.find(MAIN + "fgColor")
    if color is None:
        return None, pattern_type
    if color.get("rgb"):
        return color.get("rgb", "").upper(), pattern_type
    if color.get("indexed"):
        return f"INDEXED:{color.get('indexed')}", pattern_type
    if color.get("theme"):
        tint = color.get("tint")
        return f"THEME:{color.get('theme')}:{tint or '0'}", pattern_type
    return None, pattern_type


def parse_styles(xml_bytes: bytes) -> List[StyleInfo]:
    if not xml_bytes:
        return [StyleInfo()]
    root = ET.fromstring(xml_bytes)
    custom: Dict[int, str] = {}
    num_fmts = root.find(MAIN + "numFmts")
    if num_fmts is not None:
        for item in num_fmts.findall(MAIN + "numFmt"):
            custom[int(item.get("numFmtId", "0"))] = item.get("formatCode", "")

    fills: list[tuple[Optional[str], Optional[str]]] = []
    fill_root = root.find(MAIN + "fills")
    if fill_root is not None:
        fills = [_visible_fill(item) for item in fill_root.findall(MAIN + "fill")]

    styles: List[StyleInfo] = []
    xfs = root.find(MAIN + "cellXfs")
    if xfs is None:
        return [StyleInfo()]
    for xf in xfs.findall(MAIN + "xf"):
        fill_id = int(xf.get("fillId", "0"))
        rgb, pattern = fills[fill_id] if fill_id < len(fills) else (None, None)
        fmt_id = int(xf.get("numFmtId", "0"))
        number_format = custom.get(fmt_id, BUILTIN_FORMATS.get(fmt_id))
        styles.append(StyleInfo(rgb, pattern, number_format))
    return styles or [StyleInfo()]


def is_date_format(number_format: Optional[str]) -> bool:
    """Conservatively detect date-like Excel formats."""
    if not number_format:
        return False
    cleaned = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', "", number_format.lower())
    cleaned = re.sub(r"\[[^]]*]", "", cleaned)
    return bool(re.search(r"(^|[^a-z])[ymdhs]+([^a-z]|$)", cleaned))
