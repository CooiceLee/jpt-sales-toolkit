#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
  PYTHON_BIN=".venv/Scripts/python.exe"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

echo "JPT Sales Toolkit v0.10 validation"
echo "----------------------------------"

echo
echo "Step 1/4: JavaScript syntax"
node --check frontend/js/api-client.js
node --check frontend/js/app.js
node --check frontend/js/shared/utils.js
node --check frontend/js/shared/render.js
node --check frontend/js/modules/*.js

echo
echo "Step 2/4: Python compile"
"$PYTHON_BIN" -m py_compile \
  backend/config.py \
  backend/app_v2.py \
  backend/authorization/*.py \
  backend/routers/*.py \
  backend/services/*.py \
  backend/repositories/*.py \
  backend/migration/*.py \
  test_*.py

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
"$PYTHON_BIN" test_desktop_packaging_contract.py
"$PYTHON_BIN" test_version_contract.py
"$PYTHON_BIN" test_windows_path_contract.py
"$PYTHON_BIN" test_permissions.py
"$PYTHON_BIN" test_role_permissions.py
"$PYTHON_BIN" test_contact_validation.py
"$PYTHON_BIN" test_stage_auto_progression.py
"$PYTHON_BIN" test_backup_retention.py
"$PYTHON_BIN" test_backup_runtime_config.py
"$PYTHON_BIN" test_backup_api_cleanup.py
"$PYTHON_BIN" test_roundtrip_export_import.py
"$PYTHON_BIN" test_v07_review_trip.py
"$PYTHON_BIN" test_v09_filters_merge.py
"$PYTHON_BIN" test_runtime_contracts.py
"$PYTHON_BIN" test_pre_sales_crud.py
"$PYTHON_BIN" test_sampling_frontend_contract.py
"$PYTHON_BIN" test_frontend_module_contract.py
"$PYTHON_BIN" test_lead_dynamic_fields.py
"$PYTHON_BIN" test_intake_data_fidelity.py

echo
echo "Step 4/4: validation summary"
echo "PASS: v0.10 validation completed"
