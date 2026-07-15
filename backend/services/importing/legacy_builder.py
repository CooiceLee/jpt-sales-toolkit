"""Composed canonical accumulator for the verified legacy adapter."""

from __future__ import annotations

from collections import Counter
from typing import Dict

from .legacy_constants import LEGACY_DATASET_ID
from .legacy_entities import EntityStoreMixin
from .legacy_matching import LeadMatchingMixin
from .legacy_members import MemberMixin
from .legacy_reporting import ReportingMixin, representative_fill
from .models import Workbook

ENTITY_NAMES = (
    "customers", "aliases", "contacts", "leads", "assignments", "activities",
    "pre_sales_tasks", "after_sales_tasks",
)


class CanonicalBuilder(EntityStoreMixin, MemberMixin, LeadMatchingMixin, ReportingMixin):
    def __init__(self, workbook: Workbook):
        self.workbook = workbook
        self.dataset_id = LEGACY_DATASET_ID
        self.entities: Dict[str, list[dict]] = {name: [] for name in ENTITY_NAMES}
        self.source_trace: list[dict] = []
        self.issues: list[dict] = []
        self.source_counts: Dict[str, int] = {}
        self.won_fulfillment_rows: Counter = Counter()
        self._indexes: Dict[str, Dict[str, dict]] = {name: {} for name in ENTITY_NAMES}
        self._customer_by_name: Dict[str, dict] = {}
        self._lead_search: list[dict] = []
        self._members: Dict[str, dict] = {}


__all__ = ["CanonicalBuilder", "representative_fill"]
