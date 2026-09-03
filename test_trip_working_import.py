"""Batch 3 acceptance tests for the returned field-work workbook."""

from __future__ import annotations

import io
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile

from fastapi.testclient import TestClient

import test_trip_planner_batch4 as fixture
import test_trip_planner_batch5_exports as exports
from backend.services.importing.workbook import read_workbook


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _working(client: TestClient, ctx: dict) -> tuple[dict, bytes]:
    plan = exports._prepare_plan(client, ctx)
    response = client.get(
        f"/api/review/trip-plans/{plan['id']}/working.xlsx",
        headers=ctx["headers"]["owner"],
    )
    assert response.status_code == 200, response.text
    return plan, response.content


def _report(response, expected_status: int) -> dict:
    assert response.status_code == expected_status, response.text
    return response.json()


def _preflight(client: TestClient, ctx: dict, content: bytes):
    return client.post(
        "/api/review/trip-working/preflight",
        headers=ctx["headers"]["owner"],
        files={"file": ("returned.xlsx", content, MIME)},
    )


def _commit(
    client: TestClient,
    ctx: dict,
    content: bytes,
    report: dict | str,
    resolutions: dict | None = None,
    *,
    preview_digest: str | None = None,
):
    """Submit a workbook the way the panel does: with the preview it acted on."""
    source_hash = report["source_hash"] if isinstance(report, dict) else report
    if preview_digest is None:
        preview_digest = report.get("preview_digest", "") if isinstance(report, dict) else ""
    return client.post(
        "/api/review/trip-working/import",
        headers=ctx["headers"]["owner"],
        data={
            "expected_source_hash": source_hash,
            "expected_preview_digest": preview_digest,
            "resolutions_json": json.dumps(resolutions or {}),
        },
        files={"file": ("returned.xlsx", content, MIME)},
    )


def _edit_cells(content: bytes, changes: dict[tuple[str, str], object]) -> bytes:
    """Replace result cells while keeping the workbook's normal styles."""
    book = read_workbook(content, "returned.xlsx")
    sheet = book.sheets["现场执行"]
    headers = {
        cell.value: column
        for column, cell in sheet.row(3).cells.items()
    }
    token_column = headers["标识 / Row token"]
    field_columns = {
        "result_status": headers["结果状态 / Result status"],
        "actual_visit_date": headers["实际拜访日期 / Actually visited on"],
        "actual_visit_period": headers["实际时段 / Half-day"],
        "result_notes": headers["会议记录 / Meeting notes"],
        "visit_next_action": headers["下一步行动 / Next action"],
        "visit_followup_due_date": headers["跟进截止 / Follow-up due"],
    }
    target_refs: dict[str, object] = {}
    for (token, field), value in changes.items():
        row = next(
            row for row in sheet.rows.values()
            if row.number >= 4 and row.value(token_column, "") == token
        )
        target = row.cell(field_columns[field])
        assert target is not None, (token, field)
        target_refs[target.ref] = "" if value is None else str(value)

    ET.register_namespace("", MAIN_NS)
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for name in source.namelist():
                payload = source.read(name)
                if name == sheet.part_name:
                    root = ET.fromstring(payload)
                    for cell in root.findall(f".//{{{MAIN_NS}}}c"):
                        ref = cell.attrib.get("r")
                        if ref not in target_refs:
                            continue
                        for child in list(cell):
                            cell.remove(child)
                        cell.set("t", "inlineStr")
                        inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
                        text = ET.SubElement(inline, f"{{{MAIN_NS}}}t")
                        text.set(f"{{{XML_NS}}}space", "preserve")
                        text.text = target_refs[ref]
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(name, payload)
        return output.getvalue()


def _first_visit(report: dict) -> dict:
    assert len(report["rows"]) == 1, report
    return report["rows"][0]


def _cell_state(report: dict, field: str) -> str:
    return next(
        item["state"]
        for item in _first_visit(report)["comparisons"]
        if item["field"] == field
    )


def _fresh_plan(client: TestClient, ctx: dict) -> tuple[dict, bytes, dict]:
    plan, content = _working(client, ctx)
    preview = _report(_preflight(client, ctx, content), 200)
    return plan, content, preview


