"""
Activity service - manage lead activities and follow-ups.
"""

from __future__ import annotations

import json
from typing import Optional

from ..repositories import ActivityRepository, LeadRepository, AuditRepository
from .permission_policy import sanitize_activity_for_tech


class ActivityService:
    """Activity management service."""

    def __init__(
        self,
        activity_repo: Optional[ActivityRepository] = None,
        lead_repo: Optional[LeadRepository] = None,
        audit_repo: Optional[AuditRepository] = None,
    ):
        self.activity_repo = activity_repo or ActivityRepository()
        self.lead_repo = lead_repo or LeadRepository()
        self.audit_repo = audit_repo or AuditRepository()

    def _sync_next_followup_date(self, lead_id: str, actor_id: str) -> None:
        """Sync lead.next_followup_date from active follow-up activities."""
        activities = self.activity_repo.list_all_for_lead(lead_id, action_type="follow_up")
        dates: list[str] = []
        for activity in activities:
            try:
                payload = json.loads(activity.get("payload_json") or "{}")
            except json.JSONDecodeError:
                payload = {}
            next_date = payload.get("next_action_date")
            if next_date:
                dates.append(next_date)

        next_followup_date = min(dates) if dates else None
        lead = self.lead_repo.get_by_id(lead_id)
        if lead and lead.get("next_followup_date") != next_followup_date:
            self.lead_repo.update(
                lead_id,
                {"next_followup_date": next_followup_date},
                actor_id,
                lead["row_version"],
            )

    def add_follow_up(
        self,
        lead_id: str,
        actor_id: str,
        method: str,
        content: str,
        status: str = "pending",
        response_date: Optional[str] = None,
        customer_feedback: Optional[str] = None,
        next_action: Optional[str] = None,
        next_action_date: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> str:
        """Add formal follow-up record."""
        payload = {
            "method": method,
            "content": content,
            "status": status or "pending",
        }
        if response_date:
            payload["response_date"] = response_date
        if customer_feedback:
            payload["customer_feedback"] = customer_feedback
        if next_action:
            payload["next_action"] = next_action
        if next_action_date:
            payload["next_action_date"] = next_action_date

        activity_id = self.activity_repo.create(
            lead_id=lead_id,
            actor_id=actor_id,
            action_type="follow_up",
            summary=content[:200] if content else f"{method} follow-up",
            payload_json=json.dumps(payload),
            visibility="all",
            is_formal_follow_up=True,
            created_at=created_at,
        )

        # A formal follow-up means the lead has entered the follow-up workstream.
        lead = self.lead_repo.get_by_id(lead_id)
        if lead:
            lead_updates = {}
            if lead.get("sales_stage") in {"New", "Assigned"}:
                lead_updates["sales_stage"] = "Following"

            if lead_updates:
                self.lead_repo.update(
                    lead_id,
                    lead_updates,
                    actor_id,
                    lead["row_version"],
                )
                self.audit_repo.log(
                    entity_type="lead",
                    entity_id=lead_id,
                    event_type="follow_up_sync",
                    actor_id=actor_id,
                    before_json=json.dumps(
                        {
                            "sales_stage": lead.get("sales_stage"),
                            "next_followup_date": lead.get("next_followup_date"),
                        }
                    ),
                    after_json=json.dumps(lead_updates),
                )

        self._sync_next_followup_date(lead_id, actor_id)
        return activity_id

    def update_follow_up(
        self,
        activity_id: str,
        lead_id: str,
        actor_id: str,
        method: Optional[str] = None,
        content: Optional[str] = None,
        status: Optional[str] = None,
        response_date: Optional[str] = None,
        customer_feedback: Optional[str] = None,
        next_action: Optional[str] = None,
        next_action_date: Optional[str] = None,
        visibility: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Optional[dict]:
        """Update formal follow-up record."""
        activity = self.activity_repo.get_by_id(activity_id)
        if not activity or activity.get("lead_id") != lead_id:
            return None
        if activity.get("action_type") != "follow_up":
            raise ValueError("Only follow-up activities can be edited here")

        try:
            payload = json.loads(activity.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}

        if method is not None:
            payload["method"] = method
        if content is not None:
            payload["content"] = content
        if status is not None:
            payload["status"] = status
        if response_date is not None:
            if response_date:
                payload["response_date"] = response_date
            else:
                payload.pop("response_date", None)
        if customer_feedback is not None:
            if customer_feedback:
                payload["customer_feedback"] = customer_feedback
            else:
                payload.pop("customer_feedback", None)
        if next_action is not None:
            if next_action:
                payload["next_action"] = next_action
            else:
                payload.pop("next_action", None)
        if next_action_date is not None:
            if next_action_date:
                payload["next_action_date"] = next_action_date
            else:
                payload.pop("next_action_date", None)

        summary = (content if content is not None else payload.get("content") or activity.get("summary") or "")[:200]
        update_data = {
            "summary": summary,
            "payload_json": json.dumps(payload),
        }
        if visibility is not None:
            update_data["visibility"] = visibility
        if created_at is not None:
            update_data["created_at"] = created_at

        updated = self.activity_repo.update(activity_id, update_data)
        if updated:
            self.audit_repo.log(
                entity_type="lead_activity",
                entity_id=activity_id,
                event_type="update",
                actor_id=actor_id,
                before_json=json.dumps(dict(activity)),
                after_json=json.dumps(update_data),
            )
            self._sync_next_followup_date(lead_id, actor_id)
        return updated

    def add_comment(
        self,
        lead_id: str,
        actor_id: str,
        comment: str,
        mentions: Optional[list[str]] = None,
        visibility: str = "all",
    ) -> str:
        """Add comment to lead."""
        payload = {"comment": comment}
        if mentions:
            payload["mentions"] = mentions

        return self.activity_repo.create(
            lead_id=lead_id,
            actor_id=actor_id,
            action_type="comment",
            summary=comment[:200],
            payload_json=json.dumps(payload),
            visibility=visibility,
            is_formal_follow_up=False,
        )

    def list_for_lead(
        self,
        lead_id: str,
        actor_role: str,
        limit: int = 50,
        offset: int = 0,
        action_type: Optional[str] = None,
    ) -> list[dict]:
        """List activities for a lead with visibility filtering."""
        # Determine visibility filter based on role
        if actor_role == "leader":
            visibility_filter = None  # See all
        elif actor_role in ("owner", "collaborator"):
            visibility_filter = ["all", "internal"]
        else:
            visibility_filter = ["all"]

        activities = self.activity_repo.list_for_lead(
            lead_id=lead_id,
            limit=limit,
            offset=offset,
            action_type=action_type,
            visibility_filter=visibility_filter,
        )
        if actor_role != "tech":
            return activities
        sanitized = [sanitize_activity_for_tech(item) for item in activities]
        return [item for item in sanitized if item is not None]

    def get_due_follow_ups(
        self,
        before_date: str,
        owner_id: Optional[str] = None,
    ) -> list[dict]:
        """Get leads with follow-ups due before a date."""
        return self.activity_repo.get_follow_ups_due(before_date, owner_id)

    def get_recent_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        """Get recent activities for a user."""
        return self.activity_repo.get_recent_for_user(user_id, limit)

    def archive(self, activity_id: str, lead_id: str, actor_id: str) -> bool:
        """Archive a user-generated activity."""
        activity = self.activity_repo.get_by_id(activity_id)
        if not activity or activity.get("lead_id") != lead_id:
            return False

        if activity.get("action_type") not in {"follow_up", "comment"}:
            raise ValueError("Only follow-up and comment activities can be archived")

        success = self.activity_repo.archive(activity_id)
        if success:
            self.audit_repo.log(
                entity_type="lead_activity",
                entity_id=activity_id,
                event_type="archive",
                actor_id=actor_id,
                before_json=json.dumps(dict(activity)),
            )
            if activity.get("action_type") == "follow_up":
                self._sync_next_followup_date(lead_id, actor_id)
        return success

    def restore(self, activity_id: str, lead_id: str, actor_id: str) -> bool:
        """Restore an archived user-generated activity."""
        activity = self.activity_repo.get_by_id(activity_id)
        if not activity or activity.get("lead_id") != lead_id:
            return False

        if activity.get("action_type") not in {"follow_up", "comment"}:
            raise ValueError("Only follow-up and comment activities can be restored")

        success = self.activity_repo.restore(activity_id)
        if success:
            self.audit_repo.log(
                entity_type="lead_activity",
                entity_id=activity_id,
                event_type="restore",
                actor_id=actor_id,
                after_json=json.dumps(dict(activity)),
            )
            if activity.get("action_type") == "follow_up":
                self._sync_next_followup_date(lead_id, actor_id)
        return success
