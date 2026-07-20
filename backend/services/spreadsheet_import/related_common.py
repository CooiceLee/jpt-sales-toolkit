"""Shared identity and binding helpers for related lead records."""

from ...repositories.base import generate_uuid
from .bindings import bind, binding_id, external_keys


def local_record(conn, canonical, kind, item):
    local_id = binding_id(
        conn, canonical["dataset_id"], kind, item["external_key"]
    ) or generate_uuid()
    table = "lead_activities" if kind == "activities" else kind
    existed = conn.execute(
        f"SELECT 1 FROM {table} WHERE id = ?", (local_id,)
    ).fetchone() is not None
    return local_id, existed


def finish_record(conn, canonical, kind, item, local_id,
                  batch_id, ids, counts, existed):
    for key in external_keys(item):
        bind(conn, canonical["dataset_id"], kind, key, local_id,
             batch_id, canonical["source_hash"])
        ids[kind][key] = local_id
    counts[kind]["updated" if existed else "created"] += 1


def row_version(conn, table, local_id):
    return conn.execute(
        f"SELECT row_version FROM {table} WHERE id = ?", (local_id,)
    ).fetchone()[0]
