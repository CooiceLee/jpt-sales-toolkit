"""Loss-aware JSON payload merging for non-column spreadsheet fields."""

import json

from .persistence_common import CLEAR_TOKEN


def merged_json(existing: object, imported: dict) -> str:
    result = _object(existing)
    payload = result.get("spreadsheet_import")
    payload = dict(payload) if isinstance(payload, dict) else {}
    _merge(payload, imported)
    result["spreadsheet_import"] = payload
    return json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)


def merged_field_json(existing: object, item: dict, fields: tuple[str, ...]) -> str:
    result = _object(existing)
    _merge(result, {key: item[key] for key in fields
                    if key in item and item[key] not in (None, "")})
    return json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)


def _object(existing: object) -> dict:
    try:
        result = json.loads(existing) if existing else {}
    except (TypeError, json.JSONDecodeError):
        return {"legacy_value": str(existing)}
    return result if isinstance(result, dict) else {"legacy_value": result}


def _merge(target: dict, imported: dict) -> None:
    for key, value in imported.items():
        if value == CLEAR_TOKEN:
            target.pop(key, None)
        else:
            target[key] = value
