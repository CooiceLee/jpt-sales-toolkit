#!/usr/bin/env python3
"""
Import Excel data from 欧洲小分队进度记录.xlsx into JPT Sales Toolkit.

This script:
1. Creates users (sales team members)
2. Imports customers (deduplicated by name)
3. Imports leads from all 4 sheets
4. Creates pre_sales_tasks and after_sales_tasks
5. Generates a redundancy report
"""

import json
import os
import re
import sqlite3
import sys
import uuid
import zipfile
import xml.etree.ElementTree as ET
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Configuration
XLSX_EXTRACTED_PATH = "/tmp/xlsx_extract"
DEFAULT_XLSX_PATH = "/Users/liliang/Desktop/欧洲小分队进度记录 (1).xlsx"
DEFAULT_DB_PATH = "/Users/liliang/Desktop/jpt-sales-toolkit/data/jpt_v2.db"
DEFAULT_REPORT_PATH = "/Users/liliang/Desktop/jpt-sales-toolkit/data/import_report_excel.md"
XLSX_PATH = DEFAULT_XLSX_PATH
DB_PATH = DEFAULT_DB_PATH
REPORT_PATH = DEFAULT_REPORT_PATH

# XML namespace
NS = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

# User mapping: name -> (role, normalized_name)
USER_MAPPING = {
    'stanley': ('sales', 'Stanley'),
    'william': ('sales', 'William'),
    'milena': ('sales', 'Milena'),
    'hannah': ('sales', 'Hannah'),
    'lulu': ('leader', 'Lulu'),
    'ayden': ('tech', 'Ayden'),
    'aydenl lin': ('tech', 'Ayden'),
    'ayden lin': ('tech', 'Ayden'),
    'eric': ('tech', 'Eric'),
    'neil': ('tech', 'Neil'),
    'neil zhu': ('tech', 'Neil'),
    'gia': ('sales', 'Gia'),
    'ren': ('sales', 'Ren'),
    'slluu': ('sales', 'Slluu'),
}

# Global state
shared_strings = []
users_cache = {}  # normalized_name -> user_id
customers_cache = {}  # normalized_name -> customer_id
redundancy_log = []
owner_resolution_log = []


def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def gen_id():
    return str(uuid.uuid4())


def normalize_name(name: str) -> str:
    """Normalize company/customer name for deduplication."""
    if not name:
        return ""
    return re.sub(r'\s+', ' ', name.strip().lower())


