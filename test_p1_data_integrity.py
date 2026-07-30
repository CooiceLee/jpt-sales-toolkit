"""Targeted regressions for permission-bearing and cross-store P1 writes."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from backend.repositories import (
    ActivityRepository,
    AttachmentRepository,
    AuditRepository,
    CustomerRepository,
    LeadRepository,
)
from backend.repositories.base import ConflictError, close_db, init_db
from backend.services.attachment_service import AttachmentService
from backend.services.lead_service import LeadService
from backend.services.spreadsheet_import.persistence_common import (
    apply_archive_action,
)


def open_database(root: Path) -> sqlite3.Connection:
    close_db()
    path = root / "database.sqlite"
    init_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for user_id, role in (
        ("leader", "leader"),
        ("sales-a", "sales"),
        ("sales-b", "sales"),
    ):
        conn.execute(
            """
            INSERT INTO users
                (id, username, password_hash, display_name, role, is_active, created_at)
            VALUES (?, ?, 'hash', ?, ?, 1, '2026-07-30T00:00:00')
            """,
            (user_id, user_id, user_id, role),
        )
    conn.commit()
    return conn


def seed_lead(conn: sqlite3.Connection, suffix: str) -> tuple[str, str]:
    customer_id = CustomerRepository(conn).create(
        {
            "display_name": f"Customer {suffix}",
            "normalized_name": f"customer {suffix}".lower(),
        },
        "leader",
        commit=False,
    )
    lead_id = LeadRepository(conn).create(
        {
            "customer_id": customer_id,
            "title": f"Lead {suffix}",
            "owner_id": "sales-a",
            "sales_stage": "Following",
        },
        "leader",
        commit=False,
    )
    conn.commit()
    return customer_id, lead_id


def active_owner(conn: sqlite3.Connection, lead_id: str) -> str:
    rows = conn.execute(
        """
        SELECT user_id
        FROM lead_assignments
        WHERE lead_id = ? AND assignment_type = 'owner' AND archived_at IS NULL
        """,
        (lead_id,),
    ).fetchall()
    assert len(rows) == 1
    return rows[0]["user_id"]


def test_owner_cas_precedes_assignment(
    conn: sqlite3.Connection,
    db_path: Path,
) -> None:
    _, lead_id = seed_lead(conn, "cas")
    other = sqlite3.connect(db_path)
    other.row_factory = sqlite3.Row

    class RacingLeadRepository(LeadRepository):
        fired = False

        def _build_update(self, entity_id, data, check_version=None):
            sql, params = super()._build_update(entity_id, data, check_version)
            if not self.fired:
                self.fired = True
                other.execute(
                    """
                    UPDATE leads
                    SET title = 'Concurrent edit',
                        updated_at = '2026-07-30T00:01:00',
                        row_version = row_version + 1
                    WHERE id = ?
                    """,
                    (entity_id,),
                )
                other.commit()
            return sql, params

    repo = RacingLeadRepository(conn)
    before = repo.get_by_id(lead_id)
    try:
        repo.update(
            lead_id,
            {"owner_id": "sales-b"},
            "leader",
            before["row_version"],
        )
    except ConflictError:
        pass
    else:
        raise AssertionError("Concurrent owner write must lose the lead CAS")

    current = repo.get_by_id(lead_id)
    assert current["title"] == "Concurrent edit"
    assert current["owner_id"] == "sales-a"
    assert active_owner(conn, lead_id) == "sales-a"
    assert not conn.in_transaction
    other.close()


def test_lead_service_write_boundary(conn: sqlite3.Connection) -> None:
    _, lead_id = seed_lead(conn, "service")
    service = LeadService(
        lead_repo=LeadRepository(conn),
        activity_repo=ActivityRepository(conn),
        audit_repo=AuditRepository(conn),
        customer_repo=CustomerRepository(conn),
    )
    before = service.lead_repo.get_by_id(lead_id)
    before_audits = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    before_activities = conn.execute(
        "SELECT COUNT(*) FROM lead_activities"
    ).fetchone()[0]
    original_create = service.activity_repo.create

    def fail_activity(*args, **kwargs):
        raise RuntimeError("injected activity failure")

    service.activity_repo.create = fail_activity
    try:
        service.update(
            lead_id,
            {"owner_id": "sales-b", "title": "Must roll back"},
            "leader",
            "leader",
            before["row_version"],
        )
    except RuntimeError as exc:
        assert "injected activity failure" in str(exc)
    else:
        raise AssertionError("Injected activity failure was not raised")

    after = service.lead_repo.get_by_id(lead_id)
    assert after["title"] == before["title"]
    assert after["owner_id"] == "sales-a"
    assert after["row_version"] == before["row_version"]
    assert active_owner(conn, lead_id) == "sales-a"
    assert conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] == before_audits
    assert (
        conn.execute("SELECT COUNT(*) FROM lead_activities").fetchone()[0]
        == before_activities
    )
    assert not conn.in_transaction

    service.activity_repo.create = original_create
    updated = service.update(
        lead_id,
        {"owner_id": "sales-b", "title": "Committed"},
        "leader",
        "leader",
        before["row_version"],
    )
    assert updated["owner_id"] == "sales-b"
    assert active_owner(conn, lead_id) == "sales-b"


def test_collaborator_allowlist(conn: sqlite3.Connection) -> None:
    _, lead_id = seed_lead(conn, "collaborator")
    repo = LeadRepository(conn)
    repo.add_assignment(lead_id, "sales-b", "collaborator", "leader")
    conn.commit()
    service = LeadService(
        lead_repo=repo,
        activity_repo=ActivityRepository(conn),
        audit_repo=AuditRepository(conn),
        customer_repo=CustomerRepository(conn),
    )

    before = repo.get_by_id(lead_id)
    quoted = service.update(
        lead_id,
        {"quotation_id": "Q-001"},
        "sales-b",
        "collaborator",
        before["row_version"],
    )
    assert quoted["quotation_id"] == "Q-001"
    assert quoted["sales_stage"] == "Quoted"

    try:
        service.update(
            lead_id,
            {"source_channel": "Private override"},
            "sales-b",
            "collaborator",
            quoted["row_version"],
        )
    except PermissionError as exc:
        assert "source_channel" in str(exc)
    else:
        raise AssertionError("Unlisted collaborator field must be denied")
    assert repo.get_by_id(lead_id)["source_channel"] is None


def test_attachment_compensation(
    conn: sqlite3.Connection,
    upload_dir: Path,
) -> None:
    _, lead_id = seed_lead(conn, "attachment")
    repo = AttachmentRepository(conn)
    service = AttachmentService(upload_dir=upload_dir, repo=repo)

    try:
        service.upload(
            lead_id,
            "report",
            None,
            b"pdf",
            "application/pdf",
            "leader",
        )
    except ValueError as exc:
        assert "filename" in str(exc).lower()
    else:
        raise AssertionError("Missing filename must be rejected")

    original_create = repo.create

    def fail_create(*args, **kwargs):
        original_create(*args, **kwargs)
        raise RuntimeError("injected database failure")

    repo.create = fail_create
    try:
        service.upload(
            lead_id,
            "report",
            "failure.pdf",
            b"failure",
            "application/pdf",
            "leader",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Injected attachment database failure was not raised")
    assert conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 0
    assert not list(upload_dir.rglob("*.*"))
    assert not conn.in_transaction

    repo.create = original_create
    first = service.upload(
        lead_id,
        "report",
        "report.pdf",
        b"same bytes",
        "application/pdf",
        "leader",
    )
    exact_duplicate = service.upload(
        lead_id,
        "report",
        "report.pdf",
        b"same bytes",
        "application/pdf",
        "leader",
    )
    other_category = service.upload(
        lead_id,
        "quotation",
        "report.pdf",
        b"same bytes",
        "application/pdf",
        "leader",
    )
    other_name = service.upload(
        lead_id,
        "report",
        "renamed.pdf",
        b"same bytes",
        "application/pdf",
        "leader",
    )
    assert exact_duplicate["id"] == first["id"]
    assert len({first["id"], other_category["id"], other_name["id"]}) == 3

    original_update = repo.update_metadata

    def fail_update(*args, **kwargs):
        original_update(*args, **kwargs)
        raise RuntimeError("injected metadata database failure")

    repo.update_metadata = fail_update
    old_path = service.get_file_path(first["id"])
    new_path = upload_dir / lead_id / "quotation" / first["stored_name"]
    try:
        service.update_metadata(
            first["id"],
            lead_id,
            "leader",
            category="quotation",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Injected metadata database failure was not raised")

    assert repo.get_by_id(first["id"])["category"] == "report"
    assert old_path is not None and old_path.exists()
    assert not new_path.exists()
    assert not conn.in_transaction


def test_archive_versions_and_active_write_guard(
    conn: sqlite3.Connection,
) -> None:
    customer_id, lead_id = seed_lead(conn, "archive")
    customer_repo = CustomerRepository(conn)
    lead_repo = LeadRepository(conn)
    customer_before = customer_repo.get_by_id(customer_id)
    lead_before = lead_repo.get_by_id(lead_id)

    apply_archive_action(conn, "customers", customer_id, "ARCHIVE", "leader")
    apply_archive_action(conn, "leads", lead_id, "ARCHIVE", "leader")
    conn.commit()
    customer_archived = customer_repo.get_by_id(customer_id)
    lead_archived = lead_repo.get_by_id(lead_id)
    assert customer_archived["row_version"] == customer_before["row_version"] + 1
    assert lead_archived["row_version"] == lead_before["row_version"] + 1

    for write in (
        lambda: customer_repo.update(
            customer_id,
            {"display_name": "Stale customer edit"},
            "leader",
            customer_before["row_version"],
        ),
        lambda: lead_repo.update(
            lead_id,
            {"title": "Stale lead edit"},
            "leader",
            lead_before["row_version"],
        ),
    ):
        try:
            write()
        except ValueError:
            pass
        else:
            raise AssertionError("Archived record accepted a normal update")

    apply_archive_action(conn, "customers", customer_id, "RESTORE", "leader")
    apply_archive_action(conn, "leads", lead_id, "RESTORE", "leader")
    conn.commit()
    customer_restored = customer_repo.get_by_id(customer_id)
    lead_restored = lead_repo.get_by_id(lead_id)
    assert customer_restored["row_version"] == customer_before["row_version"] + 2
    assert lead_restored["row_version"] == lead_before["row_version"] + 2
    assert customer_restored["archived_at"] is None
    assert lead_restored["archived_at"] is None


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jpt_p1_integrity_") as directory:
        root = Path(directory)
        conn = open_database(root)
        try:
            test_owner_cas_precedes_assignment(conn, root / "database.sqlite")
            test_lead_service_write_boundary(conn)
            test_collaborator_allowlist(conn)
            test_attachment_compensation(conn, root / "attachments")
            test_archive_versions_and_active_write_guard(conn)
        finally:
            conn.close()
            close_db()
    print("PASS: P1 data-integrity regressions")


if __name__ == "__main__":
    main()
