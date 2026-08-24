"""Dependency-free OOXML writer for the formal trip workbook."""

from __future__ import annotations

import io
import re
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from .trip_export_model import LEG_HEADERS, TIMELINE_HEADERS, VISIT_HEADERS


_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


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
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><sheetViews><sheetView workbookViewId="0"><pane ySplit="{header_row}" topLeftCell="A{header_row + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>{cols}</cols><sheetData>{''.join(xml_rows)}</sheetData>{merge}<autoFilter ref="A{header_row}:{_column(width)}{last_row}"/><pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>'''


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


def render_trip_xlsx(model: dict) -> bytes:
    sheets = [
        _sheet(VISIT_HEADERS, model["visits"], metadata=(model["title"], model["metadata"])),
        _sheet(TIMELINE_HEADERS, model["timeline"]),
        _sheet(LEG_HEADERS, model["legs"]),
    ]
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("_rels/.rels", _root_relationships())
        archive.writestr("docProps/app.xml", _app_properties())
        archive.writestr("docProps/core.xml", _core_properties())
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships())
        archive.writestr("xl/styles.xml", _styles())
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet)
    return output.getvalue()


def _content_types() -> str:
    sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, 4))
    return f'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{sheets}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'''


def _root_relationships() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''


def _workbook() -> str:
    names = ("拜访计划", "完整日程", "交通行程")
    sheets = "".join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(names, 1))
    return f'''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>{sheets}</sheets></workbook>'''


def _workbook_relationships() -> str:
    sheets = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, 4))
    return f'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{sheets}<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''


def _styles() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="3"><font><sz val="10"/><name val="Aptos"/></font><font><b/><sz val="18"/><color rgb="FF4A1225"/><name val="Aptos Display"/></font><font><b/><color rgb="FFFFFFFF"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF8B2347"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border/><border><left style="thin"><color rgb="FFDED7CE"/></left><right style="thin"><color rgb="FFDED7CE"/></right><top style="thin"><color rgb="FFDED7CE"/></top><bottom style="thin"><color rgb="FFDED7CE"/></bottom></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"><alignment horizontal="right" wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment horizontal="left" wrapText="1" vertical="center"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''


def _app_properties() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>JPT Sales Toolkit</Application></Properties>'''


def _core_properties() -> str:
    return '''<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>JPT Sales Toolkit</dc:creator><dc:title>Trip Plan</dc:title></cp:coreProperties>'''
