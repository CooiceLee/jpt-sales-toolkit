"""Preflight and atomic merge for the JPT field-work workbook."""

from __future__ import annotations

from typing import Optional

import hashlib
import json
from itertools import product

from .importing.dates import parse_excel_date, parse_date_text
from .importing.exceptions import UnsupportedWorkbookError
from .importing.workbook import read_workbook
from ..repositories.base import now_iso
from .trip_plan_service import RESULT_STATUS_NEEDING_ACTUAL_TIME
from .trip_export_working import (
    CONTEXT_HEADERS,
    FORMAT_VERSION,
    RESULT_COLUMNS,
    RESULT_FIELDS,
    RESULT_HEADERS,
    TOKEN_HEADER,
)

WORKING_SHEET = "现场执行"
KEY_SHEET = "导入信息 请勿修改"
# All the file is asked for: which workbook it is, and one token per row. Which
# visit a token belongs to, and what the row was exported holding, are read
# from the issuing installation's own record - a file cannot vouch for itself.
KEY_HEADERS = ["行 / Row", TOKEN_HEADER]
FIELD_LABELS = {field: header for header, field in RESULT_COLUMNS}
ANSWER_VALUES = {
    "": None,
    "未填写 / Not answered": None,
    "是 / Yes": True,
    "否 / No": False,
}
PERIOD_VALUES = {"": None, "未填写 / Not answered": None, "AM": "AM", "PM": "PM"}
STATUS_VALUES = {
    "已计划 / Planned": "Planned",
    "已拜访 / Visited": "Visited",
    "需要跟进 / Follow-up Needed": "Follow-up Needed",
    "已跳过 / Skipped": "Skipped",
}


class TripWorkingImportError(ValueError):
    """A user-correctable workbook problem with an optional preview report."""

    def __init__(self, message: str, report: Optional[dict] = None, status_code: int = 422):
        super().__init__(message)
        self.report = report
        self.status_code = status_code


def _text(value) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _cell(sheet, row_number: int, column: int):
    return sheet.row(row_number).value(column, "")


def _cell_object(sheet, row_number: int, column: int):
    return sheet.row(row_number).cell(column)


def _headers(sheet, row_number: int) -> dict[str, int]:
    return {
        str(value.value or "").strip(): column
        for column, value in sheet.row(row_number).cells.items()
        if str(value.value or "").strip()
    }


def _required_headers(actual: dict[str, int], expected: list[str], where: str) -> None:
    missing = [header for header in expected if header not in actual]
    if missing:
        raise UnsupportedWorkbookError(
            f"Invalid JPT field workbook: {where} is missing {', '.join(missing)}"
        )


def _parse_field(field: str, value, date_1904: bool):
    cell = value if hasattr(value, "value") else None
    value = cell.value if cell is not None else value
    if field == "result_status":
        text = str(value or "").strip()
        if text not in STATUS_VALUES:
            raise ValueError("choose a valid Result status")
        return STATUS_VALUES[text]
    if field in ("visit_sample_needed", "visit_quote_needed"):
        text = str(value or "").strip()
        if text not in ANSWER_VALUES:
            raise ValueError("choose Not answered, Yes, or No")
        return ANSWER_VALUES[text]
    if field == "actual_visit_period":
        text = str(value or "").strip()
        if text not in PERIOD_VALUES:
            raise ValueError("choose Not answered, AM, or PM")
        return PERIOD_VALUES[text]
    if field in ("actual_visit_date", "visit_followup_due_date"):
        if cell is not None:
            parsed, raw, disposition = parse_excel_date(cell, date_1904)
        else:
            raw = str(value or "").strip()
            parsed, disposition = parse_date_text(raw), "normalized_text"
            if not raw:
                disposition = "empty"
        if disposition == "empty":
            return None
        if parsed is None:
            # A fixed sentence: the page shows it in the reader's language, and
            # what was typed is in the cell the message already names.
            raise ValueError("This cell does not hold a date")
        return parsed
    return _text(value)


def _current_field(field: str, value):
    if field in ("visit_sample_needed", "visit_quote_needed"):
        return None if value is None else bool(int(value))
    if field in ("actual_visit_date", "visit_followup_due_date"):
        return parse_date_text(value) if value else None
    return _text(value) if field not in ("result_status", "actual_visit_period") else value


