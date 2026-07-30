"""Static contracts for the modular Sampling frontend and task API."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.app_v2 import create_app
from backend.routers.task_models import PreSalesTaskCreate
from backend.services.spreadsheet_import.write_pre_tasks import (
    REQUEST_FIELDS,
    RESULT_FIELDS,
)


ROOT = Path(__file__).parent


def main() -> None:
    fields = json.loads((ROOT / "config" / "fields.json").read_text(encoding="utf-8"))
    assert "sample" not in fields["field_groups"]

    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    scripts = [
        "pre-sales-task-model.js",
        "sampling-task-details.js",
        "sampling-task-form.js",
        "sampling-form-data.js",
        "sampling-form-controller.js",
        "sampling-panel.js",
        "sampling-actions.js",
        "sampling.js",
    ]
    positions = [index.index(script) for script in scripts]
    assert positions == sorted(positions)
    assert index.index("worklist-sort.js") < index.index("sampling.js")
    for task_status in ("Open", "In Progress", "Completed", "Cancelled"):
        assert f'data-filter="{task_status}"' in index

    app_js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    inquiry_form_js = (ROOT / "frontend" / "js" / "modules" / "inquiry-form.js").read_text(encoding="utf-8")
    api_js = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    sampling_js = (ROOT / "frontend" / "js" / "modules" / "sampling.js").read_text(
        encoding="utf-8"
    )
    task_model_js = (
        ROOT / "frontend" / "js" / "modules" / "pre-sales-task-model.js"
    ).read_text(encoding="utf-8")
    task_details_js = (
        ROOT / "frontend" / "js" / "modules" / "sampling-task-details.js"
    ).read_text(encoding="utf-8")
    actions_js = (
        ROOT / "frontend" / "js" / "modules" / "sampling-actions.js"
    ).read_text(encoding="utf-8")
    inquiry_panel_js = (
        ROOT / "frontend" / "js" / "modules" / "inquiry-panel.js"
    ).read_text(encoding="utf-8")
    inquiry_panel_data_js = (
        ROOT / "frontend" / "js" / "modules" / "inquiry-panel-data.js"
    ).read_text(encoding="utf-8")
    followups_form_js = (
        ROOT / "frontend" / "js" / "modules" / "followups-form.js"
    ).read_text(encoding="utf-8")
    assert "async function loadSampling" not in app_js
    assert "pre_sales_active_lead_count" in app_js
    assert "SamplingModule.renderTab" in inquiry_form_js
    assert "sales_stage: 'Following'" not in sampling_js
    assert "...getSharedLeadFilters()" in sampling_js
    assert "limit: 100000" in sampling_js
    assert "listPreSalesTasks({ limit: 100000 })" in sampling_js
    assert "WorklistSort.sampling" in sampling_js
    assert "Unable to load pre-sales tasks. Please retry." in sampling_js
    assert "InquiryPanelData.load" in inquiry_panel_js
    assert "InquiryPanelData.load" in followups_form_js
    assert "listPreSalesTasks({" in inquiry_panel_data_js
    task_call = inquiry_panel_data_js[
        inquiry_panel_data_js.index("listPreSalesTasks({"):
        inquiry_panel_data_js.index(
            "listAfterSalesTasks", inquiry_panel_data_js.index("listPreSalesTasks({")
        )
    ]
    assert ".catch(" not in task_call
    assert "SamplingFormData.collect(task)" in actions_js
    for field in (
        *REQUEST_FIELDS, *RESULT_FIELDS,
        "sample_result", "report_link", "confirmed_date",
    ):
        assert field in task_model_js
    for field in (*REQUEST_FIELDS, *RESULT_FIELDS):
        assert field in task_details_js
    for label in (
        "Request description", "Current progress", "Next action", "Result summary",
        "Supplemental notes", "Latest follow-up",
    ):
        assert label in task_details_js or label in (
            ROOT / "frontend" / "js" / "modules" / "sampling-panel.js"
        ).read_text(encoding="utf-8")
    for method in ("updatePreSalesTask", "archivePreSalesTask", "restorePreSalesTask"):
        assert method in api_js
    create_payload = PreSalesTaskCreate(
        assignee_id="tech-1",
        client_request_id="browser-request-1",
        status="In Progress",
        request_json='{"request_description":"sample"}',
        result_json='{"progress_text":"submitted"}',
    ).model_dump(exclude_none=True)
    assert create_payload["status"] == "In Progress"
    assert "result_json" in create_payload
    assert create_payload["client_request_id"] == "browser-request-1"
    _assert_task_payload_round_trip()

    routes = {
        (method, route.path)
        for route in create_app().routes
        for method in (getattr(route, "methods", None) or set())
    }
    expected = {
        ("PATCH", "/api/pre-sales-tasks/{task_id}"),
        ("POST", "/api/pre-sales-tasks/{task_id}/archive"),
        ("POST", "/api/pre-sales-tasks/{task_id}/restore"),
    }
    assert expected <= routes
    print("PASS: Sampling frontend modules and task API contracts")


def _assert_task_payload_round_trip() -> None:
    model_path = ROOT / "frontend" / "js" / "modules" / "pre-sales-task-model.js"
    details_path = ROOT / "frontend" / "js" / "modules" / "sampling-task-details.js"
    card_path = ROOT / "frontend" / "js" / "modules" / "card-template.js"
    script = f"""
