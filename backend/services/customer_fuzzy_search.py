"""Dependency-free fuzzy ranking for leader customer-merge review."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


LEGAL_SUFFIXES = {
    "ag", "bv", "co", "company", "corp", "corporation", "gmbh", "group",
    "inc", "incorporated", "limited", "llc", "ltd", "plc", "sa", "sarl",
}


def normalize_search_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"[\w]+", text, flags=re.UNICODE))


def _without_legal_suffixes(value: str) -> str:
    tokens = value.split()
    reduced = [token for token in tokens if token not in LEGAL_SUFFIXES]
    return " ".join(reduced or tokens)


def _text_score(query: str, candidate: str) -> int:
    normalized = normalize_search_text(candidate)
    if not normalized:
        return 0
    if query == normalized:
        return 100

    query_core = _without_legal_suffixes(query)
    candidate_core = _without_legal_suffixes(normalized)
    if query_core and query_core == candidate_core:
        return 98

    scores = [
        SequenceMatcher(None, query, normalized).ratio() * 100,
        SequenceMatcher(None, query.replace(" ", ""), normalized.replace(" ", "")).ratio() * 100,
        SequenceMatcher(None, query_core, candidate_core).ratio() * 100,
    ]
    if query in normalized or normalized in query:
        coverage = min(len(query), len(normalized)) / max(len(query), len(normalized))
        scores.append(86 + 12 * coverage)

    query_tokens, candidate_tokens = set(query_core.split()), set(candidate_core.split())
    if query_tokens and candidate_tokens:
        overlap = len(query_tokens & candidate_tokens)
        scores.append(100 * (2 * overlap) / (len(query_tokens) + len(candidate_tokens)))
    return min(100, round(max(scores)))


def rank_merge_candidates(records: list[dict], query: str, limit: int = 12) -> list[dict]:
    normalized_query = normalize_search_text(query)
    if len(normalized_query.replace(" ", "")) < 2:
        raise ValueError("Enter at least two characters to search customers")

    ranked = []
    for record in records:
        best = {
            "score": _text_score(normalized_query, record.get("display_name") or ""),
            "matched_on": "name",
            "matched_value": record.get("display_name") or "",
        }
        for alias in record.get("aliases") or []:
            alias_score = _text_score(normalized_query, alias)
            if alias_score > best["score"]:
                best = {"score": alias_score, "matched_on": "alias", "matched_value": alias}
        if best["score"] < 45:
            continue
        ranked.append({**record, **best})

    ranked.sort(
        key=lambda item: (
            -item["score"],
            str(item.get("display_name") or "").casefold(),
            str(item.get("id") or ""),
        )
    )
    return ranked[:limit]
