"""The field workbook: what may be written in it, and what it carries back.

It is the only export that is a contract. Everything checked here is something
the import in the next batch depends on, or something that would let somebody
report a result the application cannot match back to a visit.
"""

from __future__ import annotations

import io
import re
import shutil
from zipfile import ZipFile

from fastapi.testclient import TestClient

import test_trip_planner_batch4 as fixture
import test_trip_planner_batch5_exports as plans
from backend.services.importing.workbook import read_workbook
from backend.services.trip_export_working import (
    CONTEXT_HEADERS, RESULT_HEADERS, TOKEN_HEADER, WORKING_HEADERS,
)

# Written out rather than imported: a check that reads the same constant the
# workbook is built from would pass however that constant is changed.
FORMAT_MARKER = "JPT-TRIP-WORKING-1.0"
ANSWER_CHOICES = ("未填写 / Not answered", "是 / Yes", "否 / No")
PERIOD_CHOICES = ("未填写 / Not answered", "AM", "PM")
STATUS_CHOICES = ("已计划 / Planned", "已拜访 / Visited",
                  "需要跟进 / Follow-up Needed", "已跳过 / Skipped")
from backend.services.trip_export_working_xlsx import (
    DATE_STYLE, EDITABLE_STYLE,
)

# The result columns are written in one of two styles: the plain writable one,
# and the same one carrying a date format.
WRITABLE_STYLES = frozenset({EDITABLE_STYLE, DATE_STYLE})


def _download(client: TestClient, ctx: dict, plan: dict) -> bytes:
    response = client.get(
        f"/api/review/trip-plans/{plan['id']}/working.xlsx",
        headers=ctx["headers"]["owner"],
    )
    assert response.status_code == 200, response.text[:300]
    return response.content


def _parts(content: bytes) -> dict:
    with ZipFile(io.BytesIO(content)) as archive:
        return {
            name: archive.read(name).decode()
            for name in archive.namelist() if name.endswith(".xml")
        }


def _table(content: bytes, sheet: str, header_row: int) -> list[dict]:
    book = read_workbook(content, "working.xlsx")
    rows = book.sheets[sheet].rows
    numbers = sorted(rows)
    header = {
        index: cell.value for index, cell in rows[numbers[header_row - 1]].cells.items()
    }
    return [
        {header[index]: cell.value for index, cell in rows[number].cells.items()
         if index in header}
        for number in numbers[header_row:]
    ]


# Written out from the format's own sequence rather than imported: a check
# that read the same list the writer is built from would accept any order that
# list was changed to.
WORKSHEET_ELEMENT_ORDER = (
    "sheetPr", "dimension", "sheetViews", "sheetFormatPr", "cols", "sheetData",
    "sheetCalcPr", "sheetProtection", "protectedRanges", "scenarios",
    "autoFilter", "sortState", "dataConsolidate", "customSheetViews",
    "mergeCells", "phoneticPr", "conditionalFormatting", "dataValidations",
    "hyperlinks", "printOptions", "pageMargins", "pageSetup",
)


def _worksheet_children(xml: str) -> list[str]:
    """The direct children of <worksheet>, in the order they were written."""
    body = xml[xml.index("<worksheet"):]
    children, depth = [], 0
    for match in re.finditer(r"<(/?)(\w+)[^>]*?(/?)>", body):
        closing, tag, self_closing = match.groups()
        if tag == "worksheet":
            depth += 0 if closing else 1
            continue
        if closing:
            depth -= 1
            continue
        if depth == 1:
            children.append(tag)
        if not self_closing:
            depth += 1
    return children


