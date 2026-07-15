"""Loss-aware contact migration for customer merge."""

from __future__ import annotations


CONTACT_FIELDS = ("name", "position", "phone", "whatsapp")


def merge_contacts(conn, source_id: str, target_id: str, now: str) -> dict:
    rows = conn.execute(
        """SELECT * FROM customer_contacts WHERE customer_id = ?
           ORDER BY archived_at IS NOT NULL, is_primary DESC, created_at""",
        (source_id,),
    ).fetchall()
    target_has_primary = conn.execute(
        """SELECT 1 FROM customer_contacts WHERE customer_id = ?
           AND archived_at IS NULL AND is_primary = 1 LIMIT 1""",
        (target_id,),
    ).fetchone() is not None
    result = {"moved": 0, "archived_duplicates": 0, "filled_fields": [], "conflicts": []}

    for raw in rows:
        contact = dict(raw)
        duplicate = _find_duplicate(conn, target_id, contact)
        source_active = contact.get("archived_at") is None
        if duplicate and source_active and duplicate["archived_at"] is not None:
            conn.execute(
                "UPDATE leads SET primary_contact_id = ? WHERE primary_contact_id = ?",
                (contact["id"], duplicate["id"]),
            )
            _retire_email(conn, dict(duplicate), now)
            duplicate = None
        if duplicate:
            _merge_duplicate(conn, contact, dict(duplicate), now, result)
            continue
        primary = int(bool(contact.get("is_primary")))
        if source_active and primary and target_has_primary:
            primary = 0
        conn.execute(
            """UPDATE customer_contacts SET customer_id = ?, is_primary = ?, updated_at = ?
               WHERE id = ?""",
            (target_id, primary, now, contact["id"]),
        )
        if source_active and primary:
            target_has_primary = True
        result["moved"] += 1
    return result


def _find_duplicate(conn, target_id: str, contact: dict):
    email = str(contact.get("email") or "").strip().lower()
    if not email:
        return None
    return conn.execute(
        """SELECT * FROM customer_contacts WHERE customer_id = ? AND lower(email) = ?
           ORDER BY archived_at IS NULL DESC, created_at LIMIT 1""",
        (target_id, email),
    ).fetchone()


def _merge_duplicate(conn, source: dict, target: dict, now: str, result: dict) -> None:
    updates = {}
    for field in CONTACT_FIELDS:
        source_value, target_value = source.get(field), target.get(field)
        if target_value in (None, "") and source_value not in (None, ""):
            updates[field] = source_value
            result["filled_fields"].append({
                "contact_id": target["id"], "field": field, "value": source_value,
            })
        elif source_value not in (None, "") and target_value not in (None, "") and source_value != target_value:
            result["conflicts"].append({
                "source_contact_id": source["id"], "target_contact_id": target["id"],
                "field": field, "source": source_value, "target": target_value,
                "resolution": "keep_target",
            })
    if updates:
        assignments = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"UPDATE customer_contacts SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), now, target["id"]),
        )
    conn.execute(
        "UPDATE leads SET primary_contact_id = ? WHERE primary_contact_id = ?",
        (target["id"], source["id"]),
    )
    archived_at = source.get("archived_at") or now
    email = _retired_value(source.get("email"), source["id"])
    conn.execute(
        """UPDATE customer_contacts SET customer_id = ?, email = ?, archived_at = ?,
           is_primary = 0, updated_at = ? WHERE id = ?""",
        (target["customer_id"], email, archived_at, now, source["id"]),
    )
    result["archived_duplicates"] += 1


def _retire_email(conn, contact: dict, now: str) -> None:
    conn.execute(
        "UPDATE customer_contacts SET email = ?, updated_at = ? WHERE id = ?",
        (_retired_value(contact.get("email"), contact["id"]), now, contact["id"]),
    )


def _retired_value(value, row_id: str) -> str:
    return f"{str(value or '').strip()}#merged-{row_id}"
