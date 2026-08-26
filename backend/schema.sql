-- JPT Sales Toolkit v0.6 Schema
-- Target: SQLite 3.42+
-- Generated from: docs/v0.5-ddl-draft.md, maintained through v0.6 runtime fixes

PRAGMA foreign_keys = ON;

-- ============================================================================
-- Display ID Sequence
-- ============================================================================

CREATE TABLE IF NOT EXISTS display_sequences (
    period_ym TEXT PRIMARY KEY,
    next_value INTEGER NOT NULL
);

-- ============================================================================
-- Core Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('leader', 'sales', 'tech')),
    region TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

-- ============================================================================
-- Authorization Data Layer v2
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL
);

-- Application-wide migration ledger. Unlike the authorization-only ledger
-- above, this records every runtime schema step and the app build that applied it.
CREATE TABLE IF NOT EXISTS app_schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    app_version TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

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
);

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
);

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
);

CREATE TABLE IF NOT EXISTS authorization_events (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    user_id TEXT REFERENCES users(id),
    device_authorization_id TEXT REFERENCES device_authorizations(id),
    actor_user_id TEXT REFERENCES users(id),
    event_type TEXT NOT NULL,
    event_data_json TEXT,
    created_at TEXT NOT NULL
);

INSERT OR IGNORE INTO organizations (
    id,
    name,
    slug,
    authorization_provider,
    authorization_duration_days,
    is_active,
    created_at,
    updated_at
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'JPT Local Organization',
    'jpt-local',
    'offline',
    90,
    1,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

INSERT OR IGNORE INTO schema_migrations (version, name, applied_at)
VALUES (
    1,
    'authorization_data_layer_v1',
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

INSERT OR IGNORE INTO schema_migrations (version, name, applied_at)
VALUES (
    2,
    'authorization_data_layer_v2',
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
);

CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    website TEXT,
    industry TEXT,
    customer_type TEXT,
    company_size TEXT,
    language TEXT,
    country TEXT,
    city TEXT,
    postal_code TEXT,
    address TEXT,
    region TEXT,
    lat REAL,
    lng REAL,
    normalized_address TEXT,
    geocode_source TEXT CHECK (geocode_source IN ('auto', 'manual')),
    geocode_confidence TEXT CHECK (geocode_confidence IN ('high', 'medium', 'low')),
    geocode_locked INTEGER NOT NULL DEFAULT 0 CHECK (geocode_locked IN (0, 1)),
    company_description TEXT,
    extra_json TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS customer_domains (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    domain TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT,
    updated_by TEXT REFERENCES users(id),
    archived_at TEXT,
    UNIQUE(customer_id, domain)
);

CREATE TABLE IF NOT EXISTS customer_aliases (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    alias_name TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    updated_by TEXT REFERENCES users(id),
    archived_at TEXT,
    UNIQUE(customer_id, normalized_alias)
);

CREATE TABLE IF NOT EXISTS customer_contacts (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    name TEXT NOT NULL,
    position TEXT,
    email TEXT,
    phone TEXT,
    whatsapp TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(customer_id, email)
);

CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    display_id TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    primary_contact_id TEXT REFERENCES customer_contacts(id),
    legacy_inquiry_id TEXT UNIQUE,
    title TEXT NOT NULL,
    source_channel TEXT,
    original_email TEXT,
    owner_id TEXT NOT NULL REFERENCES users(id),

    sales_stage TEXT NOT NULL CHECK (
        sales_stage IN ('New', 'Assigned', 'Following', 'Quoted', 'Won', 'Lost')
    ),
    fulfillment_status TEXT NOT NULL DEFAULT 'Not Started' CHECK (
        fulfillment_status IN ('Not Started', 'In Progress', 'Completed')
    ),
    service_status TEXT NOT NULL DEFAULT 'None' CHECK (
        service_status IN ('None', 'Open', 'In Progress', 'Resolved', 'Closed')
    ),

    quality_grade TEXT CHECK (quality_grade IN ('A', 'B', 'C', 'D')),
    urgency TEXT CHECK (urgency IN ('High', 'Medium', 'Low')),
    estimated_value NUMERIC,

    product_category TEXT,
    product_series TEXT,
    power_range TEXT,
    wavelength TEXT,
    application TEXT,
    material TEXT,
    quantity_text TEXT,

    currency TEXT,
    deal_amount NUMERIC,
    quotation_id TEXT,
    quotation_date TEXT,
    po_number TEXT,
    po_date TEXT,

    next_followup_date TEXT,
    inquiry_date TEXT,

    lost_reason_code TEXT,
    lost_reason_text TEXT,

    extra_json TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS lead_assignments (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    assignment_type TEXT NOT NULL CHECK (
        assignment_type IN ('owner', 'collaborator', 'watcher')
    ),
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    archived_at TEXT,
    UNIQUE(lead_id, user_id, assignment_type)
);

CREATE TABLE IF NOT EXISTS lead_activities (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    actor_id TEXT REFERENCES users(id),
    action_type TEXT NOT NULL CHECK (
        action_type IN ('follow_up', 'comment', 'field_change', 'assignment', 'system', 'task_update')
    ),
    visibility TEXT NOT NULL DEFAULT 'all' CHECK (
        visibility IN ('all', 'internal', 'owner_only')
    ),
    is_formal_follow_up INTEGER NOT NULL DEFAULT 0 CHECK (
        is_formal_follow_up IN (0, 1)
    ),
    summary TEXT NOT NULL,
    payload_json TEXT,
    changed_field TEXT,
    before_value TEXT,
    after_value TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    actor_id TEXT REFERENCES users(id),
    event_type TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pre_sales_tasks (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    assignee_id TEXT REFERENCES users(id),
    client_request_id TEXT,
    status TEXT NOT NULL CHECK (
        status IN ('Open', 'In Progress', 'Completed', 'Cancelled')
    ),
    request_json TEXT,
    result_json TEXT,
    due_date TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS after_sales_tasks (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    assignee_id TEXT REFERENCES users(id),
    issue_type TEXT NOT NULL CHECK (
        issue_type IN ('Technical', 'Quality', 'Delivery', 'Other')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('Open', 'In Progress', 'Resolved', 'Closed')
    ),
    issue_description TEXT NOT NULL,
    solution TEXT,
    customer_satisfaction TEXT,
    lessons_learned TEXT,
    remarks TEXT,
    due_date TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

-- ============================================================================
-- Offline Leader / Tech Task Package Exchange (application schema v2)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tech_task_exchange_batches (
    package_id TEXT PRIMARY KEY,
    package_type TEXT NOT NULL CHECK (
        package_type IN ('tech_task_assignment', 'tech_task_results')
    ),
    direction TEXT NOT NULL CHECK (
        direction IN ('leader_to_tech', 'tech_to_leader')
    ),
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    source_user_id TEXT NOT NULL REFERENCES users(id),
    recipient_user_id TEXT NOT NULL REFERENCES users(id),
    parent_package_id TEXT,
    payload_sha256 TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('exported', 'imported')),
    created_at TEXT NOT NULL,
    imported_at TEXT,
    imported_by TEXT REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tech_task_exchange_bindings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    task_type TEXT NOT NULL CHECK (task_type IN ('pre_sales', 'after_sales')),
    source_task_id TEXT NOT NULL,
    local_task_id TEXT NOT NULL,
    source_lead_id TEXT NOT NULL,
    local_lead_id TEXT NOT NULL REFERENCES leads(id),
    source_customer_id TEXT NOT NULL,
    local_customer_id TEXT NOT NULL REFERENCES customers(id),
    leader_user_id TEXT NOT NULL REFERENCES users(id),
    tech_user_id TEXT NOT NULL REFERENCES users(id),
    source_row_version INTEGER NOT NULL,
    source_snapshot_json TEXT NOT NULL,
    source_package_id TEXT NOT NULL,
    local_row_version_at_sync INTEGER NOT NULL,
    last_exported_local_row_version INTEGER,
    last_exported_result_snapshot_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(organization_id, task_type, source_task_id, tech_user_id)
);

-- ============================================================================
-- Import Identity and Governance
-- ============================================================================

CREATE TABLE IF NOT EXISTS member_import_aliases (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    source_system TEXT NOT NULL COLLATE NOCASE,
    source_name TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL REFERENCES users(id),
    UNIQUE(organization_id, source_system, normalized_alias)
);

CREATE TABLE IF NOT EXISTS import_batches (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    dataset_id TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_filename TEXT,
    source_sha256 TEXT NOT NULL,
    directory_hash TEXT,
    status TEXT NOT NULL DEFAULT 'preflight' CHECK (
        status IN ('preflight', 'ready', 'importing', 'completed', 'failed', 'rolled_back')
    ),
    summary_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS import_bindings (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    dataset_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    external_key TEXT NOT NULL,
    local_entity_id TEXT NOT NULL,
    source_hash TEXT,
    first_batch_id TEXT NOT NULL REFERENCES import_batches(id),
    last_batch_id TEXT NOT NULL REFERENCES import_batches(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(organization_id, dataset_id, entity_type, external_key)
);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES import_batches(id),
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning', 'info')),
    issue_code TEXT NOT NULL,
    entity_type TEXT,
    external_key TEXT,
    field_name TEXT,
    raw_value TEXT,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'ignored')),
    resolution_note TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolved_by TEXT REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    lead_id TEXT NOT NULL REFERENCES leads(id),
    category TEXT NOT NULL CHECK (
        category IN ('email_original', 'quotation', 'report', 'test_result', 'screenshot', 'other')
    ),
    version_no INTEGER NOT NULL DEFAULT 1,
    stored_name TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    uploaded_by TEXT REFERENCES users(id),
    uploaded_at TEXT NOT NULL,
    archived_at TEXT
);

-- ============================================================================
-- v0.7 Trip Planning
-- ============================================================================

CREATE TABLE IF NOT EXISTS trip_plans (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    owner_id TEXT NOT NULL REFERENCES users(id),
    start_date TEXT,
    end_date TEXT,
    region TEXT,
    origin_name TEXT,
    origin_lat REAL,
    origin_lng REAL,
    destination_name TEXT,
    destination_lat REAL,
    destination_lng REAL,
    travel_mode TEXT NOT NULL DEFAULT 'auto',
    route_order_mode TEXT NOT NULL DEFAULT 'auto' CHECK (
        route_order_mode IN ('auto', 'manual')
    ),
    transport_mode_priority TEXT NOT NULL DEFAULT '["flight","drive","ground_public"]',
    departure_window_start TEXT,
    departure_window_end TEXT,
    return_window_start TEXT,
    return_window_end TEXT,
    avoid_weekends INTEGER NOT NULL DEFAULT 1,
    holiday_dates TEXT,
    planning_mode TEXT NOT NULL DEFAULT 'legacy'
        CHECK (planning_mode IN ('legacy', 'team')),
    itinerary_generated_at TEXT,
    itinerary_summary TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (
        status IN ('Draft', 'Active', 'Completed')
    ),
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trip_plan_stops (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    customer_id TEXT NOT NULL REFERENCES customers(id),
    lead_id TEXT REFERENCES leads(id),
    sequence_no INTEGER NOT NULL DEFAULT 1,
    planned_date TEXT,
    planned_end_date TEXT,
    stay_days INTEGER NOT NULL DEFAULT 1,
    duration_half_days INTEGER NOT NULL DEFAULT 2 CHECK (
        duration_half_days BETWEEN 1 AND 60
    ),
    preferred_period TEXT NOT NULL DEFAULT 'auto' CHECK (
        preferred_period IN ('auto', 'AM', 'PM')
    ),
    planned_start_period TEXT CHECK (planned_start_period IN ('AM', 'PM')),
    planned_end_period TEXT CHECK (planned_end_period IN ('AM', 'PM')),
    schedule_locked INTEGER NOT NULL DEFAULT 0 CHECK (schedule_locked IN (0, 1)),
    confirmation_status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (
        confirmation_status IN (
            'unconfirmed', 'tentative', 'confirmed',
            'needs_reconfirmation', 'cancelled'
        )
    ),
    travel_from_label TEXT,
    travel_mode TEXT,
    travel_distance_km REAL,
    travel_time_hours REAL,
    travel_days INTEGER,
    visit_purpose TEXT,
    notes TEXT,
    result_status TEXT NOT NULL DEFAULT 'Planned' CHECK (
        result_status IN ('Planned', 'Visited', 'Follow-up Needed', 'Skipped')
    ),
    result_notes TEXT,
    visit_customer_needs TEXT,
    visit_competitor TEXT,
    visit_budget TEXT,
    visit_decision_maker TEXT,
    visit_next_action TEXT,
    visit_followup_due_date TEXT,
    visit_sample_needed INTEGER NOT NULL DEFAULT 0 CHECK (
        visit_sample_needed IN (0, 1)
    ),
    visit_quote_needed INTEGER NOT NULL DEFAULT 0 CHECK (
        visit_quote_needed IN (0, 1)
    ),
    followup_activity_id TEXT REFERENCES lead_activities(id),
    result_activity_id TEXT REFERENCES lead_activities(id),
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trip_plan_free_stops (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    category TEXT NOT NULL CHECK (
        category IN ('rest', 'hotel', 'airport', 'transit', 'meal', 'other')
    ),
    location_name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    country TEXT,
    lat REAL NOT NULL CHECK (lat >= -90 AND lat <= 90),
    lng REAL NOT NULL CHECK (lng >= -180 AND lng <= 180),
    sequence_no INTEGER NOT NULL DEFAULT 1,
    planned_date TEXT,
    planned_end_date TEXT,
    stay_days INTEGER NOT NULL DEFAULT 1 CHECK (stay_days >= 1 AND stay_days <= 30),
    duration_half_days INTEGER NOT NULL DEFAULT 2 CHECK (
        duration_half_days BETWEEN 1 AND 60
    ),
    preferred_period TEXT NOT NULL DEFAULT 'auto' CHECK (
        preferred_period IN ('auto', 'AM', 'PM')
    ),
    planned_start_period TEXT CHECK (planned_start_period IN ('AM', 'PM')),
    planned_end_period TEXT CHECK (planned_end_period IN ('AM', 'PM')),
    schedule_locked INTEGER NOT NULL DEFAULT 0 CHECK (schedule_locked IN (0, 1)),
    confirmation_status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (
        confirmation_status IN (
            'unconfirmed', 'tentative', 'confirmed',
            'needs_reconfirmation', 'cancelled'
        )
    ),
    travel_from_label TEXT,
    travel_mode TEXT,
    travel_distance_km REAL,
    travel_time_hours REAL,
    travel_days INTEGER,
    visit_purpose TEXT,
    notes TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trip_plan_members (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    origin_name_override TEXT,
    origin_lat_override REAL CHECK (origin_lat_override BETWEEN -90 AND 90),
    origin_lng_override REAL CHECK (origin_lng_override BETWEEN -180 AND 180),
    destination_name_override TEXT,
    destination_lat_override REAL CHECK (destination_lat_override BETWEEN -90 AND 90),
    destination_lng_override REAL CHECK (destination_lng_override BETWEEN -180 AND 180),
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trip_plan_legs (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES trip_plans(id),
    member_id TEXT NOT NULL DEFAULT '',
    leg_key TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    from_kind TEXT NOT NULL CHECK (from_kind IN ('origin', 'stop')),
    from_stop_id TEXT REFERENCES trip_plan_stops(id),
    from_free_stop_id TEXT REFERENCES trip_plan_free_stops(id),
    from_label TEXT,
    to_kind TEXT NOT NULL CHECK (to_kind IN ('stop', 'destination')),
    to_stop_id TEXT REFERENCES trip_plan_stops(id),
    to_free_stop_id TEXT REFERENCES trip_plan_free_stops(id),
    to_label TEXT,
    selected_mode TEXT NOT NULL CHECK (
        selected_mode IN ('flight', 'drive', 'ground_public', 'other')
    ),
    mode_locked INTEGER NOT NULL DEFAULT 0 CHECK (mode_locked IN (0, 1)),
    distance_km REAL NOT NULL DEFAULT 0 CHECK (distance_km >= 0),
    time_hours REAL NOT NULL DEFAULT 0 CHECK (time_hours >= 0),
    travel_days INTEGER NOT NULL DEFAULT 0 CHECK (travel_days >= 0),
    travel_half_days INTEGER NOT NULL DEFAULT 0 CHECK (
        travel_half_days BETWEEN 0 AND 60
    ),
    manual_distance_km REAL CHECK (manual_distance_km >= 0),
    manual_time_hours REAL CHECK (manual_time_hours >= 0),
    manual_travel_days INTEGER CHECK (manual_travel_days >= 0),
    manual_travel_half_days INTEGER CHECK (
        manual_travel_half_days BETWEEN 0 AND 60
    ),
    planned_start_date TEXT,
    planned_start_period TEXT CHECK (planned_start_period IN ('AM', 'PM')),
    planned_end_date TEXT,
    planned_end_period TEXT CHECK (planned_end_period IN ('AM', 'PM')),
    notes TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS trip_visit_briefings (
    id TEXT PRIMARY KEY,
    stop_id TEXT NOT NULL UNIQUE REFERENCES trip_plan_stops(id),
    timezone TEXT,
    location_json TEXT NOT NULL DEFAULT '{}',
    customer_team_json TEXT NOT NULL DEFAULT '[]',
    contacts_json TEXT NOT NULL DEFAULT '[]',
    participants_json TEXT NOT NULL DEFAULT '[]',
    channel_partner_companions_json TEXT NOT NULL DEFAULT '[]',
    equipment_json TEXT NOT NULL DEFAULT '[]',
    agenda_items_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    created_by TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    updated_by TEXT REFERENCES users(id),
    row_version INTEGER NOT NULL DEFAULT 1
);

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_nocase
    ON users(username COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_user_credentials_org ON user_credentials(organization_id, is_active);
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_auth_active_user
    ON device_authorizations(organization_id, user_id)
    WHERE is_active = 1;
CREATE UNIQUE INDEX IF NOT EXISTS idx_device_auth_active_device
    ON device_authorizations(organization_id, device_fingerprint_hash)
    WHERE is_active = 1;
CREATE INDEX IF NOT EXISTS idx_device_auth_user_history
    ON device_authorizations(user_id, issued_at DESC);
CREATE INDEX IF NOT EXISTS idx_device_auth_expiry
    ON device_authorizations(is_active, expires_at);
CREATE INDEX IF NOT EXISTS idx_authorization_events_user
    ON authorization_events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_authorization_events_device
    ON authorization_events(device_authorization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(normalized_name);
CREATE INDEX IF NOT EXISTS idx_customers_region ON customers(region, country, city);
CREATE INDEX IF NOT EXISTS idx_customer_domains_domain ON customer_domains(domain);
CREATE INDEX IF NOT EXISTS idx_customer_contacts_email ON customer_contacts(email);
CREATE INDEX IF NOT EXISTS idx_customer_domains_active
    ON customer_domains(customer_id, archived_at);
CREATE INDEX IF NOT EXISTS idx_customer_aliases_active
    ON customer_aliases(customer_id, archived_at);
CREATE INDEX IF NOT EXISTS idx_member_import_alias_user
    ON member_import_aliases(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_import_batches_dataset
    ON import_batches(organization_id, dataset_id, status);
CREATE INDEX IF NOT EXISTS idx_import_bindings_local
    ON import_bindings(entity_type, local_entity_id);
CREATE INDEX IF NOT EXISTS idx_data_quality_issues_batch
    ON data_quality_issues(batch_id, status, severity);

CREATE INDEX IF NOT EXISTS idx_leads_customer ON leads(customer_id);
CREATE INDEX IF NOT EXISTS idx_leads_owner_stage ON leads(owner_id, sales_stage);
CREATE INDEX IF NOT EXISTS idx_leads_updated_at ON leads(updated_at);
CREATE INDEX IF NOT EXISTS idx_leads_product_category ON leads(product_category);
CREATE INDEX IF NOT EXISTS idx_leads_application ON leads(application);
CREATE INDEX IF NOT EXISTS idx_leads_po_number ON leads(po_number);
CREATE INDEX IF NOT EXISTS idx_leads_quotation_id ON leads(quotation_id);
CREATE INDEX IF NOT EXISTS idx_leads_deal_amount ON leads(deal_amount);
CREATE INDEX IF NOT EXISTS idx_leads_legacy_id ON leads(legacy_inquiry_id);

CREATE INDEX IF NOT EXISTS idx_lead_assignments_lead ON lead_assignments(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_assignments_user ON lead_assignments(user_id, assignment_type);
CREATE INDEX IF NOT EXISTS idx_lead_activities_lead_time ON lead_activities(lead_id, created_at);
CREATE INDEX IF NOT EXISTS idx_pre_sales_tasks_lead ON pre_sales_tasks(lead_id);
CREATE INDEX IF NOT EXISTS idx_pre_sales_assignee ON pre_sales_tasks(assignee_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pre_sales_client_request
    ON pre_sales_tasks(lead_id, client_request_id)
    WHERE client_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_after_sales_tasks_lead ON after_sales_tasks(lead_id);
CREATE INDEX IF NOT EXISTS idx_after_sales_assignee ON after_sales_tasks(assignee_id, status);
CREATE INDEX IF NOT EXISTS idx_tech_exchange_batches_recipient
    ON tech_task_exchange_batches(recipient_user_id, direction, created_at);
CREATE INDEX IF NOT EXISTS idx_tech_exchange_bindings_local
    ON tech_task_exchange_bindings(task_type, local_task_id);
CREATE INDEX IF NOT EXISTS idx_tech_exchange_bindings_source_lead
    ON tech_task_exchange_bindings(organization_id, source_lead_id, tech_user_id);
CREATE INDEX IF NOT EXISTS idx_attachments_lead ON attachments(lead_id, category);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id, created_at);
CREATE INDEX IF NOT EXISTS idx_trip_plans_owner ON trip_plans(owner_id, status);
CREATE INDEX IF NOT EXISTS idx_trip_stops_plan ON trip_plan_stops(plan_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_trip_stops_customer ON trip_plan_stops(customer_id);
CREATE INDEX IF NOT EXISTS idx_trip_stops_lead ON trip_plan_stops(lead_id);
CREATE INDEX IF NOT EXISTS idx_trip_free_stops_plan
    ON trip_plan_free_stops(plan_id, archived_at, sequence_no);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_legs_active_member_key
    ON trip_plan_legs(plan_id, member_id, leg_key) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_trip_legs_plan_sequence
    ON trip_plan_legs(plan_id, archived_at, sequence_no);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_visit_briefings_stop
    ON trip_visit_briefings(stop_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_plan_members_user
    ON trip_plan_members(plan_id, user_id);
