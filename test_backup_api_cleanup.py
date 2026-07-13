"""
Test backup API with retention policy.

Verifies that:
1. Creating backups triggers cleanup
2. Cleanup result is included in API response
3. Old backups are automatically removed
"""

import asyncio
import time
from pathlib import Path

from backend.config import init_settings
from backend.repositories import init_db, close_db, UserRepository
from backend.services.admin_service import AdminService


def setup_test_env(test_name="default"):
    """Setup test environment."""
    test_dir = Path(f"test_backup_api_data_{test_name}")
    test_dir.mkdir(exist_ok=True)

    db_path = test_dir / "database.sqlite"
    if db_path.exists():
        db_path.unlink()

    # Initialize database
    settings = init_settings(Path.cwd())
    settings.db_path = str(db_path)
    init_db(str(db_path))

    # Create test user
    user_repo = UserRepository()
    user_id = user_repo.create(
        username="admin",
        password_hash="dummy",
        display_name="Admin",
        role="leader",
        region="EU"
    )

    return test_dir, user_id


async def test_backup_cleanup_integration():
    """Test backup API with automatic cleanup."""
    print("\n" + "="*60)
    print("TEST: Backup API Cleanup Integration")
    print("="*60)

    test_dir, user_id = setup_test_env("integration")
    backup_dir = test_dir / "backups"

    # Clean up any existing backups
    import shutil
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(exist_ok=True)

    service = AdminService(data_dir=test_dir)

    # First, create 9 dummy backups manually to avoid long sleep times
    # Use old timestamps (35+ days ago) to simulate old backups
    print("\n[Creating 9 initial dummy backups (35-50 days old)...]")
    import zipfile
    import os
    from datetime import datetime, timedelta
    base_time = datetime.now() - timedelta(days=50)
    for i in range(9):
        old_timestamp = base_time + timedelta(days=i)
        timestamp_str = old_timestamp.strftime("%Y%m%d_%H%M%S")
        dummy_name = f"backup_{timestamp_str}.zip"
        dummy_path = backup_dir / dummy_name

        # Create zip file
        with zipfile.ZipFile(dummy_path, 'w') as zf:
            zf.writestr("dummy.txt", "dummy")

        # Set file mtime to old timestamp
        old_time = old_timestamp.timestamp()
        os.utime(dummy_path, (old_time, old_time))

        print(f"  {dummy_name}")

    # Now create 3 real backups through API
    print("\n[Creating 3 real backups through API...]")
    total_deleted = 0
    for i in range(3):
        result = service.backup(backup_dir, user_id)
        print(f"  Backup {i+1}: {Path(result['backup_path']).name}")

        # Track cleanup stats
        cleanup = result.get('cleanup', {})
        deleted = cleanup.get('deleted', 0)
        if deleted > 0:
            print(f"    -> Cleanup: deleted {deleted}, kept {cleanup.get('kept', 0)}")
            total_deleted += deleted

        # Sleep to ensure different timestamps (timestamp is second-precision)
        time.sleep(1.1)

    # Check cleanup result from last backup
    print(f"\nFinal cleanup result:")
    print(f"  Last cleanup deleted: {result.get('cleanup', {}).get('deleted', 0)}")
    print(f"  Total deleted across all backups: {total_deleted}")
    print(f"  Policy: {result.get('cleanup', {}).get('policy', {})}")

    # Verify final state
    remaining_backups = list(backup_dir.glob("backup_*.zip"))
    print(f"\nFinal backup count: {len(remaining_backups)}")

    # Should have exactly 10 backups (keep_count=10)
    assert len(remaining_backups) == 10, f"Expected 10 backups, got {len(remaining_backups)}"

    # Verify cleanup was triggered (total across all backup calls)
    assert total_deleted == 2, f"Expected 2 total deleted, got {total_deleted}"

    print("\n✅ Backup API cleanup integration works correctly")

    # Close database connection before cleanup
    close_db()

    # Cleanup test directory
    import shutil
    shutil.rmtree(test_dir)


