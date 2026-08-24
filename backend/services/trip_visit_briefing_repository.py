"""Persistence and validation for one visit briefing per customer stop."""

from __future__ import annotations

import json
import math

from ..repositories.base import ConflictError, generate_uuid


CONFIRMATION_STATUSES = {
    "unconfirmed",
    "tentative",
    "confirmed",
    "needs_reconfirmation",
    "cancelled",
}
LOCATION_FIELDS = (
    "name", "address", "city", "postal_code", "country", "lat", "lng",
    "use_customer_default",
)
CUSTOMER_TEAM_FIELDS = ("name", "title", "phone", "email", "notes")
CONTACT_FIELDS = (
    "source_contact_id", "name", "position", "email", "phone", "role", "notes",
)
PARTICIPANT_FIELDS = (
    "user_id", "display_name", "role", "responsibility", "notes",
)
CHANNEL_PARTNER_COMPANION_FIELDS = (
    "company_name", "name", "position", "phone", "email", "role", "notes",
)
EQUIPMENT_FIELDS = (
    "kind", "model", "specification", "quantity", "owner_team", "notes",
)
AGENDA_FIELDS = ("topic", "owner", "preparation", "expected_outcome")


def _json(value, fallback):
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback
    return decoded


def _text(value):
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _finite(value, field: str, lower: float, upper: float):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(number) or not lower <= number <= upper:
        raise ValueError(f"{field} must be between {lower:g} and {upper:g}")
    return number


def normalize_location(value) -> dict:
    if value is None:
        value = {"use_customer_default": True}
    if not isinstance(value, dict):
        raise ValueError("location must be an object")
    unknown = set(value) - set(LOCATION_FIELDS)
    if unknown:
        raise ValueError("Unknown location fields: " + ", ".join(sorted(unknown)))
    result = {field: _text(value.get(field)) for field in LOCATION_FIELDS[:-3]}
    result["lat"] = _finite(value.get("lat"), "location.lat", -90, 90)
    result["lng"] = _finite(value.get("lng"), "location.lng", -180, 180)
    result["use_customer_default"] = bool(value.get("use_customer_default", True))
    if not result["use_customer_default"]:
        if not result.get("name"):
            raise ValueError("location.name is required for a custom visit location")
        if result["lat"] is None or result["lng"] is None:
            raise ValueError("Custom visit location requires valid lat and lng")
    return result


def location_route_signature(value) -> tuple:
    """Return only the location values that can change route geometry."""
    location = normalize_location(value)
    if location["use_customer_default"]:
        return ("customer_default",)
    return (
        "visit_briefing",
        location.get("name"),
        location.get("address"),
        location.get("city"),
        location.get("postal_code"),
        location.get("country"),
        location.get("lat"),
        location.get("lng"),
    )


def _normalize_rows(value, fields: tuple[str, ...], label: str) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    rows = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"{label}[{index - 1}] must be an object")
        unknown = set(raw) - set(fields) - {"sequence_no"}
        if unknown:
            raise ValueError(
                f"Unknown fields in {label}[{index - 1}]: "
                + ", ".join(sorted(unknown))
            )
        row = {field: _text(raw.get(field)) for field in fields}
        sequence = raw.get("sequence_no")
        if sequence is None:
            sequence = index
        if isinstance(sequence, bool):
            raise ValueError(f"{label}[{index - 1}].sequence_no must be positive")
        try:
            sequence = int(sequence)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{label}[{index - 1}].sequence_no must be positive"
            ) from exc
        if sequence < 1:
            raise ValueError(f"{label}[{index - 1}].sequence_no must be positive")
        rows.append((sequence, index, row))
    rows.sort(key=lambda item: (item[0], item[1]))
    normalized = []
    for sequence, (_, _, row) in enumerate(rows, start=1):
        row["sequence_no"] = sequence
        normalized.append(row)
    return normalized