def check_every_sheet_is_written_in_the_order_excel_reads(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """A sheet whose children are out of order is not a warning, it is a loss.

    Excel offers to repair such a file and the repair empties the sheet. A ZIP
    that opens and XML that parses prove nothing about this, so every worksheet
    this application writes is checked against the order the format defines.
    """
    base = f"/api/review/trip-plans/{plan['id']}"
    documents = {
        "working": f"{base}/working.xlsx",
        "shared": f"{base}/export.xlsx?variant=shared",
        "full": f"{base}/export.xlsx?variant=full",
    }
    for label, url in documents.items():
        response = client.get(url, headers=ctx["headers"]["owner"])
        assert response.status_code == 200, (label, response.status_code)
        with ZipFile(io.BytesIO(response.content)) as archive:
            sheets = sorted(
                name for name in archive.namelist()
                if name.startswith("xl/worksheets/")
            )
            assert sheets, f"{label} has no worksheets"
            for name in sheets:
                children = _worksheet_children(archive.read(name).decode())
                unknown = [
                    tag for tag in children if tag not in WORKSHEET_ELEMENT_ORDER
                ]
                assert not unknown, f"{label} {name} writes {unknown}"
                positions = [WORKSHEET_ELEMENT_ORDER.index(tag) for tag in children]
                assert positions == sorted(positions), (
                    f"{label} {name} is written out of order, so Excel will "
                    f"offer to repair it and empty it: {children}"
                )


def check_only_customer_visits_are_carried(content: bytes, plan: dict) -> None:
    """A hotel or an airport wait has no result to report, so it is not here."""
    rows = _table(content, "现场执行", 3)
    visits = [stop for stop in plan["stops"] if stop.get("stop_kind") != "free"]
    free = [stop for stop in plan["stops"] if stop.get("stop_kind") == "free"]
    assert free, "the fixture has no non-customer stop to leave out"
    assert len(rows) == len(visits), (
        f"{len(visits)} visits produced {len(rows)} rows"
    )
    printed = {row["客户 / Customer"] for row in rows}
    for stop in visits:
        assert stop["customer_name"] in printed, stop["customer_name"]
    for stop in free:
        assert stop["location_name"] not in printed, (
            f"{stop['location_name']} has no visit to report on"
        )


def check_preparation_is_shown_but_not_writable(content: bytes, plan: dict) -> None:
    """What was prepared is there to read; only the result may be typed over."""
    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    assert "<sheetProtection" in sheet, "every cell in the sheet is writable"

    rows = _table(content, "现场执行", 3)
    visit = next(stop for stop in plan["stops"] if stop.get("stop_kind") != "free")
    row = next(r for r in rows if r["客户 / Customer"] == visit["customer_name"])
    assert row["拜访目的 / Visit purpose"] == visit["visit_purpose"], row
    assert row["议题 / Topics"], "the visit was carried without its topics"

    editable_columns = {
        WORKING_HEADERS.index(header) + 1 for header in RESULT_HEADERS
    }
    context_columns = {
        WORKING_HEADERS.index(header) + 1 for header in CONTEXT_HEADERS
    }
    book = read_workbook(content, "working.xlsx")
    body = book.sheets["现场执行"].rows
    for number in sorted(body)[3:]:
        for index, cell in body[number].cells.items():
            style = cell.style_id
            if index in editable_columns:
                assert style in WRITABLE_STYLES, (
                    f"column {index} of the result is locked against the field "
                    f"team: style {style}"
                )
            elif index in context_columns:
                assert style not in WRITABLE_STYLES, (
                    f"column {index} carries preparation and may be typed over"
                )


def check_the_visit_is_fully_prepared_on_the_page(content: bytes, plan: dict) -> None:
    """Whoever walks into the meeting can see everything prepared for it.

    This is the copy carried into the field, so a preparation field that only
    exists in the reading copy is a piece of kit left behind or a colleague
    nobody knew was coming.
    """
    rows = _table(content, "现场执行", 3)
    visit = next(stop for stop in plan["stops"] if stop.get("stop_kind") != "free")
    row = next(item for item in rows if item["客户 / Customer"] == visit["customer_name"])
    briefing = visit["briefing"]

    assert briefing["equipment"] and briefing["participants"], (
        "the fixture prepares no equipment or colleagues, so this proves nothing"
    )
    for item in briefing["equipment"]:
        column = {
            "demo": "演示设备 / Demo laser", "po": "PO 设备 / PO laser",
        }.get(item["kind"], "其他设备 / Other equipment")
        assert item["model"] in (row[column] or ""), (
            f"{item['model']} is prepared for this visit but is not in {column}"
        )
    for item in briefing["participants"]:
        assert item["display_name"] in (row["JPT 参会人员 / JPT participants"] or ""), (
            f"{item['display_name']} is going and the workbook does not say so"
        )
    for item in briefing["channel_partner_companions"]:
        assert item["name"] in (row["渠道代理陪同 / Channel partner companions"] or ""), (
            f"{item['name']} is coming along and the workbook does not say so"
        )
    assert row["议题 / Topics"] and row["客户人员 / Customer personnel"]


def check_the_answers_are_offered_as_three_choices(content: bytes) -> None:
    """Not answered is a choice of its own, next to yes and no."""
    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    for header, choices in (
        ("需要样品 / Sample needed", ANSWER_CHOICES),
        ("需要报价 / Quote needed", ANSWER_CHOICES),
        ("实际时段 / Half-day", PERIOD_CHOICES),
        ("结果状态 / Result status", STATUS_CHOICES),
    ):
        listed = ",".join(choices)
        assert f'<formula1>"{listed}"</formula1>' in sheet.replace("&quot;", '"'), (
            f"{header} does not offer exactly {choices}"
        )
    assert sheet.count("<dataValidation ") >= 6, (
        "the dates and the four lists are not all validated"
    )
    # Excel drops an inline list longer than 255 characters, and the cell then
    # accepts anything typed into it without a word.
    for listed in re.findall(r"<formula1>&quot;(.*?)&quot;</formula1>", sheet):
        assert len(listed) <= 255, (
            f"a dropdown is {len(listed)} characters long and will be dropped: "
            f"{listed[:60]}..."
        )
    # showDropDown="1" means the arrow is hidden, which reads backwards and has
    # been shipped that way by mistake before.
    assert 'showDropDown="1"' not in sheet, (
        "the lists are there but their arrows are turned off"
    )
    assert "actually happened on" in sheet, (
        "the workbook never says a reported visit needs its time"
    )
    assert "2026-09-16" in sheet, "the date format is not shown to whoever types"
    # Excel turns a typed date into a number as it is entered, so the rule that
    # judges it has to be a date rule. A text rule rejects the very format the
    # cell asked for.
    assert sheet.count('type="date"') == 2, (
        "the date columns are not validated as dates, so typing the format "
        "they ask for is refused"
    )


def check_the_file_says_only_which_workbook_it_is(content: bytes, plan: dict) -> None:
    """The file carries its own identity and one token per row. Nothing more.

    A file cannot vouch for itself: whoever holds it can unprotect the hidden
    sheet and rewrite which visit a row is about, or the values the row was
    exported holding. Both would let a result be filed against another customer
    or a real conflict be hidden, so neither is in the file at all - the
    issuing installation keeps them.
    """
    keys = _table(content, "导入信息 请勿修改", 5)
    rows = _table(content, "现场执行", 3)
    assert len(keys) == len(rows), f"{len(rows)} rows have {len(keys)} keys"
    from backend.services.trip_export_working import KEY_HEADERS

    assert list(KEY_HEADERS) == ["行 / Row", TOKEN_HEADER], (
        f"the file was given something else to be believed about: {KEY_HEADERS}"
    )
    assert set(keys[0]) == {"行 / Row", TOKEN_HEADER}, (
        f"the key sheet carries more than the row and its token: {sorted(keys[0])}"
    )

    header = _parts(content)["xl/worksheets/sheet2.xml"]
    assert FORMAT_MARKER in header, (
        f"the workbook does not say it is a {FORMAT_MARKER} document"
    )
    # Which visit each token is, and what it held, must not be readable here.
    stops = [stop for stop in plan["stops"] if stop.get("stop_kind") != "free"]
    for stop in stops:
        assert stop["id"] not in header, (
            "the file names the visit a token belongs to, so rewriting it would "
            "move a result to another customer"
        )
    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    for name in ("停靠点 / Stop", "行版本 / Row version"):
        assert name not in header and name not in sheet, (
            f"{name} is still written into the file"
        )


def check_the_hidden_sheet_is_hidden_and_says_not_to_edit(content: bytes) -> None:
    workbook = _parts(content)["xl/workbook.xml"]
    assert 'state="hidden"' in workbook, "the key sheet is offered as a normal sheet"
    keys = _parts(content)["xl/worksheets/sheet2.xml"]
    assert "请不要修改" in keys and "do not edit" in keys, (
        "the key sheet does not say what it is for"
    )


def check_what_is_printed_is_what_is_stored(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """An unanswered question comes out unanswered, not as a no.

    The workbook is what the field team reads before they write, so an answer
    it invents is one they will confirm without noticing.
    """
    visit = next(stop for stop in plan["stops"] if stop.get("stop_kind") != "free")
    for stored, printed in ((None, "未填写 / Not answered"), (True, "是 / Yes"),
                            (False, "否 / No")):
        current = fixture._require(
            client.get(
                f"/api/review/trip-plans/{plan['id']}",
                headers=ctx["headers"]["owner"],
            ),
            200,
        )
        saved = next(s for s in current["stops"] if s["id"] == visit["id"])
        response = client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{visit['id']}",
            headers=ctx["headers"]["owner"],
            json={"row_version": saved["row_version"],
                  "visit_sample_needed": stored},
        )
        assert response.status_code == 200, response.text[:200]
        rows = _table(_download(client, ctx, plan), "现场执行", 3)
        row = next(r for r in rows if r["客户 / Customer"] == visit["customer_name"])
        assert row["需要样品 / Sample needed"] == printed, (
            f"stored as {stored!r} but printed as "
            f"{row['需要样品 / Sample needed']!r}"
        )
        assert row["实际时段 / Half-day"] == "未填写 / Not answered", (
            "a visit nobody has reported on already names the half-day it "
            f"happened in: {row['实际时段 / Half-day']!r}"
        )


def check_a_row_carries_which_visit_it_is(content: bytes, plan: dict) -> None:
    """Identity travels in the row, so sorting cannot move a result elsewhere.

    Hiding a sheet and protecting cells only stops a slip. Anybody may unprotect
    the sheet and sort it, and then a row number no longer says which visit the
    line is about - the result would be filed against another customer.
    """
    rows = _table(content, "现场执行", 3)
    keys = _table(content, "导入信息 请勿修改", 5)
    tokens = [row[TOKEN_HEADER] for row in rows]
    assert all(tokens), "a row went out with no way to say which visit it is"
    assert len(set(tokens)) == len(tokens), f"two rows share a token: {tokens}"
    assert set(tokens) == {key[TOKEN_HEADER] for key in keys}, (
        "the tokens in the sheet and in the keys are not the same set"
    )

    # The key sheet lists the same tokens in the same order as the rows, so a
    # human can still line the two up when diagnosing a returned file.
    assert [key[TOKEN_HEADER] for key in keys] == tokens, (
        "the key sheet and the rows disagree about the order of the visits"
    )

    # The token is a cell of the row, not a column heading somewhere else, so
    # that sorting the sheet carries it along.
    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    column = WORKING_HEADERS.index(TOKEN_HEADER) + 1
    assert f'<col min="{column}" max="{column}" hidden="1"' in sheet, (
        "the token column is not hidden from the field team"
    )
    for token in tokens:
        assert token in sheet, "a token is missing from the sheet it belongs to"


def check_the_manifest_says_which_visit_and_what_it_held() -> None:
    """What the file no longer carries is handed to the caller to persist.

    The comparison at import time is only as good as the values the workbook
    was issued with, so those travel out of here as data to store rather than
    as cells in a file anybody can edit.
    """
    from backend.services.trip_export_working import build_working_model

    plan = {
        "id": "plan-manifest", "title": "Manifest",
        "stops": [
            {"id": "a", "stop_kind": "customer", "customer_name": "Alpha",
             "sequence_no": 1, "row_version": 4, "result_status": "Visited",
             "actual_visit_date": "2026-09-16", "actual_visit_period": "AM",
             "visit_sample_needed": True},
            {"id": "h", "stop_kind": "free", "location_name": "Hotel", "sequence_no": 2},
        ],
    }
    model = build_working_model(plan, "2026-09-02T00:00:00Z", "workbook-1")
    assert model["workbook_id"] == "workbook-1"
    assert len(model["manifest"]) == 1, "the hotel reached the manifest"
    entry = model["manifest"][0]
    assert entry["stop_id"] == "a" and entry["row_version"] == 4, entry
    assert entry["row_token"] == model["rows"][0][TOKEN_HEADER]
    assert entry["baseline"]["result_status"] == "已拜访 / Visited", entry
    assert entry["baseline"]["actual_visit_date"] == "2026-09-16", entry
    assert entry["baseline"]["visit_sample_needed"] == "是 / Yes", entry
    assert entry["baseline"]["visit_quote_needed"] == "未填写 / Not answered", entry


def check_each_visit_gets_its_own_token() -> None:
    """Two visits in one workbook are told apart by their own tokens.

    The plan the other checks run against has a single customer visit, which
    cannot show that two rows differ.
    """
    from backend.services.trip_export_working import build_working_model

    plan = {
        "id": "plan-two", "title": "Two visits",
        "stops": [
            {"id": "a", "stop_kind": "customer", "customer_name": "Alpha",
             "sequence_no": 1, "row_version": 3, "result_status": "Planned"},
            {"id": "b", "stop_kind": "customer", "customer_name": "Beta",
             "sequence_no": 2, "row_version": 5, "result_status": "Visited"},
            {"id": "h", "stop_kind": "free", "location_name": "Hotel",
             "sequence_no": 3},
        ],
    }
    model = build_working_model(plan, "2026-09-02T00:00:00Z", "workbook-2")
    tokens = [row[TOKEN_HEADER] for row in model["rows"]]
    assert len(tokens) == 2, f"the hotel was carried in: {len(tokens)} rows"
    assert len(set(tokens)) == 2, f"both visits share one token: {tokens}"
    keyed = {row["row_token"]: row["stop_id"] for row in model["manifest"]}
    assert keyed[tokens[0]] == "a" and keyed[tokens[1]] == "b", keyed
    versions = {row["row_token"]: row["row_version"] for row in model["manifest"]}
    assert versions[tokens[0]] == 3 and versions[tokens[1]] == 5, versions


def check_a_typed_date_comes_back_as_that_date() -> None:
    """A date written into the workbook reads back as the same date.

    The cell holds the number Excel keeps a date in, not the text of one, so
    the import has to see the date through the number format - and does.
    """
    from backend.services.importing.dates import parse_excel_date
    from backend.services.trip_export_working import build_working_model
    from backend.services.trip_export_working_xlsx import render_working_xlsx

    plan = {
        "id": "plan-dates", "title": "Dates",
        "stops": [{
            "id": "s1", "stop_kind": "customer", "customer_name": "Alpha",
            "sequence_no": 1, "row_version": 2, "result_status": "Visited",
            "actual_visit_date": "2026-09-30",
            "visit_followup_due_date": "2026-10-15",
        }],
    }
    content = render_working_xlsx(
        build_working_model(plan, "2026-09-02T00:00:00Z", "workbook-3"))
    book = read_workbook(content, "dates.xlsx")
    sheet = book.sheets["现场执行"]
    numbers = sorted(sheet.rows)
    header = {i: c.value for i, c in sheet.rows[numbers[2]].cells.items()}
    row = sheet.rows[numbers[3]]
    seen = {}
    for index, cell in row.cells.items():
        name = header.get(index)
        if name not in ("实际拜访日期 / Actually visited on", "跟进截止 / Follow-up due"):
            continue
        assert "y" in (cell.style.number_format or ""), (
            f"{name} is not formatted as a date: {cell.style.number_format!r}"
        )
        # Written as the number Excel keeps a date in. Left as text it would
        # sit left-aligned next to the numbers people type in, and the column
        # would hold two kinds of thing.
        assert cell.data_type != "inlineStr", (
            f"{name} was written as text, so the column mixes text with the "
            f"dates Excel makes when somebody types one: {cell.value!r}"
        )
        parsed = parse_excel_date(cell, book.date_1904)
        assert parsed[2] == "excel_serial", (
            f"{name} did not read back as a date Excel wrote: {parsed}"
        )
        seen[name] = parsed[0]
    assert seen == {
        "实际拜访日期 / Actually visited on": "2026-09-30",
        "跟进截止 / Follow-up due": "2026-10-15",
    }, seen


def check_the_sheet_can_be_made_readable(content: bytes) -> None:
    """Nothing is written in a size or a shape the reader is stuck with.

    The workbook is filled in on a laptop in front of a customer. Text that is
    cut off and cannot be widened, raised or resized is unusable however
    correct the data behind it is.
    """
    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    start = sheet.index("<sheetProtection")
    element = sheet[start:sheet.index("/>", start)]
    flags = {
        key: value.strip('"')
        for key, value in (
            part.split("=", 1) for part in element.split()[1:] if "=" in part
        )
    }
    for allowed in ("formatCells", "formatColumns", "formatRows"):
        assert flags.get(allowed) == "0", (
            f"the sheet forbids {allowed}, so text that does not fit cannot be "
            f"made to fit: {flags.get(allowed)!r}"
        )

    # Rows below the banner claim no height, so Excel grows them to their text.
    rows = re.findall(r'<row r="(\d+)"([^>]*)>', sheet)
    for number, attributes in rows:
        if int(number) < 3:
            continue
        assert "customHeight" not in attributes, (
            f"row {number} is fixed at a height written before anyone typed "
            f"into it: {attributes.strip()}"
        )


def check_no_merged_cell_crosses_the_frozen_split(content: bytes) -> None:
    """A merge across the split is drawn twice and loses the text between.

    Excel renders the frozen columns and the scrolled ones separately, so a
    banner merged across both comes out with a piece missing from the middle -
    which reads as corrupted text rather than as a layout problem.
    """
    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    split = int(re.search(r'<pane xSplit="(\d+)"', sheet).group(1))

    def column_index(reference: str) -> int:
        letters = re.match(r"([A-Z]+)", reference).group(1)
        index = 0
        for letter in letters:
            index = index * 26 + (ord(letter) - 64)
        return index

    merges = re.findall(r'<mergeCell ref="([A-Z]+\d+):([A-Z]+\d+)"', sheet)
    assert merges, "the banner is no longer merged at all"
    for first, last in merges:
        start, end = column_index(first), column_index(last)
        assert not (start <= split < end), (
            f"{first}:{last} is merged across the frozen split at column "
            f"{split}, so part of its text will not be drawn"
        )


def check_the_yellow_cells_really_are_unlocked(content: bytes) -> None:
    """The style the writable cells use has to actually turn the lock off.

    A style may carry an unlocked flag and still be ignored: Excel only applies
    it when the entry says it applies protection. Without that the file opens
    perfectly and the one thing the workbook exists for - typing in the yellow
    cells - silently does not work.
    """
    parts = _parts(content)
    styles = parts["xl/styles.xml"]
    entries = ["<xf " + entry for entry in styles[
        styles.index("<cellXfs"):styles.index("</cellXfs>")
    ].split("<xf ")[1:]]

    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    book = read_workbook(content, "working.xlsx")
    body = book.sheets["现场执行"].rows
    writable = {
        WORKING_HEADERS.index(header) + 1 for header in RESULT_HEADERS
    }
    used = {
        cell.style_id
        for number in sorted(body)[3:]
        for index, cell in body[number].cells.items() if index in writable
    }
    assert used <= WRITABLE_STYLES, (
        f"the writable cells use a style nobody vouched for: {used}"
    )
    dated = entries[DATE_STYLE]
    assert 'applyNumberFormat="1"' in dated, (
        "the date style names a date format but never says to apply it, so "
        f"Excel shows the serial number instead of a date: {dated}"
    )
    for style in used:
        entry = entries[style]
        assert 'locked="0"' in entry, f"a writable style is locked: {entry}"
        assert 'applyProtection="1"' in entry, (
            "a writable style turns the lock off but never says to apply it, "
            f"so Excel keeps those cells read-only: {entry}"
        )

    read_only = {
        cell.style_id
        for number in sorted(body)[3:]
        for index, cell in body[number].cells.items() if index not in writable
    }
    for style in read_only:
        assert style not in WRITABLE_STYLES, (
            f"a read-only cell uses a writable style: {entries[style]}"
        )
        assert 'locked="0"' not in entries[style], (
            f"a read-only cell uses a writable style: {entries[style]}"
        )
    assert "<sheetProtection" in sheet


def check_two_downloads_do_not_share_tokens(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """Each export is its own baseline, so each carries its own tokens.

    Two workbooks of the same plan are filled in separately. If they shared
    tokens the import could not tell which baseline a returned row was written
    against, and the older one would silently overwrite the newer.
    """
    first = {row[TOKEN_HEADER] for row in _table(_download(client, ctx, plan), "现场执行", 3)}
    second = {row[TOKEN_HEADER] for row in _table(_download(client, ctx, plan), "现场执行", 3)}
    assert first and second, "an export came back with no tokens"
    assert not (first & second), (
        f"two downloads reused {len(first & second)} tokens"
    )


def check_the_writable_cells_can_be_typed_in(content: bytes) -> None:
    """Protection has to leave the yellow cells reachable.

    In OOXML each of these flags means "this is protected", so setting the one
    for unlocked cells would lock the field team out of the only cells they are
    meant to use - which no structural check would notice.
    """
    sheet = _parts(content)["xl/worksheets/sheet1.xml"]
    start = sheet.index("<sheetProtection")
    element = sheet[start:sheet.index("/>", start)]
    flags = dict(
        part.split("=", 1) for part in element.split()[1:] if "=" in part
    )
    flags = {key: value.strip('"') for key, value in flags.items()}
    assert flags.get("sheet") == "1", "the sheet is not protected at all"
    assert flags.get("selectUnlockedCells") in (None, "0"), (
        "the cells the field team writes in cannot even be selected: "
        f"selectUnlockedCells={flags.get('selectUnlockedCells')!r}"
    )
    assert flags.get("selectLockedCells") == "1", (
        "the read-only cells invite a cursor they will refuse"
    )


def check_the_read_only_workbooks_did_not_change(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """Adding a writable workbook must not touch the ones people already read."""
    from backend.services.trip_export_working_xlsx import _styles as working_styles
    from backend.services.trip_export_xlsx import _styles as shared_styles

    base = shared_styles()
    assert 'locked="0"' not in base, (
        "the shared workbooks were given the field workbook's writable style"
    )
    assert base.count("<fill>") == 3, (
        f"the shared workbooks gained a fill: {base.count('<fill>')}"
    )
    assert working_styles() != base and 'locked="0"' in working_styles()

    for variant in ("shared", "full"):
        response = client.get(
            f"/api/review/trip-plans/{plan['id']}/export.xlsx?variant={variant}",
            headers=ctx["headers"]["owner"],
        )
        assert response.status_code == 200, response.text[:200]
        parts = _parts(response.content)
        joined = "\n".join(parts.values())
        for marker in ("dataValidation", "sheetProtection", FORMAT_MARKER,
                       'state="hidden"', 'locked="0"'):
            assert marker not in joined, (
                f"the {variant} workbook picked up {marker!r} from the field "
                "workbook"
            )


def run() -> None:
    try:
        with TestClient(fixture.app) as client:
            ctx = fixture._seed(client)
            plan = plans._prepare_plan(client, ctx)
            content = _download(client, ctx, plan)
            check_every_sheet_is_written_in_the_order_excel_reads(client, ctx, plan)
            check_only_customer_visits_are_carried(content, plan)
            check_preparation_is_shown_but_not_writable(content, plan)
            check_the_visit_is_fully_prepared_on_the_page(content, plan)
            check_the_answers_are_offered_as_three_choices(content)
            check_the_file_says_only_which_workbook_it_is(content, plan)
            check_the_hidden_sheet_is_hidden_and_says_not_to_edit(content)
            check_a_row_carries_which_visit_it_is(content, plan)
            check_the_writable_cells_can_be_typed_in(content)
            check_the_yellow_cells_really_are_unlocked(content)
            check_a_typed_date_comes_back_as_that_date()
            check_the_sheet_can_be_made_readable(content)
            check_no_merged_cell_crosses_the_frozen_split(content)
            check_two_downloads_do_not_share_tokens(client, ctx, plan)
            check_each_visit_gets_its_own_token()
            check_the_manifest_says_which_visit_and_what_it_held()
            check_what_is_printed_is_what_is_stored(client, ctx, plan)
            check_the_read_only_workbooks_did_not_change(client, ctx, plan)
        print("PASS: the field workbook carries its visits, its choices and its keys")
    finally:
        fixture.close_db()
        shutil.rmtree(fixture.TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