async def test_manual_cleanup():
    """Test manual cleanup_old_backups call."""
    print("\n" + "="*60)
    print("TEST: Manual Cleanup")
    print("="*60)

    test_dir, user_id = setup_test_env("manual")
    backup_dir = test_dir / "backups"

    # Clean up any existing backups
    import shutil
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(exist_ok=True)

    service = AdminService(data_dir=test_dir)

    # Create 15 backups: 10 recent, 5 old (35+ days)
    print("\n[Creating 15 backups: 10 recent, 5 old...]")
    import zipfile
    import os
    from datetime import datetime, timedelta

    for i in range(15):
        # First 5 are old (35+ days), last 10 are recent
        if i < 5:
            old_timestamp = datetime.now() - timedelta(days=35 + i)
            timestamp_str = old_timestamp.strftime("%Y%m%d_%H%M%S")
        else:
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")

        backup_name = f"backup_{timestamp_str}_{i:02d}"
        backup_path = backup_dir / f"{backup_name}.zip"

        # Create a simple zip file
        with zipfile.ZipFile(backup_path, 'w') as zf:
            zf.writestr("test.txt", "test")

        # Set old mtime for old backups
        if i < 5:
            old_time = old_timestamp.timestamp()
            os.utime(backup_path, (old_time, old_time))

        time.sleep(0.05)

    print(f"Created {len(list(backup_dir.glob('backup_*.zip')))} backups")

    # Now run manual cleanup
    print("\n[Running manual cleanup with keep_count=10...]")
    result = service.cleanup_old_backups(backup_dir, keep_count=10, keep_days=30)

    print(f"  Deleted: {result['deleted']}")
    print(f"  Kept: {result['kept']}")

    remaining = list(backup_dir.glob("backup_*.zip"))
    print(f"  Remaining files: {len(remaining)}")

    assert result['deleted'] == 5, f"Expected 5 deleted, got {result['deleted']}"
    assert result['kept'] == 10, f"Expected 10 kept, got {result['kept']}"
    assert len(remaining) == 10, f"Expected 10 files, got {len(remaining)}"

    print("\n✅ Manual cleanup works correctly")

    # Close database connection before cleanup
    close_db()

    # Cleanup test directory
    import shutil
    shutil.rmtree(test_dir)


async def test_same_second_backups_are_unique():
    """Test repeated backups in the same second do not overwrite each other."""
    print("\n" + "="*60)
    print("TEST: Same-second Backups Are Unique")
    print("="*60)

    test_dir, user_id = setup_test_env("same_second")
    backup_dir = test_dir / "backups"

    import shutil
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(exist_ok=True)

    service = AdminService(data_dir=test_dir)

    first = service.backup(backup_dir, user_id)
    second = service.backup(backup_dir, user_id)

    first_path = Path(first["backup_path"])
    second_path = Path(second["backup_path"])
    remaining = list(backup_dir.glob("backup_*.zip"))

    print(f"  First: {first_path.name}")
    print(f"  Second: {second_path.name}")
    print(f"  Remaining files: {len(remaining)}")

    assert first_path != second_path, "Expected distinct backup paths"
    assert first_path.exists(), "First backup was overwritten or removed"
    assert second_path.exists(), "Second backup was not created"
    assert len(remaining) == 2, f"Expected 2 backups, got {len(remaining)}"

    print("\n✅ Same-second backup names are unique")

    close_db()
    shutil.rmtree(test_dir)


async def main():
    """Run all integration tests."""
    print("\n" + "="*60)
    print("BACKUP API CLEANUP INTEGRATION TESTS")
    print("="*60)

    try:
        await test_backup_cleanup_integration()
        await test_manual_cleanup()
        await test_same_second_backups_are_unique()

        print("\n" + "="*60)
        print("✅ ALL INTEGRATION TESTS PASSED")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    asyncio.run(main())
