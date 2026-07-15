"""
Data exchange router - export and import functionality.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..repositories.activity_repository import ActivityRepository
from ..repositories.audit_repository import AuditRepository
from ..repositories.attachment_repository import AttachmentRepository
from ..repositories.customer_repository import CustomerRepository
from ..repositories.lead_repository import LeadRepository
from ..repositories.task_repository import AfterSalesTaskRepository
from ..repositories.user_repository import UserRepository
from ..repositories.base import get_transaction
from ..services import CountryService, CustomerService, LeadService
from .deps import get_actor_role_for_lead, get_current_user, require_role

router = APIRouter(
    prefix="/data",
    tags=["data_exchange"],
    dependencies=[Depends(require_role("leader", "sales"))],
)


class ExportRequest(BaseModel):
    lead_ids: Optional[List[str]] = None  # If None, export all user's leads


class ImportReport(BaseModel):
    import_time: str
    imported_by: str
    total_records: int
    new_customers: int
    updated_customers: int
    new_leads: int
    updated_leads: int
    merged_activities: int = 0
    merged_tasks: int = 0
    merged_contacts: int = 0
    attachments_skipped: int = 0
    skipped_records: int
    errors: List[str]


class BatchRepairRequest(BaseModel):
    customer_ids: Optional[List[str]] = None
    lead_ids: Optional[List[str]] = None
    country: Optional[str] = None
    region: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    owner_id: Optional[str] = None
    product_category: Optional[str] = None
    application: Optional[str] = None


def _can_export_lead(lead: Optional[dict], user: dict) -> bool:
    """Return whether a lead can be included in a user's export."""
    if not lead:
        return False
    if user.get("role") == "leader":
        return True
    return get_actor_role_for_lead(lead["id"], user) in {"owner", "collaborator", "watcher"}


