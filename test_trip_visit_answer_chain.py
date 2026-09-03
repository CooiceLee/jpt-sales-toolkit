"""What a visit records once it may be left unanswered.

Schema 13 let the two answers a visit carries - whether a sample and whether a
quote are needed - stay unanswered. That only means anything if every place
that stores, reports or prints one keeps all three states, and if a visit
reported as done has to say when it actually happened.
"""

from __future__ import annotations

import json
import shutil

from fastapi.testclient import TestClient

import test_trip_planner_batch4 as fixture
import test_trip_planner_batch5_exports as plans


def _stop(client: TestClient, ctx: dict, plan_id: str, stop_id: str) -> dict:
    plan = fixture._require(
        client.get(f"/api/review/trip-plans/{plan_id}", headers=ctx["headers"]["owner"]),
        200,
    )
    return next(stop for stop in plan["stops"] if stop["id"] == stop_id)


def _save(client: TestClient, ctx: dict, plan_id: str, stop: dict, **fields):
    return client.patch(
        f"/api/review/trip-plans/{plan_id}/stops/{stop['id']}",
        headers=ctx["headers"]["owner"],
        json={"row_version": stop["row_version"], **fields},
    )


def _customer_stop(plan: dict) -> dict:
    return next(
        stop for stop in plan["stops"] if stop.get("stop_kind") != "free"
    )