def check_preflight_is_read_only_and_token_bound(client: TestClient, ctx: dict) -> None:
    _, content, before_report = _fresh_plan(client, ctx)
    before = fixture._snapshot()
    token = _first_visit(before_report)["token"]
    tampered = _edit_cells(content, {(token, "result_notes"): "现场记录"})
    # A visible token that was not issued by the hidden key must never be
    # associated by row number or customer name.
    tampered = _edit_cells(tampered, {(token, "result_notes"): "现场记录"})
    book = read_workbook(tampered, "returned.xlsx")
    sheet = book.sheets["现场执行"]
    token_column = next(
        column for column, cell in sheet.row(3).cells.items()
        if cell.value == "标识 / Row token"
    )
    row = next(row for row in sheet.rows.values() if row.number >= 4 and row.value(token_column, ""))
    ref = row.cell(token_column).ref
    ET.register_namespace("", MAIN_NS)
    with zipfile.ZipFile(io.BytesIO(tampered)) as source:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for name in source.namelist():
                payload = source.read(name)
                if name == sheet.part_name:
                    root = ET.fromstring(payload)
                    cell = next(node for node in root.findall(f".//{{{MAIN_NS}}}c") if node.get("r") == ref)
                    for child in list(cell):
                        cell.remove(child)
                    cell.set("t", "inlineStr")
                    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
                    text = ET.SubElement(inline, f"{{{MAIN_NS}}}t")
                    text.text = "not-issued-token"
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(name, payload)
        tampered = output.getvalue()

    response = _preflight(client, ctx, tampered)
    report = _report(response, 200)
    codes = {issue["code"] for issue in report["issues"]}
    assert {"unknown_token", "missing_visible_row"} <= codes, report
    assert report["can_commit"] is False
    assert fixture._snapshot() == before


def check_workbook_only_and_downstream_impact(client: TestClient, ctx: dict) -> None:
    _, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]
    changed = _edit_cells(content, {(token, "result_notes"): "客户确认测试安排"})
    report = _report(_preflight(client, ctx, changed), 200)
    assert _cell_state(report, "result_notes") == "workbook_only"
    assert "trip_visit_activity" in {item["code"] for item in _first_visit(report)["impacts"]}
    completed = _report(_commit(client, ctx, changed, report), 200)
    assert completed["committed_fields"] == 1
    conn = fixture.get_db()
    assert conn.execute(
        "SELECT result_notes FROM trip_plan_stops WHERE id = ?",
        (_first_visit(report)["stop_id"],),
    ).fetchone()[0] == "客户确认测试安排"
    assert conn.execute(
        "SELECT COUNT(*) FROM lead_activities WHERE action_type = 'comment' AND payload_json LIKE ?",
        (f"%{_first_visit(report)['stop_id']}%",),
    ).fetchone()[0] == 1


def check_current_only_and_both_same_merge(client: TestClient, ctx: dict) -> None:
    plan, content, baseline = _fresh_plan(client, ctx)
    stop_id = _first_visit(baseline)["stop_id"]
    current_plan = _report(
        client.get(
            f"/api/review/trip-plans/{plan['id']}",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    stop = next(item for item in current_plan["stops"] if item["id"] == stop_id)
    fixture._require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop_id}",
            headers=ctx["headers"]["owner"],
            json={"row_version": stop["row_version"], "result_notes": "现场先行录入"},
        ),
        200,
    )
    report = _report(_preflight(client, ctx, content), 200)
    assert _cell_state(report, "result_notes") == "current_only"
    completed = _report(_commit(client, ctx, content, report), 200)
    assert completed["committed_fields"] == 0

    # Re-export the current value, then write the same value into the returned
    # file: both sides changed from the original baseline, but agree now.
    _, same_content, same_baseline = _fresh_plan(client, ctx)
    same_token = _first_visit(same_baseline)["token"]
    same_changed = _edit_cells(same_content, {(same_token, "result_notes"): "双方相同"})
    same_plan_id = same_baseline["plan_id"]
    same_plan = _report(
        client.get(f"/api/review/trip-plans/{same_plan_id}", headers=ctx["headers"]["owner"]),
        200,
    )
    same_stop = next(item for item in same_plan["stops"] if item["id"] == _first_visit(same_baseline)["stop_id"])
    fixture._require(
        client.patch(
            f"/api/review/trip-plans/{same_plan_id}/stops/{same_stop['id']}",
            headers=ctx["headers"]["owner"],
            json={"row_version": same_stop["row_version"], "result_notes": "双方相同"},
        ),
        200,
    )
    same_report = _report(_preflight(client, ctx, same_changed), 200)
    assert _cell_state(same_report, "result_notes") == "both_same"
    assert _report(_commit(client, ctx, same_changed, same_report), 200)["committed_fields"] == 0