@router.post("/export")
async def export_data(
    request: ExportRequest,
    user: dict = Depends(get_current_user),
):
    """Export user's data to JSON format."""
    user_id = user["id"]

    lead_repo = LeadRepository()
    customer_repo = CustomerRepository()
    activity_repo = ActivityRepository()
    after_sales_repo = AfterSalesTaskRepository()
    attachment_repo = AttachmentRepository()

    # Get leads to export.
    if request.lead_ids:
        leads = [lead_repo.get_by_id(lid) for lid in request.lead_ids]
        leads = [lead for lead in leads if _can_export_lead(lead, user)]
    else:
        if user.get("role") == "leader":
            leads = lead_repo.list(limit=10000)
        else:
            # Export all leads the user can see as owner/collaborator/watcher.
            leads = lead_repo.get_leads_for_user(user_id, limit=10000)

    # Build export data structure
    export_data = {
        "export_time": datetime.utcnow().isoformat(),
        "exported_by": user_id,
        "exporter_name": user.get("display_name", ""),
        "version": "v2.0",
        "customers": {},
        "leads": []
    }

    customer_ids = set()
    for lead in leads:
        customer_ids.add(lead["customer_id"])

    # Export customers (deduplicated)
    for customer_id in customer_ids:
        customer = customer_repo.get_by_id(customer_id)
        if customer:
            # Get contacts for this customer
            contacts = customer_repo.get_contacts(customer_id)
            customer["contacts"] = contacts
            export_data["customers"][customer_id] = customer

    # Export leads with related data
    for lead in leads:
        # Get full activity history. The default list endpoint is paginated.
        activities = activity_repo.list_all_for_lead(lead["id"])

        # Get after-sales tasks
        after_sales = after_sales_repo.list({"lead_id": lead["id"], "limit": 100000})

        # Get attachment metadata (not file content)
        attachments = attachment_repo.list_for_lead(lead["id"])

        lead_export = {
            "lead": lead,
            "activities": activities,
            "after_sales_tasks": after_sales,
            "attachments": [
                {
                    "id": att["id"],
                    "category": att["category"],
                    "original_name": att["original_name"],
                    "size_bytes": att["size_bytes"],
                    "uploaded_at": att["uploaded_at"],
                    "note": "File content not included in export"
                }
                for att in attachments
            ]
        }
        export_data["leads"].append(lead_export)

    # Generate filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"jpt_export_{user.get('display_name', user_id)}_{timestamp}.json"

    # Return as streaming response
    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)

    return StreamingResponse(
        iter([json_str]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/preflight")
async def preflight_import(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Read an import file and return a non-mutating data quality report."""
    import_data = await _read_import_file(file)
    return _build_preflight_report(import_data, user)


@router.get("/governance/coordinate-audit")
async def get_coordinate_audit(
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Return recent coordinate change audit records."""
    if user.get("role") != "leader":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only leaders can view coordinate audit")
    audit_repo = AuditRepository()
    rows = audit_repo.list_recent(entity_type="customer_coordinate", limit=limit)
    return {"items": [_parse_audit_row(row) for row in rows]}


@router.post("/governance/normalize-countries")
async def normalize_countries(
    user: dict = Depends(get_current_user),
):
    """Normalize customer country names and missing regions using backend rules."""
    if user.get("role") != "leader":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only leaders can normalize countries")
    customer_service = CustomerService()
    country_service = CountryService()
    customers = customer_service.customer_repo.list_active(limit=100000)
    updated = 0
    skipped = 0
    for customer in customers:
        payload = {
            "country": customer.get("country"),
            "region": customer.get("region"),
        }
        country_service.normalize_customer_payload(payload)
        update_data = {}
        for field in ("country", "region"):
            if payload.get(field) and payload.get(field) != customer.get(field):
                update_data[field] = payload[field]
        if not update_data:
            skipped += 1
            continue
        customer_service.update(customer["id"], update_data, user["id"], customer["row_version"])
        updated += 1
    return {"updated_customers": updated, "skipped_customers": skipped}


@router.post("/governance/batch-repair")
async def batch_repair(
    request: BatchRepairRequest,
    user: dict = Depends(get_current_user),
):
    """Apply controlled batch repairs for customer and lead fields."""
    if user.get("role") != "leader":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only leaders can run batch repair")
    customer_service = CustomerService()
    lead_service = LeadService()
    result = {"updated_customers": 0, "updated_leads": 0, "errors": []}

    customer_update = {
        key: value
        for key, value in {
            "country": request.country,
            "region": request.region,
            "lat": request.lat,
            "lng": request.lng,
        }.items()
        if value is not None and value != ""
    }
    for customer_id in request.customer_ids or []:
        try:
            customer = customer_service.get(customer_id)
            if not customer:
                result["errors"].append(f"Customer {customer_id}: not found")
                continue
            if customer_update:
                customer_service.update(customer_id, dict(customer_update), user["id"], customer["row_version"])
                result["updated_customers"] += 1
        except Exception as exc:
            result["errors"].append(f"Customer {customer_id}: {exc}")

    lead_update = {
        key: value
        for key, value in {
            "owner_id": request.owner_id,
            "product_category": request.product_category,
            "application": request.application,
        }.items()
        if value is not None and value != ""
    }
    for lead_id in request.lead_ids or []:
        try:
            lead = lead_service.get(lead_id)
            if not lead:
                result["errors"].append(f"Lead {lead_id}: not found")
                continue
            if lead_update:
                lead_service.update(lead_id, dict(lead_update), user["id"], "leader", lead["row_version"])
                result["updated_leads"] += 1
        except Exception as exc:
            result["errors"].append(f"Lead {lead_id}: {exc}")

    return result


@router.post("/import")
async def import_data(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Import and merge data from exported JSON file.

    Key behaviors:
    - Only legacy_inquiry_id is used for lead matching (not display_id)
    - Activities/tasks are merged for both new and existing leads
    - Permission filtering happens BEFORE customer import to avoid pollution
    """
    user_id = user["id"]
    user_role = user.get("role", "sales")

    # Read and parse file
    try:
        content = await file.read()
        import_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON format"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error reading file: {str(e)}"
        )

    # Validate format
    if "version" not in import_data or "customers" not in import_data or "leads" not in import_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid export file format"
        )

    # Initialize report
    report = {
        "import_time": datetime.utcnow().isoformat(),
        "imported_by": user_id,
        "source_user": import_data.get("exported_by", "unknown"),
        "source_time": import_data.get("export_time", "unknown"),
        "total_records": len(import_data["leads"]),
        "new_customers": 0,
        "updated_customers": 0,
        "new_leads": 0,
        "updated_leads": 0,
        "merged_activities": 0,
        "merged_tasks": 0,
        "merged_contacts": 0,
        "attachments_skipped": 0,
        "skipped_records": 0,
        "errors": []
    }
    report["snapshot_before"] = _data_snapshot()

    customer_service = CustomerService()
    lead_service = LeadService()

    with get_transaction():
        # STEP 0: Pre-filter leads by permission to determine allowed customers
        # This prevents customer pollution when non-owner imports someone else's file
        allowed_leads = []
        allowed_customer_ids = set()

        for lead_item in import_data["leads"]:
            lead_data = lead_item["lead"]
            # Non-leader users can only import leads they own
            if user_role != "leader" and lead_data.get("owner_id") != user_id:
                report["skipped_records"] += 1
                continue

            existing_lead = _find_existing_lead(lead_service.lead_repo, lead_data)
            if existing_lead:
                target_role = get_actor_role_for_lead(existing_lead["id"], user)
                if not _can_import_existing_lead(target_role):
                    report["skipped_records"] += 1
                    continue

            allowed_leads.append(lead_item)
            allowed_customer_ids.add(lead_data["customer_id"])

        # STEP 1: Import/merge only allowed customers
        customer_id_map = {}  # old_id -> new_id

        for old_customer_id, raw_customer_data in import_data["customers"].items():
            # Skip customers that have no allowed leads
            if old_customer_id not in allowed_customer_ids:
                continue

            try:
                customer_data = deepcopy(raw_customer_data)
                # Check if customer already exists by matching email or company name
                email = None
                if customer_data.get("contacts"):
                    email = customer_data["contacts"][0].get("email")

                company_name = customer_data.get("display_name")

                matches = customer_service.match(email, company_name)

                if matches:
                    # Customer exists, update if needed
                    existing_id = matches[0]["id"]
                    customer_id_map[old_customer_id] = existing_id

                    # Update customer fields if they have newer data
                    update_data = {}
                    for field in [
                        "website",
                        "industry",
                        "customer_type",
                        "country",
                        "city",
                        "postal_code",
                        "address",
                        "region",
                        "language",
                        "company_size",
                        "company_description",
                        "lat",
                        "lng",
                        "normalized_address",
                        "geocode_source",
                        "geocode_confidence",
                        "geocode_locked",
                    ]:
                        if field in customer_data and customer_data[field]:
                            update_data[field] = customer_data[field]

                    if update_data:
                        existing = customer_service.get(existing_id)
                        customer_service.update(
                            existing_id,
                            update_data,
                            user_id,
                            existing["row_version"]
                        )
                        report["updated_customers"] += 1

                    report["merged_contacts"] += _merge_contacts(
                        existing_id,
                        customer_data.get("contacts", []),
                        user_id,
                        customer_service,
                    )
                else:
                    # Create new customer
                    contacts = customer_data.get("contacts", [])
                    customer_data = _sanitize_customer_data(customer_data)

                    new_customer = customer_service.create(customer_data, user_id)
                    new_id = new_customer["id"]
                    customer_id_map[old_customer_id] = new_id

                    # Add contacts
                    for contact in contacts:
                        customer_service.add_contact(new_id, _sanitize_contact_data(contact), user_id)
                        report["merged_contacts"] += 1

                    report["new_customers"] += 1

            except Exception as e:
                report["errors"].append(f"Customer {old_customer_id}: {str(e)}")

        # STEP 2: Import/merge allowed leads
        for lead_item in allowed_leads:
            try:
                lead_data = deepcopy(lead_item["lead"])
                old_customer_id = lead_data["customer_id"]

                # Map to new customer ID
                if old_customer_id not in customer_id_map:
                    report["errors"].append(f"Lead {lead_data.get('display_id', 'unknown')}: customer not found")
                    report["skipped_records"] += 1
                    continue

                new_customer_id = customer_id_map[old_customer_id]
                lead_data["customer_id"] = new_customer_id

                existing_lead = _find_existing_lead(lead_service.lead_repo, lead_data)

                if existing_lead:
                    target_role = get_actor_role_for_lead(existing_lead["id"], user)
                    if not _can_import_existing_lead(target_role):
                        report["skipped_records"] += 1
                        continue

                    # Update existing lead fields
                    update_fields = {}
                    for field in ["title", "product_category", "application", "deal_amount", "quotation_id", "po_number"]:
                        if field in lead_data and lead_data[field]:
                            update_fields[field] = lead_data[field]

                    if update_fields:
                        lead_service.update(
                            existing_lead["id"],
                            update_fields,
                            user_id,
                            target_role,
                            existing_lead["row_version"]
                        )

                    report["updated_leads"] += 1

                    # FIX: Merge activities for existing lead (was missing before)
                    merged_activities = _merge_activities(
                        existing_lead["id"],
                        lead_item.get("activities", []),
                        user_id
                    )
                    report["merged_activities"] += merged_activities

                    # FIX: Merge after-sales tasks for existing lead (was missing before)
                    merged_tasks = _merge_after_sales_tasks(
                        existing_lead["id"],
                        lead_item.get("after_sales_tasks", []),
                        user_id
                    )
                    report["merged_tasks"] += merged_tasks

                else:
                    # Create new lead
                    source_display_id = lead_data.pop("display_id", None)
                    source_lead_id = _get_source_lead_id(lead_data)
                    lead_data.pop("id", None)
                    lead_data.pop("created_at", None)
                    lead_data.pop("created_by", None)
                    lead_data.pop("updated_at", None)
                    lead_data.pop("updated_by", None)
                    lead_data.pop("row_version", None)
                    lead_data.pop("archived_at", None)
                    if source_display_id or source_lead_id:
                        lead_data["extra_json"] = _merge_extra_json(
                            lead_data.get("extra_json"),
                            {
                                "source_lead_id": source_lead_id,
                                "source_display_id": source_display_id,
                                "source_exported_by": report["source_user"],
                                "source_export_time": report["source_time"],
                            },
                        )

                    # Ensure owner is current user for new leads
                    lead_data["owner_id"] = user_id

                    new_lead = lead_service.create(lead_data, user_id)
                    report["new_leads"] += 1

                    # Import activities for new lead
                    merged_activities = _merge_activities(
                        new_lead["id"],
                        lead_item.get("activities", []),
                        user_id
                    )
                    report["merged_activities"] += merged_activities

                    # Import after-sales tasks for new lead
                    merged_tasks = _merge_after_sales_tasks(
                        new_lead["id"],
                        lead_item.get("after_sales_tasks", []),
                        user_id
                    )
                    report["merged_tasks"] += merged_tasks

                report["attachments_skipped"] += len(lead_item.get("attachments", []))

            except Exception as e:
                report["errors"].append(f"Lead {lead_data.get('display_id', 'unknown')}: {str(e)}")
                report["skipped_records"] += 1

    report["snapshot_after"] = _data_snapshot()
    report["snapshot_delta"] = _snapshot_delta(report["snapshot_before"], report["snapshot_after"])
    return report


def _can_import_existing_lead(actor_role: str) -> bool:
    """Return whether a user can merge data into an existing target lead."""
    return actor_role in {"leader", "owner", "collaborator"}


async def _read_import_file(file: UploadFile) -> dict:
    try:
        content = await file.read()
        import_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON format",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error reading file: {str(e)}",
        )

    if "version" not in import_data or "customers" not in import_data or "leads" not in import_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid export file format",
        )
    return import_data


def _build_preflight_report(import_data: dict, user: dict) -> dict:
    customer_service = CustomerService()
    lead_service = LeadService()
    country_service = CountryService()
    issues: list[dict] = []
    duplicate_customers: list[dict] = []
    permission_skipped = 0
    allowed_leads = []

    seen_customer_names: dict[str, str] = {}
    seen_emails: dict[str, str] = {}
    for old_customer_id, customer in (import_data.get("customers") or {}).items():
        normalized_name = _normalize_text(customer.get("display_name"))
        if not customer.get("display_name"):
            issues.append(_issue("error", "missing_field", f"customer:{old_customer_id}", "Customer display_name is required"))
        elif normalized_name in seen_customer_names:
            duplicate_customers.append({
                "type": "file_duplicate_name",
                "customer_id": old_customer_id,
                "matches": [seen_customer_names[normalized_name]],
                "name": customer.get("display_name"),
            })
        else:
            seen_customer_names[normalized_name] = old_customer_id

        for contact in customer.get("contacts") or []:
            email = str(contact.get("email") or "").strip().lower()
            if not email:
                continue
            if email in seen_emails:
                duplicate_customers.append({
                    "type": "file_duplicate_email",
                    "customer_id": old_customer_id,
                    "matches": [seen_emails[email]],
                    "email": email,
                })
            else:
                seen_emails[email] = old_customer_id

        if customer.get("country") and not country_service.center(customer.get("country")):
            issues.append(_issue("warning", "invalid_country", f"customer:{old_customer_id}", f"Country is not in region config: {customer.get('country')}"))
        lat = customer.get("lat")
        lng = customer.get("lng")
        if (lat is None) != (lng is None):
            issues.append(_issue("warning", "coordinate_anomaly", f"customer:{old_customer_id}", "Only one of lat/lng is present"))
        elif lat is not None and lng is not None:
            try:
                lat_number = float(lat)
                lng_number = float(lng)
                if lat_number < -90 or lat_number > 90 or lng_number < -180 or lng_number > 180:
                    issues.append(_issue("warning", "coordinate_anomaly", f"customer:{old_customer_id}", "Coordinates are out of range"))
            except (TypeError, ValueError):
                issues.append(_issue("warning", "coordinate_anomaly", f"customer:{old_customer_id}", "Coordinates are not numeric"))

        email = None
        if customer.get("contacts"):
            email = customer["contacts"][0].get("email")
        matches = customer_service.match(email, customer.get("display_name"))
        if matches:
            duplicate_customers.append({
                "type": "existing_customer_match",
                "customer_id": old_customer_id,
                "name": customer.get("display_name"),
                "matches": [{"id": item["id"], "display_name": item.get("display_name"), "match_type": item.get("match_type")} for item in matches[:5]],
            })

    for index, lead_item in enumerate(import_data.get("leads") or [], start=1):
        lead = lead_item.get("lead") or {}
        entity = f"lead:{lead.get('display_id') or lead.get('id') or index}"
        if user.get("role") != "leader" and lead.get("owner_id") != user.get("id"):
            permission_skipped += 1
            continue

        existing_lead = _find_existing_lead(lead_service.lead_repo, lead)
        if existing_lead:
            role = get_actor_role_for_lead(existing_lead["id"], user)
            if not _can_import_existing_lead(role):
                permission_skipped += 1
                continue
        allowed_leads.append(lead_item)

        for field in ("customer_id", "title", "owner_id", "sales_stage"):
            if not lead.get(field):
                issues.append(_issue("error", "missing_field", entity, f"Lead {field} is required"))
        if lead.get("sales_stage") and lead.get("sales_stage") not in {"New", "Assigned", "Following", "Quoted", "Won", "Lost"}:
            issues.append(_issue("error", "invalid_enum", entity, f"Invalid sales_stage: {lead.get('sales_stage')}"))
        if lead.get("service_status") and lead.get("service_status") not in {"None", "Open", "In Progress", "Resolved", "Closed"}:
            issues.append(_issue("error", "invalid_enum", entity, f"Invalid service_status: {lead.get('service_status')}"))
        if lead.get("sales_stage") in {"Quoted", "Won"} and not lead.get("currency"):
            issues.append(_issue("warning", "missing_currency", entity, "Quoted/Won lead is missing currency"))
        if lead.get("sales_stage") == "Won" and not lead.get("deal_amount"):
            issues.append(_issue("warning", "missing_amount", entity, "Won lead is missing deal_amount"))

    predicted = _predict_import_counts(import_data, allowed_leads, customer_service, lead_service)
    return {
        "preflight_time": datetime.utcnow().isoformat(),
        "source_user": import_data.get("exported_by", "unknown"),
        "source_time": import_data.get("export_time", "unknown"),
        "snapshot_before": _data_snapshot(),
        "source_snapshot": {
            "customers": len(import_data.get("customers") or {}),
            "leads": len(import_data.get("leads") or []),
        },
        "permission": {
            "allowed_leads": len(allowed_leads),
            "skipped_leads": permission_skipped,
        },
        "predicted": predicted,
        "issues": issues,
        "duplicates": duplicate_customers,
        "summary": {
            "errors": sum(1 for item in issues if item["severity"] == "error"),
            "warnings": sum(1 for item in issues if item["severity"] == "warning"),
            "duplicates": len(duplicate_customers),
        },
    }


def _predict_import_counts(
    import_data: dict,
    allowed_leads: list[dict],
    customer_service: CustomerService,
    lead_service: LeadService,
) -> dict:
    allowed_customer_ids = {item.get("lead", {}).get("customer_id") for item in allowed_leads}
    new_customers = 0
    updated_customers = 0
    for customer_id, customer in (import_data.get("customers") or {}).items():
        if customer_id not in allowed_customer_ids:
            continue
        email = customer.get("contacts", [{}])[0].get("email") if customer.get("contacts") else None
        if customer_service.match(email, customer.get("display_name")):
            updated_customers += 1
        else:
            new_customers += 1

    new_leads = 0
    updated_leads = 0
    for item in allowed_leads:
        if _find_existing_lead(lead_service.lead_repo, item.get("lead") or {}):
            updated_leads += 1
        else:
            new_leads += 1
    return {
        "new_customers": new_customers,
        "updated_customers": updated_customers,
        "new_leads": new_leads,
        "updated_leads": updated_leads,
    }


def _issue(severity: str, issue_type: str, entity: str, message: str) -> dict:
    return {
        "severity": severity,
        "type": issue_type,
        "entity": entity,
        "message": message,
    }


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower().replace(",", "").replace(".", "")


def _data_snapshot() -> dict:
    customer_repo = CustomerRepository()
    conn = customer_repo.conn
    return {
        "customers": conn.execute("SELECT COUNT(*) FROM customers WHERE archived_at IS NULL").fetchone()[0],
        "leads": conn.execute("SELECT COUNT(*) FROM leads WHERE archived_at IS NULL").fetchone()[0],
        "activities": conn.execute("SELECT COUNT(*) FROM lead_activities WHERE archived_at IS NULL").fetchone()[0],
        "attachments": conn.execute("SELECT COUNT(*) FROM attachments WHERE archived_at IS NULL").fetchone()[0],
    }


def _snapshot_delta(before: dict, after: dict) -> dict:
    return {key: int(after.get(key) or 0) - int(before.get(key) or 0) for key in set(before) | set(after)}


def _parse_audit_row(row: dict) -> dict:
    result = dict(row)
    for key in ("before_json", "after_json"):
        try:
            result[key.replace("_json", "")] = json.loads(result.get(key) or "{}")
        except json.JSONDecodeError:
            result[key.replace("_json", "")] = {}
    return result


def _find_existing_lead(lead_repo: LeadRepository, lead_data: dict) -> Optional[dict]:
    """Find an existing lead using stable cross-database identifiers only."""
    legacy_id = lead_data.get("legacy_inquiry_id")
    if legacy_id:
        return lead_repo.get_by_legacy_id(legacy_id)
    lead_id = lead_data.get("id")
    if lead_id:
        existing_by_id = lead_repo.get_by_id(lead_id)
        if existing_by_id and not existing_by_id.get("archived_at"):
            return existing_by_id
    source_lead_id = _get_source_lead_id(lead_data)
    if source_lead_id:
        return _find_lead_by_source_id(lead_repo, source_lead_id)
    return None


def _get_source_lead_id(lead_data: dict) -> Optional[str]:
    """Return the original source lead UUID carried by an export/import chain."""
    extra_json = _parse_json_object(lead_data.get("extra_json"))
    return extra_json.get("source_lead_id") or lead_data.get("id")


def _find_lead_by_source_id(lead_repo: LeadRepository, source_lead_id: str) -> Optional[dict]:
    """Find a local lead previously imported from a source lead UUID."""
    cursor = lead_repo.conn.execute(
        """
        SELECT * FROM leads
        WHERE archived_at IS NULL
          AND extra_json IS NOT NULL
        """
    )
    for row in cursor.fetchall():
        lead = dict(row)
        extra_json = _parse_json_object(lead.get("extra_json"))
        if extra_json.get("source_lead_id") == source_lead_id:
            return lead
    return None


def _sanitize_customer_data(customer_data: dict) -> dict:
    """Remove exported metadata that should not be inserted into customers."""
    data = dict(customer_data)
    for field in (
        "id",
        "contacts",
        "domains",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "row_version",
        "archived_at",
    ):
        data.pop(field, None)
    return data


def _sanitize_contact_data(contact: dict) -> dict:
    """Remove exported metadata that should not be inserted into contacts."""
    data = dict(contact)
    for field in (
        "id",
        "customer_id",
        "created_at",
        "updated_at",
        "archived_at",
    ):
        data.pop(field, None)
    return data


def _contact_signature(contact: dict) -> tuple:
    """Build a contact signature for merge detection."""
    email = (contact.get("email") or "").lower().strip()
    if email:
        return ("email", email)
    return (
        "identity",
        (contact.get("name") or "").strip().lower(),
        (contact.get("phone") or "").strip(),
    )


def _merge_contacts(
    customer_id: str,
    contacts: list,
    user_id: str,
    customer_service: CustomerService,
) -> int:
    """Merge contacts into an existing customer."""
    if not contacts:
        return 0

    existing_contacts = customer_service.customer_repo.get_contacts(customer_id)
    existing_by_signature = {
        _contact_signature(contact): contact for contact in existing_contacts
    }

    merged = 0
    for raw_contact in contacts:
        contact = _sanitize_contact_data(raw_contact)
        signature = _contact_signature(contact)
        if signature in existing_by_signature:
            existing = existing_by_signature[signature]
            update_data = {}
            for field in ("name", "position", "email", "phone", "whatsapp", "is_primary"):
                value = contact.get(field)
                if value not in (None, "") and value != existing.get(field):
                    update_data[field] = value
            if update_data:
                customer_service.update_contact(existing["id"], update_data, user_id)
                merged += 1
        else:
            contact_id = customer_service.add_contact(customer_id, contact, user_id)
            existing_by_signature[signature] = {
                **contact,
                "id": contact_id,
                "customer_id": customer_id,
            }
            merged += 1

    return merged


def _parse_json_object(value: Any) -> dict:
    """Parse a JSON object field stored as text."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _merge_extra_json(existing_value: Any, additions: dict) -> str:
    """Merge source metadata into lead.extra_json."""
    data = _parse_json_object(existing_value)
    data.update({k: v for k, v in additions.items() if v is not None})
    return json.dumps(data, ensure_ascii=False)


def _merge_payload_source(payload_json: Any, source_id: Optional[str]) -> Optional[str]:
    """Attach source activity metadata without losing the original payload."""
    payload = _parse_json_object(payload_json)
    if not payload and isinstance(payload_json, str) and payload_json.strip():
        payload = {"raw_payload": payload_json}
    if source_id:
        payload.setdefault("source_activity_id", source_id)
    return json.dumps(payload, ensure_ascii=False) if payload else None


def _activity_signature(activity: dict) -> tuple:
    """Build a stable activity signature for deduplication."""
    payload = _parse_json_object(activity.get("payload_json"))
    source_id = payload.get("source_activity_id") or activity.get("id")
    if source_id:
        return ("source", source_id)
    return (
        "content",
        activity.get("created_at"),
        activity.get("actor_id"),
        activity.get("action_type", ""),
        activity.get("summary", ""),
        json.dumps(payload, sort_keys=True, ensure_ascii=False),
        activity.get("changed_field"),
        activity.get("before_value"),
        activity.get("after_value"),
    )


def _is_recreated_system_activity(activity: dict) -> bool:
    """LeadService.create already records this local system event for new imports."""
    return (
        activity.get("action_type") == "system"
        and activity.get("summary") == "Lead created"
    )


def _resolve_user_id(user_repo: UserRepository, candidate_id: Optional[str], fallback_id: str) -> str:
    """Use imported user references only when they exist locally."""
    if candidate_id and user_repo.get_by_id(candidate_id):
        return candidate_id
    return fallback_id


def _merge_activities(lead_id: str, activities: list, user_id: str) -> int:
    """Merge activities into a lead, avoiding source and content duplicates.

    Returns the number of activities added.
    """
    if not activities:
        return 0

    activity_repo = ActivityRepository()
    user_repo = UserRepository()
    existing_activities = activity_repo.list_all_for_lead(lead_id)

    # Build a set of existing activity signatures for deduplication
    existing_signatures = set()
    for act in existing_activities:
        existing_signatures.add(_activity_signature(act))

    added = 0
    for activity in activities:
        if _is_recreated_system_activity(activity):
            continue

        sig = _activity_signature(activity)

        # Skip if this activity already exists
        if sig in existing_signatures:
            continue

        activity_repo.create(
            lead_id=lead_id,
            actor_id=_resolve_user_id(user_repo, activity.get("actor_id"), user_id),
            action_type=activity.get("action_type", "comment"),
            summary=activity.get("summary", ""),
            payload_json=_merge_payload_source(activity.get("payload_json"), activity.get("id")),
            visibility=activity.get("visibility", "all"),
            is_formal_follow_up=activity.get("is_formal_follow_up", False),
            changed_field=activity.get("changed_field"),
            before_value=activity.get("before_value"),
            after_value=activity.get("after_value"),
            created_at=activity.get("created_at"),
        )
        existing_signatures.add(sig)
        added += 1

    return added


def _task_signature(task: dict) -> tuple:
    """Build a stable after-sales task signature for deduplication."""
    return (
        task.get("created_at"),
        task.get("assignee_id"),
        task.get("issue_type", ""),
        task.get("issue_description", ""),
    )


def _merge_after_sales_tasks(lead_id: str, tasks: list, user_id: str) -> int:
    """Merge after-sales tasks into a lead, avoiding timestamp/content duplicates.

    Returns the number of tasks added.
    """
    if not tasks:
        return 0

    after_sales_repo = AfterSalesTaskRepository()
    user_repo = UserRepository()
    existing_tasks = after_sales_repo.list_for_lead(lead_id)

    # Build a set of existing task signatures for deduplication
    existing_signatures = set()
    for task in existing_tasks:
        existing_signatures.add(_task_signature(task))

    added = 0
    for task in tasks:
        sig = _task_signature(task)

        # Skip if this task already exists
        if sig in existing_signatures:
            continue

        task_data = {
            'assignee_id': _resolve_user_id(user_repo, task.get("assignee_id"), user_id),
            'issue_type': task.get("issue_type", "Other"),
            'status': task.get("status", "Open"),
            'issue_description': task.get("issue_description", ""),
            'solution': task.get("solution"),
            'due_date': task.get("due_date")
        }

        after_sales_repo.create(
            lead_id,
            task_data,
            user_id,
            created_at=task.get("created_at"),
            updated_at=task.get("updated_at"),
        )
        existing_signatures.add(sig)
        added += 1

    return added
