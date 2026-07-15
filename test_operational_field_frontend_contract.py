"""Static frontend payload and selected-contact contracts."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def main() -> None:
    fields = json.loads((ROOT / "config" / "fields.json").read_text(encoding="utf-8"))
    assert "primary_contact_id" in fields["field_groups"]["customer"]["fields"]
    assert "quantity_text" in fields["field_groups"]["requirement"]["fields"]
    after_fields = fields["array_fields"]["after_sales"]["item_fields"]
    result_fields = {"customer_satisfaction", "lessons_learned", "remarks"}
    assert result_fields <= set(after_fields)

    inquiry_fields = (MODULES / "inquiry-fields.js").read_text(encoding="utf-8")
    inquiry_save = (MODULES / "inquiry-save.js").read_text(encoding="utf-8")
    contact_views = "\n".join(
        (MODULES / name).read_text(encoding="utf-8")
        for name in ("inquiry-fields.js", "inquiry-panel.js", "lead-navigation.js")
    )
    assert "getLeadPrimaryContact" in inquiry_fields
    assert "contacts?.[0]" not in contact_views and "contacts[0]" not in contact_views
    assert "primary_contact_id" in inquiry_save and "quantity_text" in inquiry_fields

    actions = (MODULES / "aftersales-actions.js").read_text(encoding="utf-8")
    form = (MODULES / "aftersales-form.js").read_text(encoding="utf-8")
    view = (MODULES / "aftersales-view.js").read_text(encoding="utf-8")
    mappings = (MODULES / "inquiry-task-mappers.js").read_text(encoding="utf-8")
    for field, element_id in (
        ("customer_satisfaction", "as-satisfaction"),
        ("lessons_learned", "as-lessons"),
        ("remarks", "as-remarks"),
    ):
        assert actions.count(field) >= 2, f"{field} must be sent for manager and Tech saves"
        assert element_id in form and element_id in view
        assert field in mappings and field in view
    print("PASS: selected contact and operational field frontend payload contracts")


if __name__ == "__main__":
    main()