def check_conflict_requires_field_resolution(client: TestClient, ctx: dict) -> None:
    plan, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]
    stop_id = _first_visit(baseline)["stop_id"]
    uploaded = _edit_cells(content, {(token, "result_notes"): "工作簿版本"})
    current_plan = _report(
        client.get(f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]["owner"]),
        200,
    )
    stop = next(item for item in current_plan["stops"] if item["id"] == stop_id)
    fixture._require(
        client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop_id}",
            headers=ctx["headers"]["owner"],
            json={"row_version": stop["row_version"], "result_notes": "数据库版本"},
        ),
        200,
    )
    report = _report(_preflight(client, ctx, uploaded), 200)
    assert _cell_state(report, "result_notes") == "conflict"
    assert report["requires_resolution"] is True
    before = fixture._snapshot()
    unresolved = _commit(client, ctx, uploaded, report)
    error = _report(unresolved, 422)
    assert error["detail"]["report"]["missing_resolutions"]
    assert fixture._snapshot() == before
    resolved = _report(
        _commit(client, ctx, uploaded, report, {token: {"result_notes": "workbook"}}),
        200,
    )
    assert resolved["committed_fields"] == 1


def check_reparse_and_downstream_chain(client: TestClient, ctx: dict) -> None:
    plan, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]
    stop_id = _first_visit(baseline)["stop_id"]
    uploaded = _edit_cells(content, {
        (token, "result_status"): "需要跟进 / Follow-up Needed",
        (token, "actual_visit_date"): "2026-09-30",
        (token, "actual_visit_period"): "PM",
        (token, "visit_next_action"): "Call customer",
        (token, "visit_followup_due_date"): "2026-10-15",
    })
    report = _report(_preflight(client, ctx, uploaded), 200)
    impact_codes = {item["code"] for item in _first_visit(report)["impacts"]}
    assert {"trip_visit_activity", "formal_followup"} <= impact_codes
    lead_id = next(stop["lead_id"] for stop in plan["stops"] if stop["id"] == stop_id)
    lead = _report(
        client.get(f"/api/leads/{lead_id}", headers=ctx["headers"]["owner"]),
        200,
    )
    fixture._require(
        client.patch(
            f"/api/leads/{lead_id}",
            headers=ctx["headers"]["owner"],
            json={"row_version": lead["row_version"], "sales_stage": "Assigned"},
        ),
        200,
    )
    before = fixture._snapshot()
    changed_after_preflight = _edit_cells(uploaded, {(token, "visit_next_action"): "Changed after preview"})
    stale = _commit(client, ctx, changed_after_preflight, report)
    assert stale.status_code == 409, stale.text
    assert fixture._snapshot() == before

    completed = _report(_commit(client, ctx, uploaded, report), 200)
    assert completed["committed_fields"] == 5
    conn = fixture.get_db()
    activity = conn.execute(
        "SELECT lead_id, is_formal_follow_up, payload_json FROM lead_activities "
        "WHERE action_type = 'follow_up' AND is_formal_follow_up = 1 "
        "AND payload_json LIKE ?",
        (f"%{stop_id}%",),
    ).fetchone()
    assert activity is not None
    assert activity[1] == 1
    lead = conn.execute("SELECT sales_stage, next_followup_date FROM leads WHERE id = ?", (activity[0],)).fetchone()
    assert tuple(lead) == ("Following", "2026-10-15")