def parse_date(value) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD."""
    if not value:
        return None
    value = str(value).strip()

    # Excel serial date (e.g., 45742)
    if value.isdigit() and len(value) == 5:
        try:
            serial = int(value)
            # Excel epoch: 1899-12-30
            base = datetime(1899, 12, 30)
            dt = base + timedelta(days=serial)
            return dt.strftime("%Y-%m-%d")
        except:
            pass

    # YYYYMMDD format
    if re.match(r'^\d{8}$', value):
        try:
            return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
        except:
            pass

    # YYYY.M.D or YYYY.MM.DD format
    m = re.match(r'^(\d{4})\.(\d{1,2})\.(\d{1,2})$', value)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"

    # M.DD format (assume current year)
    m = re.match(r'^(\d{1,2})\.(\d{1,2})$', value)
    if m:
        year = datetime.now().year
        return f"{year}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"

    # Already in YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return value

    return None


def parse_quality_grade(value: str) -> Optional[str]:
    """Map 低/中/高 to A/B/C/D."""
    if not value:
        return None
    value = value.strip().lower()
    mapping = {
        '高': 'A',
        '中': 'B',
        '低': 'D',
        'high': 'A',
        'medium': 'B',
        'low': 'D',
    }
    return mapping.get(value)


def load_shared_strings():
    """Load shared strings from xlsx."""
    global shared_strings
    shared_strings = []
    ss_tree = ET.parse(f"{XLSX_EXTRACTED_PATH}/xl/sharedStrings.xml")
    ss_root = ss_tree.getroot()

    for si in ss_root.findall('.//main:si', NS):
        text_parts = []
        for t in si.findall('.//main:t', NS):
            if t.text:
                text_parts.append(t.text)
        shared_strings.append(''.join(text_parts))


def col_to_idx(col_str: str) -> int:
    """Convert Excel column (A, B, AA) to 0-based index."""
    result = 0
    for c in col_str:
        result = result * 26 + (ord(c.upper()) - ord('A') + 1)
    return result - 1


def parse_sheet(sheet_num: int) -> list:
    """Parse a worksheet and return rows as list of lists."""
    tree = ET.parse(f"{XLSX_EXTRACTED_PATH}/xl/worksheets/sheet{sheet_num}.xml")
    root = tree.getroot()

    rows_data = {}
    for row in root.findall('.//main:row', NS):
        row_num = int(row.get('r'))
        cells = {}
        for cell in row.findall('main:c', NS):
            cell_ref = cell.get('r')
            col_match = re.match(r'([A-Z]+)', cell_ref)
            if col_match:
                col_idx = col_to_idx(col_match.group(1))
                cell_type = cell.get('t')
                value_elem = cell.find('main:v', NS)
                if value_elem is not None and value_elem.text:
                    if cell_type == 's':
                        cells[col_idx] = shared_strings[int(value_elem.text)]
                    else:
                        cells[col_idx] = value_elem.text
        if cells:
            rows_data[row_num] = cells

    if not rows_data:
        return []

    max_row = max(rows_data.keys())
    max_col = max(max(cells.keys()) for cells in rows_data.values() if cells) + 1

    result = []
    for r in range(1, max_row + 1):
        row_cells = rows_data.get(r, {})
        row_list = [row_cells.get(c, '') for c in range(max_col)]
        result.append(row_list)
    return result


def is_example_row(row: list) -> bool:
    """Check if row is an example/template row."""
    first_cell = str(row[0]).strip().lower() if row else ''
    return (
        first_cell in ('举例', '举例：', 'example')
        or first_cell.startswith('1.打比方')
        or first_cell.startswith('2.如果')
        or first_cell.startswith('3.售前')
    )


def extract_xlsx(xlsx_path: str = XLSX_PATH):
    """Extract the source workbook into a fresh temp directory."""
    extracted = Path(XLSX_EXTRACTED_PATH)
    if extracted.exists():
        for item in extracted.iterdir():
            if item.is_dir():
                import shutil
                shutil.rmtree(item)
            else:
                item.unlink()
    else:
        extracted.mkdir(parents=True)

    with zipfile.ZipFile(xlsx_path) as zf:
        zf.extractall(extracted)


def lead_source_exists(conn: sqlite3.Connection, sheet_name: str, row_idx: int) -> bool:
    """Return True when this Excel source row has already been imported."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM leads
        WHERE json_extract(extra_json, '$.source_sheet') = ?
          AND CAST(json_extract(extra_json, '$.source_row') AS INTEGER) = ?
        LIMIT 1
        """,
        (sheet_name, row_idx),
    )
    return cursor.fetchone() is not None


def create_users(conn: sqlite3.Connection):
    """Create user accounts."""
    global users_cache
    cursor = conn.cursor()

    # Check existing users
    cursor.execute("SELECT id, display_name FROM users")
    for uid, name in cursor.fetchall():
        users_cache[name] = uid

    # Users to create
    users_to_create = {
        'Stanley': 'sales',
        'William': 'sales',
        'Milena': 'sales',
        'Hannah': 'sales',
        'Lulu': 'leader',
        'Ayden': 'tech',
        'Eric': 'tech',
        'Neil': 'tech',
        'Gia': 'sales',
        'Ren': 'sales',
        'Slluu': 'sales',
    }

    now = now_iso()
    created_count = 0

    for display_name, role in users_to_create.items():
        if display_name in users_cache:
            continue

        user_id = gen_id()
        username = display_name.lower()

        # Simple password hash (in real system would use bcrypt)
        password_hash = f"pbkdf2:sha256:mock${username}"

        cursor.execute("""
            INSERT INTO users (id, username, password_hash, display_name, role, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (user_id, username, password_hash, display_name, role, now))

        users_cache[display_name] = user_id
        created_count += 1

    conn.commit()
    print(f"Created {created_count} users, total {len(users_cache)} users in cache")
    return created_count


def fallback_owner_id() -> Optional[str]:
    """Return the default owner for unresolved legacy rows."""
    return users_cache.get('Lulu') or next(iter(users_cache.values()), None)


