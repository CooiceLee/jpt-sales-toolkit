#!/usr/bin/env python3
"""
Round-trip test for export/import functionality.

Tests:
1. Export → Import → Re-export → Compare
2. Idempotency: repeated imports don't create duplicates
3. Conflict handling: row_version validation
4. Permission filtering: non-owner leads are skipped
"""

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.repositories.base import init_db, _connection, _db_path
from backend.repositories.customer_repository import CustomerRepository
from backend.repositories.lead_repository import LeadRepository
from backend.repositories.activity_repository import ActivityRepository
from backend.repositories.task_repository import (
    AfterSalesTaskRepository,
    PreSalesTaskRepository,
)
from backend.routers.data_exchange import (
    ExportRequest,
    export_data,
    import_data,
    preflight_import,
)
from backend.services import CustomerService, LeadService
import backend.repositories.base as base_module


class MockUser:
    """Mock user for testing."""
    def __init__(self, user_id, username, display_name, role):
        self.user_dict = {
            "id": user_id,
            "username": username,
            "display_name": display_name,
            "role": role
        }


class MockRequest:
    """Mock request for export."""
    def __init__(self, lead_ids=None):
        self.lead_ids = lead_ids


class MockUploadFile:
    """Mock uploaded file."""
    def __init__(self, file_path):
        self.file_path = file_path
        self.filename = Path(file_path).name

    async def read(self):
        with open(self.file_path, 'rb') as f:
            return f.read()


async def write_streaming_response(response, output_path):
    """Persist a StreamingResponse body to disk and return parsed JSON."""
    from fastapi.responses import StreamingResponse

    if isinstance(response, StreamingResponse):
        content = b''
        async for chunk in response.body_iterator:
            content += chunk if isinstance(chunk, bytes) else chunk.encode()
        with open(output_path, 'wb') as f:
            f.write(content)
        return json.loads(output_path.read_text())

    raise AssertionError("Expected StreamingResponse")


def reset_db_connection():
    """Reset global database connection to None to allow reconnection to a different database."""
    base_module._connection = None
    base_module._db_path = None


def setup_test_database(db_path):
    """Create test database with sample data."""
    # Remove if exists
    if db_path.exists():
        db_path.unlink()

    # Initialize schema
    init_db(db_path)

    # Create test users
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # User 1: owner
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)

    # User 2: collaborator
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-2', 'collab1', 'hash2', 'Collaborator One', 'sales', 1, datetime('now'))
    """)
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-tech', 'tech1', 'hash3', 'Tech One', 'tech', 1, datetime('now'))
    """)

    conn.commit()

    # Create customers and leads using services
    customer_service = CustomerService(customer_repo=CustomerRepository(conn))
    lead_service = LeadService(
        lead_repo=LeadRepository(conn),
        activity_repo=ActivityRepository(conn),
        customer_repo=CustomerRepository(conn)
    )
    activity_repo = ActivityRepository(conn)
    task_repo = AfterSalesTaskRepository(conn)
    pre_sales_repo = PreSalesTaskRepository(conn)

    # Customer 1
    customer1 = customer_service.create({
        'display_name': 'Test Company A',
        'country': 'US',
        'city': 'New York',
        'industry': 'Technology'
    }, 'user-1')
    customer1_id = customer1['id']

    # Add contact
    customer_service.add_contact(customer1_id, {
        'name': 'John Doe',
        'email': 'john@testcompanya.com',
        'phone': '+1234567890',
        'is_primary': True
    }, 'user-1')

    # Lead 1 (owned by user-1)
    lead1 = lead_service.create({
        'customer_id': customer1_id,
        'title': 'Test Lead 1',
        'sales_stage': 'Following',
        'product_category': 'Laser',
        'owner_id': 'user-1',
        'deal_amount': 10000,
        'currency': 'USD'
    }, 'user-1')
    lead1_id = lead1['id']

    # Add activity to lead 1
    activity_repo.create(
        lead_id=lead1_id,
        actor_id='user-1',
        action_type='follow_up',
        summary='Initial follow-up',
        payload_json=json.dumps({'method': 'Email', 'content': 'Sent quotation'}),
        is_formal_follow_up=True
    )

    # Add after-sales task to lead 1
    task_repo.create(
        lead_id=lead1_id,
        data={
            'assignee_id': 'user-tech',
            'issue_type': 'Technical',
            'status': 'Open',
            'issue_description': 'Installation support needed'
        },
        actor_id='user-1'
    )

    pre_sales_repo.create(
        lead_id=lead1_id,
        data={
            'assignee_id': 'user-tech',
            'status': 'In Progress',
            'request_json': json.dumps({'sample': 'fiber'}),
            'result_json': json.dumps({'result': 'pending'}),
            'due_date': '2026-08-01',
        },
        actor_id='user-1',
    )

    # Customer 2
    customer2 = customer_service.create({
        'display_name': 'Test Company B',
        'country': 'UK',
        'city': 'London',
        'industry': 'Manufacturing'
    }, 'user-1')
    customer2_id = customer2['id']

    # Lead 2 (owned by user-1)
    lead2 = lead_service.create({
        'customer_id': customer2_id,
        'title': 'Test Lead 2',
        'sales_stage': 'Quoted',
        'product_category': 'Fiber Laser',
        'owner_id': 'user-1',
        'deal_amount': 25000,
        'currency': 'EUR'
    }, 'user-1')
    lead2_id = lead2['id']

    # Lead 3 (owned by user-2, should be skipped by user-1 import)
    lead3 = lead_service.create({
        'customer_id': customer2_id,
        'title': 'Test Lead 3',
        'sales_stage': 'New',
        'product_category': 'CO2 Laser',
        'owner_id': 'user-2'
    }, 'user-2')
    lead3_id = lead3['id']

    conn.commit()
    conn.close()

    print(f"✓ Test database created at {db_path}")
    print(f"  - 2 customers, 3 leads")
    print(f"  - Lead 1 & 2: owned by user-1")
    print(f"  - Lead 3: owned by user-2")

    return {
        'customer1_id': customer1_id,
        'customer2_id': customer2_id,
        'lead1_id': lead1_id,
        'lead2_id': lead2_id,
        'lead3_id': lead3_id
    }


