"""Legacy team-name tokenization without resolving local accounts."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .keys import member_token, split_member_names, stable_external_key


class MemberMixin:
    def member_names(self, value: Any, ref: dict) -> list[dict]:
        result = []
        for raw_name in split_member_names(value):
            token, role = member_token(raw_name)
            item = self._members.setdefault(token, {
                "username_token": token, "role_hint": role, "raw_names": [],
                "occurrences": 0, "source_refs": [],
            })
            if raw_name not in item["raw_names"]:
                item["raw_names"].append(raw_name)
            item["occurrences"] += 1
            if ref not in item["source_refs"]:
                item["source_refs"].append(ref)
            result.append({"raw_name": raw_name, "username_token": token, "role_hint": role})
        return result

    def choose_owner(self, values: Iterable[Any], ref: dict) -> tuple[Optional[str], str, list[dict]]:
        members: list[dict] = []
        for value in values:
            members.extend(self.member_names(value, ref))
        for member in members:
            if member["role_hint"] in {"leader", "sales"}:
                return member["username_token"], member["raw_name"], members
        return None, "", members

    def add_assignments(self, lead_key: str, owner_token: Optional[str],
                        members: list[dict], ref: dict) -> None:
        for member in members:
            token = member["username_token"]
            if member["role_hint"] not in {"leader", "sales"} or token == owner_token:
                continue
            key = stable_external_key(self.dataset_id, "ASG", lead_key, token, "collaborator")
            self.add_entity("assignments", {
                "external_key": key, "source_ref": ref, "lead_key": lead_key,
                "member_username_token": token, "member_name_raw": member["raw_name"],
                "assignment_type": "collaborator",
            })