def resolve_user_id(name_str: str) -> Optional[str]:
    """Resolve user name to user_id."""
    if not name_str:
        return None

    raw = str(name_str).strip()
    normalized_raw = re.sub(r'\s+', ' ', raw).strip().lower()

    if normalized_raw in USER_MAPPING:
        _, normalized = USER_MAPPING[normalized_raw]
        return users_cache.get(normalized)

    # Handle multiple names and cells accidentally containing tab-separated
    # columns, e.g. "Ren/Ayden/Gia" or "Gia\t100%\t已发货".
    names = [part.strip().lower() for part in re.split(r'[/,、&+＋\t\r\n]+', raw) if part.strip()]
    for name in names:
        if name in USER_MAPPING:
            _, normalized = USER_MAPPING[name]
            return users_cache.get(normalized)

    for cached_name, uid in users_cache.items():
        if cached_name.lower() == normalized_raw:
            return uid

    return None


def resolve_owner_id(name_str: str, sheet_name: str, row_idx: int) -> Optional[str]:
    """Resolve owner and record rows that need manual owner review."""
    user_id = resolve_user_id(name_str)
    if user_id:
        return user_id

    owner_resolution_log.append({
        'sheet': sheet_name,
        'row': row_idx,
        'owner': str(name_str).strip() if name_str else '',
        'fallback': 'Lulu',
    })
    return fallback_owner_id()


