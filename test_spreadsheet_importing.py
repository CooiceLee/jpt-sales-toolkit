#!/usr/bin/env python3
"""OOXML, legacy-source, standard-template and canonical-contract regression."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from backend.services.importing import (
    ImportWorkbookError,
    UnsupportedWorkbookError,
    parse_import_workbook,
    preflight_import_workbook,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_LEGACY = Path("/Users/liliang/Desktop/欧洲小分队进度记录.xlsx")
TEMPLATE = ROOT / "frontend" / "templates" / "JPT标准导入模板.xlsx"
LEGACY_SHA256 = "6f9b3e1fe195558d7c64671a8a15752db541ae5166a9724dad03487f53585dc5"
YELLOW_WON_ROWS = {63, 78, 85, 94, 127, 133, 136, 139, 140, 141, 142, 143, 144, 145, 146, 147}


def test_real_legacy_workbook() -> None:
    path = Path(os.environ.get("JPT_LEGACY_XLSX", str(DEFAULT_LEGACY)))
    if not path.exists():
        print(f"SKIP real source fixture: {path}")
        return
    before = (path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    assert before[2] == LEGACY_SHA256, "Real workbook changed; re-verify row boundaries before accepting it"
    canonical = parse_import_workbook(path.read_bytes(), path.name)
    after = (path.stat().st_size, path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    assert before == after, "Parser must never mutate the source workbook"

    assert canonical["summary"]["source_rows"] == {
        "潜在商业机会": 243, "售前（技术问题）": 84, "赢单": 146, "售后": 69,
    }
    assert canonical["summary"]["total_source_rows"] == 542
    assert canonical["summary"]["won_fulfillment"] == {"Completed": 130, "In Progress": 16}
    missing = [issue for issue in canonical["issues"]
               if issue["code"] == "missing_required_field" and
               issue["source_ref"]["sheet"] == "潜在商业机会"]
    assert len(missing) == 24
    assert Counter(issue["field"] for issue in missing) == {"title": 15, "customer_key": 9}
    _assert_potential_quantity_mapping(canonical)
    _assert_entity_contract(canonical)
    _assert_style_and_boundary_contract(canonical)
    json.dumps(canonical, ensure_ascii=False)


def _assert_potential_quantity_mapping(canonical: dict) -> None:
    trace = next(item for item in canonical["source_trace"]
                 if item["source_ref"]["sheet"] == "潜在商业机会" and
                 item["source_ref"]["row"] == 3)
    customers = {item["external_key"]: item for item in canonical["entities"]["customers"]}
    leads = {item["external_key"]: item for item in canonical["entities"]["leads"]}
    customer = next(customers[key] for key in trace["target_entity_keys"] if key in customers)
    lead = next(leads[key] for key in trace["target_entity_keys"] if key in leads)
    assert customer["display_name"] == "strijbosch" and not customer.get("company_size")
    assert lead["quantity_text"] == "2台"


def _assert_entity_contract(canonical: dict) -> None:
    expected = {
        "customers", "aliases", "contacts", "leads", "assignments", "activities",
        "pre_sales_tasks", "after_sales_tasks",
    }
    assert set(canonical["entities"]) == expected
    for rows in canonical["entities"].values():
        for row in rows:
            assert row.get("external_key")
            assert set(row.get("source_ref", {})) == {"sheet", "row", "record_key"}
    for lead in canonical["entities"]["leads"]:
        assert "owner_id" not in lead
    for kind in ("pre_sales_tasks", "after_sales_tasks"):
        for task in canonical["entities"][kind]:
            assert "assignee_id" not in task


def _assert_style_and_boundary_contract(canonical: dict) -> None:
    traces = canonical["source_trace"]
    won = {trace["source_ref"]["row"]: trace for trace in traces
           if trace["source_ref"]["sheet"] == "赢单" and trace["disposition"].startswith("mapped")}
    assert {row for row, trace in won.items() if trace["style_class"] == "yellow"} == YELLOW_WON_ROWS
    lead_map = {row["external_key"]: row for row in canonical["entities"]["leads"]}
    stage_by_style = defaultdict(Counter)
    for trace in traces:
        if trace["source_ref"]["sheet"] != "潜在商业机会" or not trace["disposition"].startswith("mapped"):
            continue
        lead_key = next(key for key in trace["target_entity_keys"] if key in lead_map)
        stage_by_style[trace["style_class"]][lead_map[lead_key]["sales_stage"]] += 1
    assert len(stage_by_style["gray"]) > 1 and len(stage_by_style["green"]) > 1

    excluded = {("潜在商业机会", 2), ("售前（技术问题）", 2), ("赢单", 160),
                ("赢单", 161), ("赢单", 162), ("售后", 2), ("售后", 72)}
    for rows in canonical["entities"].values():
        assert not any((row["source_ref"]["sheet"], row["source_ref"]["row"]) in excluded for row in rows)
    continuation = next(trace for trace in traces
                        if trace["source_ref"]["sheet"] == "售后" and trace["source_ref"]["row"] == 72)
    assert continuation["disposition"] == "merged_continuation"
    row_71_tasks = [task for task in canonical["entities"]["after_sales_tasks"]
                    if task["source_ref"]["row"] == 71]
    assert any("先装一台复测" in (task.get("progress_text") or "") for task in row_71_tasks)
    hidden = next(trace for trace in traces
                  if trace["source_ref"]["sheet"] == "售前（技术问题）" and trace["source_ref"]["row"] == 3)
    assert hidden["row_hidden"] is True


def test_standard_empty_template() -> None:
    assert TEMPLATE.exists(), f"Missing generated template: {TEMPLATE}"
    canonical = parse_import_workbook(TEMPLATE.read_bytes(), TEMPLATE.name)
    assert canonical["dataset_id"] == "30d886c9-9fff-4c24-a410-7d25f213c0b8"
    assert canonical["summary"]["total_source_rows"] == 0
    assert canonical["summary"]["can_import"] is True
    assert not canonical["issues"] and not canonical["source_trace"]
    assert all(not rows for rows in canonical["entities"].values())
    report = preflight_import_workbook(TEMPLATE.read_bytes(), TEMPLATE.name)
    assert report["summary"] == canonical["summary"]


def test_standard_missing_table_error() -> None:
    mutated = _rename_after_sales_table(TEMPLATE.read_bytes())
    try:
        parse_import_workbook(mutated, "missing-table.xlsx")
    except UnsupportedWorkbookError as exc:
        assert "tbl_after_sales_tasks" in str(exc) and "missing Excel tables" in str(exc)
    else:
        raise AssertionError("A standard workbook with a missing table must fail clearly")


def _rename_after_sales_table(content: bytes) -> bytes:
    output = io.BytesIO()
    replaced = False
    with ZipFile(io.BytesIO(content)) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename.startswith("xl/tables/") and b'tbl_after_sales_tasks' in data:
                data = data.replace(b'tbl_after_sales_tasks', b'tbl_after_sales_missing')
                replaced = True
            target.writestr(member, data)
    assert replaced
    return output.getvalue()


def test_invalid_package_error() -> None:
    try:
        parse_import_workbook(b"not an xlsx", "invalid.xlsx")
    except ImportWorkbookError as exc:
        assert "valid XLSX" in str(exc)
    else:
        raise AssertionError("Invalid ZIP content must be rejected")


def main() -> None:
    test_real_legacy_workbook()
    test_standard_empty_template()
    test_standard_missing_table_error()
    test_invalid_package_error()
    print("PASS: spreadsheet importing OOXML, legacy mapping and standard template contracts")


if __name__ == "__main__":
    main()
