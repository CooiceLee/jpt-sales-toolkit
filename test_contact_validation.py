"""
Customer contact validation tests.

Tests:
1. Email format validation
2. Duplicate email within same customer
3. Empty name and email rejection
4. Valid contact with only name
5. Valid contact with only email
6. Primary contact uniqueness
"""

import asyncio
from pathlib import Path

from backend.config import init_settings
from backend.repositories import close_db, init_db, UserRepository, CustomerRepository
from backend.services import CustomerService


def setup_test_db(test_dir: Path):
    """Create test database."""
    close_db()
    db_path = test_dir / "test_contact_validation.sqlite"
    if db_path.exists():
        db_path.unlink()

    # Initialize DB
    settings = init_settings(Path.cwd())
    settings.db_path = str(db_path)
    init_db(str(db_path))

    # Create user
    user_repo = UserRepository()
    user_id = user_repo.create(
        username="testuser",
        password_hash="dummy",
        display_name="Test User",
        role="sales",
        region="EU"
    )

    # Create customer
    customer_repo = CustomerRepository()
    customer_id = customer_repo.create({
        "display_name": "Test Company",
        "normalized_name": "test company",
        "country": "DE",
    }, user_id)

    return db_path, {"user_id": user_id, "customer_id": customer_id}


async def test_invalid_email_format(ids):
    """Test 1: Invalid email format is rejected."""
    print("\n" + "="*60)
    print("TEST 1: Invalid email format validation")
    print("="*60)

    service = CustomerService()

    # Test various invalid emails
    invalid_emails = [
        "notanemail",
        "@example.com",
        "user@",
        "user@@example.com",
        "user@example",
        "user@.com",
        "user@example..com",
    ]

    for email in invalid_emails:
        print(f"\n[Testing invalid email: {email}]")
        try:
            service.add_contact(
                ids["customer_id"],
                {"name": "Test Contact", "email": email},
                ids["user_id"]
            )
            print(f"❌ FAILED: Invalid email '{email}' was accepted")
            raise AssertionError(f"Invalid email '{email}' should be rejected")
        except ValueError as e:
            print(f"✅ Correctly rejected: {e}")

    print("\n✅ All invalid email formats were correctly rejected")


async def test_duplicate_email(ids):
    """Test 2: Duplicate email within same customer is rejected."""
    print("\n" + "="*60)
    print("TEST 2: Duplicate email validation")
    print("="*60)

    service = CustomerService()

    # Add first contact
    print("\n[Adding first contact with email test@example.com]")
    contact1_id = service.add_contact(
        ids["customer_id"],
        {"name": "Contact One", "email": "test@example.com"},
        ids["user_id"]
    )
    print(f"✅ First contact added: {contact1_id}")

    # Try to add duplicate email
    print("\n[Attempting to add duplicate email]")
    try:
        service.add_contact(
            ids["customer_id"],
            {"name": "Contact Two", "email": "test@example.com"},
            ids["user_id"]
        )
        print("❌ FAILED: Duplicate email was accepted")
        raise AssertionError("Duplicate email should be rejected")
    except ValueError as e:
        print(f"✅ Correctly rejected: {e}")

    # Try with different case (should still be duplicate)
    print("\n[Attempting to add email with different case: TEST@example.com]")
    try:
        service.add_contact(
            ids["customer_id"],
            {"name": "Contact Three", "email": "TEST@example.com"},
            ids["user_id"]
        )
        print("❌ FAILED: Duplicate email (different case) was accepted")
        raise AssertionError("Duplicate email (case-insensitive) should be rejected")
    except ValueError as e:
        print(f"✅ Correctly rejected: {e}")


async def test_empty_name_and_email():
    """Test 3: Contact with neither name nor email is rejected."""
    print("\n" + "="*60)
    print("TEST 3: Empty name and email validation")
    print("="*60)

    test_dir = Path("test_contact_validation_data")
    test_dir.mkdir(exist_ok=True)

    db_path, ids = setup_test_db(test_dir)
    init_db(str(db_path))

    service = CustomerService()

    # Try to add contact with no name and no email
    print("\n[Attempting to add contact with no name and no email]")
    try:
        service.add_contact(
            ids["customer_id"],
            {"position": "Manager"},  # Only position, no name or email
            ids["user_id"]
        )
        print("❌ FAILED: Contact with no name and no email was accepted")
        raise AssertionError("Contact must have name or email")
    except ValueError as e:
        print(f"✅ Correctly rejected: {e}")

    # Try with empty strings
    print("\n[Attempting to add contact with empty name and email]")
    try:
        service.add_contact(
            ids["customer_id"],
            {"name": "", "email": "", "position": "Manager"},
            ids["user_id"]
        )
        print("❌ FAILED: Contact with empty name and email was accepted")
        raise AssertionError("Contact must have name or email")
    except ValueError as e:
        print(f"✅ Correctly rejected: {e}")


async def test_valid_name_only():
    """Test 4: Contact with only name (no email) is valid."""
    print("\n" + "="*60)
    print("TEST 4: Valid contact with name only")
    print("="*60)

    test_dir = Path("test_contact_validation_data")
    test_dir.mkdir(exist_ok=True)

    db_path, ids = setup_test_db(test_dir)
    init_db(str(db_path))

    service = CustomerService()

    # Add contact with only name
    print("\n[Adding contact with only name]")
    try:
        contact_id = service.add_contact(
            ids["customer_id"],
            {"name": "John Smith", "position": "CEO"},
            ids["user_id"]
        )
        print(f"✅ Contact with name only added successfully: {contact_id}")
    except Exception as e:
        print(f"❌ FAILED: Contact with name only should be valid: {e}")
        raise