def get_database_snapshot(db_path):
    """Get snapshot of database for comparison."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    snapshot = {
        'customers': [],
        'leads': [],
        'activities': [],
        'tasks': [],
        'pre_sales_tasks': [],
    }

    # Customers
    for row in conn.execute("SELECT * FROM customers WHERE archived_at IS NULL ORDER BY id"):
        snapshot['customers'].append({
            'display_name': row['display_name'],
            'country': row['country'],
            'city': row['city'],
            'industry': row['industry']
        })

    # Leads
    for row in conn.execute("SELECT * FROM leads WHERE archived_at IS NULL ORDER BY id"):
        snapshot['leads'].append({
            'title': row['title'],
            'sales_stage': row['sales_stage'],
            'product_category': row['product_category'],
            'deal_amount': row['deal_amount'],
            'currency': row['currency']
        })

    # Activities
    for row in conn.execute("SELECT * FROM lead_activities WHERE archived_at IS NULL ORDER BY id"):
        snapshot['activities'].append({
            'action_type': row['action_type'],
            'summary': row['summary']
        })

    # Tasks
    for row in conn.execute("SELECT * FROM after_sales_tasks WHERE archived_at IS NULL ORDER BY id"):
        snapshot['tasks'].append({
            'issue_type': row['issue_type'],
            'issue_description': row['issue_description'],
            'status': row['status']
        })

    for row in conn.execute("SELECT * FROM pre_sales_tasks WHERE archived_at IS NULL ORDER BY id"):
        snapshot['pre_sales_tasks'].append({
            'status': row['status'],
            'request_json': row['request_json'],
            'result_json': row['result_json'],
            'due_date': row['due_date'],
        })

    conn.close()
    return snapshot


async def test_roundtrip():
    """Test export → import → re-export → compare."""
    print("\n" + "="*60)
    print("TEST 1: Round-trip Verification")
    print("="*60)

    test_dir = Path(__file__).parent / "test_data_exchange"
    test_dir.mkdir(exist_ok=True)

    db1_path = test_dir / "test_db1.sqlite"
    db2_path = test_dir / "test_db2.sqlite"
    export1_path = test_dir / "export1.json"
    export2_path = test_dir / "export2.json"

    # Delete old database files to ensure clean state
    for db_file in [db1_path, db2_path]:
        if db_file.exists():
            db_file.unlink()

    # Step 1: Create initial database
    print("\n[1] Creating initial database...")
    init_db(db1_path)
    test_data = setup_test_database(db1_path)
    # Note: snapshot1 includes all data, but export will only include user-1's data
    # We'll compare based on exported data instead

    # Step 2: First export
    print("\n[2] First export...")
    init_db(db1_path)  # Reinitialize connection

    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')
    mock_request = MockRequest(lead_ids=None)

    from fastapi.responses import StreamingResponse
    response = await export_data(mock_request, mock_user.user_dict)

    # Save export
    if isinstance(response, StreamingResponse):
        content = b''
        async for chunk in response.body_iterator:
            content += chunk if isinstance(chunk, bytes) else chunk.encode()
        with open(export1_path, 'wb') as f:
            f.write(content)

    export1_data = json.loads(export1_path.read_text())
    print(f"✓ Exported {len(export1_data['leads'])} leads")
    print(f"✓ Exported {len(export1_data['customers'])} customers")

    # Step 3: Import to new database
    print("\n[3] Importing to new database...")
    reset_db_connection()  # Reset connection before switching database
    init_db(db2_path)

    # Create same users in db2 (if not exist)
    conn2 = sqlite3.connect(str(db2_path))
    conn2.execute("""
        INSERT OR IGNORE INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)
    conn2.execute("""
        INSERT OR IGNORE INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-2', 'collab1', 'hash2', 'Collaborator One', 'sales', 1, datetime('now'))
    """)
    conn2.execute("""
        INSERT OR IGNORE INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-tech', 'tech1', 'hash3', 'Tech One', 'tech', 1, datetime('now'))
    """)
    conn2.commit()
    conn2.close()

    init_db(db2_path)  # Reinitialize

    mock_file = MockUploadFile(str(export1_path))
    import_report = await import_data(mock_file, mock_user.user_dict)

    print(f"✓ Import report:")
    print(f"  - New customers: {import_report['new_customers']}")
    print(f"  - New leads: {import_report['new_leads']}")
    print(f"  - Updated customers: {import_report['updated_customers']}")
    print(f"  - Updated leads: {import_report['updated_leads']}")
    print(f"  - Skipped: {import_report['skipped_records']}")
    print(f"  - Errors: {len(import_report['errors'])}")

    if import_report['errors']:
        print("  Errors:")
        for err in import_report['errors']:
            print(f"    - {err}")

    # Step 4: Second export from imported database
    print("\n[4] Second export from imported database...")
    reset_db_connection()  # Ensure we're using db2
    init_db(db2_path)
    response2 = await export_data(mock_request, mock_user.user_dict)

    if isinstance(response2, StreamingResponse):
        content = b''
        async for chunk in response2.body_iterator:
            content += chunk if isinstance(chunk, bytes) else chunk.encode()
        with open(export2_path, 'wb') as f:
            f.write(content)

    export2_data = json.loads(export2_path.read_text())

    # Step 5: Compare based on exported data
    print("\n[5] Comparing export results...")
    snapshot2 = get_database_snapshot(db2_path)

    # Compare counts based on what was exported, not the full DB1
    exported_customer_count = len(export1_data['customers'])
    exported_lead_count = len(export1_data['leads'])

    print(f"  Exported: {exported_customer_count} customers, {exported_lead_count} leads")
    print(f"  DB2: {len(snapshot2['customers'])} customers, {len(snapshot2['leads'])} leads")

    # Verify imported counts match exported counts
    assert exported_customer_count == len(snapshot2['customers']), \
        f"Customer count mismatch: exported {exported_customer_count} vs imported {len(snapshot2['customers'])}"
    assert exported_lead_count == len(snapshot2['leads']), \
        f"Lead count mismatch: exported {exported_lead_count} vs imported {len(snapshot2['leads'])}"

    # Compare two exports: export1 and export2 should be identical (except timestamps)
    print(f"  Export1: {len(export1_data['customers'])} customers, {len(export1_data['leads'])} leads")
    print(f"  Export2: {len(export2_data['customers'])} customers, {len(export2_data['leads'])} leads")

    assert len(export1_data['customers']) == len(export2_data['customers']), \
        "Customer count mismatch between exports"
    assert len(export1_data['leads']) == len(export2_data['leads']), \
        "Lead count mismatch between exports"
    assert len(snapshot2['pre_sales_tasks']) == 1, \
        "Pre-sales tasks should survive export/import"

    # Compare customer display names
    export1_customers = sorted([c['display_name'] for c in export1_data['customers'].values()])
    export2_customers = sorted([c['display_name'] for c in export2_data['customers'].values()])
    assert export1_customers == export2_customers, \
        f"Customer names mismatch: {export1_customers} vs {export2_customers}"

    # Compare lead titles
    export1_leads = sorted([l['lead']['title'] for l in export1_data['leads']])
    export2_leads = sorted([l['lead']['title'] for l in export2_data['leads']])
    assert export1_leads == export2_leads, \
        f"Lead titles mismatch: {export1_leads} vs {export2_leads}"

    print("✓ All counts and key fields match!")
    print("\n✅ Round-trip test PASSED")

    return test_dir