def _same(left, right) -> bool:
    return left == right


def _issue(code: str, message: str, *, token=None, field=None) -> dict:
    return {
        "code": code,
        "severity": "error",
        "message": message,
        "token": token,
        "field": field,
    }


def _read_workbook(content: bytes, filename: str) -> dict:
    book = read_workbook(content, filename)
    if WORKING_SHEET not in book.sheets or KEY_SHEET not in book.sheets:
        raise UnsupportedWorkbookError(
            f"Unsupported trip workbook. Expected {FORMAT_VERSION} with "
            f"sheets {WORKING_SHEET} and {KEY_SHEET}"
        )
    working = book.sheets[WORKING_SHEET]
    keys = book.sheets[KEY_SHEET]
    working_headers = _headers(working, 3)
    key_headers = _headers(keys, 5)
    _required_headers(working_headers, CONTEXT_HEADERS + RESULT_HEADERS + [TOKEN_HEADER], WORKING_SHEET)
    _required_headers(key_headers, KEY_HEADERS, KEY_SHEET)

    marker = str(_cell(keys, 1, 2) or "").strip()
    if marker != FORMAT_VERSION:
        raise UnsupportedWorkbookError(
            f"Unsupported trip workbook format {marker or '<missing>'}; expected {FORMAT_VERSION}"
        )
    workbook_id = _text(_cell(keys, 2, 2))
    if not workbook_id:
        raise UnsupportedWorkbookError("The field workbook does not identify itself")

    issues: list[dict] = []
    rows: list[dict] = []
    seen_tokens: set[str] = set()
    for number in sorted(working.rows):
        if number < 4 or not working.rows[number].nonempty():
            continue
        token = _text(_cell(working, number, working_headers[TOKEN_HEADER]))
        if not token:
            issues.append(_issue("missing_token", f"Visible row {number} has no row token"))
            continue
        if token in seen_tokens:
            issues.append(_issue("duplicate_token", "A visible row token appears more than once", token=token))
            continue
        seen_tokens.add(token)
        values = {}
        for header, field in RESULT_COLUMNS:
            cell = _cell_object(working, number, working_headers[header])
            if cell is not None and cell.formula:
                issues.append(_issue(
                    "formula_cell",
                    "A result cell holds a formula. Replace it with the value it "
                    "should report before importing.",
                    token=token, field=field,
                ))
                continue
            try:
                values[field] = _parse_field(field, cell, book.date_1904)
            except ValueError as exc:
                issues.append(_issue("invalid_field", str(exc), token=token, field=field))
        rows.append({"row": number, "token": token, "values": values})

    return {
        "format": marker,
        "workbook_id": workbook_id,
        "source_hash": book.source_hash,
        "generated_at": _text(_cell(keys, 3, 2)),
        "rows": rows,
        "issues": issues,
    }


def _impact_fields(fields: set[str], stop: dict) -> list[dict]:
    impacts = []
    if fields:
        impacts.append({
            "code": "trip_visit_activity",
            "label": "Trip visit activity",
            "detail": "The visit result activity will be created or updated for this lead.",
        })
    if fields & {"result_status", "visit_next_action", "visit_followup_due_date"} and stop.get("lead_id"):
        impacts.append({
            "code": "formal_followup",
            "label": "Formal follow-up and Lead",
            "detail": "A formal follow-up may be created, updated, or archived; the Lead follow-up date and stage may change.",
        })
    return impacts


# The only fields that decide whether a reported visit can be saved.
EXECUTION_TIME_FIELDS = ("result_status", "actual_visit_date", "actual_visit_period")


def _effective(comparisons: list[dict], stop: dict, choices: dict | None = None) -> dict:
    """The row as it would stand if this workbook were imported now.

    Each conflicted field is decided on its own, so the row depends on the
    combination and not on one answer for all of them: keeping the app's status
    while taking the workbook's date is a different row again.
    """
    choices = choices or {}
    effective = {field: _current_field(field, stop.get(field)) for field in RESULT_FIELDS}
    for comparison in comparisons:
        field = comparison["field"]
        if comparison["state"] == "workbook_only":
            effective[field] = comparison["uploaded"]
        elif comparison["state"] == "conflict" and choices.get(field) == "workbook":
            effective[field] = comparison["uploaded"]
    return effective


