"""Constants and DDL for the authorization data layer."""

AUTHORIZATION_SCHEMA_VERSION = 2
AUTHORIZATION_SCHEMA_NAME = "authorization_data_layer_v2"
AUTHORIZATION_MIGRATIONS = (
    (1, "authorization_data_layer_v1"),
    (AUTHORIZATION_SCHEMA_VERSION, AUTHORIZATION_SCHEMA_NAME),
)
DEFAULT_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001"


AUTHORIZATION_DDL = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        applied_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        authorization_provider TEXT NOT NULL DEFAULT 'offline' CHECK (
            authorization_provider IN ('offline', 'remote')
        ),
        authorization_duration_days INTEGER NOT NULL DEFAULT 90 CHECK (
            authorization_duration_days > 0
        ),
        signing_key_id TEXT,
        signing_public_key TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        deactivated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_credentials (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
        password_hash TEXT NOT NULL,
        password_scheme TEXT NOT NULL,
        must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (
            must_change_password IN (0, 1)
        ),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        password_changed_at TEXT,
        deactivated_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_authorizations (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        user_id TEXT NOT NULL REFERENCES users(id),
        device_fingerprint_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('leader', 'sales', 'tech')),
        activation_state TEXT NOT NULL DEFAULT 'issued' CHECK (
            activation_state IN ('issued', 'activated')
        ),
        authorization_version INTEGER NOT NULL DEFAULT 1 CHECK (
            authorization_version > 0
        ),
        payload_json TEXT NOT NULL,
        signature TEXT NOT NULL,
        signature_algorithm TEXT NOT NULL DEFAULT 'ed25519',
        signing_key_id TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_by TEXT REFERENCES users(id),
        updated_at TEXT NOT NULL,
        deactivated_at TEXT,
        deactivation_reason TEXT,
        replaced_by_id TEXT REFERENCES device_authorizations(id),
        CHECK (expires_at > valid_from)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS authorization_events (
        id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL REFERENCES organizations(id),
        user_id TEXT REFERENCES users(id),
        device_authorization_id TEXT REFERENCES device_authorizations(id),
        actor_user_id TEXT REFERENCES users(id),
        event_type TEXT NOT NULL,
        event_data_json TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """CREATE INDEX IF NOT EXISTS idx_user_credentials_org
       ON user_credentials(organization_id, is_active)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_device_auth_active_user
       ON device_authorizations(organization_id, user_id) WHERE is_active = 1""",
    """CREATE INDEX IF NOT EXISTS idx_device_auth_user_history
       ON device_authorizations(user_id, issued_at DESC)""",
    """CREATE INDEX IF NOT EXISTS idx_device_auth_expiry
       ON device_authorizations(is_active, expires_at)""",
    """CREATE INDEX IF NOT EXISTS idx_authorization_events_user
       ON authorization_events(user_id, created_at DESC)""",
    """CREATE INDEX IF NOT EXISTS idx_authorization_events_device
       ON authorization_events(device_authorization_id, created_at DESC)""",
)
