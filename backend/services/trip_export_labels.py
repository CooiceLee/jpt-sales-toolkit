"""Final bilingual labels for formal trip exports."""

from __future__ import annotations


STATUS_LABELS = {
    "unconfirmed": "未确认 / Unconfirmed",
    "tentative": "暂定 / Tentative",
    "confirmed": "已确认 / Confirmed",
    "needs_reconfirmation": "需重新确认 / Needs reconfirmation",
    "cancelled": "已取消 / Cancelled",
}
MODE_LABELS = {
    "auto": "自动 / Automatic",
    "flight": "航班 / Flight",
    "drive": "自驾 / Driving",
    "ground_public": "公共交通 / Public transport",
    "other": "其他 / Other",
}
CATEGORY_LABELS = {
    "rest": "休息 / Rest", "hotel": "酒店 / Hotel",
    "airport": "机场 / Airport", "transit": "中转 / Transit",
    "meal": "用餐 / Meal", "other": "其他 / Other",
}
ROLE_LABELS = {
    "leader": "负责人 / Leader", "sales": "销售 / Sales", "tech": "技术 / Tech",
}
BASIS_LABELS = {
    "manual_values_locked": "已人工确认 / Manually confirmed",
    "mode_locked_metrics_estimated": "交通方式已确认，里程与时长为估算 / Mode confirmed; distance and duration estimated",
    "heuristic_estimate_confirm_manually": "估算，需人工确认 / Estimate, confirm manually",
}
REGION_LABELS = {
    "GLOBAL": "全球 / Global",
    "EU": "欧洲 / Europe",
    "AM": "北美、加拿大、澳洲 / North America, Canada & Australia",
    "RIMEA": "俄罗斯、土耳其、中东 / Russia, Türkiye & Middle East",
    "SEA": "东南亚 / Southeast Asia",
}


def product_status(value) -> str:
    return STATUS_LABELS.get(value, str(value or ""))


def product_mode(value) -> str:
    return MODE_LABELS.get(value, str(value or ""))


def product_category(value) -> str:
    return CATEGORY_LABELS.get(value, str(value or ""))


def product_role(value) -> str:
    return ROLE_LABELS.get(value, str(value or ""))


def product_basis(value) -> str:
    return BASIS_LABELS.get(value, str(value or ""))


def product_region(value) -> str:
    return REGION_LABELS.get(value, str(value or ""))
