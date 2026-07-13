"""
Test backup retention policy.

Tests:
1. Keep last 10 backups (count-based)
2. Keep backups from last 30 days (time-based)
3. Mixed policy (most permissive wins)
"""

import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from backend.config import init_settings
from backend.services.admin_service import AdminService


def create_test_backup(backup_dir: Path, name: str, age_days: int = 0):
    """Create a test backup file with specific age."""
    backup_file = backup_dir / f"backup_{name}.zip"
    backup_file.write_text("test")

    # Set modification time to simulate age
    if age_days > 0:
        old_time = time.time() - (age_days * 24 * 3600)
        backup_file.touch()
        import os
        os.utime(backup_file, (old_time, old_time))

    return backup_file


def test_count_based_retention():
    """Test: Keep last 10 backups."""
    print("\n" + "="*60)
    print("TEST 1: Count-based retention (keep last 10)")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir) / "backups"
        backup_dir.mkdir()

        # Create 15 backups, all older than 30 days (so time-based doesn't interfere)
        for i in range(15):
            create_test_backup(backup_dir, f"test{i:02d}", age_days=35 + i)

        print(f"\nCreated 15 backups (all > 30 days old)")

        service = AdminService()
        result = service.cleanup_old_backups(backup_dir, keep_count=10, keep_days=30)

        print(f"Deleted: {result['deleted']}")
        print(f"Kept: {result['kept']}")
        print(f"Policy: {result['policy']}")

        remaining = list(backup_dir.glob("backup_*.zip"))
        print(f"Remaining files: {len(remaining)}")

        assert result['deleted'] == 5, f"Expected 5 deleted, got {result['deleted']}"
        assert result['kept'] == 10, f"Expected 10 kept, got {result['kept']}"
        assert len(remaining) == 10, f"Expected 10 files, got {len(remaining)}"

        print("\n✅ Count-based retention works correctly")


def test_time_based_retention():
    """Test: Keep backups from last 30 days."""
    print("\n" + "="*60)
    print("TEST 2: Time-based retention (keep last 30 days)")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir) / "backups"
        backup_dir.mkdir()

        # Create backups with varying ages
        # 5 backups within 30 days
        for i in range(5):
            create_test_backup(backup_dir, f"recent{i:02d}", age_days=i)

        # 8 backups older than 30 days
        for i in range(8):
            create_test_backup(backup_dir, f"old{i:02d}", age_days=31 + i)

        print(f"\nCreated 5 recent + 8 old backups")

        service = AdminService()
        result = service.cleanup_old_backups(backup_dir, keep_count=10, keep_days=30)

        print(f"Deleted: {result['deleted']}")
        print(f"Kept: {result['kept']}")

        # All 5 recent should be kept, plus 5 oldest (to reach keep_count=10)
        # Actually, time-based would keep 5, count-based would keep 10
        # Most permissive wins, so keep 10

        remaining = list(backup_dir.glob("backup_*.zip"))
        print(f"Remaining files: {len(remaining)}")

        assert result['kept'] == 10, f"Expected 10 kept (count-based wins), got {result['kept']}"
        assert len(remaining) == 10, f"Expected 10 files, got {len(remaining)}"

        print("\n✅ Time-based retention works correctly")


def test_mixed_retention():
    """Test: Mixed policy (most permissive wins)."""
    print("\n" + "="*60)
    print("TEST 3: Mixed retention (most permissive)")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir) / "backups"
        backup_dir.mkdir()

        # Create 12 backups:
        # - 8 within last 30 days
        # - 4 older than 30 days
        for i in range(8):
            create_test_backup(backup_dir, f"recent{i:02d}", age_days=i * 3)

        for i in range(4):
            create_test_backup(backup_dir, f"old{i:02d}", age_days=35 + i * 5)

        print(f"\nCreated 8 recent (within 30 days) + 4 old backups")

        service = AdminService()
        result = service.cleanup_old_backups(backup_dir, keep_count=10, keep_days=30)

        print(f"Deleted: {result['deleted']}")
        print(f"Kept: {result['kept']}")

        # Should keep:
        # - All 8 recent (time-based)
        # - 2 oldest (to reach keep_count=10)
        # Total: 10

        remaining = list(backup_dir.glob("backup_*.zip"))
        print(f"Remaining files: {len(remaining)}")

        assert result['kept'] == 10, f"Expected 10 kept, got {result['kept']}"
        assert result['deleted'] == 2, f"Expected 2 deleted, got {result['deleted']}"
        assert len(remaining) == 10, f"Expected 10 files, got {len(remaining)}"

        print("\n✅ Mixed retention works correctly")


def test_no_cleanup_needed():
    """Test: No cleanup when backups <= keep_count."""
    print("\n" + "="*60)
    print("TEST 4: No cleanup needed")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = Path(tmpdir) / "backups"
        backup_dir.mkdir()

        # Create only 5 backups
        for i in range(5):
            create_test_backup(backup_dir, f"test{i:02d}")

        print(f"\nCreated 5 backups (less than keep_count=10)")

        service = AdminService()
        result = service.cleanup_old_backups(backup_dir, keep_count=10, keep_days=30)

        print(f"Deleted: {result['deleted']}")
        print(f"Kept: {result['kept']}")
        print(f"Reason: {result.get('reason')}")

        assert result['deleted'] == 0, f"Expected 0 deleted, got {result['deleted']}"
        assert result['kept'] == 5, f"Expected 5 kept, got {result['kept']}"

        print("\n✅ No cleanup when not needed")


def main():
    """Run all backup retention tests."""
    print("\n" + "="*60)
    print("BACKUP RETENTION POLICY TESTS")
    print("="*60)

    try:
        test_count_based_retention()
        test_time_based_retention()
        test_mixed_retention()
        test_no_cleanup_needed()

        print("\n" + "="*60)
        print("✅ ALL BACKUP RETENTION TESTS PASSED")
        print("="*60)

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