def check_strict_marker(client: TestClient, ctx: dict) -> None:
    _, content, _ = _fresh_plan(client, ctx)
    book = read_workbook(content, "returned.xlsx")
    sheet = book.sheets["导入信息 请勿修改"]
    ref = sheet.row(1).cell(2).ref
    ET.register_namespace("", MAIN_NS)
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target_zip:
            for name in source.namelist():
                payload = source.read(name)
                if name == sheet.part_name:
                    root = ET.fromstring(payload)
                    cell = next(node for node in root.findall(f".//{{{MAIN_NS}}}c") if node.get("r") == ref)
                    for child in list(cell):
                        cell.remove(child)
                    cell.set("t", "inlineStr")
                    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
                    ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = "JPT-TRIP-WORKING-0.9"
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                target_zip.writestr(name, payload)
        invalid = output.getvalue()
    response = _preflight(client, ctx, invalid)
    assert response.status_code == 400, response.text
    assert "JPT-TRIP-WORKING-1.0" in response.text


def _set_cell(content: bytes, sheet_name: str, ref: str, *, formula=None, text=None) -> bytes:
    """Rewrite one cell, as somebody who unprotected the sheet would."""
    book = read_workbook(content, "returned.xlsx")
    part = book.sheets[sheet_name].part_name
    ET.register_namespace("", MAIN_NS)
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for name in source.namelist():
                payload = source.read(name)
                if name == part:
                    root = ET.fromstring(payload)
                    cell = next(node for node in root.findall(f".//{{{MAIN_NS}}}c")
                                if node.get("r") == ref)
                    for child in list(cell):
                        cell.remove(child)
                    cell.attrib.pop("t", None)
                    if formula is not None:
                        ET.SubElement(cell, f"{{{MAIN_NS}}}f").text = formula
                        ET.SubElement(cell, f"{{{MAIN_NS}}}v").text = text or "0"
                    else:
                        cell.set("t", "inlineStr")
                        inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
                        ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = text or ""
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                target.writestr(name, payload)
        return output.getvalue()


def _result_ref(content: bytes, header: str) -> str:
    book = read_workbook(content, "returned.xlsx")
    sheet = book.sheets["现场执行"]
    column = {cell.value: index for index, cell in sheet.row(3).cells.items()}[header]
    numbers = [n for n in sorted(sheet.rows) if n >= 4 and sheet.rows[n].nonempty()]
    return sheet.rows[numbers[0]].cell(column).ref


def check_the_file_cannot_vouch_for_itself(client: TestClient, ctx: dict) -> None:
    """Nothing the holder of the file can rewrite decides what is imported.

    A hidden sheet is a convenience, not a guarantee: anybody can unprotect it.
    So which visit a row is about, and what the row was exported holding, are
    not in the file - forging them has nothing to forge.
    """
    plan, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]
    stop_id = _first_visit(baseline)["stop_id"]

    book = read_workbook(content, "returned.xlsx")
    keys = book.sheets["导入信息 请勿修改"]
    assert [cell.value for cell in keys.row(5).cells.values()] == ["行 / Row", "标识 / Row token"], (
        "the file still carries what the import has to be sure of"
    )
    assert stop_id not in content.decode("latin-1"), (
        "the file names the visit a token belongs to, so rewriting it would "
        "move a result to another customer"
    )

    # The app and the workbook disagree, and no edit to the file can hide it.
    current = _report(_preflight(client, ctx, content), 200)
    stop = next(
        item for item in client.get(
            f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]["owner"]
        ).json()["stops"] if item["id"] == stop_id
    )
    assert client.patch(
        f"/api/review/trip-plans/{plan['id']}/stops/{stop_id}",
        headers=ctx["headers"]["owner"],
        json={"row_version": stop["row_version"], "result_notes": "app"},
    ).status_code == 200
    edited = _edit_cells(content, {(token, "result_notes"): "workbook"})
    assert _cell_state(_report(_preflight(client, ctx, edited), 200), "result_notes") == "conflict"

    # A workbook this installation never issued has nothing to compare against.
    forged = _set_cell(edited, "导入信息 请勿修改", "B2", text="not-issued")
    response = _preflight(client, ctx, forged)
    assert response.status_code == 422, response.status_code
    assert "not issued by this installation" in response.text, response.text[:200]
    assert current["preview_digest"], "the preview does not say what it was based on"