def check_an_answer_can_be_yes_no_or_nothing(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """All three states survive a save and a read, and nothing is invented."""
    stop = _customer_stop(plan)
    assert stop["visit_sample_needed"] is None, (
        f"a new visit already claims an answer: {stop['visit_sample_needed']!r}"
    )

    for sent, expected in ((True, True), (False, False), (None, None)):
        current = _stop(client, ctx, plan["id"], stop["id"])
        response = _save(
            client, ctx, plan["id"], current, visit_sample_needed=sent,
            visit_quote_needed=sent,
        )
        assert response.status_code == 200, response.text
        saved = _stop(client, ctx, plan["id"], stop["id"])
        assert saved["visit_sample_needed"] == expected, (
            f"sending {sent!r} stored {saved['visit_sample_needed']!r}"
        )
        assert saved["visit_quote_needed"] == expected

    # And not sending the field at all leaves the stored answer alone.
    current = _stop(client, ctx, plan["id"], stop["id"])
    _save(client, ctx, plan["id"], current, visit_sample_needed=True)
    current = _stop(client, ctx, plan["id"], stop["id"])
    assert _save(
        client, ctx, plan["id"], current, result_notes="unrelated edit"
    ).status_code == 200
    kept = _stop(client, ctx, plan["id"], stop["id"])["visit_sample_needed"]
    assert kept is not None and bool(kept), (
        f"an edit that never mentioned the answer changed it to {kept!r}"
    )


def check_a_visit_reported_as_done_says_when(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """Visited and Follow-up Needed need the date and half-day it happened on."""
    stop_id = _customer_stop(plan)["id"]

    def reset() -> dict:
        response = _save(
            client, ctx, plan["id"], _stop(client, ctx, plan["id"], stop_id),
            result_status="Planned", actual_visit_date=None,
            actual_visit_period=None,
        )
        assert response.status_code == 200, response.status_code
        return _stop(client, ctx, plan["id"], stop_id)

    for status in ("Visited", "Follow-up Needed"):
        stop = reset()
        refused = _save(client, ctx, plan["id"], stop, result_status=status)
        assert refused.status_code == 400, (status, refused.status_code)
        assert "actually happened" in refused.text, refused.text[:200]

        half_only = _save(
            client, ctx, plan["id"], stop, result_status=status,
            actual_visit_date="2026-09-16",
        )
        assert half_only.status_code == 400, (
            f"{status} was accepted without the half-day it happened on: "
            f"{half_only.status_code}"
        )

        accepted = _save(
            client, ctx, plan["id"], stop, result_status=status,
            actual_visit_date="2026-09-16", actual_visit_period="PM",
        )
        assert accepted.status_code == 200, accepted.status_code
        saved = _stop(client, ctx, plan["id"], stop_id)
        assert (saved["actual_visit_date"], saved["actual_visit_period"]) == (
            "2026-09-16", "PM"
        )

    # Once a visit says when it happened, neither an unrelated edit nor
    # confirming the same status again has to repeat it.
    stop = _stop(client, ctx, plan["id"], stop_id)
    assert _save(
        client, ctx, plan["id"], stop, result_notes="follow-up call booked"
    ).status_code == 200
    again = _save(
        client, ctx, plan["id"], _stop(client, ctx, plan["id"], stop_id),
        result_status="Follow-up Needed",
    )
    assert again.status_code == 200, (
        "a visit that already says when it happened was asked to say it again: "
        f"{again.status_code} {again.text[:120]}"
    )

    # A stop that is only planned, or skipped, does not have to say when.
    for status in ("Planned", "Skipped"):
        response = _save(
            client, ctx, plan["id"], _stop(client, ctx, plan["id"], stop_id),
            result_status=status, actual_visit_date=None,
            actual_visit_period=None,
        )
        assert response.status_code == 200, (status, response.status_code)


def check_a_result_edit_cannot_slip_past_the_missing_time(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """Editing any result field on a visit reported as done needs the time too.

    A caller that sends only what changed - which is how results come back
    from a workbook - must not be able to edit a result while leaving out when
    the visit happened, just because it did not resend the status.
    """
    stop_id = _customer_stop(plan)["id"]
    # A stop that was reported as done before the rule existed: saved as done,
    # then left without the time it happened on.
    assert _save(
        client, ctx, plan["id"], _stop(client, ctx, plan["id"], stop_id),
        result_status="Visited", actual_visit_date="2026-09-16",
        actual_visit_period="AM",
    ).status_code == 200
    fixture.close_db()
    import sqlite3

    from backend.config import get_settings

    conn = sqlite3.connect(str(get_settings().db_path))
    try:
        conn.execute(
            "UPDATE trip_plan_stops SET actual_visit_date = NULL, "
            "actual_visit_period = NULL WHERE id = ?", (stop_id,)
        )
        conn.commit()
    finally:
        conn.close()

    history = _stop(client, ctx, plan["id"], stop_id)
    assert history["result_status"] == "Visited"
    assert history["actual_visit_date"] is None, "the fixture did not lose the time"

    # Editing what the customer needs is reporting on the visit.
    for field, value in (
        ("visit_customer_needs", "wants a 3kW demo"),
        ("visit_next_action", "send the quotation"),
        ("visit_sample_needed", True),
        ("result_notes", "went well"),
    ):
        refused = _save(
            client, ctx, plan["id"], _stop(client, ctx, plan["id"], stop_id),
            **{field: value},
        )
        assert refused.status_code == 400, (
            f"editing {field} on a visit reported as done was accepted without "
            f"the time it happened: {refused.status_code}"
        )
        assert "actually happened" in refused.text, refused.text[:160]

    # Moving the visit in the plan is not reporting on it, so history opens.
    moved = _save(
        client, ctx, plan["id"], _stop(client, ctx, plan["id"], stop_id),
        planned_date="2026-09-15",
    )
    assert moved.status_code == 200, (
        "a visit that predates the rule became unreachable for planning: "
        f"{moved.status_code} {moved.text[:160]}"
    )

    # And supplying the time alongside the edit is accepted.
    accepted = _save(
        client, ctx, plan["id"], _stop(client, ctx, plan["id"], stop_id),
        visit_customer_needs="wants a 3kW demo",
        actual_visit_date="2026-09-16", actual_visit_period="AM",
    )
    assert accepted.status_code == 200, accepted.text[:160]


def check_the_activity_does_not_record_an_answer_nobody_gave(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """The lead activity a visit writes keeps unanswered as unanswered."""
    stop = _stop(client, ctx, plan["id"], _customer_stop(plan)["id"])
    assert stop.get("lead_id"), "the fixture visit has no lead to write an activity to"
    assert _save(
        client, ctx, plan["id"], stop, result_status="Visited",
        actual_visit_date="2026-09-17", actual_visit_period="AM",
        visit_sample_needed=True, visit_quote_needed=None,
    ).status_code == 200
    saved = _stop(client, ctx, plan["id"], stop["id"])
    activities = fixture._require(
        client.get(
            f"/api/leads/{saved['lead_id']}/activities",
            headers=ctx["headers"]["owner"],
        ),
        200,
    )
    payloads = [
        json.loads(row["payload_json"])
        for row in activities
        if row.get("payload_json") and "Trip visit" in (row.get("summary") or "")
    ]
    assert payloads, "the visit wrote no activity to read back"
    recorded = payloads[0]
    assert recorded["sample_needed"] is True, recorded
    assert recorded["quote_needed"] is None, (
        f"the activity answered for the user: {recorded['quote_needed']!r}"
    )
    assert recorded["actual_visit_date"] == "2026-09-17", recorded
    assert recorded["actual_visit_period"] == "AM", recorded


def check_the_files_say_unanswered_rather_than_no(
    client: TestClient, ctx: dict, plan: dict
) -> None:
    """The daily report and the CSV print three states, not two."""
    base = f"/api/review/trip-plans/{plan['id']}"
    report = client.get(f"{base}/execution.md", headers=ctx["headers"]["owner"])
    assert report.status_code == 200, report.status_code
    markdown = report.text
    assert "未填写 / Not answered" in markdown, (
        "a question nobody answered is printed as an answer"
    )
    assert "是 / Yes" in markdown, "an answer that was given is not printed"
    assert "- Actually visited: 2026-09-17 AM" in markdown, (
        "the report does not say when the visit actually happened"
    )

    export = client.get(f"{base}/export.csv", headers=ctx["headers"]["owner"])
    assert export.status_code == 200, export.status_code
    csv_text = export.text
    header = csv_text.splitlines()[0]
    for column in ("sample_needed", "quote_needed", "actual_visit_date",
                   "actual_visit_period"):
        assert column in header, f"{column} is missing from the CSV: {header}"
    assert "未填写 / Not answered" in csv_text, (
        "the CSV answers a question nobody answered"
    )
    assert "2026-09-17" in csv_text, "the CSV does not carry the actual visit date"


def run() -> None:
    try:
        with TestClient(fixture.app) as client:
            ctx = fixture._seed(client)
            plan = plans._prepare_plan(client, ctx)
            check_an_answer_can_be_yes_no_or_nothing(client, ctx, plan)
            check_a_visit_reported_as_done_says_when(client, ctx, plan)
            check_a_result_edit_cannot_slip_past_the_missing_time(client, ctx, plan)
            check_the_activity_does_not_record_an_answer_nobody_gave(client, ctx, plan)
            check_the_files_say_unanswered_rather_than_no(client, ctx, plan)
        print("PASS: a visit answer stays unanswered until somebody answers it")
    finally:
        fixture.close_db()
        shutil.rmtree(fixture.TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    run()