def normalize_payload(data: dict) -> dict:
    status = str(data.get("confirmation_status") or "unconfirmed")
    if status not in CONFIRMATION_STATUSES:
        raise ValueError("Unsupported confirmation_status")
    customer_team = _normalize_rows(
        data.get("customer_team"), CUSTOMER_TEAM_FIELDS, "customer_team"
    )
    for index, row in enumerate(customer_team):
        if not row.get("name"):
            raise ValueError(f"customer_team[{index}].name is required")

    contacts = _normalize_rows(data.get("contacts"), CONTACT_FIELDS, "contacts")
    for index, row in enumerate(contacts):
        if not any(row.get(field) for field in ("name", "email", "phone")):
            raise ValueError(
                f"contacts[{index}] requires at least name, email or phone"
            )

    participants = _normalize_rows(
        data.get("participants"), PARTICIPANT_FIELDS, "participants"
    )
    for index, row in enumerate(participants):
        if not row.get("user_id"):
            raise ValueError(f"participants[{index}].user_id is required")

    channel_partner_companions = _normalize_rows(
        data.get("channel_partner_companions"),
        CHANNEL_PARTNER_COMPANION_FIELDS,
        "channel_partner_companions",
    )
    for index, row in enumerate(channel_partner_companions):
        if not row.get("name"):
            raise ValueError(
                f"channel_partner_companions[{index}].name is required"
            )

    equipment = _normalize_rows(data.get("equipment"), EQUIPMENT_FIELDS, "equipment")
    for index, row in enumerate(equipment):
        if row.get("kind") not in {"demo", "po", "other"}:
            raise ValueError(f"equipment[{index}].kind must be demo, po or other")
        if not row.get("model") and not row.get("specification"):
            raise ValueError(
                f"equipment[{index}] requires model or specification"
            )

    agenda_items = _normalize_rows(
        data.get("agenda_items"), AGENDA_FIELDS, "agenda_items"
    )
    for index, row in enumerate(agenda_items):
        if not row.get("topic"):
            raise ValueError(f"agenda_items[{index}].topic is required")

    return {
        "confirmation_status": status,
        "timezone": _text(data.get("timezone")),
        "location": normalize_location(data.get("location")),
        "customer_team": customer_team,
        "contacts": contacts,
        "participants": participants,
        "channel_partner_companions": channel_partner_companions,
        "equipment": equipment,
        "agenda_items": agenda_items,
    }