def _unsaveable_combinations(comparisons: list[dict], stop: dict,
                             row_conflicts: list[str]) -> list[dict]:
    """Every mixture of choices that would leave a row that cannot be saved.

    Only three fields decide it, so there are at most eight mixtures - few
    enough to work them all out here and hand the reader the answer for
    whichever one they are standing on, rather than letting them submit and
    find out.
    """
    deciding = [field for field in row_conflicts if field in EXECUTION_TIME_FIELDS]
    if not deciding:
        return []
    combinations = []
    for picks in product(("current", "workbook"), repeat=len(deciding)):
        choices = dict(zip(deciding, picks))
        message = _incomplete_result(_effective(comparisons, stop, choices))
        if message:
            combinations.append({"choices": choices, "message": message})
    return combinations


def _incomplete_result(effective: dict) -> Optional[str]:
    """Why this row could not be saved, in the same terms the app uses."""
    status = effective.get("result_status")
    if status not in RESULT_STATUS_NEEDING_ACTUAL_TIME:
        return None
    if effective.get("actual_visit_date") and effective.get("actual_visit_period"):
        return None
    return (
        "A visit reported as visited or needing follow-up needs the date and "
        "the half-day it actually happened on."
    )


def _preview_digest(rows: list[dict], parsed: dict) -> str:
    """What the reader was shown the database holding, in one value.

    A choice between the workbook and the application was made against these
    values. If any of them moves before the workbook is submitted, the choice
    was made about something else and has to be made again.
    """
    state = [
        [
            row["token"], row["stop_id"], row["row_version"],
            [[item["field"], item["current"]] for item in row["comparisons"]],
        ]
        for row in sorted(rows, key=lambda row: row["token"])
    ]
    payload = json.dumps(
        [parsed["workbook_id"], parsed["source_hash"], state],
        ensure_ascii=False, sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compare(parsed: dict, plan: Optional[dict], manifest: dict) -> dict:
    issues = list(parsed["issues"])
    rows = []
    conflicts = []
    stop_by_id = {
        stop.get("id"): stop
        for stop in (plan or {}).get("stops", [])
        if stop.get("stop_kind") == "customer"
    }
    seen = set()
    for item in parsed["rows"]:
        key = manifest.get(item["token"])
        if not key:
            issues.append(_issue(
                "unknown_token",
                "This row was not issued by this workbook, so there is nothing "
                "to compare it against.",
                token=item["token"],
            ))
            continue
        seen.add(item["token"])
        stop = stop_by_id.get(key["stop_id"])
        if not stop:
            issues.append(_issue("stop_not_found", "The visit no longer exists in this trip plan", token=item["token"]))
            continue
        comparisons = []
        row_conflicts = []
        changed_fields = set()
        for field in RESULT_FIELDS:
            baseline = key["baseline"].get(field)
            uploaded = item["values"].get(field)
            current = _current_field(field, stop.get(field))
            uploaded_changed = not _same(uploaded, baseline)
            current_changed = not _same(current, baseline)
            if uploaded_changed and current_changed:
                state = "both_same" if _same(uploaded, current) else "conflict"
            elif uploaded_changed:
                state = "workbook_only"
            elif current_changed:
                state = "current_only"
            else:
                state = "unchanged"
            if state in {"workbook_only", "conflict"}:
                changed_fields.add(field)
            if state == "conflict":
                row_conflicts.append(field)
                conflicts.append({"token": item["token"], "field": field})
            comparisons.append({
                "field": field,
                "label": FIELD_LABELS[field],
                "baseline": baseline,
                "uploaded": uploaded,
                "current": current,
                "state": state,
            })
        # Worked out for every mixture the reader can choose, so one that
        # would leave the visit unsaveable is said before they submit.
        unsaveable = _unsaveable_combinations(comparisons, stop, row_conflicts)
        deciding = [f for f in row_conflicts if f in EXECUTION_TIME_FIELDS]
        if deciding:
            # Blocked only when no mixture at all can produce a saveable row.
            if len(unsaveable) == 2 ** len(deciding):
                issues.append(_issue(
                    "incomplete_result", unsaveable[0]["message"], token=item["token"]
                ))
        else:
            message = _incomplete_result(_effective(comparisons, stop))
            if message and changed_fields:
                issues.append(_issue("incomplete_result", message, token=item["token"]))
        rows.append({
            "row": item["row"],
            "token": item["token"],
            "stop_id": key["stop_id"],
            "customer": stop.get("customer_name") or "",
            "planned_date": stop.get("planned_date") or "",
            "planned_period": stop.get("planned_start_period") or "",
            "row_version": int(stop.get("row_version") or 0),
            "comparisons": comparisons,
            "conflicts": row_conflicts,
            "unsaveable_combinations": unsaveable,
            "impacts": _impact_fields(changed_fields, stop),
        })
    for token in sorted(set(manifest) - seen):
        issues.append(_issue(
            "missing_visible_row",
            "A visit this workbook was issued for has no row to read.",
            token=token,
        ))
    plan_id = (plan or {}).get("id") or manifest_plan_id(manifest)
    title = (plan or {}).get("title") or plan_id
    return {
        "format": parsed["format"],
        "workbook_id": parsed["workbook_id"],
        "source_hash": parsed["source_hash"],
        "generated_at": parsed["generated_at"],
        "plan_id": plan_id,
        "plan_title": title,
        "rows": rows,
        "conflicts": conflicts,
        "issues": issues,
        "can_commit": not issues and not conflicts,
        "requires_resolution": bool(conflicts),
        "preview_digest": _preview_digest(rows, parsed),
    }


def manifest_plan_id(manifest: dict) -> Optional[str]:
    for row in manifest.values():
        return row.get("plan_id")
    return None


class TripWorkingImportService:
    def __init__(self, core):
        self.core = core

    def _manifest(self, workbook_id: str) -> dict:
        """What this installation issued this workbook with."""
        conn = self.core.lead_repo.conn
        rows = conn.execute(
            "SELECT r.row_token, r.stop_id, r.row_version, r.baseline_json, "
            "e.plan_id FROM trip_working_export_rows r "
            "JOIN trip_working_exports e ON e.workbook_id = r.workbook_id "
            "WHERE r.workbook_id = ?",
            (workbook_id,),
        ).fetchall()
        manifest = {}
        for row in rows:
            manifest[row["row_token"]] = {
                "token": row["row_token"],
                "stop_id": row["stop_id"],
                "row_version": int(row["row_version"]),
                "plan_id": row["plan_id"],
                "baseline": {
                    field: _parse_field(field, value, False)
                    for field, value in json.loads(row["baseline_json"]).items()
                },
            }
        return manifest

    def _read(self, content: bytes, filename: str, actor_id: str, actor_role: str):
        parsed = _read_workbook(content, filename)
        manifest = self._manifest(parsed["workbook_id"])
        if not manifest:
            raise TripWorkingImportError(
                "This workbook was not issued by this installation, so there is "
                "nothing to match its results against. Export a new field "
                "workbook from the plan and fill that in."
            )
        plan_id = manifest_plan_id(manifest)
        plan = self.core.get_trip_plan(plan_id, actor_id, actor_role)
        if not plan:
            parsed["issues"].append(_issue(
                "plan_not_found",
                "The trip plan this workbook was issued for is not available to "
                "this user.",
            ))
        return parsed, plan, manifest

    def preflight(self, content: bytes, filename: str, actor_id: str, actor_role: str) -> dict:
        parsed, plan, manifest = self._read(content, filename, actor_id, actor_role)
        return _compare(parsed, plan, manifest)

    def commit(
        self,
        content: bytes,
        filename: str,
        expected_source_hash: str,
        expected_preview_digest: str,
        resolutions: dict,
        actor_id: str,
        actor_role: str,
    ) -> dict:
        parsed = _read_workbook(content, filename)
        if parsed["source_hash"] != expected_source_hash:
            raise TripWorkingImportError(
                "The workbook changed after preflight. Run preflight again with the file you will submit.",
                status_code=409,
            )
        conn = self.core.lead_repo.conn
        savepoint = "trip_working_import"
        owns_transaction = not conn.in_transaction
        try:
            if owns_transaction:
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute(f"SAVEPOINT {savepoint}")
            manifest = self._manifest(parsed["workbook_id"])
            plan_id = manifest_plan_id(manifest)
            plan = self.core.get_trip_plan(plan_id, actor_id, actor_role) if manifest else None
            report = _compare(parsed, plan, manifest)
            # A choice between the workbook and the application was made about
            # what the application held then. If any of that moved, the choice
            # is about something else now and has to be made again.
            if report["preview_digest"] != expected_preview_digest:
                report["resolutions_cleared"] = True
                raise TripWorkingImportError(
                    "The plan changed after the preview. Review the new "
                    "comparison and choose again.",
                    report, 409,
                )
            if report["issues"]:
                raise TripWorkingImportError("The workbook cannot be imported until the blocking issues are fixed.", report)
            if report["conflicts"]:
                missing = []
                for conflict in report["conflicts"]:
                    choice = (resolutions.get(conflict["token"], {}) or {}).get(conflict["field"])
                    if choice not in {"workbook", "current"}:
                        missing.append(conflict)
                if missing:
                    report["missing_resolutions"] = missing
                    raise TripWorkingImportError("Resolve every field conflict before importing the workbook.", report)

            applied_rows = 0
            applied_fields = 0
            for row_report in report["rows"]:
                changes = {}
                for comparison in row_report["comparisons"]:
                    field = comparison["field"]
                    if comparison["state"] == "workbook_only":
                        changes[field] = comparison["uploaded"]
                    elif comparison["state"] == "conflict":
                        choice = (resolutions.get(row_report["token"], {}) or {}).get(field)
                        if choice == "workbook":
                            changes[field] = comparison["uploaded"]
                if not changes:
                    continue
                current = self.core._get_trip_stop(row_report["stop_id"])
                if not current or current.get("plan_id") != plan_id:
                    raise TripWorkingImportError("A visit disappeared while the workbook was being submitted.", report, 409)
                try:
                    self.core.trip_plan_service._require_actual_visit_time(current, changes)
                except ValueError as exc:
                    raise TripWorkingImportError(
                        f"{row_report['customer'] or row_report['token']}: {exc}",
                        report,
                    ) from exc
                timestamp = now_iso()
                update_data = {**changes, "updated_at": timestamp, "updated_by": actor_id,
                               "row_version": int(current.get("row_version") or 1) + 1}
                assignments = ", ".join(f"{field} = ?" for field in update_data)
                values = [*update_data.values(), row_report["stop_id"], plan_id, current["row_version"]]
                cursor = conn.execute(
                    f"UPDATE trip_plan_stops SET {assignments} "
                    "WHERE id = ? AND plan_id = ? AND archived_at IS NULL AND row_version = ?",
                    tuple(values),
                )
                if cursor.rowcount != 1:
                    raise TripWorkingImportError("A visit changed while the workbook was being submitted. Run preflight again.", report, 409)
                updated = self.core._get_trip_stop(row_report["stop_id"])
                if updated:
                    if any(field in changes for field in RESULT_FIELDS):
                        self.core._sync_trip_result_activity(updated, actor_id)
                    self.core._sync_trip_followup_activity(
                        updated, actor_id, previous_lead_id=current.get("lead_id")
                    )
                applied_rows += 1
                applied_fields += len(changes)
            report.update({"status": "completed", "committed_rows": applied_rows, "committed_fields": applied_fields})
            conn.execute(
                "UPDATE trip_working_exports SET last_imported_at = ?, "
                "last_imported_by = ? WHERE workbook_id = ?",
                (now_iso(), actor_id, parsed["workbook_id"]),
            )
            if applied_rows:
                conn.execute(
                    """
                    UPDATE trip_plans
                    SET updated_at = ?, updated_by = ?, row_version = row_version + 1
                    WHERE id = ? AND archived_at IS NULL
                    """,
                    (now_iso(), actor_id, plan_id),
                )
            if owns_transaction:
                conn.commit()
            else:
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            return report
        except Exception:
            if owns_transaction:
                conn.rollback()
            else:
                conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            raise


__all__ = ["TripWorkingImportError", "TripWorkingImportService"]
