"""OOXML writer for the field workbook, with its dropdowns and its keys."""

from __future__ import annotations

import io
from datetime import date
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape, quoteattr

from .trip_export_working import (
    CONTEXT_HEADERS, DATE_COLUMNS, DROPDOWNS, KEY_HEADERS, RESULT_HEADERS,
    TOKEN_HEADER, WORKING_HEADERS,
)
from .trip_export_xlsx import (
    _app_properties, _cell, _column, _core_properties, _root_relationships,
    _worksheet, _styles as _base_styles,
)

# The field workbook needs one style the read-only workbooks do not: a cell
# that stays writable once the sheet is protected, tinted so the field team can
# see where to type. It is appended to the shared styles rather than added to
# them, so the shared and full workbooks come out byte for byte as before.
_EDITABLE_FILL = (
    '<fill><patternFill patternType="solid"><fgColor rgb="FFFFF8E7"/>'
    '<bgColor indexed="64"/></patternFill></fill>'
)


def _serial(value) -> object:
    """A stored date as the number Excel keeps it in, or left as it is."""
    text = str(value or "").strip()
    if len(text) != 10:
        return value
    try:
        return (date.fromisoformat(text) - EXCEL_EPOCH).days
    except ValueError:
        return value


def _counted(text: str, tag: str) -> int:
    marker = f'<{tag} count="'
    start = text.index(marker) + len(marker)
    return int(text[start:text.index('"', start)])


def _styles() -> str:
    base = _base_styles()
    fills, styles = _counted(base, "fills"), _counted(base, "cellXfs")
    # applyProtection is what makes the unlocked flag take effect. Without it
    # Excel keeps the inherited lock and the field team cannot type in the very
    # cells the workbook exists for - and the file still opens without a word.
    editable = (
        f'<xf numFmtId="0" fontId="0" fillId="{fills}" borderId="1" xfId="0"'
        ' applyFill="1" applyBorder="1" applyAlignment="1" applyProtection="1">'
        '<alignment wrapText="1" vertical="top"/>'
        '<protection locked="0"/></xf>'
    )
    dated = editable.replace('numFmtId="0"', f'numFmtId="{DATE_NUMBER_FORMAT_ID}"')
    dated = dated.replace("applyProtection=", 'applyNumberFormat="1" applyProtection=')
    return (
        base
        .replace(
            "<fonts ",
            f'<numFmts count="1"><numFmt numFmtId="{DATE_NUMBER_FORMAT_ID}"'
            ' formatCode="yyyy\\-mm\\-dd"/></numFmts><fonts ',
        )
        .replace(f'<fills count="{fills}">', f'<fills count="{fills + 1}">')
        .replace("</fills>", f"{_EDITABLE_FILL}</fills>")
        .replace(f'<cellXfs count="{styles}">', f'<cellXfs count="{styles + 2}">')
        .replace("</cellXfs>", f"{editable}{dated}</cellXfs>")
    )


EDITABLE_STYLE = _counted(_base_styles(), "cellXfs")
DATE_STYLE = EDITABLE_STYLE + 1
DATE_PROMPT = (
    "填一个日期，例如 2026-09-16。 / Enter a date, for example 2026-09-16."
)
# Excel turns a typed date into a number the moment it is entered, so these
# cells are dates rather than text - anything else fails its own validation the
# first time somebody types the format it asked for.
DATE_NUMBER_FORMAT_ID = 164
EXCEL_EPOCH = date(1899, 12, 30)
DONE_PROMPT = (
    "标记为已拜访或需要跟进时，必须填写实际拜访日期和时段。 / "
    "A visit marked Visited or Follow-up Needed must carry the date and the "
    "half-day it actually happened on."
)
# How many columns stay in view when the sheet is scrolled right: the number
# and the customer, so a row can always be told apart from another.
FROZEN_COLUMNS = 2
NOTICE_LABEL = "填写说明 / How to fill in"
HALF_DAY_TITLE = "实际时段 / Half-day"
KEY_NOTICE = (
    "本表由系统写入，用于把结果对回原计划。请不要修改。 / Written by the "
    "application to match results back to the plan. Please do not edit."
)