const fs = require('fs');
global.window = global;
global.escapeHtml = value => String(value ?? '').replace(/&/g, '&amp;')
  .replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');
global.formatDate = value => {{
  if (value === '4.13') throw new Error('raw date was parsed');
  return String(value);
}};
global.I18n = {{ t: value => value }};
eval(fs.readFileSync({json.dumps(str(model_path))}, 'utf8'));
const raw = {{
  request_json: JSON.stringify({{
    request_description: 'request-marker',
    request_date: '2026-07-01',
    request_date_raw: 'request-date-raw-marker',
    due_date_raw: 'due-date-raw-marker',
    customer_decision_maker: 'decision-maker-marker',
    quantity_text: 'quantity-marker',
    competitor: 'competitor-marker',
    key_points: 'key-points-marker',
    concerns: 'concerns-marker'
  }}),
  result_json: JSON.stringify({{
    progress_text: 'progress-marker',
    result_summary: 'result-summary-marker',
    next_action: 'next-action-marker',
    supplemental_notes: 'notes-marker'
  }}),
  due_date: '2026-07-31'
}};
const view = PreSalesTaskModel.toView(raw);
if (view.request_description !== 'request-marker') throw new Error('request mapping');
if (view.progress_text !== 'progress-marker') throw new Error('progress mapping');
const request = PreSalesTaskModel.mergeRequest(view, {{ request_description: 'updated' }});
if (request.competitor !== 'competitor-marker'
    || request.request_date_raw !== 'request-date-raw-marker'
    || request.key_points !== 'key-points-marker') {{
  throw new Error('request preservation');
}}
const result = PreSalesTaskModel.mergeResult(view, {{ progress_text: 'done' }});
if (result.supplemental_notes !== 'notes-marker'
    || result.next_action !== 'next-action-marker') throw new Error('result preservation');
const corruptRequest = PreSalesTaskModel.toView({{
  request_json: '{{broken-request',
  result_json: '{{"progress_text":"safe"}}'
}});
if (corruptRequest._request_valid !== false) throw new Error('invalid request not detected');
let requestBlocked = false;
try {{
  PreSalesTaskModel.mergeRequest(corruptRequest, {{ request_description: 'overwrite' }});
}} catch (error) {{
  requestBlocked = error.message.includes('damaged JSON');
}}
if (!requestBlocked || corruptRequest.request_json !== '{{broken-request') {{
  throw new Error('invalid request overwrite not blocked');
}}
const corruptResult = PreSalesTaskModel.toView({{
  request_json: '{{"request_description":"safe"}}',
  result_json: '{{broken-result'
}});
if (corruptResult._result_valid !== false) throw new Error('invalid result not detected');
let resultBlocked = false;
try {{
  PreSalesTaskModel.mergeResult(corruptResult, {{ progress_text: 'overwrite' }});
}} catch (error) {{
  resultBlocked = error.message.includes('damaged JSON');
}}
if (!resultBlocked || corruptResult.result_json !== '{{broken-result') {{
  throw new Error('invalid result overwrite not blocked');
}}
eval(fs.readFileSync({json.dumps(str(details_path))}, 'utf8'));
const details = SamplingTaskDetails.render(view);
for (const marker of [
  'request-marker', '2026-07-01', 'request-date-raw-marker',
  '2026-07-31', 'due-date-raw-marker', 'decision-maker-marker',
  'quantity-marker', 'competitor-marker', 'key-points-marker',
  'concerns-marker', 'progress-marker', 'result-summary-marker',
  'next-action-marker', 'notes-marker'
]) {{
  if (!details.includes(marker)) throw new Error(`right-panel omission: ${{marker}}`);
}}
eval(fs.readFileSync({json.dumps(str(card_path))}, 'utf8'));
const html = renderInquiryCard({{
  id: 'lead-1', inquiry_id: 'JPT-1', company_name: 'Safe',
  stage: 'Following',
  latest_follow_up_at: '<img src=x onerror=alert(1)>',
  latest_follow_up_at_raw: '4.13'
}}, 'sampling');
if (!html.includes('4.13')) throw new Error('raw date preservation');
const escapedHtml = renderInquiryCard({{
  id: 'lead-2', inquiry_id: 'JPT-2', company_name: 'Safe',
  stage: 'Following', latest_follow_up_at: '<img src=x onerror=alert(1)>'
}}, 'sampling');
if (escapedHtml.includes('<img') || !escapedHtml.includes('&lt;img')) {{
  throw new Error('date escaping');
}}
"""
    subprocess.run(["node", "-e", script], check=True)


if __name__ == "__main__":
    main()
