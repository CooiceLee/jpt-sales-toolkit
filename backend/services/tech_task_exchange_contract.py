"""Strict, minimal contract for offline Leader/Tech task packages."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .permission_policy import TECH_PRE_SALES_RESULT_FIELDS
from .tech_task_exchange_validation import (
    PackageValidationError,
    require_strings,
    validate_digest,
    validate_optional_string,
    validate_scalar_mapping,
    validate_timestamp,
)


PACKAGE_VERSION = "1.0"
ASSIGNMENT_TYPE = "tech_task_assignment"
RESULT_TYPE = "tech_task_results"
LEADER_TO_TECH = "leader_to_tech"
TECH_TO_LEADER = "tech_to_leader"

PACKAGE_FIELDS = frozenset({
    "package_type", "package_version", "package_id", "direction",
    "organization_id", "source_user_id", "recipient_user_id", "created_at",
    "parent_package_id", "tasks", "payload_sha256",
})
ASSIGNMENT_ITEM_FIELDS = frozenset({
    "task_type", "source_task_id", "source_lead_id", "source_customer_id",
    "base_row_version", "customer_context", "lead_context", "task",
})
RESULT_ITEM_FIELDS = frozenset({
    "task_type", "source_task_id", "source_lead_id", "base_row_version",
    "source_package_id", "changes",
})
CUSTOMER_CONTEXT_FIELDS = frozenset({
    "display_name", "industry", "customer_type", "country", "city", "region",
    "language", "company_size", "company_description",
})
LEAD_CONTEXT_FIELDS = frozenset({
    "display_id", "title", "sales_stage", "fulfillment_status", "service_status",
    "quality_grade", "urgency", "product_category", "product_series",
    "power_range", "wavelength", "application", "material", "quantity_text",
    "inquiry_date", "next_followup_date", "special_requirements",
    "potential_needs", "products_detail",
})
PRE_REQUEST_FIELDS = frozenset({
    "request_description", "sample_requested", "sample_params", "sample_parameters",
    "requirements", "request_date",
    "request_date_raw", "due_date_raw",
    "quantity_text", "competitor", "key_points", "concerns",
})
PRE_RESULT_FIELDS = TECH_PRE_SALES_RESULT_FIELDS
PRE_TASK_FIELDS = frozenset({"status", "request_json", "result_json", "due_date"})
AFTER_TASK_FIELDS = frozenset({
    "status", "issue_type", "issue_description", "solution",
    "customer_satisfaction", "lessons_learned", "remarks", "due_date",
})
PRE_CHANGE_FIELDS = frozenset({"status", "result_json"})
AFTER_CHANGE_FIELDS = frozenset({
    "status", "solution", "customer_satisfaction", "lessons_learned", "remarks",
})
PRE_STATUSES = frozenset({"Open", "In Progress", "Completed", "Cancelled"})
AFTER_STATUSES = frozenset({"Open", "In Progress", "Resolved", "Closed"})
AFTER_ISSUE_TYPES = frozenset({"Technical", "Quality", "Delivery", "Other"})


def parse_object(value: Any) -> dict:
    """Parse a stored JSON object; malformed or non-object values become empty."""
    if isinstance(value, dict):
        return deepcopy(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def project(source: dict, fields: frozenset[str]) -> dict:
    """Build a JSON-safe positive-field projection."""
    return {key: source.get(key) for key in fields if key in source}


def project_json(value: Any, fields: frozenset[str]) -> dict:
    return project(parse_object(value), fields)


def canonical_bytes(package: dict) -> bytes:
    unsigned = {key: value for key, value in package.items() if key != "payload_sha256"}
    return json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def package_digest(package: dict) -> str:
    return hashlib.sha256(canonical_bytes(package)).hexdigest()


def finalize_package(package: dict) -> dict:
    result = deepcopy(package)
    result["payload_sha256"] = package_digest(result)
    return result


def validate_package_envelope(package: Any) -> dict:
    if not isinstance(package, dict):
        raise PackageValidationError("invalid_package", "Task package must be a JSON object")
    unknown = set(package) - PACKAGE_FIELDS
    if unknown:
        raise PackageValidationError(
            "unknown_package_fields", f"Unsupported package fields: {', '.join(sorted(unknown))}"
        )
    required = {
        "package_type", "package_version", "package_id", "direction",
        "organization_id", "source_user_id", "recipient_user_id", "created_at", "tasks",
        "payload_sha256",
    }
    missing = sorted(key for key in required if package.get(key) in (None, ""))
    if missing:
        raise PackageValidationError("missing_package_fields", f"Missing package fields: {', '.join(missing)}")
    if package.get("package_version") != PACKAGE_VERSION:
        raise PackageValidationError("unsupported_package_version", "Unsupported Tech task package version")
    require_strings(
        package,
        {
            "package_type", "package_version", "package_id", "direction",
            "organization_id", "source_user_id", "recipient_user_id", "created_at",
        },
        "invalid_package_fields",
    )
    validate_optional_string(package, "parent_package_id", "invalid_parent_package_id")
    validate_timestamp(package["created_at"])
    validate_digest(package.get("payload_sha256"))
    expected = {
        ASSIGNMENT_TYPE: LEADER_TO_TECH,
        RESULT_TYPE: TECH_TO_LEADER,
    }.get(package.get("package_type"))
    if not expected or package.get("direction") != expected:
        raise PackageValidationError("invalid_package_direction", "Package type and direction do not match")
    if not isinstance(package.get("tasks"), list):
        raise PackageValidationError("invalid_tasks", "Task package items must be a list")
    if package_digest(package) != package.get("payload_sha256"):
        raise PackageValidationError("package_digest_mismatch", "Task package content checksum does not match")
    return package


def validate_assignment_item(item: Any) -> dict:
    return _validate_item(item, ASSIGNMENT_ITEM_FIELDS, assignment=True)


def validate_result_item(item: Any) -> dict:
    return _validate_item(item, RESULT_ITEM_FIELDS, assignment=False)


def _validate_item(item: Any, allowed: frozenset[str], *, assignment: bool) -> dict:
    if not isinstance(item, dict):
        raise PackageValidationError("invalid_task_item", "Task package item must be an object")
    unknown = set(item) - allowed
    if unknown:
        raise PackageValidationError("unknown_task_fields", f"Unsupported task fields: {', '.join(sorted(unknown))}")
    required = {"task_type", "source_task_id", "source_lead_id", "base_row_version"}
    if assignment:
        required |= {"source_customer_id", "customer_context", "lead_context", "task"}
    else:
        required |= {"source_package_id", "changes"}
    missing = sorted(key for key in required if item.get(key) is None or item.get(key) == "")
    if missing:
        raise PackageValidationError("missing_task_fields", f"Missing task fields: {', '.join(missing)}")
    id_fields = {"task_type", "source_task_id", "source_lead_id"}
    id_fields |= {"source_customer_id"} if assignment else {"source_package_id"}
    require_strings(item, id_fields, "invalid_task_identity")
    if item["task_type"] not in {"pre_sales", "after_sales"}:
        raise PackageValidationError("invalid_task_type", "Unsupported task type")
    if type(item.get("base_row_version")) is not int or item["base_row_version"] < 1:
        raise PackageValidationError("invalid_row_version", "Task base_row_version must be positive")
    if assignment:
        _validate_assignment_payload(item)
    else:
        _validate_changes(item)
    return item


def _validate_assignment_payload(item: dict) -> None:
    for key, allowed in (("customer_context", CUSTOMER_CONTEXT_FIELDS), ("lead_context", LEAD_CONTEXT_FIELDS)):
        value = item.get(key)
        if not isinstance(value, dict) or set(value) - allowed:
            raise PackageValidationError("unknown_context_fields", f"Unsupported {key} fields")
        validate_scalar_mapping(value, "invalid_context_values", key)
    task = item.get("task")
    allowed = PRE_TASK_FIELDS if item["task_type"] == "pre_sales" else AFTER_TASK_FIELDS
    if not isinstance(task, dict) or set(task) - allowed:
        raise PackageValidationError("unknown_task_payload_fields", "Unsupported task payload fields")
    if not isinstance(task.get("status"), str) or task["status"] not in (
        PRE_STATUSES if item["task_type"] == "pre_sales" else AFTER_STATUSES
    ):
        raise PackageValidationError("invalid_task_status", "Unsupported task status")
    if item["task_type"] == "pre_sales":
        request = task.get("request_json")
        result = task.get("result_json")
        if not isinstance(request, dict) or set(request) - PRE_REQUEST_FIELDS:
            raise PackageValidationError("unknown_request_fields", "Unsupported pre-sales request fields")
        if not isinstance(result, dict) or set(result) - PRE_RESULT_FIELDS:
            raise PackageValidationError("unknown_result_fields", "Unsupported pre-sales result fields")
        validate_scalar_mapping(request, "invalid_request_values", "request_json")
        validate_scalar_mapping(result, "invalid_result_values", "result_json")
        validate_scalar_mapping(
            {key: value for key, value in task.items() if key not in {"request_json", "result_json"}},
            "invalid_task_values",
            "pre-sales task",
        )
    elif not isinstance(task.get("issue_type"), str) or task["issue_type"] not in AFTER_ISSUE_TYPES:
        raise PackageValidationError("invalid_after_sales_task", "After-sales issue type is required")
    elif not isinstance(task.get("issue_description"), str) or not task["issue_description"].strip():
        raise PackageValidationError("invalid_after_sales_task", "After-sales issue description is required")
    else:
        validate_scalar_mapping(task, "invalid_task_values", "after-sales task")


def _validate_changes(item: dict) -> None:
    changes = item.get("changes")
    allowed = PRE_CHANGE_FIELDS if item["task_type"] == "pre_sales" else AFTER_CHANGE_FIELDS
    if not isinstance(changes, dict) or set(changes) - allowed:
        raise PackageValidationError("unknown_result_fields", "Unsupported Tech result fields")
    if not changes:
        raise PackageValidationError("empty_result_changes", "Tech result item has no changes")
    if "status" in changes:
        statuses = PRE_STATUSES if item["task_type"] == "pre_sales" else AFTER_STATUSES
        if not isinstance(changes["status"], str) or changes["status"] not in statuses:
            raise PackageValidationError("invalid_task_status", "Unsupported task status")
    if item["task_type"] == "pre_sales" and "result_json" in changes:
        value = changes["result_json"]
        if not isinstance(value, dict) or set(value) - PRE_RESULT_FIELDS:
            raise PackageValidationError("unknown_result_fields", "Unsupported pre-sales result fields")
        validate_scalar_mapping(value, "invalid_result_values", "result_json")
        validate_scalar_mapping(
            {key: value for key, value in changes.items() if key != "result_json"},
            "invalid_result_values",
            "pre-sales changes",
        )
    elif item["task_type"] == "after_sales":
        validate_scalar_mapping(changes, "invalid_result_values", "after-sales changes")
