"""Build the correction-first report consumed by the import UI."""

from .alias_validation import alias_issues
from .bindings import bound_entity_keys
from .customer_matching import resolve_customers
from .contact_integrity import contact_integrity_issues
from .entity_scope import scope_entities
from .issue_format import finalize_issues
from .lifecycle_validation import lifecycle_issues
from .member_matching import resolve_members
from .prediction import predicted_counts
from .record_validation import record_issues
from .source_issues import mapping_issues, parser_issues
from .update_field_validation import update_field_issues


def build_preflight(conn, canonical: dict, resolutions: dict) -> tuple[dict, dict]:
    excluded = resolutions["excluded_records"]
    entities = scope_entities(canonical, excluded)
    scoped = {**canonical, "entities": entities}
    members, member_ids = resolve_members(conn, scoped, resolutions["member_mappings"])
    customers, customer_targets = resolve_customers(
        conn, scoped, resolutions["customer_mappings"], excluded
    )
    bound_keys = bound_entity_keys(conn, canonical["dataset_id"], entities)
    issues = parser_issues(canonical, excluded, entities, bound_keys)
    issues.extend(mapping_issues(members, customers))
    issues.extend(record_issues(entities, member_ids, customer_targets))
    issues.extend(update_field_issues(entities))
    issues.extend(contact_integrity_issues(entities, customer_targets))
    issues.extend(alias_issues(conn, entities, customer_targets))
    issues.extend(lifecycle_issues(
        conn, canonical["dataset_id"], entities, customer_targets
    ))
    if not any(entities.values()):
        issues.append({
            "severity": "error", "code": "no_import_records",
            "entity_type": None, "external_key": None, "field": None,
            "message": "Workbook contains no import records",
        })
    issues = finalize_issues(issues)
    errors = sum(item["severity"] == "error" for item in issues)
    warnings = sum(item["severity"] == "warning" for item in issues)
    summary = {
        "total": sum(len(items) for items in entities.values()),
        "entities": {name: len(items) for name, items in entities.items()},
        "issues": len(issues), "error_count": errors, "warning_count": warnings,
    }
    report = {
        "format": canonical.get("format"), "dataset_id": canonical.get("dataset_id"),
        "source_hash": canonical.get("source_hash"), "source": canonical.get("source"),
        "summary": summary, "canonical_summary": canonical.get("summary") or {},
        "predicted": predicted_counts(conn, canonical["dataset_id"], entities, excluded),
        "member_mappings": members, "customer_mappings": customers,
        "issues": issues, "can_commit": errors == 0,
    }
    context = {
        "entities": entities, "member_ids": member_ids,
        "customer_targets": customer_targets, "issues": issues,
        "excluded": excluded, "resolutions": resolutions,
    }
    return report, context