async def test_idempotency(test_dir):
    """Test that repeated imports are idempotent."""
    print("\n" + "="*60)
    print("TEST 2: Idempotency (Repeated Import)")
    print("="*60)

    db_path = test_dir / "test_db_idem.sqlite"
    export_path = test_dir / "export1.json"

    # Delete old database file to ensure clean state
    if db_path.exists():
        db_path.unlink()

    # Create fresh database
    print("\n[1] Creating fresh database...")
    reset_db_connection()
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)
    conn.commit()
    conn.close()

    init_db(db_path)
    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')

    # First import
    print("\n[2] First import...")
    mock_file = MockUploadFile(str(export_path))
    report1 = await import_data(mock_file, mock_user.user_dict)
    snapshot1 = get_database_snapshot(db_path)

    print(f"  - New customers: {report1['new_customers']}")
    print(f"  - New leads: {report1['new_leads']}")

    # Second import (should be idempotent)
    print("\n[3] Second import (should update, not duplicate)...")
    mock_file2 = MockUploadFile(str(export_path))
    report2 = await import_data(mock_file2, mock_user.user_dict)
    snapshot2 = get_database_snapshot(db_path)

    print(f"  - New customers: {report2['new_customers']}")
    print(f"  - New leads: {report2['new_leads']}")
    print(f"  - Updated customers: {report2['updated_customers']}")
    print(f"  - Updated leads: {report2['updated_leads']}")

    # Verify no duplicates
    assert report2['new_customers'] == 0, "Should not create duplicate customers"
    assert report2['new_leads'] == 0, "Should not create duplicate leads"
    assert len(snapshot1['customers']) == len(snapshot2['customers']), "Customer count should not change"
    assert len(snapshot1['leads']) == len(snapshot2['leads']), "Lead count should not change"

    print("\n✅ Idempotency test PASSED - no duplicates created")