class TripVisitBriefingRepository:
    def __init__(self, conn):
        self.conn = conn

    def get_row(self, stop_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM trip_visit_briefings WHERE stop_id = ?", (stop_id,)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def decode(row: dict | None) -> dict:
        if not row:
            return {
                "id": None,
                "exists": False,
                "row_version": None,
                "timezone": None,
                "location": normalize_location(None),
                "customer_team": [],
                "contacts": [],
                "participants": [],
                "channel_partner_companions": [],
                "equipment": [],
                "agenda_items": [],
            }
        return {
            "id": row.get("id"),
            "exists": True,
            "row_version": int(row.get("row_version") or 1),
            "timezone": row.get("timezone"),
            "location": normalize_location(_json(row.get("location_json"), None)),
            "customer_team": _json(row.get("customer_team_json"), []),
            "contacts": _json(row.get("contacts_json"), []),
            "participants": _json(row.get("participants_json"), []),
            "channel_partner_companions": _json(
                row.get("channel_partner_companions_json"), []
            ),
            "equipment": _json(row.get("equipment_json"), []),
            "agenda_items": _json(row.get("agenda_items_json"), []),
        }

    def replace(
        self,
        stop_id: str,
        payload: dict,
        actor_id: str,
        timestamp: str,
        expected_version: int | None,
    ) -> dict:
        existing = self.get_row(stop_id)
        if existing is None:
            if expected_version is not None:
                raise ConflictError(0, int(expected_version), {"stop_id": stop_id})
            briefing_id = generate_uuid()
            self.conn.execute(
                """
                INSERT INTO trip_visit_briefings (
                    id, stop_id, timezone, location_json, customer_team_json,
                    contacts_json, participants_json,
                    channel_partner_companions_json, equipment_json,
                    agenda_items_json, created_at, created_by, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    briefing_id,
                    stop_id,
                    payload["timezone"],
                    json.dumps(payload["location"], ensure_ascii=False),
                    json.dumps(payload["customer_team"], ensure_ascii=False),
                    json.dumps(payload["contacts"], ensure_ascii=False),
                    json.dumps(payload["participants"], ensure_ascii=False),
                    json.dumps(
                        payload["channel_partner_companions"], ensure_ascii=False
                    ),
                    json.dumps(payload["equipment"], ensure_ascii=False),
                    json.dumps(payload["agenda_items"], ensure_ascii=False),
                    timestamp,
                    actor_id,
                    timestamp,
                    actor_id,
                ),
            )
        else:
            current_version = int(existing.get("row_version") or 1)
            if expected_version is None or int(expected_version) != current_version:
                raise ConflictError(
                    current_version,
                    int(expected_version or 0),
                    {"id": existing.get("id"), "stop_id": stop_id},
                )
            cursor = self.conn.execute(
                """
                UPDATE trip_visit_briefings
                SET timezone = ?, location_json = ?, customer_team_json = ?,
                    contacts_json = ?, participants_json = ?,
                    channel_partner_companions_json = ?, equipment_json = ?,
                    agenda_items_json = ?, updated_at = ?, updated_by = ?,
                    row_version = row_version + 1
                WHERE stop_id = ? AND row_version = ?
                """,
                (
                    payload["timezone"],
                    json.dumps(payload["location"], ensure_ascii=False),
                    json.dumps(payload["customer_team"], ensure_ascii=False),
                    json.dumps(payload["contacts"], ensure_ascii=False),
                    json.dumps(payload["participants"], ensure_ascii=False),
                    json.dumps(
                        payload["channel_partner_companions"], ensure_ascii=False
                    ),
                    json.dumps(payload["equipment"], ensure_ascii=False),
                    json.dumps(payload["agenda_items"], ensure_ascii=False),
                    timestamp,
                    actor_id,
                    stop_id,
                    current_version,
                ),
            )
            if cursor.rowcount != 1:
                latest = self.get_row(stop_id) or {}
                raise ConflictError(
                    int(latest.get("row_version") or 0),
                    current_version,
                    {"id": latest.get("id"), "stop_id": stop_id},
                )
        return self.decode(self.get_row(stop_id))

    def available_contacts(self, customer_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT id, name, position, email, phone, whatsapp, is_primary
            FROM customer_contacts
            WHERE customer_id = ? AND archived_at IS NULL
            ORDER BY is_primary DESC, created_at, id
            """,
            (customer_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def available_participants(self, actor_id: str) -> list[dict]:
        actor_credential = self.conn.execute(
            """
            SELECT organization_id
            FROM user_credentials
            WHERE user_id = ? AND is_active = 1
            """,
            (actor_id,),
        ).fetchone()
        if actor_credential:
            rows = self.conn.execute(
                """
                SELECT u.id AS user_id, u.display_name, u.role, u.region
                FROM users u
                JOIN user_credentials uc
                  ON uc.user_id = u.id AND uc.is_active = 1
                WHERE u.is_active = 1 AND uc.organization_id = ?
                ORDER BY u.display_name COLLATE NOCASE, u.id
                """,
                (actor_credential["organization_id"],),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT u.id AS user_id, u.display_name, u.role, u.region
                FROM users u
                WHERE u.is_active = 1
                  AND (
                      u.id = ?
                      OR NOT EXISTS (
                          SELECT 1 FROM user_credentials uc
                          WHERE uc.user_id = u.id AND uc.is_active = 1
                      )
                  )
                ORDER BY u.display_name COLLATE NOCASE, u.id
                """,
                (actor_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def validate_snapshots(
        self,
        customer_id: str,
        contacts: list[dict],
        participants: list[dict],
        actor_id: str,
    ) -> None:
        available_contacts = {
            row["id"]: row for row in self.available_contacts(customer_id)
        }
        for item in contacts:
            source_id = item.get("source_contact_id")
            if source_id and source_id not in available_contacts:
                raise ValueError(
                    "source_contact_id must belong to the stop customer and be active"
                )
            if source_id:
                source = available_contacts[source_id]
                for field in ("name", "position", "email", "phone"):
                    if not item.get(field):
                        item[field] = source.get(field)
        users = {
            row["user_id"]: row for row in self.available_participants(actor_id)
        }
        for item in participants:
            user_id = item.get("user_id")
            if user_id not in users:
                raise ValueError("participant user_id must reference an active user")
            item["display_name"] = users[user_id]["display_name"]
            item["role"] = users[user_id]["role"]

    @staticmethod
    def effective_location(stop: dict, briefing: dict | None) -> dict:
        location = (briefing or {}).get("location") or normalize_location(None)
        if not location.get("use_customer_default", True):
            return {
                **location,
                "label": location.get("name"),
                "full_address": ", ".join(
                    str(value) for value in (
                        location.get("address"), location.get("city"),
                        location.get("postal_code"), location.get("country"),
                    ) if value
                ),
                "source": "visit_briefing",
            }
        return {
            "name": stop.get("customer_name") or stop.get("location_name"),
            "address": stop.get("address"),
            "city": stop.get("city"),
            "postal_code": stop.get("postal_code"),
            "country": stop.get("country"),
            "lat": stop.get("lat"),
            "lng": stop.get("lng"),
            "use_customer_default": True,
            "label": stop.get("customer_name") or stop.get("location_name"),
            "full_address": ", ".join(
                str(value) for value in (
                    stop.get("address"), stop.get("city"),
                    stop.get("postal_code"), stop.get("country"),
                ) if value
            ),
            "source": "customer",
        }
