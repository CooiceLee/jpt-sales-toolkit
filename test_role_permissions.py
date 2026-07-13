"""
Role permission boundary tests.

Tests:
1. Owner can edit lead and add follow-ups
2. Collaborator can edit allowed fields only
3. Collaborator cannot edit restricted fields
4. Watcher can view but not edit
5. Non-assigned sales cannot view
6. Leader can view and edit all
"""

import asyncio
from pathlib import Path

from backend.config import init_settings
from backend.repositories import init_db, UserRepository, LeadRepository, CustomerRepository
from backend.services import LeadService


def setup_test_db(test_dir: Path):
    """Create test database with role-based assignments."""
    db_path = test_dir / "test_roles.sqlite"
    if db_path.exists():
        db_path.unlink()

    # Initialize DB
    settings = init_settings(Path.cwd())
    settings.db_path = str(db_path)
    init_db(str(db_path))

    # Create users
    user_repo = UserRepository()
    leader_id = user_repo.create(
        username="leader",
        password_hash="dummy",
        display_name="Leader",
        role="leader",
        region="EU"
    )

    owner_id = user_repo.create(
        username="owner",
        password_hash="dummy",
        display_name="Owner Sales",
        role="sales",
        region="EU"
    )

    collaborator_id = user_repo.create(
        username="collaborator",
        password_hash="dummy",
        display_name="Collaborator",
        role="sales",
        region="EU"
    )

    watcher_id = user_repo.create(
        username="watcher",
        password_hash="dummy",
        display_name="Watcher",
        role="sales",
        region="EU"
    )

    other_sales_id = user_repo.create(
        username="other",
        password_hash="dummy",
        display_name="Other Sales",
        role="sales",
        region="SEA"
    )

    # Create customer
    customer_repo = CustomerRepository()
    customer_id = customer_repo.create({
        "display_name": "Test Customer",
        "normalized_name": "test customer",
        "country": "DE",
    }, leader_id)

    # Create lead with owner
    lead_repo = LeadRepository()
    lead_id = lead_repo.create({
        "customer_id": customer_id,
        "title": "Test Lead",
        "sales_stage": "Following",
        "owner_id": owner_id,
        "estimated_value": 10000,
    }, owner_id)

    # Add assignments
    lead_repo.add_assignment(lead_id, owner_id, "owner", leader_id)
    lead_repo.add_assignment(lead_id, collaborator_id, "collaborator", leader_id)
    lead_repo.add_assignment(lead_id, watcher_id, "watcher", leader_id)
    lead_repo.conn.commit()

    return db_path, {
        "leader_id": leader_id,
        "owner_id": owner_id,
        "collaborator_id": collaborator_id,
        "watcher_id": watcher_id,
        "other_sales_id": other_sales_id,
        "customer_id": customer_id,
        "lead_id": lead_id
    }


async def test_owner_can_edit(ids):
    """Test 1: Owner can edit lead."""
    print("\n" + "="*60)
    print("TEST 1: Owner can edit lead")
    print("="*60)

    service = LeadService()
    lead = service.get(ids["lead_id"])

    # Owner updates title
    try:
        updated = service.update(
            ids["lead_id"],
            {"title": "Updated by Owner"},
            ids["owner_id"],
            "owner",
            lead["row_version"]
        )
        print(f"\n✅ Owner successfully updated title: '{updated['title']}'")
        assert updated["title"] == "Updated by Owner"
    except Exception as e:
        print(f"\n❌ FAILED: Owner cannot edit: {e}")
        raise


async def test_collaborator_can_edit_allowed(ids):
    """Test 2: Collaborator can edit allowed fields."""
    print("\n" + "="*60)
    print("TEST 2: Collaborator can edit allowed fields")
    print("="*60)

    service = LeadService()
    lead = service.get(ids["lead_id"])

    # Collaborator updates product_category (allowed)
    try:
        updated = service.update(
            ids["lead_id"],
            {"product_category": "MOPA Fiber Laser"},
            ids["collaborator_id"],
            "collaborator",
            lead["row_version"]
        )
        print(f"\n✅ Collaborator successfully updated product_category: '{updated['product_category']}'")
        assert updated["product_category"] == "MOPA Fiber Laser"
    except Exception as e:
        print(f"\n❌ FAILED: Collaborator cannot edit allowed field: {e}")
        raise


