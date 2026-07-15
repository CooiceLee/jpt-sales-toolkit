"""Stable issue IDs and de-duplication."""

import hashlib
import json


def finalize_issues(issues: list[dict]) -> list[dict]:
    seen, result = set(), []
    for item in issues:
        ref = item.get("source_ref") or {}
        key = (
            item.get("code"), item.get("external_key"), item.get("field"),
            item.get("message"), ref.get("record_key"), ref.get("sheet"), ref.get("row"),
        )
        if key in seen:
            continue
        seen.add(key)
        payload = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str).encode()
        result.append({"id": hashlib.sha256(payload).hexdigest()[:16], **item})
    return result
