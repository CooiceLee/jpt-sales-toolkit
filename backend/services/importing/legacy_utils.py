"""Business-safe normalization helpers shared by legacy sheet adapters."""

from __future__ import annotations

import re
from typing import Any, Optional

from .dates import parse_excel_date
from .keys import clean_text
from .models import Row, Workbook


def text(row: Row, column: int) -> str:
    return clean_text(row.value(column))


def date_value(workbook: Workbook, row: Row, column: int) -> tuple[Optional[str], str, str]:
    return parse_excel_date(row.cell(column), workbook.date_1904)


def quality_grade(raw: Any) -> Optional[str]:
    value = clean_text(raw).casefold()
    return {"高": "A", "high": "A", "中": "B", "medium": "B",
            "低": "D", "low": "D"}.get(value)


def activity_method(raw: Any) -> tuple[str, str]:
    value = clean_text(raw)
    lowered = value.casefold()
    if "邮件" in value or "email" in lowered:
        return "Email", value
    if "微信" in value or "wechat" in lowered:
        return "WeChat", value
    if "whatsapp" in lowered:
        return "WhatsApp", value
    if "电话" in value or "phone" in lowered:
        return "Phone", value
    if "会议" in value or "展会" in value or "meeting" in lowered:
        return "Meeting", value
    if "线上" in value or "video" in lowered:
        return "Video Call", value
    return "Other", value


def potential_stage(next_action: str, remarks: str, has_follow_up: bool) -> str:
    evidence = f"{next_action} {remarks}"
    if re.search(r"已关闭|夭折|项目取消|明确取消", evidence):
        return "Lost"
    if re.search(r"转售后|转赢单|已赢单|已下单|订单已下|下单已", evidence):
        return "Won"
    if re.search(r"已报价|报价已发|发报价", evidence):
        return "Quoted"
    return "Following" if has_follow_up else "New"


def pre_sales_status(progress: str, next_action: str) -> str:
    evidence = f"{progress} {next_action}"
    if re.search(r"取消|终止", evidence):
        return "Cancelled"
    if re.search(r"完结|完成|已下单|已提供|已回复", evidence):
        return "Completed"
    return "In Progress" if evidence.strip() else "Open"


def after_sales_status(progress: str, remarks: str) -> str:
    evidence = f"{progress} {remarks}"
    if re.search(r"完结|已完成|已修好|维修完成|已解决|已寄回|已退回", evidence):
        return "Closed"
    if re.search(r"已确认|已回复|已提供|已更换|已修复", evidence):
        return "Resolved"
    return "In Progress" if evidence.strip() else "Open"


def issue_type(description: str) -> str:
    if re.search(r"交期|发货|物流|运输|快递|包材", description):
        return "Delivery"
    if re.search(r"品质|质量|标签|包装|图纸|孔位", description):
        return "Quality"
    return "Technical"


def amount_value(raw: Any) -> tuple[Optional[float], Optional[str], str]:
    text_value = clean_text(raw)
    if not text_value or text_value in {"/", "-"}:
        return None, None, text_value
    currency = None
    if "$" in text_value or "usd" in text_value.casefold() or "美金" in text_value:
        currency = "USD"
    elif "€" in text_value or "eur" in text_value.casefold():
        currency = "EUR"
    elif "£" in text_value or "gbp" in text_value.casefold():
        currency = "GBP"
    elif "rmb" in text_value.casefold() or "人民币" in text_value or "¥" in text_value:
        currency = "CNY"
    numbers = re.findall(r"(?<![A-Za-z])\d+(?:[,.]\d+)*(?![A-Za-z])", text_value)
    if len(numbers) != 1:
        return None, currency, text_value
    try:
        return float(numbers[0].replace(",", "")), currency, text_value
    except ValueError:
        return None, currency, text_value