def check_a_choice_expires_when_the_plan_moves(client: TestClient, ctx: dict) -> None:
    """A choice made about one set of values is not applied to another.

    The reader chose between the workbook and the application while the
    application held B. If it holds C by the time they submit, the choice was
    about something else, and applying it would overwrite C unseen.
    """
    plan, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]
    stop_id = _first_visit(baseline)["stop_id"]

    def write(notes: str) -> None:
        stop = next(
            item for item in client.get(
                f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]["owner"]
            ).json()["stops"] if item["id"] == stop_id
        )
        assert client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop_id}",
            headers=ctx["headers"]["owner"],
            json={"row_version": stop["row_version"], "result_notes": notes},
        ).status_code == 200

    write("B")
    uploaded = _edit_cells(content, {(token, "result_notes"): "A"})
    report = _report(_preflight(client, ctx, uploaded), 200)
    assert _cell_state(report, "result_notes") == "conflict"

    write("C")
    response = _commit(client, ctx, uploaded, report, {token: {"result_notes": "workbook"}})
    assert response.status_code == 409, response.status_code
    detail = response.json()["detail"]
    assert detail["report"], "the reader is not given the new comparison to choose from"
    assert detail["report"]["resolutions_cleared"] is True, detail["report"].keys()
    conn = fixture.get_db()
    assert conn.execute(
        "SELECT result_notes FROM trip_plan_stops WHERE id = ?", (stop_id,)
    ).fetchone()[0] == "C", "the stale choice overwrote what the app held"

    # Choosing again against the new comparison works.
    again = _report(_preflight(client, ctx, uploaded), 200)
    assert _report(_commit(client, ctx, uploaded, again,
                           {token: {"result_notes": "workbook"}}), 200)["status"] == "completed"
    assert conn.execute(
        "SELECT result_notes FROM trip_plan_stops WHERE id = ?", (stop_id,)
    ).fetchone()[0] == "A"


def check_preflight_refuses_what_commit_would(client: TestClient, ctx: dict) -> None:
    """Anything that would stop the import is said before the button is pressed."""
    plan, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]

    # Reported as done, but not when it happened.
    edited = _edit_cells(content, {(token, "result_status"): "已拜访 / Visited"})
    report = _report(_preflight(client, ctx, edited), 200)
    assert report["can_commit"] is False, "the panel would have offered to import this"
    codes = {issue["code"] for issue in report["issues"]}
    assert "incomplete_result" in codes, codes

    # A formula reports a value nobody typed and nobody can see.
    formula = _set_cell(
        content, "现场执行", _result_ref(content, "会议记录 / Meeting notes"),
        formula='HYPERLINK("http://example.test","x")', text="cached",
    )
    report = _report(_preflight(client, ctx, formula), 200)
    assert report["can_commit"] is False
    assert "formula_cell" in {issue["code"] for issue in report["issues"]}


def check_the_upload_is_refused_at_the_door(client: TestClient, ctx: dict) -> None:
    """A body that cannot be a workbook is turned away before it is read."""
    for filename, payload, says in (
        ("notes.txt", b"hello", "Only .xlsx"),
        ("empty.xlsx", b"", "empty"),
    ):
        response = client.post(
            "/api/review/trip-working/preflight",
            headers=ctx["headers"]["owner"],
            files={"file": (filename, payload, MIME)},
        )
        assert response.status_code == 400, (filename, response.status_code)
        # Refused for what it is, not for failing to unzip further in.
        assert says in response.text, (filename, response.text[:160])


