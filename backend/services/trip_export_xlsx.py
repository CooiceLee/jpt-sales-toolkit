"""Dependency-free OOXML writer for the formal trip workbook."""

from __future__ import annotations

import io
import re
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from .trip_export_model import (
    LEG_HEADERS, OVERVIEW_HEADERS, TIMELINE_HEADERS, VISIT_HEADERS,
)


_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# A worksheet's children have a fixed order. Out of order, Excel does not
# report a warning it can work around: it offers to repair the file and the
# repair empties the sheet. Nothing in a ZIP or XML check sees this, so the
# order lives in one list that every sheet is assembled through.
WORKSHEET_ELEMENT_ORDER = (
    "sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols", "sheetData",
    "sheetCalcPr", "sheetProtection", "protectedRanges", "scenarios",
    "autoFilter", "sortState", "dataConsolidate", "customSheetViews",
    "mergeCells", "phoneticPr", "conditionalFormatting", "dataValidations",
    "hyperlinks", "printOptions", "pageMargins", "pageSetup",
)


def _worksheet(**parts: str) -> str:
    """One worksheet, with its children written in the order Excel reads them."""
    unknown = set(parts) - set(WORKSHEET_ELEMENT_ORDER)
    if unknown:
        raise ValueError(f"worksheet element not in the reading order: {unknown}")
    body = "".join(
        parts[name] for name in WORKSHEET_ELEMENT_ORDER if parts.get(name)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{body}</worksheet>"
    )


def _column(index: int) -> str:
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def _cell(row: int, column: int, value, style: int = 4) -> str:
    reference = f"{_column(column)}{row}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{reference}" s="{style}"><v>{value}</v></c>'
    text = escape(_ILLEGAL.sub("", str(value or "")))
    preserve = ' xml:space="preserve"' if text.strip() != text else ""
    return f'<c r="{reference}" s="{style}" t="inlineStr"><is><t{preserve}>{text}</t></is></c>'


def _sheet(headers: list[str], rows: list[dict], *, metadata=None) -> str:
    width = len(headers)
    widths = _widths(width)
    xml_rows, header_row = [], 1
    merge_refs = []
    if metadata is not None:
        xml_rows.append(f'<row r="1" ht="28" customHeight="1">{_cell(1, 1, metadata[0], 1)}</row>')
        merge_refs.append(f"A1:{_column(width)}1")
        for row_index, (label, value) in enumerate(metadata[1], start=2):
            xml_rows.append(f'<row r="{row_index}" ht="24" customHeight="1">{_cell(row_index, 1, label, 2)}{_cell(row_index, 3, value, 5)}</row>')
            merge_refs.extend((f"A{row_index}:B{row_index}", f"C{row_index}:{_column(width)}{row_index}"))
        header_row = len(metadata[1]) + 3
    xml_rows.append(
        f'<row r="{header_row}" ht="30" customHeight="1">'
        + "".join(_cell(header_row, col, value, 3) for col, value in enumerate(headers, 1))
        + "</row>"
    )
    for row_index, row in enumerate(rows, start=header_row + 1):
        height = _row_height(row, headers, widths)
        xml_rows.append(
            f'<row r="{row_index}" ht="{height}" customHeight="1">'
            + "".join(_cell(row_index, col, row.get(header)) for col, header in enumerate(headers, 1))
            + "</row>"
        )
    last_row = max(header_row, header_row + len(rows))
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width_value}" customWidth="1"/>'
        for index, width_value in enumerate(widths, start=1)
    )
    merge = ""
    if merge_refs:
        cells = "".join(f'<mergeCell ref="{reference}"/>' for reference in merge_refs)
        merge = f'<mergeCells count="{len(merge_refs)}">{cells}</mergeCells>'
    return _worksheet(
        sheetPr='<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>',
        sheetViews=(
            '<sheetViews><sheetView workbookViewId="0">'
            f'<pane ySplit="{header_row}" topLeftCell="A{header_row + 1}" '
            'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        ),
        sheetFormatPr='<sheetFormatPr defaultRowHeight="18"/>',
        cols=f"<cols>{cols}</cols>",
        sheetData=f"<sheetData>{''.join(xml_rows)}</sheetData>",
        autoFilter=f'<autoFilter ref="A{header_row}:{_column(width)}{last_row}"/>',
        mergeCells=merge,
        pageMargins='<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>',
        pageSetup='<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>',
    )


def _widths(count: int) -> list[int]:
    preferred = [9, 24, 34, 24, 27, 27, 27, 32, 34, 42, 18, 20, 30]
    return preferred[:count] + [20] * max(0, count - len(preferred))


def _row_height(row: dict, headers: list[str], widths: list[int]) -> int:
    max_lines = 1
    for header, width in zip(headers, widths):
        text = str(row.get(header) or "")
        line_width = max(8, int(width * 1.25))
        lines = sum(
            max(1, (len(part) + line_width - 1) // line_width)
            for part in text.splitlines() or [""]
        )
        max_lines = max(max_lines, lines)
    return min(300, max(30, max_lines * 15 + 8))


def _plan(model: dict) -> list[tuple[str, list[str], list[dict]]]:
    """Which sheets this workbook has, in reading order.

    The trip overview is a sheet of its own. It used to ride on top of whichever
    sheet came first, so a workbook that leaves that sheet out would lose the
    plan name, the travel team and the risks with it.
    """
    sheets = [("行程总览", OVERVIEW_HEADERS, model["overview"])]
    if model.get("visits"):
        sheets.append(("拜访计划", VISIT_HEADERS, model["visits"]))
    sheets.append(("完整日程", TIMELINE_HEADERS, model["timeline"]))
    sheets.append(("交通行程", LEG_HEADERS, model["legs"]))
    return sheets


def render_trip_xlsx(model: dict) -> bytes:
    plan = _plan(model)
    sheets = [
        _sheet(headers, rows, metadata=(model["title"], []) if index == 0 else None)
        for index, (_, headers, rows) in enumerate(plan)
    ]
    names = [name for name, _, _ in plan]
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(len(sheets)))
        archive.writestr("_rels/.rels", _root_relationships())
        archive.writestr("docProps/app.xml", _app_properties())
        archive.writestr("docProps/core.xml", _core_properties())
        archive.writestr("xl/workbook.xml", _workbook(names))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships(len(sheets)))
        archive.writestr("xl/styles.xml", _styles())
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet)
    return output.getvalue()


def _content_types(count: int) -> str:
    sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, count + 1))
    return f'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{sheets}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'''


def _root_relationships() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''


def _workbook(names: list[str]) -> str:
    sheets = "".join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, 1))
    return f'''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>{sheets}</sheets></workbook>'''


def _workbook_relationships(count: int) -> str:
    sheets = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, count + 1))
    return f'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{sheets}<Relationship Id="rId{count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''


def _styles() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="3"><font><sz val="10"/><name val="Aptos"/></font><font><b/><sz val="18"/><color rgb="FF4A1225"/><name val="Aptos Display"/></font><font><b/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF8B2347"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border/><border><left style="thin"><color rgb="FFDED7CE"/></left><right style="thin"><color rgb="FFDED7CE"/></right><top style="thin"><color rgb="FFDED7CE"/></top><bottom style="thin"><color rgb="FFDED7CE"/></bottom></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment horizontal="right" wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment horizontal="left" wrapText="1" vertical="center"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''


def _app_properties() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>JPT Sales Toolkit</Application></Properties>'''


def _core_properties() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>JPT Sales Toolkit</dc:creator><dc:title>Trip Plan</dc:title></cp:coreProperties>'''
