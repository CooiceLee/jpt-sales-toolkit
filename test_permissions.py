"""
Permission verification test suite.

Tests:
1. Leader can see all leads
2. Sales can only see own leads
3. Leader can see all customers on map
4. Sales can only see customers of own leads
5. Assignment changes are reflected in permissions
"""

import asyncio
import sqlite3
from pathlib import Path

from backend.config import init_settings
from backend.repositories import init_db, UserRepository, LeadRepository, CustomerRepository
from backend.services import ReviewService


def setup_test_db(test_dir: Path, test_name: str):
    """Create test database with 3 users and 4 leads."""
    db_path = test_dir / f"{test_name}.sqlite"
    if db_path.exists():
        db_path.unlink()

    # Initialize DB
    settings = init_settings(Path.cwd())
    settings.db_path = str(db_path)
    init_db(str(db_path))

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Create users
    user_repo = UserRepository()
    leader_id = user_repo.create(
        username="leader1",
        password_hash="dummy",
        display_name="Leader One",
        role="leader",
        region="EU"
    )

    sales1_id = user_repo.create(
        username="sales1",
        password_hash="dummy",
        display_name="Sales One",
        role="sales",
        region="EU"
    )

    sales2_id = user_repo.create(
        username="sales2",
        password_hash="dummy",
        display_name="Sales Two",
        role="sales",
        region="SEA"
    )

    # Create customers
    customer_repo = CustomerRepository()
    customer1_id = customer_repo.create({
        "display_name": "Customer A",
        "normalized_name": "customer a",
        "country": "DE",
        "lat": 52.5200,
        "lng": 13.4050
    }, leader_id)

    customer2_id = customer_repo.create({
        "display_name": "Customer B",
        "normalized_name": "customer b",
        "country": "SG",
        "lat": 1.3521,
        "lng": 103.8198
    }, leader_id)

    # Create leads
    lead_repo = LeadRepository()

    # Lead 1: owned by sales1
    lead1_id = lead_repo.create({
        "customer_id": customer1_id,
        "title": "Lead 1 for Sales1",
        "sales_stage": "New",
        "owner_id": sales1_id
    }, sales1_id)

    # Lead 2: owned by sales1
    lead2_id = lead_repo.create({
        "customer_id": customer1_id,
        "title": "Lead 2 for Sales1",
        "sales_stage": "Following",
        "owner_id": sales1_id
    }, sales1_id)

    # Lead 3: owned by sales2
    lead3_id = lead_repo.create({
        "customer_id": customer2_id,
        "title": "Lead 3 for Sales2",
        "sales_stage": "Won",
        "owner_id": sales2_id
    }, sales2_id)

    # Lead 4: owned by sales2
    lead4_id = lead_repo.create({
        "customer_id": customer2_id,
        "title": "Lead 4 for Sales2",
        "sales_stage": "Following",
        "owner_id": sales2_id
    }, sales2_id)

    return db_path, {
        "leader_id": leader_id,
        "sales1_id": sales1_id,
        "sales2_id": sales2_id,
        "customer1_id": customer1_id,
        "customer2_id": customer2_id,
        "lead1_id": lead1_id,
        "lead2_id": lead2_id,
        "lead3_id": lead3_id,
        "lead4_id": lead4_id
    }


async def test_leader_sees_all(ids):
    """Test 1: Leader can see all leads."""
    print("\n" + "="*60)
    print("TEST 1: Leader sees all leads")
    print("="*60)

    service = ReviewService()
    dashboard = service.get_dashboard_data(ids["leader_id"], "leader")

    print(f"\n[Leader view]")
    print(f"  Total leads: {dashboard['total_leads']}")
    print(f"  By stage: {dashboard['stage_counts']}")

    assert dashboard["total_leads"] == 4, f"Expected 4 leads, got {dashboard['total_leads']}"
    assert dashboard["stage_counts"]["New"] == 1
    assert dashboard["stage_counts"]["Following"] == 2
    assert dashboard["stage_counts"]["Won"] == 1

    print(f"\n✅ Leader sees all 4 leads")


async def test_sales_sees_own_only(ids):
    """Test 2: Sales can only see own leads."""
    print("\n" + "="*60)
    print("TEST 2: Sales sees only own leads")
    print("="*60)

    service = ReviewService()

    # Sales1 should see 2 leads
    dashboard_s1 = service.get_dashboard_data(ids["sales1_id"], "sales")
    print(f"\n[Sales1 view]")
    print(f"  Total leads: {dashboard_s1['total_leads']}")
    print(f"  By stage: {dashboard_s1['stage_counts']}")

    assert dashboard_s1["total_leads"] == 2, f"Sales1 should see 2 leads, got {dashboard_s1['total_leads']}"
    assert dashboard_s1["stage_counts"]["New"] == 1
    assert dashboard_s1["stage_counts"]["Following"] == 1

    # Sales2 should see 2 leads
    dashboard_s2 = service.get_dashboard_data(ids["sales2_id"], "sales")
    print(f"\n[Sales2 view]")
    print(f"  Total leads: {dashboard_s2['total_leads']}")
    print(f"  By stage: {dashboard_s2['stage_counts']}")

    assert dashboard_s2["total_leads"] == 2, f"Sales2 should see 2 leads, got {dashboard_s2['total_leads']}"
    assert dashboard_s2["stage_counts"]["Following"] == 1
    assert dashboard_s2["stage_counts"]["Won"] == 1

    print(f"\n✅ Sales users see only their own leads")