def get_or_create_customer(conn: sqlite3.Connection, name: str, country: str = None,
                           city: str = None, industry: str = None,
                           company_size: str = None) -> Optional[str]:
    """Get existing customer or create new one."""
    global customers_cache

    if not name or name.strip() in ('', '无', '/', '？', '个人'):
        return None

    name = name.strip()
    normalized = normalize_name(name)

    if normalized in customers_cache:
        return customers_cache[normalized]

    cursor = conn.cursor()

    # Check if exists
    cursor.execute("SELECT id FROM customers WHERE normalized_name = ?", (normalized,))
    row = cursor.fetchone()
    if row:
        customers_cache[normalized] = row[0]
        return row[0]

    # Create new customer
    customer_id = gen_id()
    now = now_iso()

    cursor.execute("""
        INSERT INTO customers (
            id, display_name, normalized_name, country, city, industry,
            company_size, created_at, updated_at, row_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (customer_id, name, normalized, country, city, industry, company_size, now, now))

    customers_cache[normalized] = customer_id
    return customer_id


def create_contact(conn: sqlite3.Connection, customer_id: str, name: str,
                   contact_method: str = None, position: str = None) -> Optional[str]:
    """Create customer contact."""
    if not customer_id or not name or name.strip() in ('', '/', '？'):
        return None

    cursor = conn.cursor()
    contact_id = gen_id()
    now = now_iso()

    email = None
    phone = None
    if contact_method:
        if '@' in contact_method:
            email = contact_method
        elif contact_method not in ('邮件', '微信', '微信&邮件', '1'):
            phone = contact_method

    try:
        cursor.execute("""
            INSERT INTO customer_contacts (
                id, customer_id, name, position, email, phone, is_primary, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (contact_id, customer_id, name.strip(), position, email, phone, now, now))
        return contact_id
    except sqlite3.IntegrityError:
        # Contact already exists
        return None


def generate_display_id(conn: sqlite3.Connection) -> str:
    """Generate unique display_id for lead."""
    cursor = conn.cursor()
    period = datetime.now().strftime("%Y%m")

    cursor.execute("""
        INSERT INTO display_sequences (period_ym, next_value)
        VALUES (?, 1)
        ON CONFLICT(period_ym) DO UPDATE SET next_value = next_value + 1
    """, (period,))
    cursor.execute("SELECT next_value FROM display_sequences WHERE period_ym = ?", (period,))
    seq = cursor.fetchone()[0]

    return f"L{period}-{seq:04d}"


def import_sheet1_opportunities(conn: sqlite3.Connection, data: list) -> dict:
    """Import Sheet 1: 潜在商业机会."""
    sheet_name = '潜在商业机会'
    stats = {'leads': 0, 'customers': 0, 'contacts': 0, 'existing': 0, 'skipped': 0}
    cursor = conn.cursor()
    now = now_iso()

    # Skip header row
    for row_idx, row in enumerate(data[1:], 2):
        if is_example_row(row) or not any(row):
            stats['skipped'] += 1
            continue

        # Parse row
        seq = row[0] if len(row) > 0 else ''
        biz_name = row[1] if len(row) > 1 else ''
        biz_desc = row[2] if len(row) > 2 else ''
        customer_name = row[3] if len(row) > 3 else ''
        contact_name = row[4] if len(row) > 4 else ''
        country = row[5] if len(row) > 5 else ''
        city = row[6] if len(row) > 6 else ''
        contact_method = row[7] if len(row) > 7 else ''
        industry = row[8] if len(row) > 8 else ''
        scale = row[9] if len(row) > 9 else ''
        first_contact = row[10] if len(row) > 10 else ''
        owner_name = row[11] if len(row) > 11 else ''
        last_followup = row[12] if len(row) > 12 else ''
        next_plan = row[13] if len(row) > 13 else ''
        conversion_rate = row[15] if len(row) > 15 else ''
        remarks = row[16] if len(row) > 16 else ''

        if not customer_name or not biz_name:
            stats['skipped'] += 1
            continue

        # Get or create customer
        customer_id = get_or_create_customer(
            conn, customer_name, country, city, industry, scale
        )
        if not customer_id:
            stats['skipped'] += 1
            redundancy_log.append({
                'sheet': sheet_name,
                'row': row_idx,
                'reason': f'Invalid customer: {customer_name}',
                'data': row[:5]
            })
            continue

        if lead_source_exists(conn, sheet_name, row_idx):
            stats['existing'] += 1
            continue

        stats['customers'] += 1

        # Create contact
        if contact_name:
            if create_contact(conn, customer_id, contact_name, contact_method):
                stats['contacts'] += 1

        # Create lead
        lead_id = gen_id()
        display_id = generate_display_id(conn)
        owner_id = resolve_owner_id(owner_name, sheet_name, row_idx)

        inquiry_date = parse_date(first_contact)
        quality = parse_quality_grade(conversion_rate)

        # Determine sales_stage from remarks
        sales_stage = 'Following'
        if remarks and ('已关闭' in remarks or '关闭' in remarks):
            sales_stage = 'Lost'
        elif remarks and '已下单' in remarks:
            sales_stage = 'Won'
        elif next_plan and ('报价' in next_plan or '已报价' in next_plan):
            sales_stage = 'Quoted'

        extra = {
            'original_seq': seq,
            'description': biz_desc,
            'quantity': scale,
            'next_plan': next_plan,
            'remarks': remarks,
            'source_sheet': sheet_name,
            'source_row': row_idx,
        }

        cursor.execute("""
            INSERT INTO leads (
                id, display_id, customer_id, title, owner_id, sales_stage,
                quality_grade, application, inquiry_date, next_followup_date,
                extra_json, created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            lead_id, display_id, customer_id, biz_name, owner_id, sales_stage,
            quality, biz_desc, inquiry_date, parse_date(last_followup),
            json.dumps(extra, ensure_ascii=False), now, owner_id, now, owner_id
        ))

        stats['leads'] += 1

    conn.commit()
    return stats


def import_sheet2_presales(conn: sqlite3.Connection, data: list) -> dict:
    """Import Sheet 2: 售前（技术问题）."""
    sheet_name = '售前（技术问题）'
    stats = {'leads': 0, 'tasks': 0, 'existing': 0, 'skipped': 0}
    cursor = conn.cursor()
    now = now_iso()

    for row_idx, row in enumerate(data[1:], 2):
        if is_example_row(row) or not any(row):
            stats['skipped'] += 1
            continue

        seq = row[0] if len(row) > 0 else ''
        biz_name = row[1] if len(row) > 1 else ''
        biz_detail = row[2] if len(row) > 2 else ''
        customer_name = row[3] if len(row) > 3 else ''
        contact_name = row[4] if len(row) > 4 else ''
        contact_method = row[5] if len(row) > 5 else ''
        decision_maker = row[6] if len(row) > 6 else ''
        scale = row[7] if len(row) > 7 else ''
        start_date = row[8] if len(row) > 8 else ''
        expected_close = row[9] if len(row) > 9 else ''
        owner_name = row[10] if len(row) > 10 else ''
        competitor = row[11] if len(row) > 11 else ''
        key_points = row[12] if len(row) > 12 else ''
        concerns = row[13] if len(row) > 13 else ''
        progress = row[14] if len(row) > 14 else ''
        next_action = row[15] if len(row) > 15 else ''

        if not customer_name:
            stats['skipped'] += 1
            continue

        if lead_source_exists(conn, sheet_name, row_idx):
            stats['existing'] += 1
            continue

        # Get or create customer
        customer_id = get_or_create_customer(conn, customer_name)
        if not customer_id:
            stats['skipped'] += 1
            continue

        # Create contact if decision maker specified
        if decision_maker and decision_maker not in ('', '/', '？'):
            create_contact(conn, customer_id, decision_maker, None, 'Decision Maker')

        # Create lead
        lead_id = gen_id()
        display_id = generate_display_id(conn)
        owner_id = resolve_owner_id(owner_name, sheet_name, row_idx)

        title = biz_name if biz_name else f"售前支持 - {customer_name}"

        extra = {
            'original_seq': seq,
            'description': biz_detail,
            'quantity': scale,
            'competitor': competitor,
            'key_points': key_points,
            'concerns': concerns,
            'expected_close_date': parse_date(expected_close),
            'source_sheet': sheet_name,
            'source_row': row_idx,
        }

        cursor.execute("""
            INSERT INTO leads (
                id, display_id, customer_id, title, owner_id, sales_stage,
                application, inquiry_date, extra_json,
                created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, 'Quoted', ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            lead_id, display_id, customer_id, title, owner_id,
            biz_detail, parse_date(start_date), json.dumps(extra, ensure_ascii=False),
            now, owner_id, now, owner_id
        ))
        stats['leads'] += 1

        # Create pre_sales_task
        task_id = gen_id()
        tech_id = resolve_user_id('ayden') or owner_id

        # Determine status from progress/next_action
        task_status = 'In Progress'
        if next_action and ('完结' in next_action or '已完成' in next_action or '已下单' in next_action):
            task_status = 'Completed'
        elif progress == '1':
            task_status = 'Completed'

        request_json = {
            'description': biz_detail,
            'key_points': key_points,
            'concerns': concerns,
        }
        result_json = {
            'progress': progress,
            'next_action': next_action,
        }

        cursor.execute("""
            INSERT INTO pre_sales_tasks (
                id, lead_id, assignee_id, status, request_json, result_json,
                created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            task_id, lead_id, tech_id, task_status,
            json.dumps(request_json, ensure_ascii=False),
            json.dumps(result_json, ensure_ascii=False),
            now, owner_id, now, owner_id
        ))
        stats['tasks'] += 1

    conn.commit()
    return stats


def import_sheet3_won(conn: sqlite3.Connection, data: list) -> dict:
    """Import Sheet 3: 赢单."""
    sheet_name = '赢单'
    stats = {'leads': 0, 'existing': 0, 'skipped': 0}
    cursor = conn.cursor()
    now = now_iso()

    for row_idx, row in enumerate(data[1:], 2):
        if is_example_row(row) or not any(row):
            stats['skipped'] += 1
            continue

        seq = row[0] if len(row) > 0 else ''
        biz_name = row[1] if len(row) > 1 else ''
        contract_content = row[2] if len(row) > 2 else ''
        quantity = row[3] if len(row) > 3 else ''
        customer_name = row[4] if len(row) > 4 else ''
        contact_name = row[5] if len(row) > 5 else ''
        contact_method = row[6] if len(row) > 6 else ''
        contract_amount = row[7] if len(row) > 7 else ''
        contract_date = row[8] if len(row) > 8 else ''
        start_date = row[9] if len(row) > 9 else ''
        contract_period = row[10] if len(row) > 10 else ''
        owner_name = row[11] if len(row) > 11 else ''
        progress = row[12] if len(row) > 12 else ''
        feedback = row[13] if len(row) > 13 else ''
        issues = row[14] if len(row) > 14 else ''
        measures = row[15] if len(row) > 15 else ''
        next_plan = row[16] if len(row) > 16 else ''
        remarks = row[17] if len(row) > 17 else ''

        if not customer_name:
            stats['skipped'] += 1
            continue

        if lead_source_exists(conn, sheet_name, row_idx):
            stats['existing'] += 1
            continue

        # Get or create customer
        customer_id = get_or_create_customer(conn, customer_name)
        if not customer_id:
            stats['skipped'] += 1
            continue

        # Create contact
        if contact_name and contact_name not in ('/', '？'):
            create_contact(conn, customer_id, contact_name, contact_method)

        # Create lead
        lead_id = gen_id()
        display_id = generate_display_id(conn)
        owner_id = resolve_owner_id(owner_name, sheet_name, row_idx)

        title = biz_name if biz_name else f"赢单 - {contract_content}"

        # Parse deal amount
        deal_amount = None
        if contract_amount and contract_amount not in ('/', '？', ''):
            try:
                deal_amount = float(re.sub(r'[^\d.]', '', contract_amount))
            except:
                pass

        # Determine fulfillment status from M column (合同执行进度)
        # "1" = 100% = Completed
        # "" or empty = 0% = Not Started
        # Other text like "货好就发" = In Progress
        fulfillment = 'Not Started'
        if progress == '1':
            fulfillment = 'Completed'
        elif progress and progress not in ('', '0'):
            # Any non-empty, non-zero value means in progress
            fulfillment = 'In Progress'
        # Override by next_plan if explicitly says shipped
        if next_plan and '已发货' in next_plan:
            fulfillment = 'Completed'

        extra = {
            'original_seq': seq,
            'contract_content': contract_content,
            'quantity': quantity,
            'contract_period': contract_period,
            'feedback': feedback,
            'issues': issues,
            'measures': measures,
            'next_plan': next_plan,
            'remarks': remarks,
            'source_sheet': sheet_name,
            'source_row': row_idx,
        }

        cursor.execute("""
            INSERT INTO leads (
                id, display_id, customer_id, title, owner_id, sales_stage,
                fulfillment_status, product_series, deal_amount, po_date,
                extra_json, created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, 'Won', ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            lead_id, display_id, customer_id, title, owner_id,
            fulfillment, contract_content, deal_amount, parse_date(contract_date),
            json.dumps(extra, ensure_ascii=False), now, owner_id, now, owner_id
        ))
        stats['leads'] += 1

    conn.commit()
    return stats


def import_sheet4_aftersales(conn: sqlite3.Connection, data: list) -> dict:
    """Import Sheet 4: 售后."""
    sheet_name = '售后'
    stats = {'leads': 0, 'tasks': 0, 'existing': 0, 'skipped': 0}
    cursor = conn.cursor()
    now = now_iso()

    for row_idx, row in enumerate(data[1:], 2):
        if is_example_row(row) or not any(row):
            stats['skipped'] += 1
            continue

        seq = row[0] if len(row) > 0 else ''
        biz_name = row[1] if len(row) > 1 else ''
        issue_content = row[2] if len(row) > 2 else ''
        customer_name = row[3] if len(row) > 3 else ''
        contact_name = row[4] if len(row) > 4 else ''
        contact_method = row[5] if len(row) > 5 else ''
        owner_name = row[6] if len(row) > 6 else ''
        progress = row[7] if len(row) > 7 else ''
        satisfaction = row[8] if len(row) > 8 else ''
        lessons = row[9] if len(row) > 9 else ''
        remarks = row[10] if len(row) > 10 else ''

        if not customer_name:
            stats['skipped'] += 1
            continue

        if lead_source_exists(conn, sheet_name, row_idx):
            stats['existing'] += 1
            continue

        # Get or create customer
        customer_id = get_or_create_customer(conn, customer_name)
        if not customer_id:
            stats['skipped'] += 1
            continue

        # Create lead (Won with service status)
        lead_id = gen_id()
        display_id = generate_display_id(conn)
        owner_id = resolve_owner_id(owner_name, sheet_name, row_idx)

        title = biz_name if biz_name else f"售后 - {issue_content[:30]}"

        # Determine service status
        service_status = 'Open'
        if progress and ('完结' in progress or '已完成' in progress or '已修好' in progress):
            service_status = 'Resolved'
        elif progress and '进行' in progress:
            service_status = 'In Progress'

        extra = {
            'original_seq': seq,
            'issue_content': issue_content,
            'satisfaction': satisfaction,
            'lessons': lessons,
            'remarks': remarks,
            'source_sheet': sheet_name,
            'source_row': row_idx,
        }

        cursor.execute("""
            INSERT INTO leads (
                id, display_id, customer_id, title, owner_id, sales_stage,
                service_status, extra_json,
                created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, 'Won', ?, ?, ?, ?, ?, ?, 1)
        """, (
            lead_id, display_id, customer_id, title, owner_id,
            service_status, json.dumps(extra, ensure_ascii=False),
            now, owner_id, now, owner_id
        ))
        stats['leads'] += 1

        # Create after_sales_task
        task_id = gen_id()
        tech_id = resolve_user_id(owner_name) or owner_id

        # Determine task status
        task_status = 'Open'
        if progress and ('完结' in progress or '已完成' in progress or '已修好' in progress):
            task_status = 'Resolved'
        elif progress and '进行' in progress:
            task_status = 'In Progress'

        # Determine issue type
        issue_type = 'Technical'
        if issue_content:
            if '运输' in issue_content or '损坏' in issue_content:
                issue_type = 'Delivery'
            elif '品质' in issue_content:
                issue_type = 'Quality'

        cursor.execute("""
            INSERT INTO after_sales_tasks (
                id, lead_id, assignee_id, issue_type, status, issue_description, solution,
                created_at, created_by, updated_at, updated_by, row_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            task_id, lead_id, tech_id, issue_type, task_status,
            issue_content, f"Progress: {progress}\nLessons: {lessons}",
            now, owner_id, now, owner_id
        ))
        stats['tasks'] += 1

    conn.commit()
    return stats


def database_counts() -> dict:
    """Return current database totals for report clarity."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    tables = ["users", "customers", "leads", "customer_contacts", "pre_sales_tasks", "after_sales_tasks"]
    counts = {}
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cursor.fetchone()[0]
    conn.close()
    return counts


def generate_report(all_stats: dict):
    """Generate import report."""
    counts = database_counts()
    db_dir = Path(DB_PATH).resolve().parent
    backup_dir = db_dir / "backups"
    report = f"""# Excel 数据导入报告

生成时间: {now_iso()}
目标数据库: `{DB_PATH}`

## 导入统计

| Sheet | New Leads | Existing Rows | Customers | Contacts | Tasks | Skipped |
|-------|-----------|---------------|-----------|----------|-------|---------|
| 潜在商业机会 | {all_stats['sheet1']['leads']} | {all_stats['sheet1']['existing']} | {all_stats['sheet1']['customers']} | {all_stats['sheet1']['contacts']} | - | {all_stats['sheet1']['skipped']} |
| 售前（技术问题） | {all_stats['sheet2']['leads']} | {all_stats['sheet2']['existing']} | - | - | {all_stats['sheet2']['tasks']} | {all_stats['sheet2']['skipped']} |
| 赢单 | {all_stats['sheet3']['leads']} | {all_stats['sheet3']['existing']} | - | - | - | {all_stats['sheet3']['skipped']} |
| 售后 | {all_stats['sheet4']['leads']} | {all_stats['sheet4']['existing']} | - | - | {all_stats['sheet4']['tasks']} | {all_stats['sheet4']['skipped']} |

## 用户创建

创建了 {all_stats['users']} 个用户账户。

## 客户去重

本次导入过程解析到 {len(customers_cache)} 个客户名称（已存在或新建，按名称去重）。

## 当前数据库总量

| 类型 | 数量 |
|------|------|
| 用户 | {counts['users']} |
| 客户 | {counts['customers']} |
| Lead | {counts['leads']} |
| 联系人 | {counts['customer_contacts']} |
| 售前任务 | {counts['pre_sales_tasks']} |
| 售后任务 | {counts['after_sales_tasks']} |

## 冗余信息记录

以下字段已存入 `extra_json`，可后续手动处理：

- `description`: 业务内容简述/详述
- `quantity`: 业务规模/数量
- `competitor`: 竞争对手情况
- `key_points`: 当前赢单要点
- `concerns`: 客户顾虑/关注点
- `lessons`: 经验教训
- `feedback`: 客户反馈
- `issues`: 存在问题
- `measures`: 应对措施
- `remarks`: 备注

## 跳过的记录

"""
    if redundancy_log:
        report += "| Sheet | Row | Reason | Preview |\n|-------|-----|--------|--------|\n"
        for item in redundancy_log[:50]:
            preview = str(item['data'])[:50].replace('|', '\\|')
            report += f"| {item['sheet']} | {item['row']} | {item['reason']} | {preview} |\n"
        if len(redundancy_log) > 50:
            report += f"\n... 还有 {len(redundancy_log) - 50} 条记录 ...\n"
    else:
        report += "无跳过记录。\n"

    report += "\n## 负责人解析待确认\n\n"
    if owner_resolution_log:
        report += "| Sheet | Row | Original Owner | Fallback Owner |\n|-------|-----|----------------|----------------|\n"
        for item in owner_resolution_log[:50]:
            owner = item['owner'].replace('|', '\\|')
            report += f"| {item['sheet']} | {item['row']} | {owner or '(blank)'} | {item['fallback']} |\n"
        if len(owner_resolution_log) > 50:
            report += f"\n... 还有 {len(owner_resolution_log) - 50} 条负责人待确认 ...\n"
    else:
        report += "所有非空负责人均已解析到系统用户。\n"

    report += f"""

## 后续操作建议

1. **验证数据**: 登录系统检查导入的数据是否正确
2. **补充信息**: 部分客户缺少国家/城市信息，可手动补充
3. **合并重复**: 如有客户名称变体（如 VJT/VJSH），可考虑手动合并
4. **调整阶段**: 根据实际情况调整 Lead 的 sales_stage

---

数据库目录: `{db_dir}`
备份目录: `{backup_dir}`
"""

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\nReport saved to: {REPORT_PATH}")


def main():
    global XLSX_PATH, DB_PATH, REPORT_PATH

    parser = argparse.ArgumentParser(description="Import Excel data into a target JPT database")
    parser.add_argument(
        "--xlsx-path",
        default=DEFAULT_XLSX_PATH,
        help="Path to the source Excel workbook.",
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="Path to the target SQLite database file.",
    )
    parser.add_argument(
        "--data-dir",
        help="Target data directory. If provided, database path becomes <data-dir>/database.sqlite.",
    )
    parser.add_argument(
        "--report-path",
        help="Optional markdown report output path. Defaults to <db dir>/import_report_excel.md.",
    )
    args = parser.parse_args()

    XLSX_PATH = str(Path(args.xlsx_path).expanduser().resolve())
    if args.data_dir:
        data_dir = Path(args.data_dir).expanduser().resolve()
        DB_PATH = str(data_dir / "database.sqlite")
        REPORT_PATH = str((data_dir / "import_report_excel.md").resolve())
    else:
        DB_PATH = str(Path(args.db_path).expanduser().resolve())
        REPORT_PATH = str((Path(DB_PATH).resolve().parent / "import_report_excel.md").resolve())
    if args.report_path:
        REPORT_PATH = str(Path(args.report_path).expanduser().resolve())

    print("=" * 60)
    print("Excel Data Import for JPT Sales Toolkit")
    print("=" * 60)
    print(f"Workbook: {XLSX_PATH}")
    print(f"Target DB: {DB_PATH}")
    print(f"Report:   {REPORT_PATH}")

    # Load shared strings
    print("\n[1/6] Loading Excel data...")
    extract_xlsx(XLSX_PATH)
    load_shared_strings()
    print(f"Loaded {len(shared_strings)} shared strings")

    # Parse all sheets
    sheet1 = parse_sheet(1)
    sheet2 = parse_sheet(2)
    sheet3 = parse_sheet(3)
    sheet4 = parse_sheet(4)
    print(f"Sheet sizes: {len(sheet1)}, {len(sheet2)}, {len(sheet3)}, {len(sheet4)}")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    all_stats = {}

    # Create users
    print("\n[2/6] Creating users...")
    all_stats['users'] = create_users(conn)

    # Import Sheet 1
    print("\n[3/6] Importing 潜在商业机会...")
    all_stats['sheet1'] = import_sheet1_opportunities(conn, sheet1)
    print(f"  Leads: {all_stats['sheet1']['leads']}, Skipped: {all_stats['sheet1']['skipped']}")

    # Import Sheet 2
    print("\n[4/6] Importing 售前（技术问题）...")
    all_stats['sheet2'] = import_sheet2_presales(conn, sheet2)
    print(f"  Leads: {all_stats['sheet2']['leads']}, Tasks: {all_stats['sheet2']['tasks']}")

    # Import Sheet 3
    print("\n[5/6] Importing 赢单...")
    all_stats['sheet3'] = import_sheet3_won(conn, sheet3)
    print(f"  Leads: {all_stats['sheet3']['leads']}")

    # Import Sheet 4
    print("\n[6/6] Importing 售后...")
    all_stats['sheet4'] = import_sheet4_aftersales(conn, sheet4)
    print(f"  Leads: {all_stats['sheet4']['leads']}, Tasks: {all_stats['sheet4']['tasks']}")

    conn.close()

    # Generate report
    generate_report(all_stats)

    print("\n" + "=" * 60)
    print("Import completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
