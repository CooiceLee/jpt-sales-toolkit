#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  :
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
  PYTHON_BIN=".venv/Scripts/python.exe"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

echo "JPT Sales Toolkit v0.12 validation"
echo "----------------------------------"

echo
echo "Step 1/4: JavaScript syntax"
node --check frontend/js/i18n.js
node --check frontend/js/api-client.js
node --check frontend/js/app.js
node --check frontend/js/shared/utils.js
node --check frontend/js/shared/render.js
node --check frontend/js/modules/*.js

echo
echo "Step 2/4: Python compile"
"$PYTHON_BIN" -m py_compile \
  backend/config.py \
  backend/database_access.py \
  backend/app_v2.py \
  backend/authorization/*.py \
  backend/routers/*.py \
  backend/services/*.py \
  backend/repositories/*.py \
  backend/migration/*.py \
  test_*.py
"$PYTHON_BIN" -m compileall -q \
  backend/services/geocoding \
  backend/services/importing \
  backend/services/spreadsheet_import

echo
echo "Step 3/4: core regression tests"
"$PYTHON_BIN" test_password_service.py
"$PYTHON_BIN" test_authorization_crypto.py
"$PYTHON_BIN" test_authorization_clock.py
"$PYTHON_BIN" test_authorization_data_layer.py
"$PYTHON_BIN" test_authorization_transactions.py
"$PYTHON_BIN" test_authorization_api.py
"$PYTHON_BIN" test_authorization_role_boundary.py
"$PYTHON_BIN" test_authorization_security_regressions.py
"$PYTHON_BIN" test_tech_workload_summary.py
"$PYTHON_BIN" test_desktop_packaging_contract.py
"$PYTHON_BIN" test_release_hygiene.py
"$PYTHON_BIN" test_lan_test_accounts_security.py
"$PYTHON_BIN" test_version_contract.py
"$PYTHON_BIN" test_windows_path_contract.py
"$PYTHON_BIN" test_permissions.py
"$PYTHON_BIN" test_role_permissions.py
"$PYTHON_BIN" test_p1_data_integrity.py
"$PYTHON_BIN" test_customer_write_permissions.py
"$PYTHON_BIN" test_coordinate_integrity.py
"$PYTHON_BIN" test_review_map_module_contract.py
"$PYTHON_BIN" test_contact_validation.py
"$PYTHON_BIN" test_stage_auto_progression.py
"$PYTHON_BIN" test_backup_retention.py
"$PYTHON_BIN" test_backup_runtime_config.py
"$PYTHON_BIN" test_backup_api_cleanup.py
"$PYTHON_BIN" test_admin_restore_upload_security.py
"$PYTHON_BIN" test_database_access_gate.py
"$PYTHON_BIN" test_restore_cancellation_gate.py
"$PYTHON_BIN" test_restore_maintenance_gate.py
"$PYTHON_BIN" test_safe_upgrade.py
"$PYTHON_BIN" test_roundtrip_export_import.py
"$PYTHON_BIN" test_tech_task_package_exchange.py
"$PYTHON_BIN" test_json_sales_distribution.py
"$PYTHON_BIN" test_json_import_record_atomicity.py
"$PYTHON_BIN" test_json_recipient_export.py
"$PYTHON_BIN" test_json_roundtrip_business_fields.py
"$PYTHON_BIN" test_json_exchange_frontend_contract.py
"$PYTHON_BIN" test_tech_task_package_frontend_contract.py
"$PYTHON_BIN" test_tech_navigation_counts_frontend_contract.py
"$PYTHON_BIN" test_import_identity_schema.py
"$PYTHON_BIN" test_member_identity_service.py
"$PYTHON_BIN" test_spreadsheet_importing.py
"$PYTHON_BIN" test_spreadsheet_import.py
"$PYTHON_BIN" test_spreadsheet_import_frontend_contract.py
"$PYTHON_BIN" test_data_quality_issue_service.py
"$PYTHON_BIN" test_data_quality_issue_api.py
"$PYTHON_BIN" test_data_quality_frontend_contract.py
"$PYTHON_BIN" test_operational_field_roundtrip.py
"$PYTHON_BIN" test_operational_field_frontend_contract.py
"$PYTHON_BIN" test_inquiry_atomic_save.py
"$PYTHON_BIN" test_inquiry_atomic_frontend_contract.py
"$PYTHON_BIN" test_v07_review_trip.py
"$PYTHON_BIN" test_trip_planner_stability.py
"$PYTHON_BIN" test_trip_planner_stability_frontend_contract.py
"$PYTHON_BIN" test_trip_planner_transport_v2.py
"$PYTHON_BIN" test_trip_planner_free_stops.py
"$PYTHON_BIN" test_trip_planner_transport_v2_frontend_contract.py
"$PYTHON_BIN" test_trip_transport_suggestions.py
"$PYTHON_BIN" test_trip_transport_suggestions_endpoint.py
"$PYTHON_BIN" test_trip_planner_batch3_frontend_contract.py
"$PYTHON_BIN" test_trip_planner_batch4.py
"$PYTHON_BIN" test_trip_planner_batch4_frontend_contract.py
"$PYTHON_BIN" test_trip_export_renderers.py
"$PYTHON_BIN" test_trip_planner_batch5_exports.py
"$PYTHON_BIN" test_trip_flight_airports.py
"$PYTHON_BIN" test_trip_team_roundtrip.py
"$PYTHON_BIN" test_trip_team_ui_frontend_contract.py
"$PYTHON_BIN" test_trip_team_map_frontend_contract.py
"$PYTHON_BIN" test_trip_team_suggestions.py
"$PYTHON_BIN" test_trip_team_export.py
"$PYTHON_BIN" test_trip_planner_batch5_frontend_contract.py
"$PYTHON_BIN" test_v09_filters_merge.py
"$PYTHON_BIN" test_business_region_filters.py
"$PYTHON_BIN" test_customer_merge_integrity.py
"$PYTHON_BIN" test_customer_merge_frontend_contract.py
"$PYTHON_BIN" test_map_frontend_contract.py
"$PYTHON_BIN" test_geocoding_service.py
"$PYTHON_BIN" test_geocoding_frontend_contract.py
"$PYTHON_BIN" test_intake_router_module_contract.py
"$PYTHON_BIN" test_runtime_contracts.py
"$PYTHON_BIN" test_pre_sales_crud.py
"$PYTHON_BIN" test_pre_sales_read_model.py
"$PYTHON_BIN" test_sampling_frontend_contract.py
"$PYTHON_BIN" test_i18n_frontend_contract.py
"$PYTHON_BIN" test_worklist_ux_frontend_contract.py
"$PYTHON_BIN" test_stable_ux_frontend_contract.py
"$PYTHON_BIN" test_worklist_sort_frontend_contract.py
"$PYTHON_BIN" test_followup_filter_frontend_contract.py
"$PYTHON_BIN" test_frontend_module_contract.py
"$PYTHON_BIN" test_lead_dynamic_fields.py
"$PYTHON_BIN" test_intake_data_fidelity.py

echo
echo "Step 4/4: validation summary"
echo "PASS: v0.12 validation completed"