async def test_leader_sees_all_customers(ids):
    """Test 3: Leader sees all customers on map."""
    print("\n" + "="*60)
    print("TEST 3: Leader sees all customers on map")
    print("="*60)

    service = ReviewService()
    map_data = service.get_map_data(ids["leader_id"], "leader")

    print(f"\n[Leader map view]")
    print(f"  Customer points: {len(map_data['points'])}")
    print(f"  Customers: {[p['customer_name'] for p in map_data['points']]}")

    assert len(map_data["points"]) == 2, f"Leader should see 2 customer points, got {len(map_data['points'])}"

    print(f"\n✅ Leader sees all 2 customer points")


async def test_sales_sees_own_customers(ids):
    """Test 4: Sales sees only customers of own leads."""
    print("\n" + "="*60)
    print("TEST 4: Sales sees only customers of own leads")
    print("="*60)

    service = ReviewService()

    # Sales1 should see 1 customer (Customer A)
    map_s1 = service.get_map_data(ids["sales1_id"], "sales")
    print(f"\n[Sales1 map view]")
    print(f"  Customer points: {len(map_s1['points'])}")
    print(f"  Customers: {[p['customer_name'] for p in map_s1['points']]}")

    assert len(map_s1["points"]) == 1, f"Sales1 should see 1 customer, got {len(map_s1['points'])}"
    assert map_s1["points"][0]["customer_name"] == "Customer A"

    # Sales2 should see 1 customer (Customer B)
    map_s2 = service.get_map_data(ids["sales2_id"], "sales")
    print(f"\n[Sales2 map view]")
    print(f"  Customer points: {len(map_s2['points'])}")
    print(f"  Customers: {[p['customer_name'] for p in map_s2['points']]}")

    assert len(map_s2["points"]) == 1, f"Sales2 should see 1 customer, got {len(map_s2['points'])}"
    assert map_s2["points"][0]["customer_name"] == "Customer B"

    print(f"\n✅ Sales users see only customers of their own leads")


async def test_reassignment(ids):
    """Test 5: Reassignment changes permissions."""
    print("\n" + "="*60)
    print("TEST 5: Reassignment changes permissions")
    print("="*60)

    service = ReviewService()

    # Before: Sales1 sees 2 leads
    before = service.get_dashboard_data(ids["sales1_id"], "sales")
    print(f"\n[Before reassignment]")
    print(f"  Sales1 total leads: {before['total_leads']}")

    assert before["total_leads"] == 2

    # Reassign Lead2 from Sales1 to Sales2
    lead_repo = LeadRepository()
    lead_repo.update(ids["lead2_id"], {"owner_id": ids["sales2_id"]}, ids["leader_id"], 1)

    # After: Sales1 sees 1 lead, Sales2 sees 3 leads
    after_s1 = service.get_dashboard_data(ids["sales1_id"], "sales")
    after_s2 = service.get_dashboard_data(ids["sales2_id"], "sales")

    print(f"\n[After reassignment: Lead2 → Sales2]")
    print(f"  Sales1 total leads: {after_s1['total_leads']}")
    print(f"  Sales2 total leads: {after_s2['total_leads']}")

    assert after_s1["total_leads"] == 1, f"Sales1 should now see 1 lead, got {after_s1['total_leads']}"
    assert after_s2["total_leads"] == 3, f"Sales2 should now see 3 leads, got {after_s2['total_leads']}"

    print(f"\n✅ Reassignment correctly updates permissions")


async def main():
    """Run all permission tests."""
    print("\n" + "="*60)
    print("PERMISSION VERIFICATION TEST SUITE")
    print("="*60)

    # Setup once for all tests
    test_dir = Path("test_permissions_data")
    test_dir.mkdir(exist_ok=True)

    db_path, ids = setup_test_db(test_dir, "test_permissions")
    init_db(str(db_path))

    try:
        # Run tests sequentially with shared setup
        await test_leader_sees_all(ids)
        await test_sales_sees_own_only(ids)
        await test_leader_sees_all_customers(ids)
        await test_sales_sees_own_customers(ids)
        await test_reassignment(ids)

        print("\n" + "="*60)
        print("✅ ALL PERMISSION TESTS PASSED")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
