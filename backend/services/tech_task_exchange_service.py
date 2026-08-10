"""Facade for offline task-only exchange between Leader and Tech installs."""

from __future__ import annotations

import sqlite3
from typing import Optional

from ..repositories.base import get_db
from ..repositories.tech_task_exchange_repository import TechTaskExchangeRepository
from .tech_task_exchange_adoption import ExactSourceAdoptionMixin
from .tech_task_exchange_assignment import AssignmentSyncMixin
from .tech_task_exchange_common import ExchangeCommonMixin, TechTaskExchangeError
from .tech_task_exchange_contract import (
    ASSIGNMENT_TYPE,
    PackageValidationError,
    validate_package_envelope,
)
from .tech_task_exchange_export import AssignmentExportMixin
from .tech_task_exchange_merge_policy import ResultMergePolicyMixin
from .tech_task_exchange_replica_context import ReplicaContextMixin
from .tech_task_exchange_replica_task import ReplicaTaskMixin
from .tech_task_exchange_result_helpers import ResultStateMixin
from .tech_task_exchange_results import ResultMergeMixin
from .tech_task_exchange_snapshot import AssignmentSnapshotMixin


class TechTaskExchangeService(
    AssignmentExportMixin,
    ExactSourceAdoptionMixin,
    AssignmentSyncMixin,
    AssignmentSnapshotMixin,
    ReplicaContextMixin,
    ReplicaTaskMixin,
    ResultMergeMixin,
    ResultMergePolicyMixin,
    ResultStateMixin,
    ExchangeCommonMixin,
):
    """Create, validate and atomically apply minimal Tech task packages."""

    def __init__(self, conn: Optional[sqlite3.Connection] = None):
        self.conn = conn or get_db()
        self.repo = TechTaskExchangeRepository(self.conn)

    def preflight(self, package: dict, actor: dict) -> dict:
        try:
            validate_package_envelope(package)
            self._validate_actor(package, actor)
            duplicate = self._duplicate_state(package)
            self._reject_source_installation(duplicate)
            if duplicate == "imported":
                return self._report(package, [], duplicate=True)
            if package["package_type"] == ASSIGNMENT_TYPE:
                issues = self._assignment_issues(package)
            else:
                issues, _ = self._result_analysis(package)
            return self._report(package, issues)
        except (PackageValidationError, TechTaskExchangeError) as error:
            issue = self._issue(
                "error", getattr(error, "code", "invalid_package"), str(error)
            )
            return self._report(package if isinstance(package, dict) else {}, [issue])

    def import_package(self, package: dict, actor: dict) -> dict:
        validate_package_envelope(package)
        self._validate_actor(package, actor)
        duplicate = self._duplicate_state(package)
        self._reject_source_installation(duplicate)
        if duplicate == "imported":
            return self._idempotent_report(package)
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            # Recheck inside the write lock. Preflight approval is never trusted.
            duplicate = self._duplicate_state(package)
            self._reject_source_installation(duplicate)
            if duplicate == "imported":
                self.conn.rollback()
                return self._idempotent_report(package)
            issues, result = self._analyze_and_apply(package, actor)
            self.repo.record_batch(package, "imported", imported_by=actor["id"])
            self.conn.commit()
            report = self._report(package, issues)
            report.update(result)
            report["idempotent"] = False
            return report
        except Exception:
            self.conn.rollback()
            raise

    def _analyze_and_apply(self, package: dict, actor: dict) -> tuple[list[dict], dict]:
        if package["package_type"] == ASSIGNMENT_TYPE:
            issues = self._assignment_issues(package)
            self._raise_blockers(issues)
            return issues, self._apply_assignments(package, actor)
        issues, plans = self._result_analysis(package)
        self._raise_blockers(issues)
        return issues, self._apply_results(package, actor, plans)

    def _idempotent_report(self, package: dict) -> dict:
        report = self._report(package, [], duplicate=True)
        report.update({"imported": 0, "updated": 0, "idempotent": True})
        return report


__all__ = ["TechTaskExchangeError", "TechTaskExchangeService"]
