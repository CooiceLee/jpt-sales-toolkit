"""Transactional invalidation helpers for Trip Planner route dependencies."""

from __future__ import annotations

import json
from collections.abc import Iterable

from ..repositories.base import now_iso


STALE_MESSAGES = {
    "route_settings_changed": "Route settings changed. Preview and save the route again.",
    "stop_added": "A stop was added. Preview and save the route again.",
    "stop_schedule_changed": "A stop date, stay, or sequence changed. Preview and save the route again.",
    "stop_order_changed": "The stop order changed. Preview and save the route again.",
    "stop_removed": "A stop was removed. Preview and save the route again.",
    "customer_location_changed": "A customer route location changed. Preview and save the route again.",
    "customer_merged": "A customer in this route was merged. Preview and save the route again.",
    "visit_location_changed": "A saved visit location changed. Preview and save the route again.",
}

ROUTE_LOCATION_FIELDS = frozenset(
    {
        "address",
        "city",
        "postal_code",
        "country",
        "normalized_address",
        "lat",
        "lng",
    }
)


def stale_itinerary_summary(reason: str, timestamp: str) -> str:
    return json.dumps(
        {
            "valid": False,
            "stale": True,
            "reason": reason,
            "invalidated_at": timestamp,
            "warnings": [
                STALE_MESSAGES.get(
                    reason,
                    "The itinerary is out of date. Preview and save it again.",
                )
            ],
        },
        ensure_ascii=False,
    )


def _unique_ids(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values if value})


def route_dependencies_for_customers(conn, customer_ids: Iterable[str]) -> dict:
    """Return active stop and plan IDs before a customer mutation/rebind."""
    ids = _unique_ids(customer_ids)
    if not ids:
        return {"stop_ids": [], "plan_ids": []}
    marks = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT s.id AS stop_id, s.plan_id
        FROM trip_plan_stops s
        JOIN trip_plans p ON p.id = s.plan_id
        WHERE s.customer_id IN ({marks})
          AND s.archived_at IS NULL
          AND p.archived_at IS NULL
        """,
        ids,
    ).fetchall()
    return {
        "stop_ids": _unique_ids(row["stop_id"] for row in rows),
        "plan_ids": _unique_ids(row["plan_id"] for row in rows),
    }


def clear_locked_overrides_for_stops(
    conn,
    stop_ids: Iterable[str],
    actor_id: str,
    timestamp: str,
) -> int:
    """Prevent old manual metrics from surviving a changed route endpoint."""
    ids = _unique_ids(stop_ids)
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    cursor = conn.execute(
        f"""
        UPDATE trip_plan_legs
        SET mode_locked = 0,
            updated_at = ?, updated_by = ?, row_version = row_version + 1
        WHERE mode_locked = 1
          AND (from_stop_id IN ({marks}) OR to_stop_id IN ({marks}))
        """,
        (timestamp, actor_id, *ids, *ids),
    )
    return cursor.rowcount


def clear_locked_overrides_for_free_stops(
    conn,
    free_stop_ids: Iterable[str],
    actor_id: str,
    timestamp: str,
) -> int:
    ids = _unique_ids(free_stop_ids)
    if not ids:
        return 0
    marks = ",".join("?" for _ in ids)
    cursor = conn.execute(
        f"""
        UPDATE trip_plan_legs
        SET mode_locked = 0,
            updated_at = ?, updated_by = ?, row_version = row_version + 1
        WHERE mode_locked = 1
          AND (
              from_free_stop_id IN ({marks})
              OR to_free_stop_id IN ({marks})
          )
        """,
        (timestamp, actor_id, *ids, *ids),
    )
    return cursor.rowcount


def invalidate_trip_plan_ids(
    conn,
    plan_ids: Iterable[str],
    actor_id: str,
    reason: str,
    *,
    timestamp: str | None = None,
) -> int:
    """Archive active legs and stale generated plans in the caller transaction."""
    ids = _unique_ids(plan_ids)
    if not ids:
        return 0
    timestamp = timestamp or now_iso()
    marks = ",".join("?" for _ in ids)
    conn.execute(
        f"""
        UPDATE trip_plan_legs
        SET archived_at = ?, updated_at = ?, updated_by = ?,
            row_version = row_version + 1
        WHERE plan_id IN ({marks}) AND archived_at IS NULL
        """,
        (timestamp, timestamp, actor_id, *ids),
    )
    for table in ("trip_plan_stops", "trip_plan_free_stops"):
        conn.execute(
            f"""
            UPDATE {table}
            SET confirmation_status = 'needs_reconfirmation',
                updated_at = ?, updated_by = ?, row_version = row_version + 1
            WHERE plan_id IN ({marks}) AND archived_at IS NULL
              AND confirmation_status = 'confirmed'
            """,
            (timestamp, actor_id, *ids),
        )
    cursor = conn.execute(
        f"""
        UPDATE trip_plans
        SET itinerary_generated_at = NULL,
            itinerary_summary = ?,
            updated_at = ?, updated_by = ?, row_version = row_version + 1
        WHERE id IN ({marks}) AND archived_at IS NULL
          AND (itinerary_generated_at IS NOT NULL OR itinerary_summary IS NOT NULL)
        """,
        (
            stale_itinerary_summary(reason, timestamp),
            timestamp,
            actor_id,
            *ids,
        ),
    )
    return cursor.rowcount


def invalidate_customer_route_dependencies(
    conn,
    customer_ids: Iterable[str],
    actor_id: str,
    reason: str,
    *,
    timestamp: str | None = None,
) -> int:
    timestamp = timestamp or now_iso()
    dependencies = route_dependencies_for_customers(conn, customer_ids)
    clear_locked_overrides_for_stops(
        conn,
        dependencies["stop_ids"],
        actor_id,
        timestamp,
    )
    return invalidate_trip_plan_ids(
        conn,
        dependencies["plan_ids"],
        actor_id,
        reason,
        timestamp=timestamp,
    )
