"""Schema 13: a visit may be unanswered, and says when it actually happened.

The two answers a visit records - whether a sample and whether a quote are
needed - used to be stored as a plain 0 or 1, so a box nobody touched and a
deliberate "no" were the same value. SQLite cannot loosen NOT NULL in place,
so the table every leg and briefing points at has to be rebuilt. These checks
are about what the rebuild must not lose.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from backend.repositories.trip_planning_schema import (
    apply_trip_planning_schema_v13)
from test_safe_upgrade import _restore_schema12_stops

ROOT = Path(__file__).parent
STAMP = "2026-08-01T00:00:00Z"


def _schema12_database() -> sqlite3.Connection:
    """A database on schema 12 holding a plan, its stops and what points at them."""
    conn = sqlite3.connect(":memory:")
    conn.executescript((ROOT / "backend" / "schema.sql").read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO users (id,username,display_name,role,password_hash,"
        "is_active,created_at) VALUES ('u1','ann','Ann','leader','h',1,?)", (STAMP,))
    conn.execute(
        "INSERT INTO customers (id,display_name,normalized_name,created_at,"
        "updated_at,row_version) VALUES ('c1','Alpha GmbH','alpha gmbh',?,?,1)",
        (STAMP, STAMP))
    conn.execute(
        "INSERT INTO leads (id,customer_id,display_id,title,owner_id,"
        "sales_stage,created_at,created_by,updated_at,updated_by,row_version) "
        "VALUES ('l1','c1','L-1','Frame welding','u1','Following',?,?,?,?,1)",
        (STAMP, "u1", STAMP, "u1"))
    conn.execute(
        "INSERT INTO lead_activities (id,lead_id,actor_id,action_type,summary,"
        "created_at) VALUES ('a1','l1','u1','follow_up','Visited Alpha',?)",
        (STAMP,))
    conn.execute(
        "INSERT INTO trip_plans (id,title,owner_id,start_date,end_date,status,"
        "created_at,created_by,updated_at,updated_by,row_version) VALUES "
        "('p1','September trip','u1','2026-09-01','2026-09-20','Active',?,?,?,?,1)",
        (STAMP, "u1", STAMP, "u1"))
    for index, (stop_id, sample, quote, status) in enumerate((
        ("s1", 1, 1, "Visited"),
        ("s2", 0, 0, "Planned"),
        ("s3", 1, 0, "Follow-up Needed"),
    ), start=1):
        conn.execute(
            "INSERT INTO trip_plan_stops (id,plan_id,customer_id,lead_id,"
            "sequence_no,planned_date,planned_start_period,duration_half_days,"
            "confirmation_status,visit_purpose,notes,result_status,result_notes,"
            "visit_customer_needs,visit_competitor,visit_budget,"
            "visit_decision_maker,visit_next_action,visit_followup_due_date,"
            "visit_sample_needed,visit_quote_needed,result_activity_id,"
            "followup_activity_id,created_at,created_by,updated_at,updated_by,"
            "row_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,?)",
            (stop_id, "p1", "c1", "l1", index, f"2026-09-0{index}", "AM", 2,
             "confirmed", f"目的 {index}", f"备注 {index}", status,
             f"结果 {index}", "需求", "对手", "预算", "决策人", "下一步",
             "2026-10-01", sample, quote, "a1", "a1", STAMP, "u1", STAMP, "u1",
             index + 1),
        )
    conn.execute(
        "INSERT INTO trip_plan_legs (id,plan_id,leg_key,sequence_no,from_kind,"
        "from_stop_id,to_kind,to_stop_id,selected_mode,created_at,created_by,"
        "updated_at,updated_by,row_version) VALUES "
        "('leg1','p1','s1>s2',1,'stop','s1','stop','s2','drive',?,?,?,?,1)",
        (STAMP, "u1", STAMP, "u1"))
    conn.execute(
        "INSERT INTO trip_visit_briefings (id,stop_id,created_at,created_by,"
        "updated_at,updated_by,row_version) VALUES ('b1','s1',?,?,?,?,1)",
        (STAMP, "u1", STAMP, "u1"))
    # PRAGMA foreign_keys only takes effect outside a transaction, and the
    # inserts above opened one.
    conn.commit()
    _restore_schema12_stops(conn)
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _stops(conn: sqlite3.Connection) -> list[dict]:
    names = [row[1] for row in conn.execute("PRAGMA table_info(trip_plan_stops)")]
    return [
        dict(zip(names, row))
        for row in conn.execute(
            f"SELECT {', '.join(names)} FROM trip_plan_stops ORDER BY id"
        )
    ]


def _indexes(conn: sqlite3.Connection) -> set:
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND tbl_name = 'trip_plan_stops' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _migrate(conn: sqlite3.Connection) -> None:
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    apply_trip_planning_schema_v13(conn)
    orphans = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert not orphans, f"the rebuild left rows pointing at nothing: {orphans}"
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def check_nothing_stored_on_a_stop_is_lost() -> None:
    """Every column of every stop reads back the same, in a rebuilt table."""
    conn = _schema12_database()
    before = _stops(conn)
    indexes = _indexes(conn)
    legs = sorted(conn.execute(
        "SELECT id, from_stop_id, to_stop_id FROM trip_plan_legs"))
    briefings = sorted(conn.execute("SELECT id, stop_id FROM trip_visit_briefings"))

    _migrate(conn)

    after = _stops(conn)
    assert len(after) == len(before) == 3, f"{len(before)} stops became {len(after)}"
    changed = {"visit_sample_needed", "visit_quote_needed"}
    for old, new in zip(before, after):
        for column, value in old.items():
            if column in changed:
                continue
            assert new[column] == value, (
                f"stop {old['id']} lost {column}: {value!r} became {new[column]!r}"
            )
    assert _indexes(conn) == indexes, (
        f"the rebuild left the table without its indexes: {_indexes(conn)}"
    )
    assert sorted(conn.execute(
        "SELECT id, from_stop_id, to_stop_id FROM trip_plan_legs")) == legs, (
        "a leg no longer points at the stop it was travelling to"
    )
    assert sorted(conn.execute(
        "SELECT id, stop_id FROM trip_visit_briefings")) == briefings, (
        "a visit briefing lost the stop it was prepared for"
    )
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def check_an_untouched_box_stops_claiming_an_answer() -> None:
    """A stored 1 is kept; a stored 0 becomes "not answered"."""
    conn = _schema12_database()
    _migrate(conn)
    answers = {
        row["id"]: (row["visit_sample_needed"], row["visit_quote_needed"])
        for row in _stops(conn)
    }
    assert answers["s1"] == (1, 1), f"answers that were given were lost: {answers['s1']}"
    assert answers["s2"] == (None, None), (
        f"boxes nobody touched were upgraded into a deliberate no: {answers['s2']}"
    )
    assert answers["s3"] == (1, None), f"one answer of two survived wrongly: {answers['s3']}"

    stored = {row["id"]: row for row in _stops(conn)}
    for stop in stored.values():
        assert stop["actual_visit_date"] is None, (
            "the planned date was written in as the date the visit happened: "
            f"{stop['actual_visit_date']!r}"
        )
        assert stop["actual_visit_period"] is None

    # And the new shape accepts all three states, including the deliberate no.
    conn.execute(
        "UPDATE trip_plan_stops SET visit_sample_needed = 0, "
        "actual_visit_date = '2026-09-02', actual_visit_period = 'PM' "
        "WHERE id = 's2'"
    )
    row = conn.execute(
        "SELECT visit_sample_needed, actual_visit_date, actual_visit_period "
        "FROM trip_plan_stops WHERE id = 's2'"
    ).fetchone()
    assert row == (0, "2026-09-02", "PM"), row


def check_running_it_again_changes_nothing() -> None:
    """A second start must not rebuild a table that is already the new shape."""
    conn = _schema12_database()
    _migrate(conn)
    once = _stops(conn)
    conn.execute(
        "UPDATE trip_plan_stops SET visit_quote_needed = 0 WHERE id = 's1'"
    )
    edited = _stops(conn)
    _migrate(conn)
    assert _stops(conn) == edited, "a second start rewrote stored answers"
    assert edited != once, "the fixture did not actually change anything"


def check_a_column_it_does_not_know_stops_the_rebuild() -> None:
    """A column the new table has no place for is refused, not dropped."""
    conn = _schema12_database()
    conn.execute("ALTER TABLE trip_plan_stops ADD COLUMN local_only TEXT")
    conn.execute("UPDATE trip_plan_stops SET local_only = 'keep me'")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        apply_trip_planning_schema_v13(conn)
    except RuntimeError as error:
        assert "local_only" in str(error), error
    else:
        raise AssertionError("a stored column was dropped without a word")
    conn.rollback()
    assert conn.execute(
        "SELECT local_only FROM trip_plan_stops WHERE id = 's1'"
    ).fetchone()[0] == "keep me", "the refused rebuild still changed the table"


def run() -> None:
    check_nothing_stored_on_a_stop_is_lost()
    check_an_untouched_box_stops_claiming_an_answer()
    check_running_it_again_changes_nothing()
    check_a_column_it_does_not_know_stops_the_rebuild()
    print("PASS: schema 13 rebuilds trip stops without losing what they hold")


if __name__ == "__main__":
    sys.exit(run())