async def test_same_database_exchange_idempotency(test_dir):
    """Test that export→import in the same DB does not duplicate existing leads."""
    print("\n" + "="*60)
    print("TEST 3: Same Database Exchange Idempotency")
    print("="*60)

    db_path = test_dir / "test_db_same_exchange.sqlite"
    export_path = test_dir / "same_exchange_export.json"

    if db_path.exists():
        db_path.unlink()

    print("\n[1] Creating source database...")
    reset_db_connection()
    init_db(db_path)
    setup_test_database(db_path)

    reset_db_connection()
    init_db(db_path)
    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')
    response = await export_data(MockRequest(None), mock_user.user_dict)
    export_json = await write_streaming_response(response, export_path)
    exported_lead_count = len(export_json["leads"])
    print(f"  - Exported leads: {exported_lead_count}")

    before = get_database_snapshot(db_path)

    print("\n[2] Importing export back into the same database...")
    report = await import_data(MockUploadFile(str(export_path)), mock_user.user_dict)
    after = get_database_snapshot(db_path)

    print(f"  - New leads: {report['new_leads']}")
    print(f"  - Updated leads: {report['updated_leads']}")
    print(f"  - Errors: {len(report['errors'])}")

    assert report["new_leads"] == 0, "Same-DB import should update, not duplicate leads"
    assert report["updated_leads"] == exported_lead_count, "Same-DB import should match exported leads"
    assert len(before["leads"]) == len(after["leads"]), "Lead count should remain unchanged"
    assert not report["errors"], f"Same-DB import should not have errors: {report['errors']}"

    print("\n✅ Same database exchange idempotency test PASSED")