def check_a_choice_that_cannot_be_saved_is_said_beside_the_choice(
    client: TestClient, ctx: dict
) -> None:
    """A conflict has two answers, and each is judged on its own.

    The workbook says the visit happened but not when; the app says it was
    skipped. Choosing the workbook leaves a row that cannot be saved, and
    choosing the app leaves one that can - so the reader is told which is
    which beside the dropdown, instead of finding out after submitting.
    """
    plan, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]
    stop_id = _first_visit(baseline)["stop_id"]

    stop = next(
        item for item in client.get(
            f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]["owner"]
        ).json()["stops"] if item["id"] == stop_id
    )
    assert client.patch(
        f"/api/review/trip-plans/{plan['id']}/stops/{stop_id}",
        headers=ctx["headers"]["owner"],
        json={"row_version": stop["row_version"], "result_status": "Skipped"},
    ).status_code == 200

    uploaded = _edit_cells(content, {(token, "result_status"): "已拜访 / Visited"})
    report = _report(_preflight(client, ctx, uploaded), 200)
    row = _first_visit(report)
    assert _cell_state(report, "result_status") == "conflict"
    combinations = row["unsaveable_combinations"]
    assert combinations == [{
        "choices": {"result_status": "workbook"},
        "message": combinations[0]["message"] if combinations else None,
    }], (
        "the panel is not told which choice would leave the visit unsaveable: "
        f"{combinations}"
    )
    assert "actually happened" in combinations[0]["message"]
    # One of the two choices works, so the workbook is not blocked outright.
    assert report["can_commit"] is False and report["requires_resolution"] is True
    assert not any(
        issue["code"] == "incomplete_result" for issue in report["issues"]
    ), "a workable choice exists, so nothing should be blocking"

    # Choosing the one that cannot be saved is refused, with the report.
    refused = _commit(client, ctx, uploaded, report, {token: {"result_status": "workbook"}})
    assert refused.status_code == 422, refused.status_code
    detail = refused.json()["detail"]
    assert detail["report"], "the refusal arrives without the comparison it is about"
    assert "actually happened" in detail["message"], detail["message"]

    # And the one that can be saved goes through.
    accepted = _report(
        _commit(client, ctx, uploaded, report, {token: {"result_status": "current"}}), 200)
    assert accepted["status"] == "completed"
    conn = fixture.get_db()
    assert conn.execute(
        "SELECT result_status FROM trip_plan_stops WHERE id = ?", (stop_id,)
    ).fetchone()[0] == "Skipped"


def check_a_row_with_no_workable_choice_is_blocked(client: TestClient, ctx: dict) -> None:
    """When neither answer can be saved, the workbook is stopped in preflight."""
    plan, content, baseline = _fresh_plan(client, ctx)
    token = _first_visit(baseline)["token"]
    stop_id = _first_visit(baseline)["stop_id"]

    stop = next(
        item for item in client.get(
            f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]["owner"]
        ).json()["stops"] if item["id"] == stop_id
    )
    # The app already reports the visit as done, without saying when - the
    # shape a database from before that rule was added is in.
    assert client.patch(
        f"/api/review/trip-plans/{plan['id']}/stops/{stop_id}",
        headers=ctx["headers"]["owner"],
        json={"row_version": stop["row_version"], "result_status": "Visited",
              "actual_visit_date": "2026-09-16", "actual_visit_period": "AM"},
    ).status_code == 200
    fixture.close_db()
    conn = fixture.get_db()
    conn.execute(
        "UPDATE trip_plan_stops SET actual_visit_date = NULL, "
        "actual_visit_period = NULL, result_notes = 'app' WHERE id = ?", (stop_id,))
    conn.commit()

    uploaded = _edit_cells(content, {
        (token, "result_status"): "需要跟进 / Follow-up Needed",
        (token, "result_notes"): "workbook",
    })
    report = _report(_preflight(client, ctx, uploaded), 200)
    combinations = _first_visit(report)["unsaveable_combinations"]
    assert [item["choices"] for item in combinations] == [
        {"result_status": "current"}, {"result_status": "workbook"},
    ], combinations
    assert "incomplete_result" in {issue["code"] for issue in report["issues"]}
    assert report["can_commit"] is False


