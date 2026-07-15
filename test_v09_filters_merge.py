"""
Regression coverage for v0.9 stage filters and customer merge.
"""

from pathlib import Path

from backend.config import init_settings
from backend.repositories import (
    init_db,
    UserRepository,
    CustomerRepository,
    LeadRepository,
    PreSalesTaskRepository,
)
from backend.repositories.base import ConflictError
from backend.services import LeadService, CustomerService


def setup_test_db(test_dir: Path):
    db_path = test_dir / "test_v09_filters_merge.sqlite"
    if db_path.exists():
        db_path.unlink()

    settings = init_settings(Path.cwd())
    settings.db_path = str(db_path)
    init_db(str(db_path))

    user_repo = UserRepository()
    leader_id = user_repo.create("leader", "dummy", "Leader", "leader", region="EU")
    sales1_id = user_repo.create("sales1", "dummy", "Sales One", "sales", region="EU")
    sales2_id = user_repo.create("sales2", "dummy", "Sales Two", "sales", region="EU")
    tech1_id = user_repo.create("tech1", "dummy", "Tech One", "tech", region="EU")

    customer_repo = CustomerRepository()
    source_customer_id = customer_repo.create({
        "display_name": "Acme Laser Europe",
        "normalized_name": "acme laser europe",
        "country": "Germany",
        "city": "Berlin",
        "address": "Plant 1",
        "website": "https://source.example.com",
    }, leader_id)
    target_customer_id = customer_repo.create({
        "display_name": "Acme Laser GmbH",
        "normalized_name": "acme laser gmbh",
    }, leader_id)
    other_customer_id = customer_repo.create({
        "display_name": "Photon Works",
        "normalized_name": "photon works",
        "country": "France",
        "city": "Lyon",
    }, leader_id)

    customer_repo.add_contact(target_customer_id, {
        "name": "Main Contact",
        "email": "main@acme.com",
        "is_primary": True,
    })
    customer_repo.add_contact(source_customer_id, {
        "name": "Duplicate Contact",
        "email": "main@acme.com",
        "is_primary": True,
    })
    customer_repo.add_contact(source_customer_id, {
        "name": "Field Contact",
        "email": "field@acme.com",
        "phone": "+49-123",
        "is_primary": False,
    })
    customer_repo.add_domain(source_customer_id, "acme-europe.example.com", True)

    lead_repo = LeadRepository()
    source_lead_id = lead_repo.create({
        "customer_id": source_customer_id,
        "title": "MOPA Retrofit",
        "sales_stage": "Following",
        "owner_id": sales1_id,
        "product_category": "MOPA",
    }, sales1_id)
    other_lead_id = lead_repo.create({
        "customer_id": other_customer_id,
        "title": "QCW Quote",
        "sales_stage": "Quoted",
        "owner_id": sales2_id,
        "product_category": "QCW",
    }, sales2_id)
    lead_repo.conn.commit()

    pre_sales_repo = PreSalesTaskRepository()
    pre_sales_repo.create(source_lead_id, {"assignee_id": tech1_id, "status": "Open"}, leader_id)

    return {
        "db_path": db_path,
        "leader_id": leader_id,
        "sales1_id": sales1_id,
        "sales2_id": sales2_id,
        "tech1_id": tech1_id,
        "source_customer_id": source_customer_id,
        "target_customer_id": target_customer_id,
        "other_customer_id": other_customer_id,
        "source_lead_id": source_lead_id,
        "other_lead_id": other_lead_id,
    }


def test_lead_filters(ids):
    lead_service = LeadService()

    owner_filtered = lead_service.list(
        actor_id=ids["leader_id"],
        actor_role="leader",
        owner_id=ids["sales1_id"],
    )
    assert len(owner_filtered) == 1
    assert owner_filtered[0]["id"] == ids["source_lead_id"]

    tech_filtered_for_leader = lead_service.list(
        actor_id=ids["leader_id"],
        actor_role="leader",
        tech_id=ids["tech1_id"],
    )
    assert len(tech_filtered_for_leader) == 1
    assert tech_filtered_for_leader[0]["id"] == ids["source_lead_id"]

    sales_view = lead_service.list(
        actor_id=ids["sales1_id"],
        actor_role="sales",
        tech_id=ids["tech1_id"],
        search="Acme",
    )
    assert len(sales_view) == 1
    assert sales_view[0]["customer"]["display_name"] == "Acme Laser Europe"

    tech_view = lead_service.list(
        actor_id=ids["tech1_id"],
        actor_role="tech",
        owner_id=ids["sales1_id"],
        search="field@acme.com",
    )
    assert len(tech_view) == 1
    assert tech_view[0]["id"] == ids["source_lead_id"]


def test_customer_merge(ids):
    customer_service = CustomerService()

    source_before = customer_service.get(ids["source_customer_id"])
    target_before = customer_service.get(ids["target_customer_id"])

    result = customer_service.merge_customers(
        source_customer_id=ids["source_customer_id"],
        target_customer_id=ids["target_customer_id"],
        actor_id=ids["leader_id"],
        source_row_version=source_before["row_version"],
        target_row_version=target_before["row_version"],
    )

    assert result["moved_leads"] == 1
    assert result["moved_contacts"] == 1
    assert result["archived_duplicate_contacts"] == 1
    assert result["moved_domains"] == 1
    assert result["moved_aliases"] >= 1
    assert result["target_updates"]["country"] == "Germany"

    lead_service = LeadService()
    moved_lead = lead_service.get(ids["source_lead_id"])
    assert moved_lead["customer_id"] == ids["target_customer_id"]

    source_after = customer_service.get(ids["source_customer_id"])
    assert source_after["archived_at"] is not None

    target_after = customer_service.get(ids["target_customer_id"])
    assert target_after["country"] == "Germany"
    assert any(contact.get("email") == "field@acme.com" for contact in target_after["contacts"])

    alias_row = customer_service.customer_repo.conn.execute(
        """
        SELECT 1 FROM customer_aliases
        WHERE customer_id = ? AND normalized_alias = ?
        """,
        (ids["target_customer_id"], "acme laser europe"),
    ).fetchone()
    assert alias_row is not None


def test_customer_merge_conflict(ids):
    customer_service = CustomerService()

    source_before = customer_service.get(ids["source_customer_id"])
    target_before = customer_service.get(ids["target_customer_id"])
    customer_service.update(
        ids["target_customer_id"],
        {"city": "Munich"},
        ids["leader_id"],
        target_before["row_version"],
    )

    try:
        customer_service.merge_customers(
            source_customer_id=ids["source_customer_id"],
            target_customer_id=ids["target_customer_id"],
            actor_id=ids["leader_id"],
            source_row_version=source_before["row_version"],
            target_row_version=target_before["row_version"],
        )
    except ConflictError as err:
        assert err.current_version > target_before["row_version"]
        assert err.your_version == target_before["row_version"]
        assert err.current_data["id"] == ids["target_customer_id"]
    else:
        raise AssertionError("Expected ConflictError for stale target row_version")


def main():
    test_dir = Path("test_output")
    test_dir.mkdir(exist_ok=True)
    ids = setup_test_db(test_dir)
    test_lead_filters(ids)
    test_customer_merge_conflict(ids)
    test_customer_merge(ids)
    print("v0.9 filter/merge regression passed")


if __name__ == "__main__":
    main()
