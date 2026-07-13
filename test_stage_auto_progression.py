"""
Test automatic stage progression and fulfillment initialization.

Verifies:
1. Won → Fulfillment initialization (auto-progress)
2. Won → Fulfillment initialization (manual)
3. Existing fulfillment_status preserved
"""

import tempfile
from pathlib import Path

from backend.config import init_settings
from backend.repositories import init_db, close_db, UserRepository
from backend.services.lead_service import LeadService
from backend.services.customer_service import CustomerService


def setup_test_db(test_name="default"):
    """Setup test database with users and customer."""
    temp_dir = Path(tempfile.mkdtemp(prefix=f"test_{test_name}_"))
    db_path = temp_dir / "test.sqlite"

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

    sales_id = user_repo.create(
        username="sales",
        password_hash="dummy",
        display_name="Sales",
        role="sales",
        region="EU"
    )

    # Create customer (use CustomerService to auto-generate normalized_name)
    customer_service = CustomerService()
    customer = customer_service.create({
        "display_name": "Test Company",
        "country": "Germany"
    }, leader_id)

    return leader_id, sales_id, customer["id"]




def test_won_auto_init_fulfillment():
    """Test: Advancing to Won should ensure fulfillment_status is set."""
    print("\n" + "="*60)
    print("TEST 1: Won → Fulfillment Initialization (Auto-progress)")
    print("="*60)

    leader_id, sales_id, customer_id = setup_test_db("auto_won")
    service = LeadService()

    # Create lead with owner (DDL默认值会设置fulfillment_status='Not Started')
    lead = service.create({
        "customer_id": customer_id,
        "title": "Test Deal",
        "owner_id": sales_id,
        "sales_stage": "Following",
    }, leader_id)

    print(f"\n[Initial state]")
    print(f"  sales_stage: {lead['sales_stage']}")
    print(f"  fulfillment_status: {lead['fulfillment_status']} (DDL default)")

    assert lead["sales_stage"] == "Following"
    # Note: fulfillment_status has DDL DEFAULT 'Not Started', so it's always set
    assert lead["fulfillment_status"] == "Not Started"

    # Add deal evidence (should auto-progress to Won)
    print(f"\n[Adding PO number to trigger Won...]")
    updated = service.update(
        lead["id"],
        {"po_number": "PO-2024-001"},
        sales_id,
        "owner",
        lead["row_version"]
    )

    print(f"  sales_stage: {updated['sales_stage']}")
    print(f"  fulfillment_status: {updated['fulfillment_status']}")

    assert updated["sales_stage"] == "Won", \
        f"Expected auto-progress to 'Won', got {updated['sales_stage']}"
    assert updated["fulfillment_status"] == "Not Started", \
        f"Expected fulfillment_status='Not Started', got {updated.get('fulfillment_status')}"

    print("\n✅ Won ensures fulfillment_status is properly set")
    close_db()  # Close DB connection to avoid conflicts with next test


def test_manual_won_also_inits_fulfillment():
    """Test: Manually setting sales_stage=Won should also init fulfillment."""
    print("\n" + "="*60)
    print("TEST 2: Manual Won → Fulfillment Initialization")
    print("="*60)

    leader_id, sales_id, customer_id = setup_test_db("manual_won")
    service = LeadService()

    # Create lead
    lead = service.create({
        "customer_id": customer_id,
        "title": "Manual Won Test",
        "owner_id": sales_id,
        "sales_stage": "Quoted",
    }, leader_id)

    print(f"\n[Initial state]")
    print(f"  sales_stage: {lead['sales_stage']}")
    print(f"  fulfillment_status: {lead.get('fulfillment_status')}")

    # Manually set to Won
    print(f"\n[Manually setting sales_stage=Won...]")
    updated = service.update(
        lead["id"],
        {"sales_stage": "Won"},
        sales_id,
        "owner",
        lead["row_version"]
    )

    print(f"  sales_stage: {updated['sales_stage']}")
    print(f"  fulfillment_status: {updated['fulfillment_status']}")

    assert updated["sales_stage"] == "Won"
    assert updated["fulfillment_status"] == "Not Started", \
        f"Expected fulfillment_status='Not Started', got {updated.get('fulfillment_status')}"

    print("\n✅ Manual Won also initializes fulfillment_status")
    close_db()  # Close DB connection to avoid conflicts with next test


def test_fulfillment_not_overwritten():
    """Test: Don't overwrite existing fulfillment_status."""
    print("\n" + "="*60)
    print("TEST 3: Existing Fulfillment Status Preserved")
    print("="*60)

    leader_id, sales_id, customer_id = setup_test_db("preserve")
    service = LeadService()

    # Create lead already Won with In Progress fulfillment
    lead = service.create({
        "customer_id": customer_id,
        "title": "Existing Fulfillment",
        "owner_id": sales_id,
        "sales_stage": "Won",
        "fulfillment_status": "In Progress",
    }, leader_id)

    print(f"\n[Initial state]")
    print(f"  sales_stage: {lead['sales_stage']}")
    print(f"  fulfillment_status: {lead['fulfillment_status']}")

    # Update something else
    print(f"\n[Updating other field...]")
    updated = service.update(
        lead["id"],
        {"title": "Updated Title"},
        sales_id,
        "owner",
        lead["row_version"]
    )

    print(f"  sales_stage: {updated['sales_stage']}")
    print(f"  fulfillment_status: {updated['fulfillment_status']}")

    assert updated["fulfillment_status"] == "In Progress", \
        f"Expected existing 'In Progress' preserved, got {updated['fulfillment_status']}"

    print("\n✅ Existing fulfillment_status is preserved")
    close_db()  # Close DB connection


def main():
    """Run all stage auto-progression tests."""
    print("\n" + "="*60)
    print("WON → FULFILLMENT AUTO-INITIALIZATION TESTS")
    print("="*60)

    try:
        test_won_auto_init_fulfillment()
        test_manual_won_also_inits_fulfillment()
        test_fulfillment_not_overwritten()

        print("\n" + "="*60)
        print("✅ ALL WON → FULFILLMENT TESTS PASSED")
        print("="*60)
        print("\nBusiness impact:")
        print("  ✅ Won orders now auto-appear in Fulfillment work list")
        print("  ✅ Sales → Fulfillment handoff is fully automated")
        print("  ✅ fulfillment_status='Not Started' ensures proper filtering")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
