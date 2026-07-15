"""Shared temporary-database fixture for quality-issue permission tests."""

from __future__ import annotations

from pathlib import Path

from backend.repositories import (
    ActivityRepository, AfterSalesTaskRepository, CustomerRepository,
    LeadRepository, PreSalesTaskRepository, UserRepository, close_db, get_db, init_db,
)
from backend.repositories.authorization_schema import DEFAULT_ORGANIZATION_ID
from backend.repositories.base import generate_uuid, now_iso


def actor(ids: dict, name: str) -> dict:
    return {"id": ids[name], "role": "leader" if name == "leader" else name.split("_")[0]}


def build_fixture(data_dir: Path) -> dict:
    """Create active, archived, bound, and unbound quality issues."""
    data_dir.mkdir(parents=True, exist_ok=True)
    close_db(); init_db(data_dir / "database.sqlite")
    users = UserRepository()
    roles = {
        "leader": "leader", "sales_owner": "sales", "sales_collab": "sales",
        "sales_watcher": "sales", "sales_other": "sales",
        "tech_assigned": "tech", "tech_other": "tech",
    }
    ids = {name: users.create(name, "x", name, role) for name, role in roles.items()}
    customers = CustomerRepository()
    customer = customers.create({"display_name": "Owner Customer", "normalized_name": "owner customer"}, ids["leader"])
    other_customer = customers.create({"display_name": "Other Customer", "normalized_name": "other customer"}, ids["leader"])
    archived_customer = customers.create({"display_name": "Archived Customer", "normalized_name": "archived customer"}, ids["leader"])
    leads = LeadRepository()
    lead = leads.create({"customer_id": customer, "title": "Owner Lead", "sales_stage": "Following", "owner_id": ids["sales_owner"]}, ids["leader"])
    other_lead = leads.create({"customer_id": other_customer, "title": "Other Lead", "sales_stage": "New", "owner_id": ids["sales_other"]}, ids["leader"])
    archived_lead = leads.create({"customer_id": customer, "title": "Archived Lead", "sales_stage": "Lost", "owner_id": ids["sales_owner"]}, ids["leader"])
    customer_archived_lead = leads.create({"customer_id": archived_customer, "title": "Customer Archived Lead", "sales_stage": "Lost", "owner_id": ids["sales_owner"]}, ids["leader"])
    assignment = leads.add_assignment(lead, ids["sales_collab"], "collaborator", ids["leader"])
    leads.add_assignment(lead, ids["sales_watcher"], "watcher", ids["leader"])
    leads.conn.commit()
    conn, now = get_db(), now_iso()
    contact, archived_contact, alias = generate_uuid(), generate_uuid(), generate_uuid()
    for item_id, name, archived in ((contact, "Alice", None), (archived_contact, "Old Alice", now)):
        conn.execute("INSERT INTO customer_contacts (id,customer_id,name,archived_at,created_at,updated_at) VALUES (?,?,?,?,?,?)", (item_id, customer, name, archived, now, now))
    conn.execute("INSERT INTO customer_aliases (id,customer_id,alias_name,normalized_alias,created_at,updated_at) VALUES (?,?,?,?,?,?)", (alias, customer, "Owner Europe", "owner europe", now, now))
    activity = ActivityRepository().create(lead, ids["sales_owner"], "follow_up", "Called customer")
    pre = PreSalesTaskRepository()
    pre_assigned = pre.create(lead, {"assignee_id": ids["tech_assigned"]}, ids["leader"])
    pre_other = pre.create(lead, {"assignee_id": ids["tech_other"]}, ids["leader"])
    archived_task = pre.create(lead, {"assignee_id": ids["tech_assigned"]}, ids["leader"])
    pre.archive(archived_task, ids["leader"])
    after_assigned = AfterSalesTaskRepository().create(lead, {
        "assignee_id": ids["tech_assigned"], "issue_type": "Technical",
        "issue_description": "Check alignment",
    }, ids["leader"])
    leads.archive(archived_lead, ids["leader"])
    customers.archive(archived_customer, ids["leader"])
    batch = generate_uuid()
    conn.execute("""INSERT INTO import_batches
        (id,organization_id,dataset_id,source_system,source_filename,source_sha256,status,
         created_at,created_by,updated_at,completed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (batch, DEFAULT_ORGANIZATION_ID, "quality-test", "test", "test.xlsx", "abc", "completed", now, ids["leader"], now, now))
    entities = {
        "customer": ("customers", customer), "contact": ("contacts", contact),
        "alias": ("aliases", alias), "lead": ("leads", lead),
        "assignment": ("assignments", assignment), "activity": ("activities", activity),
        "pre_assigned": ("pre_sales_tasks", pre_assigned),
        "pre_other": ("pre_sales_tasks", pre_other),
        "after_assigned": ("after_sales_tasks", after_assigned),
        "other_lead": ("leads", other_lead), "archived_lead": ("leads", archived_lead),
        "archived_customer": ("customers", archived_customer),
        "customer_archived_lead": ("leads", customer_archived_lead),
        "archived_task": ("pre_sales_tasks", archived_task),
        "archived_contact": ("contacts", archived_contact),
    }
    issues = {}
    for key, (entity_type, entity_id) in entities.items():
        external, binding_id, issue_id = f"ext-{key}", generate_uuid(), generate_uuid()
        conn.execute("""INSERT INTO import_bindings
            (id,organization_id,dataset_id,entity_type,external_key,local_entity_id,source_hash,
             first_batch_id,last_batch_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (binding_id, DEFAULT_ORGANIZATION_ID, "quality-test", entity_type, external,
             entity_id, "row", batch, batch, now, now))
        conn.execute("""INSERT INTO data_quality_issues
            (id,batch_id,severity,issue_code,entity_type,external_key,message,status,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (issue_id, batch, "warning", f"test_{key}", entity_type, external, key, "open", now))
        issues[key] = issue_id
    issues["unbound"] = generate_uuid()
    conn.execute("""INSERT INTO data_quality_issues
        (id,batch_id,severity,issue_code,entity_type,external_key,message,status,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""", (issues["unbound"], batch, "warning", "test_unbound",
        "leads", "missing-binding", "unbound", "open", now))
    conn.commit()
    ids.update({"issues": issues, "lead_id": lead})
    return ids
