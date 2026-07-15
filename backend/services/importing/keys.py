"""Stable external keys, human-name tokens, and conservative matching text."""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Iterable

MEMBER_SPLIT = re.compile(r"\s*(?:/|&|＆|、|,|，|;|；|\+|\band\b)\s*", re.I)
NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
MODEL_TOKEN = re.compile(r"(?=[A-Z0-9+-]*[A-Z])(?=[A-Z0-9+-]*\d)[A-Z0-9]+(?:-[A-Z0-9+]+)+")

MEMBER_ALIASES = {
    "aydenl lin": ("ayden", "tech"), "ayden lin": ("ayden", "tech"),
    "ayden": ("ayden", "tech"), "eric": ("eric", "tech"),
    "neil zhu": ("neil", "tech"), "neil": ("neil", "tech"),
    "stanley liu": ("stanley", "sales"), "stanley": ("stanley", "sales"),
    "william": ("william", "sales"), "willam": ("william", "sales"),
    "milena": ("milena", "sales"), "hannah": ("hannah", "sales"),
    "lulu": ("lulu", "leader"), "gia": ("gia", "sales"),
    "ren": ("ren", "sales"), "slluu": ("slluu", "sales"),
    "slluu'": ("slluu", "sales"), "slluu‘": ("slluu", "sales"),
    "li liang": ("liang", "sales"), "liang": ("liang", "sales"),
}


def clean_text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def normalize_text(value: object) -> str:
    text = clean_text(value).casefold()
    return NON_WORD.sub("", text)


def stable_external_key(dataset_id: str, prefix: str, *parts: object) -> str:
    material = "|".join(clean_text(part) for part in parts)
    digest = uuid.uuid5(uuid.NAMESPACE_URL, f"jpt:{dataset_id}:{prefix}:{material}").hex[:20]
    return f"{prefix.upper()}-{digest}"


def split_member_names(value: object) -> list[str]:
    text = clean_text(value)
    if not text or text in {"/", "-", "?", "？"}:
        return []
    return [item.strip() for item in MEMBER_SPLIT.split(text) if item.strip()]


def member_token(name: object) -> tuple[str, str]:
    raw = clean_text(name)
    normalized = " ".join(raw.casefold().replace("’", "'").split())
    return MEMBER_ALIASES.get(normalized, (normalized, "unknown"))


def model_tokens(*values: object) -> set[str]:
    text = " ".join(clean_text(value).upper() for value in values)
    return {match.group(0).strip("-") for match in MODEL_TOKEN.finditer(text)}


def first_known_member(names: Iterable[str], allowed_roles: set[str]) -> tuple[str, str, str]:
    for raw in names:
        token, role = member_token(raw)
        if role in allowed_roles:
            return raw, token, role
    return "", "", "unknown"
