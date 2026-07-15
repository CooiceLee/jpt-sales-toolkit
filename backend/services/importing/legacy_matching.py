"""Conservative downstream-to-opportunity matching for legacy rows."""

from __future__ import annotations

from typing import Any, Optional

from .keys import model_tokens, normalize_text


class LeadMatchingMixin:
    def register_searchable_lead(self, lead: dict, content: Any, contact_name: Any,
                                 source_sheet: str) -> None:
        self._lead_search.append({
            "lead_key": lead["external_key"], "customer_key": lead.get("customer_key"),
            "title": normalize_text(lead.get("title")), "blob": normalize_text(content),
            "models": model_tokens(content, lead.get("title")),
            "contact": normalize_text(contact_name), "source_sheet": source_sheet,
        })

    def match_lead(self, customer_key: Optional[str], content: Any, contact_name: Any,
                   allowed_sheets: set[str]) -> tuple[Optional[dict], str, str]:
        if not customer_key:
            return None, "none", "none"
        raw = [item for item in self._lead_search
               if item["customer_key"] == customer_key and item["source_sheet"] in allowed_sheets]
        candidates: dict[str, dict] = {}
        for item in raw:
            candidate = candidates.setdefault(item["lead_key"], dict(item))
            candidate["models"] = candidate["models"] | item["models"]
            candidate["blob"] += item["blob"]
            candidate["contact"] = candidate["contact"] or item["contact"]
        values = list(candidates.values())
        if not values:
            return None, "none", "none"
        incoming_models = model_tokens(content)
        matches = [item for item in values if incoming_models & item["models"]]
        if len(matches) == 1:
            return self._lead(matches[0]), "customer+model", "high"
        contact = normalize_text(contact_name)
        matches = [item for item in values if contact and item["contact"] == contact]
        if len(matches) == 1:
            return self._lead(matches[0]), "customer+contact", "high"
        normalized_content = normalize_text(content)
        matches = [item for item in values if len(item["title"]) >= 6 and
                   item["title"] in normalized_content]
        if len(matches) == 1:
            return self._lead(matches[0]), "customer+title", "high"
        return None, "ambiguous_customer", "low"

    def _lead(self, match: dict) -> dict:
        return self._indexes["leads"][match["lead_key"]]
