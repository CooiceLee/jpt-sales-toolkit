"""Apply explicit exclusions and cascade them to dependent canonical records."""

from .resolutions import is_excluded

ENTITY_ORDER = (
    "customers", "aliases", "contacts", "leads", "assignments", "activities",
    "pre_sales_tasks", "after_sales_tasks",
)


def scope_entities(canonical: dict, excluded: set[str]) -> dict[str, list[dict]]:
    raw = canonical.get("entities") or {}
    scoped = {
        kind: [item for item in raw.get(kind, [])
               if not is_excluded(item, excluded)
               and str(item.get("action") or "UPSERT").upper() != "SKIP"]
        for kind in ENTITY_ORDER
    }
    removed_customers = _removed_keys(raw.get("customers", []), scoped["customers"])
    if removed_customers:
        for kind in ("aliases", "contacts", "leads"):
            scoped[kind] = [item for item in scoped[kind]
                            if item.get("customer_key") not in removed_customers]
    removed_leads = _removed_keys(raw.get("leads", []), scoped["leads"])
    if removed_leads:
        for kind in ("assignments", "activities", "pre_sales_tasks", "after_sales_tasks"):
            scoped[kind] = [item for item in scoped[kind]
                            if item.get("lead_key") not in removed_leads]
    return scoped


def _removed_keys(original: list[dict], scoped: list[dict]) -> set[str]:
    remaining = {item.get("external_key") for item in scoped}
    return {item.get("external_key") for item in original
            if item.get("external_key") not in remaining}