async def test_permission_filtering(test_dir):
    """Test that non-leader users can't import others' leads."""
    print("\n" + "="*60)
    print("TEST 4: Permission Filtering")
    print("="*60)

    db_path = test_dir / "test_db_perm.sqlite"
    export_path = test_dir / "export1.json"

    # Delete old database file to ensure clean state
    if db_path.exists():
        db_path.unlink()

    # Create fresh database with user-2 (not owner of exported leads)
    print("\n[1] Creating database with different user...")
    reset_db_connection()
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-2', 'collab1', 'hash2', 'Collaborator One', 'sales', 1, datetime('now'))
    """)
    conn.commit()
    conn.close()

    reset_db_connection()
    init_db(db_path)
    mock_user = MockUser('user-2', 'collab1', 'Collaborator One', 'sales')

    # Import as user-2 (should skip leads owned by user-1)
    print("\n[2] Importing as user-2 (should skip user-1's leads)...")
    mock_file = MockUploadFile(str(export_path))
    report = await import_data(mock_file, mock_user.user_dict)

    print(f"  - Total records: {report['total_records']}")
    print(f"  - Skipped: {report['skipped_records']}")
    print(f"  - New leads: {report['new_leads']}")

    # All leads should be skipped (they're owned by user-1)
    assert report['skipped_records'] == report['total_records'], \
        "All leads should be skipped for non-owner user"

    print("\n✅ Permission filtering test PASSED")


async def test_activity_merge(test_dir):
    """Test that importing to existing lead merges activities correctly."""
    print("\n" + "="*60)
    print("TEST 5: Existing Lead Activity Merge")
    print("="*60)

    db_path = test_dir / "test_db_merge.sqlite"

    # Delete old database file to ensure clean state
    if db_path.exists():
        db_path.unlink()

    # Create fresh database with a lead that has an activity
    print("\n[1] Creating database with lead and activity...")
    reset_db_connection()
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)
    conn.commit()
    conn.close()

    reset_db_connection()
    init_db(db_path)

    customer_service = CustomerService()
    lead_service = LeadService()
    activity_repo = ActivityRepository()

    customer = customer_service.create({
        'display_name': 'Merge Test Company',
        'country': 'US'
    }, 'user-1')

    lead = lead_service.create({
        'customer_id': customer['id'],
        'title': 'Merge Test Lead',
        'sales_stage': 'Following',
        'owner_id': 'user-1',
        'legacy_inquiry_id': 'LEGACY-MERGE-001'  # Use legacy_id for matching
    }, 'user-1')

    # Add an activity
    activity_repo.create(
        lead_id=lead['id'],
        actor_id='user-1',
        action_type='follow_up',
        summary='Original activity from source',
        is_formal_follow_up=True
    )

    initial_activities = activity_repo.list_for_lead(lead['id'])
    print(f"✓ Created lead with {len(initial_activities)} activity")

    # Export
    print("\n[2] Exporting...")
    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')
    mock_request = MockRequest(None)

    from backend.routers.data_exchange import export_data
    from fastapi.responses import StreamingResponse
    response = await export_data(mock_request, mock_user.user_dict)

    export_path = test_dir / "merge_export.json"
    if isinstance(response, StreamingResponse):
        content = b''
        async for chunk in response.body_iterator:
            content += chunk if isinstance(chunk, bytes) else chunk.encode()
        with open(export_path, 'wb') as f:
            f.write(content)

    export_data_json = json.loads(export_path.read_text())
    print(f"✓ Exported lead with {len(export_data_json['leads'][0]['activities'])} activity")

    # Add a NEW activity locally (after export)
    print("\n[3] Adding new activity locally (after export)...")
    reset_db_connection()
    init_db(db_path)

    activity_repo_new = ActivityRepository()
    activity_repo_new.create(
        lead_id=lead['id'],
        actor_id='user-1',
        action_type='comment',
        summary='New local activity added after export',
        is_formal_follow_up=False
    )

    activities_before_import = activity_repo_new.list_for_lead(lead['id'])
    print(f"✓ Lead now has {len(activities_before_import)} activities before import")

    # Import - should merge, not overwrite
    print("\n[4] Importing (should merge activities)...")
    reset_db_connection()
    init_db(db_path)

    from backend.routers.data_exchange import import_data
    mock_file = MockUploadFile(str(export_path))
    report = await import_data(mock_file, mock_user.user_dict)

    print(f"  - Updated leads: {report['updated_leads']}")
    print(f"  - Merged activities: {report.get('merged_activities', 0)}")
    print(f"  - Errors: {len(report['errors'])}")

    # Verify both activities exist
    reset_db_connection()
    init_db(db_path)
    activity_repo_final = ActivityRepository()
    final_activities = activity_repo_final.list_for_lead(lead['id'])

    print(f"\n[5] Verifying activity merge...")
    print(f"  - Final activity count: {len(final_activities)}")

    activity_summaries = [a['summary'] for a in final_activities]
    original_exists = 'Original activity from source' in activity_summaries
    new_exists = 'New local activity added after export' in activity_summaries

    print(f"  - Original activity exists: {original_exists}")
    print(f"  - New local activity exists: {new_exists}")

    # After import, we should have all activities from before import (no data loss)
    assert len(final_activities) >= len(activities_before_import), \
        f"Activity count decreased: had {len(activities_before_import)}, now {len(final_activities)}"
    assert original_exists, "Original activity was lost during merge"
    assert new_exists, "New local activity was overwritten"

    print("\n✅ Activity merge test PASSED")


async def test_full_activity_export(test_dir):
    """Test that export/import handles more than the default 50 activities."""
    print("\n" + "="*60)
    print("TEST 6: Full Activity Export (>50 activities)")
    print("="*60)

    db_path = test_dir / "test_db_many_activities.sqlite"
    export_path = test_dir / "many_activities_export.json"
    target_db_path = test_dir / "test_db_many_activities_import.sqlite"

    for db_file in [db_path, target_db_path]:
        if db_file.exists():
            db_file.unlink()

    print("\n[1] Creating source database...")
    reset_db_connection()
    init_db(db_path)
    test_data = setup_test_database(db_path)

    reset_db_connection()
    init_db(db_path)
    activity_repo = ActivityRepository()
    for idx in range(60):
        activity_repo.create(
            lead_id=test_data["lead1_id"],
            actor_id="user-1",
            action_type="comment",
            summary=f"Bulk activity {idx:02d}",
            payload_json=json.dumps({"idx": idx}),
        )

    print("\n[2] Exporting selected lead...")
    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')
    response = await export_data(MockRequest([test_data["lead1_id"]]), mock_user.user_dict)
    export_json = await write_streaming_response(response, export_path)
    exported_count = len(export_json["leads"][0]["activities"])
    print(f"  - Exported activities: {exported_count}")

    assert exported_count > 50, "Export should include full activity history, not default page size"

    print("\n[3] Importing to clean database...")
    reset_db_connection()
    init_db(target_db_path)
    conn = sqlite3.connect(str(target_db_path))
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)
    conn.commit()
    conn.close()

    reset_db_connection()
    init_db(target_db_path)
    report = await import_data(MockUploadFile(str(export_path)), mock_user.user_dict)
    print(f"  - Merged activities: {report['merged_activities']}")
    print(f"  - Errors: {len(report['errors'])}")

    assert not report["errors"], f"Import should not have errors: {report['errors']}"

    conn = sqlite3.connect(str(target_db_path))
    final_count = conn.execute(
        "SELECT COUNT(*) FROM lead_activities WHERE archived_at IS NULL"
    ).fetchone()[0]
    conn.close()
    print(f"  - Imported active activities: {final_count}")

    assert final_count > 50, "Import should retain more than 50 activities"

    print("\n✅ Full activity export test PASSED")


async def test_display_id_conflict_import(test_dir):
    """Test that imported display_id is not reused across databases."""
    print("\n" + "="*60)
    print("TEST 7: Cross-database display_id conflict")
    print("="*60)

    source_db_path = test_dir / "test_db_display_source.sqlite"
    target_db_path = test_dir / "test_db_display_target.sqlite"
    export_path = test_dir / "display_conflict_export.json"

    for db_file in [source_db_path, target_db_path]:
        if db_file.exists():
            db_file.unlink()

    print("\n[1] Creating source database and export...")
    reset_db_connection()
    init_db(source_db_path)
    source_data = setup_test_database(source_db_path)

    reset_db_connection()
    init_db(source_db_path)
    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')
    response = await export_data(MockRequest([source_data["lead1_id"]]), mock_user.user_dict)
    export_json = await write_streaming_response(response, export_path)
    source_display_id = export_json["leads"][0]["lead"]["display_id"]
    print(f"  - Source display_id: {source_display_id}")

    print("\n[2] Creating target database with same local display_id...")
    reset_db_connection()
    init_db(target_db_path)
    conn = sqlite3.connect(str(target_db_path))
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)
    conn.commit()
    conn.close()

    reset_db_connection()
    init_db(target_db_path)
    customer_service = CustomerService()
    lead_service = LeadService()
    target_customer = customer_service.create({
        "display_name": "Target Local Company",
        "country": "US",
    }, "user-1")
    target_lead = lead_service.create({
        "customer_id": target_customer["id"],
        "title": "Existing Local Lead",
        "sales_stage": "New",
        "owner_id": "user-1",
    }, "user-1")
    print(f"  - Target existing display_id: {target_lead['display_id']}")

    assert target_lead["display_id"] == source_display_id, \
        "Test setup expects matching display_id values"

    print("\n[3] Importing source export...")
    report = await import_data(MockUploadFile(str(export_path)), mock_user.user_dict)
    print(f"  - New leads: {report['new_leads']}")
    print(f"  - Errors: {len(report['errors'])}")

    assert report["new_leads"] == 1, "Import should create a new lead"
    assert not report["errors"], f"Import should not fail on display_id conflict: {report['errors']}"

    conn = sqlite3.connect(str(target_db_path))
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(
        "SELECT title, display_id, extra_json FROM leads WHERE archived_at IS NULL ORDER BY created_at"
    )]
    conn.close()

    imported = next(row for row in rows if row["title"] == "Test Lead 1")
    assert imported["display_id"] != source_display_id, "Imported lead should receive a local display_id"
    extra_json = json.loads(imported["extra_json"])
    assert extra_json["source_display_id"] == source_display_id, \
        "Original display_id should be preserved as source metadata"

    print("\n✅ display_id conflict test PASSED")


async def test_existing_lead_permission_guard(test_dir):
    """Test that imported owner_id cannot bypass local existing-lead permissions."""
    print("\n" + "="*60)
    print("TEST 8: Existing Lead Permission Guard")
    print("="*60)

    db_path = test_dir / "test_db_permission_guard.sqlite"
    import_path = test_dir / "permission_guard_import.json"

    if db_path.exists():
        db_path.unlink()

    reset_db_connection()
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-2', 'owner2', 'hash2', 'Owner Two', 'sales', 1, datetime('now'))
    """)
    conn.commit()
    conn.close()

    reset_db_connection()
    init_db(db_path)
    customer_service = CustomerService()
    lead_service = LeadService()
    customer = customer_service.create({
        "display_name": "Protected Customer",
        "country": "US",
    }, "user-2")
    lead = lead_service.create({
        "customer_id": customer["id"],
        "title": "Protected Lead",
        "sales_stage": "Following",
        "owner_id": "user-2",
        "legacy_inquiry_id": "LEGACY-SENSITIVE",
    }, "user-2")

    payload = {
        "export_time": datetime.utcnow().isoformat(),
        "exported_by": "user-1",
        "exporter_name": "Owner One",
        "version": "v2.0",
        "customers": {
            "source-customer": {
                "id": "source-customer",
                "display_name": "Polluting Customer",
                "country": "CA",
                "contacts": [],
            }
        },
        "leads": [
            {
                "lead": {
                    "id": "source-lead",
                    "display_id": "EXT-0001",
                    "customer_id": "source-customer",
                    "title": "Unauthorized Update",
                    "sales_stage": "Won",
                    "owner_id": "user-1",
                    "legacy_inquiry_id": "LEGACY-SENSITIVE",
                },
                "activities": [],
                "after_sales_tasks": [],
                "attachments": [],
            }
        ],
    }
    import_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print("\n[1] Importing crafted file as non-owner...")
    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')
    report = await import_data(MockUploadFile(str(import_path)), mock_user.user_dict)
    print(f"  - Skipped: {report['skipped_records']}")
    print(f"  - Updated leads: {report['updated_leads']}")

    assert report["skipped_records"] == 1, "Existing lead should be skipped"
    assert report["updated_leads"] == 0, "Unauthorized import should not update lead"

    reset_db_connection()
    init_db(db_path)
    lead_after = LeadRepository().get_by_id(lead["id"])
    assert lead_after["title"] == "Protected Lead", "Protected lead title changed"

    customer_count = CustomerRepository().count("archived_at IS NULL")
    assert customer_count == 1, "Skipped import should not pollute customers"

    print("\n✅ Existing lead permission guard test PASSED")


