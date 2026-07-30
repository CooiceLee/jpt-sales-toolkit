"""SQL boundary for review-map rows."""

from __future__ import annotations


BASE_QUERY = """
    SELECT DISTINCT
        l.id as lead_id,
        l.display_id,
        l.title,
        l.sales_stage,
        l.service_status,
        l.owner_id,
        l.estimated_value,
        l.deal_amount,
        l.currency,
        l.product_category,
        l.application,
        l.next_followup_date,
        l.updated_at as lead_updated_at,
        u.display_name as owner_name,
        c.id as customer_id,
        c.display_name,
        c.country,
        c.city,
        c.postal_code,
        c.address,
        c.normalized_address,
        c.lat,
        c.lng,
        c.region,
        c.geocode_source,
        c.geocode_confidence,
        c.geocode_locked,
        c.row_version as customer_row_version,
        {can_edit_sql} as actor_can_edit
    FROM leads l
    JOIN customers c ON l.customer_id = c.id
    LEFT JOIN users u ON l.owner_id = u.id
    LEFT JOIN lead_assignments la
        ON l.id = la.lead_id AND la.archived_at IS NULL
    WHERE l.archived_at IS NULL
      AND c.archived_at IS NULL
"""


def build_map_query(actor_id: str, actor_role: str, filters: dict) -> tuple[str, list]:
    """Build map SQL while preserving placeholder order used by permissions."""
    params = []
    if actor_role == "leader":
        can_edit_sql = "1"
    else:
        can_edit_sql = """CASE WHEN l.owner_id = ? OR EXISTS (
            SELECT 1 FROM lead_assignments edit_assignment
            WHERE edit_assignment.lead_id = l.id
              AND edit_assignment.user_id = ?
              AND edit_assignment.assignment_type = 'collaborator'
              AND edit_assignment.archived_at IS NULL
        ) THEN 1 ELSE 0 END"""
        params.extend([actor_id, actor_id])

    sql = BASE_QUERY.format(can_edit_sql=can_edit_sql)
    if actor_role != "leader":
        sql += " AND (l.owner_id = ? OR la.user_id = ?)"
        params.extend([actor_id, actor_id])

    owner_id = filters.get("owner_id")
    if owner_id:
        sql += " AND l.owner_id = ?"
        params.append(owner_id)
    sales_stage = filters.get("sales_stage")
    if sales_stage:
        sql += " AND l.sales_stage = ?"
        params.append(sales_stage)

    outcome = filters.get("outcome")
    if outcome == "won":
        sql += " AND l.sales_stage = 'Won'"
    elif outcome == "lost":
        sql += " AND l.sales_stage = 'Lost'"
    elif outcome == "open":
        sql += " AND l.sales_stage NOT IN ('Won', 'Lost')"

    service_status = filters.get("service_status")
    if service_status:
        sql += " AND l.service_status = ?"
        params.append(service_status)
    return sql + " ORDER BY c.display_name ASC, l.updated_at DESC", params


def load_map_rows(conn, actor_id: str, actor_role: str, filters: dict) -> list[dict]:
    sql, params = build_map_query(actor_id, actor_role, filters)
    return [dict(row) for row in conn.execute(sql, params).fetchall()]
