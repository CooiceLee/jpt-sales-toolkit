"""Shared infrastructure for the offline Tech task exchange service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from ..repositories.base import DEFAULT_ORGANIZATION_ID
from .tech_task_exchange_contract import ASSIGNMENT_TYPE


class TechTaskExchangeError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class ExchangeCommonMixin:
    """Identity, transaction and response helpers shared by exchange flows."""

    def _validate_actor(self, package: dict, actor: dict) -> None:
        expected_role = "tech" if package["package_type"] == ASSIGNMENT_TYPE else "leader"
        if actor.get("role") != expected_role:
            raise TechTaskExchangeError(
                "wrong_import_role",
                f"This package must be imported by a {expected_role.title()} account",
                403,
            )
        if package["recipient_user_id"] != actor.get("id"):
            raise TechTaskExchangeError(
                "wrong_recipient", "This task package was issued for another member account", 403
            )
        if package["organization_id"] != self._organization_id(actor["id"]):
            raise TechTaskExchangeError(
                "organization_mismatch", "Task package belongs to another organization", 403
            )
        source_role = "leader" if package["package_type"] == ASSIGNMENT_TYPE else "tech"
        source = self._active_user(package["source_user_id"], source_role)
        if self._organization_id(source["id"]) != package["organization_id"]:
            raise TechTaskExchangeError(
                "source_organization_mismatch", "Package source belongs to another organization", 403
            )

    def _duplicate_state(self, package: dict) -> Optional[str]:
        existing = self.repo.get_batch(package.get("package_id"))
        if not existing:
            return None
        if existing["payload_sha256"] != package.get("payload_sha256"):
            raise TechTaskExchangeError(
                "package_id_reused", "Package ID was already used for different content", 409
            )
        return existing["status"]

    @staticmethod
    def _reject_source_installation(state: Optional[str]) -> None:
        if state == "exported":
            raise TechTaskExchangeError(
                "package_on_source_installation",
                "This package was exported by this installation and must be imported on the recipient installation",
                409,
            )

    def _active_user(self, user_id: Optional[str], role: str) -> dict:
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1 AND role = ?",
            (user_id, role),
        ).fetchone()
        if not row:
            raise TechTaskExchangeError(
                "invalid_member", f"Active {role.title()} member was not found", 400
            )
        return dict(row)

    def _organization_id(self, user_id: str) -> str:
        row = self.conn.execute(
            "SELECT organization_id FROM user_credentials WHERE user_id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
        return row[0] if row else DEFAULT_ORGANIZATION_ID

    def _default_leader_id(self) -> str:
        rows = self.conn.execute(
            "SELECT id FROM users WHERE role = 'leader' AND is_active = 1 ORDER BY created_at, id"
        ).fetchall()
        if len(rows) != 1:
            raise TechTaskExchangeError(
                "leader_recipient_required",
                "A single active Leader is required before exporting Tech results",
                409,
            )
        return rows[0][0]

    def _transactional(self, callback) -> None:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            callback()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json(value: Optional[dict]) -> Optional[str]:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value else None

    @staticmethod
    def _stored(value):
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
            except (json.JSONDecodeError, TypeError):
                return value
        return value

    @staticmethod
    def _task_table(task_type: str) -> str:
        return "pre_sales_tasks" if task_type == "pre_sales" else "after_sales_tasks"

    def _row(self, table: str, row_id: str) -> Optional[dict]:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return dict(row) if row else None

    def _task(self, task_type: str, task_id: str) -> Optional[dict]:
        return self._row(self._task_table(task_type), task_id)

    @staticmethod
    def _issue(
        severity: str, code: str, message: str, task_id: Optional[str] = None
    ) -> dict:
        result = {"severity": severity, "code": code, "message": message}
        if task_id:
            result["task_id"] = task_id
        return result

    def _report(self, package: dict, issues: list[dict], duplicate: bool = False) -> dict:
        raw_tasks = package.get("tasks")
        tasks = raw_tasks if isinstance(raw_tasks, list) else []
        blockers = sum(issue["severity"] in {"error", "conflict"} for issue in issues)
        return {
            "package_id": package.get("package_id"),
            "package_type": package.get("package_type"),
            "direction": package.get("direction"),
            "source_user_id": package.get("source_user_id"),
            "recipient_user_id": package.get("recipient_user_id"),
            "duplicate": duplicate,
            "can_import": blockers == 0,
            "issues": issues,
            "summary": {
                "total": len(tasks),
                "pre_sales_tasks": sum(
                    isinstance(item, dict) and item.get("task_type") == "pre_sales"
                    for item in tasks
                ),
                "after_sales_tasks": sum(
                    isinstance(item, dict) and item.get("task_type") == "after_sales"
                    for item in tasks
                ),
                "errors": sum(issue["severity"] == "error" for issue in issues),
                "warnings": sum(issue["severity"] == "warning" for issue in issues),
                "conflicts": sum(issue["severity"] == "conflict" for issue in issues),
                "skipped": 0,
            },
        }

    @staticmethod
    def _raise_blockers(issues: list[dict]) -> None:
        blockers = [issue for issue in issues if issue["severity"] in {"error", "conflict"}]
        if blockers:
            raise TechTaskExchangeError(
                "package_preflight_failed",
                f"Task package has {len(blockers)} blocking issue(s); run preflight and resolve them first",
                409,
            )
