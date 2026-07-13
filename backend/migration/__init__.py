"""
JPT Sales Toolkit - Legacy Data Migration Module

Migration pipeline for converting JSON-based Inquiry records to SQLite v0.5 schema.

Execution order:
1. migrate_users.py
2. migrate_customers.py
3. migrate_leads.py
4. migrate_activities.py
5. migrate_tasks.py
6. migrate_artifact_links.py (optional)

Output files:
- migration_report.json
- legacy_id_map.json
- legacy_user_map.json
- new_database.sqlite
"""

from .runner import run_migration, run_dry_migration

__all__ = ["run_migration", "run_dry_migration"]