def check_a_mixture_of_choices_is_judged_as_the_mixture(
    client: TestClient, ctx: dict
) -> None:
    """Each conflict is chosen separately, so each combination is its own row.

    Taking the workbook's status while keeping the app's date is a different
    result from taking both, and only some of those combinations can be saved.
    Judging only "all from the workbook" and "all from the app" would let a
    mixture through to fail on submit.
    """
    plan, _ = _working(client, ctx)
    stop_id = next(
        stop["id"] for stop in plan["stops"] if stop.get("stop_kind") != "free"
    )

    def save(**fields):
        stop = next(
            item for item in client.get(
                f"/api/review/trip-plans/{plan['id']}", headers=ctx["headers"]["owner"]
            ).json()["stops"] if item["id"] == stop_id
        )
        response = client.patch(
            f"/api/review/trip-plans/{plan['id']}/stops/{stop_id}",
            headers=ctx["headers"]["owner"],
            json={"row_version": stop["row_version"], **fields},
        )
        assert response.status_code == 200, response.text[:200]

    # Exported while the visit was reported as done, with its time.
    save(result_status="Visited", actual_visit_date="2026-09-16",
         actual_visit_period="AM")
    content = client.get(
        f"/api/review/trip-plans/{plan['id']}/working.xlsx",
        headers=ctx["headers"]["owner"],
    ).content
    baseline = _report(_preflight(client, ctx, content), 200)
    token = _first_visit(baseline)["token"]

    # The app moved all three on; the workbook moved the same three elsewhere.
    save(result_status="Skipped", actual_visit_date="2026-09-20",
         actual_visit_period="PM")
    uploaded = _edit_cells(content, {
        (token, "result_status"): "需要跟进 / Follow-up Needed",
        (token, "actual_visit_date"): None,
        (token, "actual_visit_period"): "未填写 / Not answered",
    })
    report = _report(_preflight(client, ctx, uploaded), 200)
    row = _first_visit(report)
    assert set(row["conflicts"]) == {
        "result_status", "actual_visit_date", "actual_visit_period",
    }, row["conflicts"]

    unsaveable = {
        tuple(sorted(item["choices"].items()))
        for item in row["unsaveable_combinations"]
    }
    assert unsaveable, "no mixture was reported as unsaveable"
    # Reported as needing follow-up with the time taken from the workbook,
    # which cleared it: that mixture cannot be saved.
    bad = (("actual_visit_date", "workbook"), ("actual_visit_period", "current"),
           ("result_status", "workbook"))
    assert tuple(sorted(bad)) in unsaveable, (
        f"the mixture the audit found is not reported: {sorted(unsaveable)}"
    )
    # Keeping the app's time with the workbook's status is fine.
    good = (("actual_visit_date", "current"), ("actual_visit_period", "current"),
            ("result_status", "workbook"))
    assert tuple(sorted(good)) not in unsaveable, (
        "a mixture that can be saved was reported as unsaveable"
    )
    # Some mixture works, so the workbook itself is not blocked.
    assert not any(
        issue["code"] == "incomplete_result" for issue in report["issues"]
    ), report["issues"]

    # The server refuses the bad mixture rather than saving half of it.
    refused = _commit(client, ctx, uploaded, report, {token: dict(bad)})
    assert refused.status_code == 422, refused.status_code
    assert "actually happened" in refused.json()["detail"]["message"]
    conn = fixture.get_db()
    assert conn.execute(
        "SELECT result_status FROM trip_plan_stops WHERE id = ?", (stop_id,)
    ).fetchone()[0] == "Skipped", "half of a refused mixture was saved"

    accepted = _report(_commit(client, ctx, uploaded, report, {token: dict(good)}), 200)
    assert accepted["status"] == "completed"
    row = conn.execute(
        "SELECT result_status, actual_visit_date, actual_visit_period "
        "FROM trip_plan_stops WHERE id = ?", (stop_id,)
    ).fetchone()
    assert tuple(row) == ("Follow-up Needed", "2026-09-20", "PM"), tuple(row)


def run() -> None:
    try:
        with TestClient(fixture.app) as client:
            ctx = fixture._seed(client)
            check_preflight_is_read_only_and_token_bound(client, ctx)
            check_workbook_only_and_downstream_impact(client, ctx)
            check_current_only_and_both_same_merge(client, ctx)
            check_conflict_requires_field_resolution(client, ctx)
            check_reparse_and_downstream_chain(client, ctx)
            check_strict_marker(client, ctx)
        check_the_file_cannot_vouch_for_itself(client, ctx)
        check_a_choice_expires_when_the_plan_moves(client, ctx)
        check_preflight_refuses_what_commit_would(client, ctx)
        check_the_upload_is_refused_at_the_door(client, ctx)
        check_a_choice_that_cannot_be_saved_is_said_beside_the_choice(client, ctx)
        check_a_row_with_no_workable_choice_is_blocked(client, ctx)
        check_a_mixture_of_choices_is_judged_as_the_mixture(client, ctx)
        print("PASS: trip working workbook preflight, token binding, three-way merge, impacts, and atomic import")
    finally:
        fixture.close_db()
        shutil.rmtree(fixture.TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
