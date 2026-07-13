#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "JPT Sales Toolkit v0.9 validation"
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
python3 -m py_compile \
  backend/config.py \
  backend/app_v2.py \
  backend/routers/*.py \
  backend/services/*.py \
  backend/repositories/*.py \
  backend/migration/*.py \
  test_*.py

echo
echo "Step 3/4: core regression tests"
python3 test_permissions.py
python3 test_role_permissions.py
python3 test_contact_validation.py
python3 test_stage_auto_progression.py
python3 test_backup_retention.py
python3 test_backup_api_cleanup.py
python3 test_roundtrip_export_import.py
python3 test_v07_review_trip.py
python3 test_runtime_contracts.py
python3 test_pre_sales_crud.py
python3 test_sampling_frontend_contract.py
python3 test_frontend_module_contract.py
python3 test_lead_dynamic_fields.py
python3 test_intake_data_fidelity.py

echo
echo "Step 4/4: validation summary"
echo "PASS: v0.9 validation completed"