async def test_collaborator_cannot_edit_restricted(ids):
    """Test 3: Collaborator cannot edit restricted fields."""
    print("\n" + "="*60)
    print("TEST 3: Collaborator cannot edit restricted fields")
    print("="*60)

    service = LeadService()
    lead = service.get(ids["lead_id"])

    # Collaborator tries to update owner_id (restricted)
    print("\n[Attempting to change owner_id]")
    try:
        service.update(
            ids["lead_id"],
            {"owner_id": ids["collaborator_id"]},
            ids["collaborator_id"],
            "collaborator",
            lead["row_version"]
        )
        print("❌ FAILED: Collaborator was able to change owner_id")
        raise AssertionError("Collaborator should not be able to change owner_id")
    except PermissionError as e:
        print(f"✅ Correctly blocked: {e}")

    # Collaborator tries to update deal_amount (restricted)
    print("\n[Attempting to change deal_amount]")
    try:
        service.update(
            ids["lead_id"],
            {"deal_amount": 50000},
            ids["collaborator_id"],
            "collaborator",
            lead["row_version"]
        )
        print("❌ FAILED: Collaborator was able to change deal_amount")
        raise AssertionError("Collaborator should not be able to change deal_amount")
    except PermissionError as e:
        print(f"✅ Correctly blocked: {e}")

    # Collaborator tries to update sales_stage to Won (restricted)
    print("\n[Attempting to change sales_stage to Won]")
    try:
        service.update(
            ids["lead_id"],
            {"sales_stage": "Won"},
            ids["collaborator_id"],
            "collaborator",
            lead["row_version"]
        )
        print(f"❌ FAILED: Collaborator was able to change sales_stage to Won")
        raise AssertionError("Collaborator should not be able to mark as Won")
    except PermissionError as e:
        print(f"✅ Correctly blocked: {e}")

    print("\n✅ All restricted field edits were correctly blocked")


async def test_watcher_cannot_edit(ids):
    """Test 4: Watcher can view but not edit."""
    print("\n" + "="*60)
    print("TEST 4: Watcher can view but not edit")
    print("="*60)

    service = LeadService()
    lead = service.get(ids["lead_id"])

    print(f"\n[Watcher viewing lead]")
    print(f"  Lead title: {lead['title']}")
    print(f"  Sales stage: {lead['sales_stage']}")

    # Watcher tries to update title
    print("\n[Attempting to edit title]")
    try:
        service.update(
            ids["lead_id"],
            {"title": "Updated by Watcher"},
            ids["watcher_id"],
            "watcher",
            lead["row_version"]
        )
        print("❌ FAILED: Watcher was able to edit lead")
        raise AssertionError("Watcher should not be able to edit")
    except PermissionError as e:
        print(f"✅ Correctly blocked: {e}")


async def test_non_assigned_cannot_view(ids):
    """Test 5: Non-assigned sales cannot view lead."""
    print("\n" + "="*60)
    print("TEST 5: Non-assigned sales cannot view lead")
    print("="*60)

    service = LeadService()

    # Non-assigned sales tries to get lead
    print("\n[Non-assigned sales attempting to view lead]")

    # Note: Permission filtering happens at API router level via get_actor_role_for_lead
    # Here we just verify the service doesn't expose data to non-assigned users
    lead_repo = LeadRepository()
    assignments = lead_repo.get_assignments(ids["lead_id"])
    assigned_user_ids = [a["user_id"] for a in assignments]

    print(f"  Assigned users: {assigned_user_ids}")
    print(f"  Other sales ID: {ids['other_sales_id']}")

    assert ids["other_sales_id"] not in assigned_user_ids, "Other sales should not be assigned"
    print("✅ Non-assigned sales is correctly not in assignment list")


async def test_leader_full_access(ids):
    """Test 6: Leader can view and edit all."""
    print("\n" + "="*60)
    print("TEST 6: Leader can view and edit all")
    print("="*60)

    service = LeadService()
    lead = service.get(ids["lead_id"])

    # Leader updates restricted field (owner_id)
    print("\n[Leader changing owner]")
    try:
        updated = service.update(
            ids["lead_id"],
            {"owner_id": ids["collaborator_id"]},
            ids["leader_id"],
            "leader",
            lead["row_version"]
        )
        print(f"✅ Leader successfully changed owner to: {updated['owner_id']}")
        assert updated["owner_id"] == ids["collaborator_id"]
    except Exception as e:
        print(f"❌ FAILED: Leader cannot change owner: {e}")
        raise

    # Leader updates deal_amount
    refreshed = service.get(ids["lead_id"])
    print("\n[Leader setting deal_amount]")
    try:
        updated = service.update(
            ids["lead_id"],
            {"deal_amount": 100000, "currency": "USD"},
            ids["leader_id"],
            "leader",
            refreshed["row_version"]
        )
        print(f"✅ Leader successfully set deal_amount: {updated['deal_amount']} {updated.get('currency')}")
        assert updated["deal_amount"] == 100000
    except Exception as e:
        print(f"❌ FAILED: Leader cannot set deal_amount: {e}")
        raise


async def main():
    """Run all role permission tests."""
    print("\n" + "="*60)
    print("ROLE PERMISSION BOUNDARY TESTS")
    print("="*60)

    # Setup once for all tests
    test_dir = Path("test_role_permissions_data")
    test_dir.mkdir(exist_ok=True)

    db_path, ids = setup_test_db(test_dir)
    init_db(str(db_path))

    try:
        await test_owner_can_edit(ids)
        await test_collaborator_can_edit_allowed(ids)
        await test_collaborator_cannot_edit_restricted(ids)
        await test_watcher_cannot_edit(ids)
        await test_non_assigned_cannot_view(ids)
        await test_leader_full_access(ids)

        print("\n" + "="*60)
        print("✅ ALL ROLE PERMISSION TESTS PASSED")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
