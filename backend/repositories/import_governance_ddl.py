"""SQLite table definitions for repeatable data imports."""

CUSTOMER_RELATION_DDL = (
    """
    CREATE TABLE IF NOT EXISTS customer_domains (
        id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
        domain TEXT NOT NULL, is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
        created_at TEXT NOT NULL, updated_at TEXT, updated_by TEXT REFERENCES users(id),
        archived_at TEXT, UNIQUE(customer_id, domain)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_aliases (
        id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
        alias_name TEXT NOT NULL, normalized_alias TEXT NOT NULL, created_at TEXT NOT NULL,
        updated_at TEXT, updated_by TEXT REFERENCES users(id), archived_at TEXT,
        UNIQUE(customer_id, normalized_alias)
    )
    """,
)

IMPORT_GOVERNANCE_DDL = (
    """
    CREATE TABLE IF NOT EXISTS import_batches (
        id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id),
        dataset_id TEXT NOT NULL, source_system TEXT NOT NULL, source_filename TEXT,
        source_sha256 TEXT NOT NULL, directory_hash TEXT,
        status TEXT NOT NULL DEFAULT 'preflight' CHECK (
            status IN ('preflight','ready','importing','completed','failed','rolled_back')
        ),
        summary_json TEXT, error_message TEXT, created_at TEXT NOT NULL,
        created_by TEXT NOT NULL REFERENCES users(id), updated_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS import_bindings (
        id TEXT PRIMARY KEY, organization_id TEXT NOT NULL REFERENCES organizations(id),
        dataset_id TEXT NOT NULL, entity_type TEXT NOT NULL, external_key TEXT NOT NULL,
        local_entity_id TEXT NOT NULL, source_hash TEXT,
        first_batch_id TEXT NOT NULL REFERENCES import_batches(id),
        last_batch_id TEXT NOT NULL REFERENCES import_batches(id),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(organization_id, dataset_id, entity_type, external_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_quality_issues (
        id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES import_batches(id),
        severity TEXT NOT NULL CHECK (severity IN ('error','warning','info')),
        issue_code TEXT NOT NULL, entity_type TEXT, external_key TEXT, field_name TEXT,
        raw_value TEXT, message TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','ignored')),
        resolution_note TEXT, created_at TEXT NOT NULL, resolved_at TEXT,
        resolved_by TEXT REFERENCES users(id)
    )
    """,
)

INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_customer_domains_active ON customer_domains(customer_id, archived_at)",
    "CREATE INDEX IF NOT EXISTS idx_customer_aliases_active ON customer_aliases(customer_id, archived_at)",
    "CREATE INDEX IF NOT EXISTS idx_import_batches_dataset ON import_batches(organization_id, dataset_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_import_bindings_local ON import_bindings(entity_type, local_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_data_quality_issues_batch ON data_quality_issues(batch_id, status, severity)",
)