def _validations(headers: list[str], first: int, last: int) -> str:
    rules = []
    for index, header in enumerate(headers, start=1):
        reference = f"{_column(index)}{first}:{_column(index)}{last}"
        if header in DROPDOWNS:
            choices = ",".join(DROPDOWNS[header])
            prompt = DONE_PROMPT if header == "实际时段 / Half-day" else ""
            rules.append(
                f'<dataValidation type="list" allowBlank="1" showInputMessage="1"'
                f' showErrorMessage="1" errorTitle={quoteattr("请从列表中选择")}'
                f' error={quoteattr("请选择列表中的一项。 / Choose one of the listed values.")}'
                f'{f" promptTitle={quoteattr(HALF_DAY_TITLE)} prompt={quoteattr(prompt)}" if prompt else ""}'
                # Excel reads an inline list as one quoted string.
                f' sqref="{reference}"><formula1>{escape(chr(34) + choices + chr(34))}'
                f"</formula1></dataValidation>"
            )
        elif header in DATE_COLUMNS:
            rules.append(
                f'<dataValidation type="date" operator="between" allowBlank="1"'
                f' showInputMessage="1" showErrorMessage="1"'
                f' errorTitle={quoteattr("日期格式")} error={quoteattr(DATE_PROMPT)}'
                f' promptTitle={quoteattr("日期格式")} prompt={quoteattr(DATE_PROMPT)}'
                f' sqref="{reference}"><formula1>DATE(2000,1,1)</formula1>'
                "<formula2>DATE(2100,12,31)</formula2></dataValidation>"
            )
    if not rules:
        return ""
    return f'<dataValidations count="{len(rules)}">{"".join(rules)}</dataValidations>'


def _working_sheet(model: dict) -> str:
    headers = model["headers"]
    width = len(headers)
    editable = {headers.index(header) + 1 for header in RESULT_HEADERS}
    dated = {headers.index(header) + 1 for header in DATE_COLUMNS}
    # No fixed heights below the banner: the field team types into these rows,
    # and a height written now cannot know how much they will write. Excel
    # grows a row to fit its wrapped text as long as nothing claims to have
    # chosen the height already.
    rows = [
        f'<row r="1" ht="28" customHeight="1">{_cell(1, 1, model["title"], 1)}</row>',
        f'<row r="2" ht="34" customHeight="1">'
        + _cell(2, 1, NOTICE_LABEL, 2)
        + _cell(2, FROZEN_COLUMNS + 1, DONE_PROMPT, 5)
        + "</row>",
        '<row r="3">'
        + "".join(_cell(3, col, value, 3) for col, value in enumerate(headers, 1))
        + "</row>",
    ]
    for index, row in enumerate(model["rows"], start=4):
        rows.append(
            f'<row r="{index}">'
            + "".join(
                _cell(index, col,
                      _serial(row.get(header)) if col in dated else row.get(header),
                      DATE_STYLE if col in dated
                      else EDITABLE_STYLE if col in editable else 4)
                for col, header in enumerate(headers, 1)
            )
            + "</row>"
        )
    last = max(4, 3 + len(model["rows"]))
    # The token is not for reading, so it is out of the way - but it is a
    # normal cell in a normal column, so sorting carries it with its row.
    token_column = headers.index(TOKEN_HEADER) + 1
    widths = "".join(
        f'<col min="{index}" max="{index}" '
        + ('hidden="1" width="0"' if index == token_column
           else f'width="{28 if index > len(CONTEXT_HEADERS) else 22}"')
        + ' customWidth="1"/>'
        for index in range(1, width + 1)
    )
    return _worksheet(
        sheetPr='<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>',
        sheetViews=(
            '<sheetViews><sheetView workbookViewId="0">'
            f'<pane xSplit="{FROZEN_COLUMNS}" ySplit="3" '
            f'topLeftCell="{_column(FROZEN_COLUMNS + 1)}4" '
            'activePane="bottomRight" state="frozen"/>'
            "</sheetView></sheetViews>"
        ),
        sheetFormatPr='<sheetFormatPr defaultRowHeight="18"/>',
        cols=f"<cols>{widths}</cols>",
        sheetData=f'<sheetData>{"".join(rows)}</sheetData>',
        # Protection is here to stop the plan being typed over, not to stop
        # somebody making the sheet readable. Widening a column, raising a row
        # or changing the type size stays theirs to do.
        sheetProtection=(
            '<sheetProtection sheet="1" objects="1" scenarios="1"'
            ' selectLockedCells="1" selectUnlockedCells="0" sort="0"'
            ' autoFilter="0" formatCells="0" formatColumns="0"'
            ' formatRows="0"/>'
        ),
        autoFilter=f'<autoFilter ref="A3:{_column(width)}{last}"/>',
        # A merged range that crosses the frozen split is drawn in two places
        # and loses the text in between, so neither of these crosses it.
        mergeCells=(
            '<mergeCells count="3">'
            f'<mergeCell ref="A1:{_column(FROZEN_COLUMNS)}1"/>'
            f'<mergeCell ref="A2:{_column(FROZEN_COLUMNS)}2"/>'
            f'<mergeCell ref="{_column(FROZEN_COLUMNS + 1)}2:{_column(width)}2"/>'
            "</mergeCells>"
        ),
        dataValidations=_validations(headers, 4, max(last, 4)),
        pageMargins='<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>',
        pageSetup='<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>',
    )


