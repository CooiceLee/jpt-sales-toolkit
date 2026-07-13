"""
Migration runner - orchestrates the full migration pipeline.

Usage:
    from migration import run_migration, run_dry_migration

    # Dry run (in-memory, no files written)
    report = run_dry_migration(legacy_data_dir)

    # Real migration
    report = run_migration(legacy_data_dir, output_dir)
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Union

from .base import MigrationContext
from .migrate_users import migrate_users
from .migrate_customers import migrate_customers
from .migrate_leads import migrate_leads
from .migrate_activities import migrate_activities
from .migrate_tasks import migrate_tasks


def init_schema(ctx: MigrationContext) -> None:
    """Initialize database schema from schema.sql."""
    schema_path = Path(__file__).parent.parent / "schema.sql"
    if schema_path.exists():
        with open(schema_path, "r", encoding="utf-8") as f:
            ctx.conn.executescript(f.read())
    else:
        raise FileNotFoundError(f"schema.sql not found at {schema_path}")


def backup_legacy_data(legacy_data_dir: Path, backup_dir: Path) -> Path:
    """Create a backup of legacy data before migration."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"legacy_{timestamp}.zip"
    backup_dir.mkdir(parents=True, exist_ok=True)

    shutil.make_archive(
        str(backup_path).replace(".zip", ""),
        "zip",
        legacy_data_dir.parent,
        legacy_data_dir.name,
    )
    return backup_path


def save_report(ctx: MigrationContext, output_dir: Path) -> None:
    """Save migration report and maps to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    report = ctx.generate_report()

    with open(output_dir / "migration_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open(output_dir / "legacy_user_map.json", "w", encoding="utf-8") as f:
        json.dump(ctx.legacy_user_map, f, indent=2, ensure_ascii=False)

    with open(output_dir / "legacy_id_map.json", "w", encoding="utf-8") as f:
        json.dump(ctx.legacy_id_map, f, indent=2, ensure_ascii=False)


def run_migration(
    legacy_data_dir: Union[Path, str],
    output_dir: Union[Path, str],
    skip_backup: bool = False,
) -> dict:
    """
    Run full migration pipeline.

    Args:
        legacy_data_dir: Path to legacy data/ directory
        output_dir: Path to output directory for new database and reports
        skip_backup: If True, skip creating backup archive

    Returns:
        Migration report dict
    """
    legacy_data_dir = Path(legacy_data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Backup legacy data
    if not skip_backup:
        backup_dir = output_dir / "backups"
        backup_path = backup_legacy_data(legacy_data_dir, backup_dir)
        print(f"Backup created: {backup_path}")

    # Initialize context
    output_db = output_dir / "database.sqlite"
    ctx = MigrationContext(legacy_data_dir, output_db, dry_run=False)

    try:
        ctx.open_db()
        init_schema(ctx)

        # Load legacy data
        inquiries = ctx.load_legacy_inquiries()
        print(f"Loaded {len(inquiries)} legacy inquiries")

        # Run migration steps
        print("Step 1: Migrating users...")
        migrate_users(ctx, inquiries)
        print(f"  Created {ctx.stats['users_created']} users")

        print("Step 2: Migrating customers...")
        inquiry_to_customer = migrate_customers(ctx, inquiries)
        print(f"  Created {ctx.stats['customers_created']} customers")

        print("Step 3: Migrating leads...")
        migrate_leads(ctx, inquiries, inquiry_to_customer)
        print(f"  Created {ctx.stats['leads_created']} leads")

        print("Step 4: Migrating activities...")
        migrate_activities(ctx, inquiries)
        print(f"  Created {ctx.stats['activities_created']} activities")

        print("Step 5: Migrating tasks...")
        migrate_tasks(ctx, inquiries)
        print(f"  Created {ctx.stats['pre_sales_tasks_created']} pre-sales tasks")
        print(f"  Created {ctx.stats['after_sales_tasks_created']} after-sales tasks")

        # Save reports
        save_report(ctx, output_dir)
        print(f"Migration complete. Database: {output_db}")

        if ctx.warnings:
            print(f"Warnings: {len(ctx.warnings)} (see migration_report.json)")

        return ctx.generate_report()

    finally:
        ctx.close_db()


def run_dry_migration(legacy_data_dir: Union[Path, str]) -> dict:
    """
    Run migration in dry-run mode (in-memory database).

    Args:
        legacy_data_dir: Path to legacy data/ directory

    Returns:
        Migration report dict (no files written)
    """
    legacy_data_dir = Path(legacy_data_dir)

    ctx = MigrationContext(legacy_data_dir, Path(":memory:"), dry_run=True)

    try:
        ctx.open_db()
        init_schema(ctx)

        inquiries = ctx.load_legacy_inquiries()

        migrate_users(ctx, inquiries)
        inquiry_to_customer = migrate_customers(ctx, inquiries)
        migrate_leads(ctx, inquiries, inquiry_to_customer)
        migrate_activities(ctx, inquiries)
        migrate_tasks(ctx, inquiries)

        return ctx.generate_report()

    finally:
        ctx.close_db()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m migration.runner <legacy_data_dir> [output_dir]")
        print("       python -m migration.runner <legacy_data_dir> --dry-run")
        sys.exit(1)

    legacy_dir = Path(sys.argv[1])

    if "--dry-run" in sys.argv:
        report = run_dry_migration(legacy_dir)
        print(json.dumps(report, indent=2))
    else:
        output = Path(sys.argv[2]) if len(sys.argv) > 2 else legacy_dir.parent / "migrated"
        report = run_migration(legacy_dir, output)