async def test_customer_contact_merge(test_dir):
    """Test that importing into an existing customer merges contacts."""
    print("\n" + "="*60)
    print("TEST 9: Customer Contact Merge")
    print("="*60)

    db_path = test_dir / "test_db_contact_merge.sqlite"
    import_path = test_dir / "contact_merge_import.json"

    if db_path.exists():
        db_path.unlink()

    reset_db_connection()
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
        VALUES ('user-1', 'owner1', 'hash1', 'Owner One', 'sales', 1, datetime('now'))
    """)
    conn.commit()
    conn.close()

    reset_db_connection()
    init_db(db_path)
    customer_service = CustomerService()
    customer = customer_service.create({
        "display_name": "Contact Merge Company",
        "country": "US",
    }, "user-1")
    customer_service.add_contact(customer["id"], {
        "name": "Alice",
        "email": "alice@example.com",
        "phone": "old-phone",
        "is_primary": True,
    }, "user-1")

    payload = {
        "export_time": datetime.utcnow().isoformat(),
        "exported_by": "user-1",
        "exporter_name": "Owner One",
        "version": "v2.0",
        "customers": {
            "source-customer": {
                "id": "source-customer",
                "display_name": "Contact Merge Company",
                "country": "US",
                "contacts": [
                    {
                        "id": "source-contact-1",
                        "name": "Alice",
                        "email": "alice@example.com",
                        "phone": "new-phone",
                        "is_primary": True,
                    },
                    {
                        "id": "source-contact-2",
                        "name": "Bob",
                        "email": "bob@example.com",
                        "phone": "bob-phone",
                        "is_primary": False,
                    },
                ],
            }
        },
        "leads": [
            {
                "lead": {
                    "id": "source-lead",
                    "display_id": "EXT-0002",
                    "customer_id": "source-customer",
                    "title": "Contact Merge Lead",
                    "sales_stage": "New",
                    "owner_id": "user-1",
                },
                "activities": [],
                "after_sales_tasks": [],
                "attachments": [],
            }
        ],
    }
    import_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print("\n[1] Importing contact merge file...")
    mock_user = MockUser('user-1', 'owner1', 'Owner One', 'sales')
    report = await import_data(MockUploadFile(str(import_path)), mock_user.user_dict)
    print(f"  - New customers: {report['new_customers']}")
    print(f"  - Merged contacts: {report['merged_contacts']}")
    print(f"  - Errors: {len(report['errors'])}")

    assert report["new_customers"] == 0, "Existing customer should be matched, not duplicated"
    assert report["merged_contacts"] == 2, "Should update Alice and add Bob"
    assert not report["errors"], f"Import should not have errors: {report['errors']}"

    contacts = CustomerRepository().get_contacts(customer["id"])
    assert len(contacts) == 2, f"Expected 2 contacts, got {len(contacts)}"
    by_email = {contact["email"]: contact for contact in contacts}
    assert by_email["alice@example.com"]["phone"] == "new-phone", "Existing contact not updated"
    assert "bob@example.com" in by_email, "New contact not added"

    print("\n✅ Customer contact merge test PASSED")


async def test_identity_and_pre_sales_hardening(test_dir):
    """Verify source owners, nullable history identities, task roles, and idempotency."""
    print("\n" + "="*60)
    print("TEST 10: Identity-safe import and pre-sales round-trip")
    print("="*60)

    db_path = test_dir / "test_db_identity_hardening.sqlite"
    import_path = test_dir / "identity_hardening_import.json"
    export_path = test_dir / "identity_hardening_export.json"
    if db_path.exists():
        db_path.unlink()

    reset_db_connection()
    init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    users = (
        ("leader-local", "leader", "Local Leader", "leader", 1),
        ("sales-source", "sales", "Source Sales", "sales", 1),
        ("tech-active", "tech", "Active Tech", "tech", 1),
        ("sales-inactive", "inactive", "Inactive Sales", "sales", 0),
        ("tech-inactive", "inactive-tech", "Inactive Tech", "tech", 0),
    )
    conn.executemany(
        """
        INSERT INTO users (
            id, username, password_hash, display_name, role, is_active, created_at
        ) VALUES (?, ?, 'hash', ?, ?, ?, datetime('now'))
        """,
        users,
    )
    conn.commit()
    conn.close()

    def lead_item(source_id, customer_id, owner_id, title, related=False):
        item = {
            "lead": {
                "id": source_id,
                "display_id": f"EXT-{source_id}",
                "customer_id": customer_id,
                "title": title,
                "sales_stage": "Following",
                "owner_id": owner_id,
            },
            "activities": [],
            "pre_sales_tasks": [],
            "after_sales_tasks": [],
            "attachments": [],
        }
        if not related:
            return item
        item["activities"] = [
            {
                "id": "activity-unknown",
                "actor_id": "missing-actor",
                "action_type": "comment",
                "summary": "Unknown historical actor",
                "created_at": "2026-01-01T09:00:00",
            },
            {
                "id": "activity-inactive",
                "actor_id": "tech-inactive",
                "action_type": "comment",
                "summary": "Inactive historical actor",
                "created_at": "2026-01-01T09:05:00",
            },
        ]
        item["pre_sales_tasks"] = [
            {
                "id": "pre-valid",
                "assignee_id": "tech-active",
                "status": "In Progress",
                "request_json": {"sample": "A"},
                "result_json": {"result": "pending"},
                "due_date": "2026-02-01",
                "created_at": "2026-01-01T10:00:00",
                "updated_at": "2026-01-02T10:00:00",
            },
            {
                "id": "pre-sales-role",
                "assignee_id": "sales-source",
                "status": "Open",
                "request_json": {"sample": "B"},
                "created_at": "2026-01-01T10:05:00",
            },
            {
                "id": "pre-inactive",
                "assignee_id": "tech-inactive",
                "status": "Open",
                "request_json": {"sample": "C"},
                "created_at": "2026-01-01T10:10:00",
            },
            {
                "id": "pre-unknown",
                "assignee_id": "missing-tech",
                "status": "Open",
                "request_json": {"sample": "D"},
                "created_at": "2026-01-01T10:15:00",
            },
        ]
        item["after_sales_tasks"] = [
            {
                "id": "after-valid",
                "assignee_id": "tech-active",
                "issue_type": "Technical",
                "status": "Open",
                "issue_description": "Valid technical owner",
                "created_at": "2026-01-01T11:00:00",
            },
            {
                "id": "after-unknown",
                "assignee_id": "missing-tech",
                "issue_type": "Other",
                "status": "Open",
                "issue_description": "Unknown technical owner",
                "created_at": "2026-01-01T11:05:00",
            },
        ]
        return item

    customer_specs = {
        "customer-valid": "Identity Valid Customer",
        "customer-tech-owner": "Identity Tech Owner Customer",
        "customer-inactive-owner": "Identity Inactive Owner Customer",
        "customer-unknown-owner": "Identity Unknown Owner Customer",
    }
    payload = {
        "export_time": "2026-01-03T00:00:00",
        "exported_by": "source-system",
        "exporter_name": "Source System",
        "version": "v2.0",
        "customers": {
            key: {"id": key, "display_name": name, "contacts": []}
            for key, name in customer_specs.items()
        },
        "leads": [
            lead_item(
                "lead-valid", "customer-valid", "sales-source",
                "Valid source owner", related=True,
            ),
            lead_item(
                "lead-tech-owner", "customer-tech-owner", "tech-active",
                "Tech cannot own lead",
            ),
            lead_item(
                "lead-inactive-owner", "customer-inactive-owner", "sales-inactive",
                "Inactive sales cannot own lead",
            ),
            lead_item(
                "lead-unknown-owner", "customer-unknown-owner", "missing-sales",
                "Unknown sales cannot own lead",
            ),
        ],
    }
    import_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    leader = MockUser("leader-local", "leader", "Local Leader", "leader")
    preflight = await preflight_import(
        MockUploadFile(str(import_path)),
        leader.user_dict,
    )
    assert preflight["permission"]["allowed_leads"] == 1
    assert preflight["summary"]["errors"] == 3
    assert preflight["source_snapshot"]["pre_sales_tasks"] == 4
    assert preflight["source_snapshot"]["after_sales_tasks"] == 2

    first = await import_data(MockUploadFile(str(import_path)), leader.user_dict)
    assert first["new_leads"] == 1, "Only the valid source owner lead should import"
    assert first["skipped_records"] == 3, "Invalid owners must block their leads"
    assert first["merged_pre_sales_tasks"] == 4
    assert first["merged_after_sales_tasks"] == 2
    assert first["merged_tasks"] == 6
    assert first["snapshot_delta"]["pre_sales_tasks"] == 4
    assert first["snapshot_delta"]["after_sales_tasks"] == 2
    assert len(first["errors"]) == 3
    assert any("must have role leader/sales" in error for error in first["errors"])
    assert any("is inactive" in error for error in first["errors"])
    assert any("does not exist locally" in error for error in first["errors"])
    assert any("imported as null" in warning for warning in first["warnings"])
    assert any("imported as unassigned" in warning for warning in first["warnings"])

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    imported_lead = dict(conn.execute(
        "SELECT id, owner_id FROM leads WHERE title = 'Valid source owner'"
    ).fetchone())
    assert imported_lead["owner_id"] == "sales-source", \
        "Leader import must preserve a valid source commercial owner"
    assert conn.execute(
        "SELECT COUNT(*) FROM customers WHERE archived_at IS NULL"
    ).fetchone()[0] == 1, "Blocked leads must not pollute customers"

    activity_actors = {
        row["summary"]: row["actor_id"]
        for row in conn.execute(
            "SELECT summary, actor_id FROM lead_activities WHERE lead_id = ?",
            (imported_lead["id"],),
        )
    }
    assert activity_actors["Unknown historical actor"] is None
    assert activity_actors["Inactive historical actor"] is None

    pre_assignees = [row[0] for row in conn.execute(
        "SELECT assignee_id FROM pre_sales_tasks WHERE lead_id = ? ORDER BY created_at",
        (imported_lead["id"],),
    )]
    after_assignees = [row[0] for row in conn.execute(
        "SELECT assignee_id FROM after_sales_tasks WHERE lead_id = ? ORDER BY created_at",
        (imported_lead["id"],),
    )]
    assert pre_assignees == ["tech-active", None, None, None]
    assert after_assignees == ["tech-active", None]
    conn.close()

    try:
        LeadRepository().add_assignment(
            imported_lead["id"],
            "tech-active",
            "collaborator",
            "leader-local",
        )
    except ValueError as exc:
        assert "cannot be lead owners or collaborators" in str(exc)
    else:
        raise AssertionError("Tech must not be accepted as a lead collaborator")

    second = await import_data(MockUploadFile(str(import_path)), leader.user_dict)
    assert second["new_leads"] == 0
    assert second["merged_activities"] == 0
    assert second["merged_pre_sales_tasks"] == 0
    assert second["merged_after_sales_tasks"] == 0

    response = await export_data(
        MockRequest([imported_lead["id"]]),
        leader.user_dict,
    )
    exported = await write_streaming_response(response, export_path)
    exported_lead = exported["leads"][0]
    assert len(exported_lead["pre_sales_tasks"]) == 4
    assert len(exported_lead["after_sales_tasks"]) == 2
    assert any(
        task["assignee_id"] == "tech-active"
        for task in exported_lead["pre_sales_tasks"]
    )

    print("\n✅ Identity-safe import and pre-sales round-trip test PASSED")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("EXPORT/IMPORT ROUND-TRIP VALIDATION")
    print("="*60)

    try:
        # Test 1: Round-trip
        test_dir = await test_roundtrip()

        # Test 2: Idempotency
        await test_idempotency(test_dir)

        # Test 3: Same database exchange idempotency
        await test_same_database_exchange_idempotency(test_dir)

        # Test 4: Permission filtering
        await test_permission_filtering(test_dir)

        # Test 5: Existing lead activity merge
        await test_activity_merge(test_dir)

        # Test 6: Full activity export/import
        await test_full_activity_export(test_dir)

        # Test 7: Cross-database display_id conflict
        await test_display_id_conflict_import(test_dir)

        # Test 8: Existing lead permission guard
        await test_existing_lead_permission_guard(test_dir)

        # Test 9: Customer contact merge
        await test_customer_contact_merge(test_dir)

        # Test 10: Identity-safe import and pre-sales round-trip
        await test_identity_and_pre_sales_hardening(test_dir)

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print(f"\nTest artifacts saved in: {test_dir}")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    import asyncio
    sys.exit(asyncio.run(main()))