def _key_sheet(model: dict) -> str:
    headers = list(KEY_HEADERS)
    rows = [
        f'<row r="1">{_cell(1, 1, "格式 / Format", 2)}{_cell(1, 2, model["format"], 4)}</row>',
        f'<row r="2">{_cell(2, 1, "工作簿 / Workbook", 2)}{_cell(2, 2, model["workbook_id"], 4)}</row>',
        f'<row r="3">{_cell(3, 1, "导出时间 / Exported at", 2)}{_cell(3, 2, model["generated_at"], 4)}</row>',
        f'<row r="4">{_cell(4, 1, KEY_NOTICE, 5)}</row>',
        f'<row r="5">'
        + "".join(_cell(5, col, value, 3) for col, value in enumerate(headers, 1))
        + "</row>",
    ]
    for index, key in enumerate(model["keys"], start=6):
        rows.append(
            f'<row r="{index}">'
            + "".join(
                _cell(index, col, key.get(header))
                for col, header in enumerate(headers, 1)
            )
            + "</row>"
        )
    return _worksheet(
        sheetData=f'<sheetData>{"".join(rows)}</sheetData>',
        sheetProtection='<sheetProtection sheet="1" objects="1" scenarios="1"/>',
        pageMargins='<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>',
    )


SHEET_NAMES = ("现场执行", "导入信息 请勿修改")


def _workbook() -> str:
    sheets = (
        f'<sheet name="{escape(SHEET_NAMES[0])}" sheetId="1" r:id="rId1"/>'
        f'<sheet name="{escape(SHEET_NAMES[1])}" sheetId="2" r:id="rId2" state="hidden"/>'
    )
    return ('<?xml version="1.0" encoding="UTF-8"?><workbook '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<bookViews><workbookView/></bookViews><sheets>{sheets}</sheets></workbook>')


def _relationships() -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>")


def _content_types() -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in (1, 2)
    )
    return ('<?xml version="1.0" encoding="UTF-8"?><Types '
            'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{sheets}"
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            "</Types>")


def render_working_xlsx(model: dict) -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("_rels/.rels", _root_relationships())
        archive.writestr("docProps/app.xml", _app_properties())
        archive.writestr("docProps/core.xml", _core_properties())
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _relationships())
        archive.writestr("xl/styles.xml", _styles())
        archive.writestr("xl/worksheets/sheet1.xml", _working_sheet(model))
        archive.writestr("xl/worksheets/sheet2.xml", _key_sheet(model))
    return output.getvalue()
