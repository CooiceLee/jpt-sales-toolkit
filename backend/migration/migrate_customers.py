"""
Step 2: Migrate legacy inquiry company data to customers table.

Matching rules (in order):
1. Exact customer_contacts.email match
2. Exact customer_domains.domain match
3. Exact customers.normalized_name match
4. Create new customer

One customer may own multiple migrated leads.
"""

from __future__ import annotations

from .base import (
    MigrationContext,
    generate_uuid,
    now_iso,
    normalize_name,
    extract_domain,
    safe_numeric,
    empty_to_none,
)


def get_field_value(inquiry: dict, field_name: str) -> str:
    """Extract field value from legacy inquiry structure."""
    fields = inquiry.get("fields", {})
    field_data = fields.get(field_name, {})
    if isinstance(field_data, dict):
        value = field_data.get("value")
    else:
        value = field_data
    return empty_to_none(value) if isinstance(value, str) else None


def find_or_create_customer(ctx: MigrationContext, inquiry: dict) -> str:
    """Find existing customer or create new one. Returns customer_id."""
    email = get_field_value(inquiry, "email")
    company_name = get_field_value(inquiry, "company_name")
    website = get_field_value(inquiry, "website")

    domain = extract_domain(email)
    normalized = normalize_name(company_name) if company_name else ""

    # 1. Check by email
    if email and email.lower() in ctx.email_map:
        return ctx.email_map[email.lower()]

    # 2. Check by domain
    if domain and domain in ctx.domain_map:
        return ctx.domain_map[domain]

    # 3. Check by normalized name
    if normalized and normalized in ctx.customer_map:
        return ctx.customer_map[normalized]

    # 4. Create new customer
    customer_id = generate_uuid()
    actor_id = ctx.legacy_user_map.get(
        get_field_value(inquiry, "created_by") or "", {}
    ).get("user_id")

    lat = safe_numeric(get_field_value(inquiry, "lat"))
    lng = safe_numeric(get_field_value(inquiry, "lng"))

    legacy_id = inquiry.get("inquiry_id", "")
    if lat is None and get_field_value(inquiry, "lat"):
        ctx.add_warning(legacy_id, "lat", "invalid_numeric", get_field_value(inquiry, "lat"))
    if lng is None and get_field_value(inquiry, "lng"):
        ctx.add_warning(legacy_id, "lng", "invalid_numeric", get_field_value(inquiry, "lng"))

    ctx.conn.execute(
        """
        INSERT INTO customers (
            id, display_name, normalized_name, website, industry, customer_type,
            company_size, language, country, city, postal_code, address, region,
            lat, lng, company_description, created_at, created_by, updated_at, updated_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            company_name or "Unknown",
            normalized or "unknown",
            website,
            get_field_value(inquiry, "industry"),
            get_field_value(inquiry, "customer_type"),
            get_field_value(inquiry, "company_size"),
            get_field_value(inquiry, "language"),
            get_field_value(inquiry, "country"),
            get_field_value(inquiry, "city"),
            get_field_value(inquiry, "postal_code"),
            get_field_value(inquiry, "address"),
            get_field_value(inquiry, "region"),
            lat,
            lng,
            get_field_value(inquiry, "company_description"),
            now_iso(),
            actor_id,
            now_iso(),
            actor_id,
        ),
    )

    # Add domain record
    if domain:
        ctx.conn.execute(
            """
            INSERT INTO customer_domains (id, customer_id, domain, is_primary, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (generate_uuid(), customer_id, domain, now_iso()),
        )
        ctx.domain_map[domain] = customer_id

    # Add primary contact
    contact_name = get_field_value(inquiry, "contact_name")
    if contact_name or email:
        ctx.conn.execute(
            """
            INSERT INTO customer_contacts (
                id, customer_id, name, position, email, phone, whatsapp,
                is_primary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                generate_uuid(),
                customer_id,
                contact_name or "Unknown",
                get_field_value(inquiry, "contact_position"),
                email,
                get_field_value(inquiry, "phone"),
                None,  # whatsapp not in legacy
                now_iso(),
                now_iso(),
            ),
        )
        if email:
            ctx.email_map[email.lower()] = customer_id

    # Update maps
    if normalized:
        ctx.customer_map[normalized] = customer_id

    ctx.stats["customers_created"] += 1
    return customer_id


def migrate_customers(ctx: MigrationContext, inquiries: list[dict]) -> dict[str, str]:
    """
    Process all inquiries and create/match customers.
    Returns mapping: inquiry_id -> customer_id
    """
    inquiry_to_customer: dict[str, str] = {}

    for inquiry in inquiries:
        inquiry_id = inquiry.get("inquiry_id", "")
        customer_id = find_or_create_customer(ctx, inquiry)
        inquiry_to_customer[inquiry_id] = customer_id

    ctx.conn.commit()
    return inquiry_to_customer
