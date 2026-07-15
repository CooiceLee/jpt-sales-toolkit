"""Orchestrate transactional activity and technical-task writers."""

from .write_activities import write_activity
from .write_after_tasks import write_after_task
from .write_pre_tasks import write_pre_task


def write_related_entities(conn, canonical: dict, context: dict, actor_id: str,
                           batch_id: str, ids: dict) -> tuple[dict, dict[str, dict]]:
    kinds = ("activities", "pre_sales_tasks", "after_sales_tasks")
    ids.update({kind: {} for kind in kinds})
    counts = {kind: {"created": 0, "updated": 0} for kind in kinds}
    for item in context["entities"]["activities"]:
        write_activity(conn, canonical, context, actor_id, batch_id, ids, counts, item)
    for item in context["entities"]["pre_sales_tasks"]:
        write_pre_task(conn, canonical, context, actor_id, batch_id, ids, counts, item)
    for item in context["entities"]["after_sales_tasks"]:
        write_after_task(conn, canonical, context, actor_id, batch_id, ids, counts, item)
    return ids, counts
