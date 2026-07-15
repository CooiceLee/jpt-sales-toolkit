"""Leader alias CRUD and purpose-aware stable member resolution."""

from __future__ import annotations

import tempfile
from pathlib import Path

from backend.repositories import UserRepository, close_db, init_db
from backend.services.member_identity_errors import MemberIdentityError
from backend.services.member_identity_service import MemberIdentityService


def expect_code(action, code: str) -> None:
    try:
        action()
    except MemberIdentityError as exc:
        assert exc.code == code, (exc.code, code)
        return
    raise AssertionError(f"Expected member identity error: {code}")


def seed_users() -> dict[str, str]:
    users = UserRepository()
    ids = {
        "leader": users.create("leader.identity", "x", "Leader", "leader"),
        "sales": users.create("sales.identity", "x", "Alex", "sales"),
        "tech": users.create("tech.identity", "x", "Ayden", "tech"),
        "tech2": users.create("tech.two", "x", "Shared Tech", "tech"),
        "tech3": users.create("tech.three", "x", "Shared Tech", "tech"),
        "inactive": users.create("tech.inactive", "x", "Former Tech", "tech"),
        "inactive_sales": users.create("sales.inactive", "x", "Former Sales", "sales"),
    }
    users.deactivate(ids["inactive"])
    users.deactivate(ids["inactive_sales"])
    return ids


def assert_alias_crud(service: MemberIdentityService, ids: dict[str, str]) -> None:
    alias = service.create_alias(
        {"source_system": "Excel", "source_name": "  Alex Sales  ", "user_id": ids["sales"]},
        ids["leader"],
    )
    assert service.get_alias(alias["id"], ids["leader"])["user_id"] == ids["sales"]
    assert len(service.list_aliases(ids["leader"], "EXCEL")) == 1
    expect_code(
        lambda: service.create_alias(
            {"source_system": "excel", "source_name": "ＡＬＥＸ SALES", "user_id": ids["sales"]},
            ids["leader"],
        ),
        "alias_conflict",
    )
    resolved = service.resolve_member("ＡＬＥＸ  SALES", "excel", "owner")
    assert resolved == {"user_id": ids["sales"], "role": "sales", "matched_by": "alias"}
    changed = service.update_alias(
        alias["id"], {"source_name": "Primary Sales"}, ids["leader"]
    )
    assert changed["normalized_alias"] == "primary sales"
    assert service.delete_alias(alias["id"], ids["leader"])
    expect_code(lambda: service.get_alias(alias["id"], ids["leader"]), "alias_not_found")


def assert_resolution_rules(service: MemberIdentityService, ids: dict[str, str]) -> None:
    assert service.resolve_member(ids["sales"], "excel", "owner")["matched_by"] == "stable_id"
    assert service.resolve_member("Leader", "excel", "owner")["role"] == "leader"
    assert service.resolve_member("Alex", "excel", "collaborator")["role"] == "sales"
    assert service.resolve_member("TECH.IDENTITY", "excel", "task_assignee")["user_id"] == ids["tech"]
    expect_code(lambda: service.resolve_member("Ayden", "excel", "owner"), "role_mismatch")
    expect_code(lambda: service.resolve_member("Alex", "excel", "task_assignee"), "role_mismatch")
    expect_code(lambda: service.resolve_member("Former Tech", "excel", "task_assignee"), "inactive_member")
    expect_code(lambda: service.resolve_member("Former Sales", "excel", "owner"), "inactive_member")
    expect_code(lambda: service.resolve_member("Nobody", "excel", "owner"), "unknown_member")
    expect_code(lambda: service.resolve_member("Shared Tech", "excel", "task_assignee"), "ambiguous_member")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        close_db(); init_db(Path(temp_dir) / "identity.sqlite")
        ids = seed_users()
        service = MemberIdentityService()
        assert_alias_crud(service, ids)
        assert_resolution_rules(service, ids)
        expect_code(
            lambda: service.create_alias(
                {"source_system": "excel", "source_name": "No Access", "user_id": ids["sales"]},
                ids["sales"],
            ),
            "leader_required",
        )
        close_db()
    print("PASS: Leader alias CRUD and stable member role resolution")


if __name__ == "__main__":
    main()