async def test_valid_email_only():
    """Test 5: Contact with only email (no name) is valid."""
    print("\n" + "="*60)
    print("TEST 5: Valid contact with email only")
    print("="*60)

    test_dir = Path("test_contact_validation_data")
    test_dir.mkdir(exist_ok=True)

    db_path, ids = setup_test_db(test_dir)
    init_db(str(db_path))

    service = CustomerService()

    # Add contact with only email
    print("\n[Adding contact with only email]")
    try:
        contact_id = service.add_contact(
            ids["customer_id"],
            {"email": "contact@example.com", "position": "Sales Manager"},
            ids["user_id"]
        )
        print(f"✅ Contact with email only added successfully: {contact_id}")
    except Exception as e:
        print(f"❌ FAILED: Contact with email only should be valid: {e}")
        raise


async def test_primary_contact_uniqueness():
    """Test 6: Only one primary contact per customer."""
    print("\n" + "="*60)
    print("TEST 6: Primary contact uniqueness")
    print("="*60)

    test_dir = Path("test_contact_validation_data")
    test_dir.mkdir(exist_ok=True)

    db_path, ids = setup_test_db(test_dir)
    init_db(str(db_path))

    service = CustomerService()
    customer_repo = CustomerRepository()

    # Add first primary contact
    print("\n[Adding first primary contact]")
    contact1_id = service.add_contact(
        ids["customer_id"],
        {"name": "Primary One", "email": "primary1@example.com", "is_primary": True},
        ids["user_id"]
    )
    print(f"✅ First primary contact added: {contact1_id}")

    contacts = customer_repo.get_contacts(ids["customer_id"])
    primary_count = sum(1 for c in contacts if c["is_primary"])
    print(f"  Primary contacts count: {primary_count}")
    assert primary_count == 1, f"Expected 1 primary contact, got {primary_count}"

    # Add second primary contact (should replace first)
    print("\n[Adding second primary contact]")
    contact2_id = service.add_contact(
        ids["customer_id"],
        {"name": "Primary Two", "email": "primary2@example.com", "is_primary": True},
        ids["user_id"]
    )
    print(f"✅ Second primary contact added: {contact2_id}")

    contacts = customer_repo.get_contacts(ids["customer_id"])
    primary_count = sum(1 for c in contacts if c["is_primary"])
    primary_contact = next((c for c in contacts if c["is_primary"]), None)

    print(f"  Primary contacts count: {primary_count}")
    print(f"  Primary contact: {primary_contact['name'] if primary_contact else 'None'}")

    assert primary_count == 1, f"Expected 1 primary contact, got {primary_count}"
    assert primary_contact["id"] == contact2_id, "New contact should be primary"

    print("\n✅ Primary contact uniqueness maintained")


async def test_update_validation():
    """Test 7: Update validation works correctly."""
    print("\n" + "="*60)
    print("TEST 7: Update validation")
    print("="*60)

    test_dir = Path("test_contact_validation_data")
    test_dir.mkdir(exist_ok=True)

    db_path, ids = setup_test_db(test_dir)
    init_db(str(db_path))

    service = CustomerService()

    # Add two contacts
    print("\n[Adding two contacts]")
    contact1_id = service.add_contact(
        ids["customer_id"],
        {"name": "Contact One", "email": "one@example.com"},
        ids["user_id"]
    )
    contact2_id = service.add_contact(
        ids["customer_id"],
        {"name": "Contact Two", "email": "two@example.com"},
        ids["user_id"]
    )
    print(f"✅ Added contacts: {contact1_id}, {contact2_id}")

    # Try to update contact1 to use contact2's email (should fail)
    print("\n[Attempting to update contact1 with contact2's email]")
    try:
        service.update_contact(
            contact1_id,
            {"email": "two@example.com"},
            ids["user_id"]
        )
        print("❌ FAILED: Update to duplicate email was accepted")
        raise AssertionError("Update to duplicate email should be rejected")
    except ValueError as e:
        print(f"✅ Correctly rejected: {e}")

    # Update contact1 to keep its own email (should succeed)
    print("\n[Updating contact1 with its own email (no change)]")
    try:
        service.update_contact(
            contact1_id,
            {"email": "one@example.com", "position": "Updated Position"},
            ids["user_id"]
        )
        print("✅ Update with same email succeeded")
    except Exception as e:
        print(f"❌ FAILED: Update with same email should succeed: {e}")
        raise

    # Update contact1 to invalid email (should fail)
    print("\n[Attempting to update contact1 with invalid email]")
    try:
        service.update_contact(
            contact1_id,
            {"email": "invalid-email"},
            ids["user_id"]
        )
        print("❌ FAILED: Update to invalid email was accepted")
        raise AssertionError("Update to invalid email should be rejected")
    except ValueError as e:
        print(f"✅ Correctly rejected: {e}")


async def main():
    """Run all contact validation tests."""
    print("\n" + "="*60)
    print("CUSTOMER CONTACT VALIDATION TESTS")
    print("="*60)

    try:
        test_dir = Path("test_contact_validation_data")
        test_dir.mkdir(exist_ok=True)

        db_path, ids = setup_test_db(test_dir)
        init_db(str(db_path))
        await test_invalid_email_format(ids)

        db_path, ids = setup_test_db(test_dir)
        init_db(str(db_path))
        await test_duplicate_email(ids)

        await test_empty_name_and_email()
        await test_valid_name_only()
        await test_valid_email_only()
        await test_primary_contact_uniqueness()
        await test_update_validation()

        print("\n" + "="*60)
        print("✅ ALL CONTACT VALIDATION TESTS PASSED")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
