"""
邮件解析服务 - 模块化重构版
遵循原则：函数职责单一、代码简洁、易于测试
"""
import re
from typing import Dict, Optional, List


# ==================== 基础提取函数 ====================

def extract_email(text: str) -> Optional[str]:
    """提取邮箱地址"""
    # 优先从尖括号中提取
    match = re.search(r'<([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>', text)
    if match:
        return match.group(1)
    # 普通格式
    match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    return match.group(0) if match else None


def extract_name_from_email(email: str) -> Optional[str]:
    """从邮箱地址推断姓名"""
    if not email:
        return None
    local = email.split('@')[0]
    # firstname.lastname 格式
    if '.' in local:
        parts = local.split('.')
        return ' '.join(p.capitalize() for p in parts if len(p) > 1)
    # firstnamelastname 格式 - 尝试在中间分割
    if len(local) > 6:
        # 尝试找到合理的分割点
        for i in range(3, len(local) - 2):
            first = local[:i]
            last = local[i:]
            if first.isalpha() and last.isalpha():
                return f"{first.capitalize()} {last.capitalize()}"
    return local.capitalize() if len(local) > 2 else None


def extract_company_from_domain(email: str) -> Optional[str]:
    """从邮箱域名提取公司名"""
    if not email or '@' not in email:
        return None
    domain = email.split('@')[1].split('.')[0]
    generic = ['gmail', 'yahoo', 'hotmail', 'outlook', 'qq', '163', '126', 'icloud', 'live']
    if domain.lower() in generic:
        return None
    return domain.capitalize() if len(domain) > 3 else domain.upper()


def extract_phone(text: str) -> Optional[str]:
    """提取电话号码"""
    patterns = [
        r'(?:Mobile|Phone|Tel|Fax)[:\s]*([+\d\s\-\(\)]{8,20})',
        r'(\+\d{1,3}[\s\-]?\d[\d\s\-]{7,15})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_website(text: str) -> Optional[str]:
    """提取网站URL"""
    match = re.search(r'(https?://[^\s]+|www\.[a-zA-Z0-9\-]+\.[a-zA-Z]{2,})', text)
    if match:
        url = match.group(1)
        return url if url.startswith('http') else 'https://' + url
    return None


# ==================== 签名块解析 ====================

def find_signature_block(text: str) -> Optional[str]:
    """定位签名块（从Regards等结束语之后）"""
    markers = ['Regards', 'Best regards', 'Kind regards', 'Thanks', 'Cordialement', 'Sincerely']
    for marker in markers:
        idx = text.lower().find(marker.lower())
        if idx != -1:
            return text[idx:]
    # 尝试找最后的换行段落
    paragraphs = text.strip().split('\n\n')
    if len(paragraphs) > 1:
        return '\n\n'.join(paragraphs[-2:])
    return None


def extract_name_from_signature(sig: str) -> Optional[str]:
    """从签名块提取姓名"""
    if not sig:
        return None
    lines = [l.strip() for l in sig.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        # 跳过问候语行
        if any(x in line.lower() for x in ['regards', 'thanks', 'sincerely', 'cordialement']):
            continue
        # 名字行：2-3个单词，首字母大写
        words = line.split()
        if 2 <= len(words) <= 4:
            if all(w[0].isupper() for w in words if w.isalpha()):
                # 排除职位行
                if not any(x in line.lower() for x in ['manager', 'director', 'coordinator', 'engineer', 'ceo', 'vp']):
                    return line
    return None


def extract_position_from_signature(sig: str) -> Optional[str]:
    """从签名块提取职位"""
    if not sig:
        return None
    keywords = ['Manager', 'Director', 'Coordinator', 'Engineer', 'CEO', 'VP', 'President', 'Owner', 'Founder']
    for line in sig.split('\n'):
        for kw in keywords:
            if kw.lower() in line.lower():
                return line.strip()
    return None


def extract_company_from_signature(sig: str) -> Optional[str]:
    """从签名块提取公司名"""
    if not sig:
        return None
    # 排除词
    skip_words = ['regards', 'thanks', 'sincerely', 'cordialement', 'best', 'kind', 'mobile', 'phone', 'tel', 'email']

    lines = [l.strip() for l in sig.split('\n') if l.strip()]
    for line in lines:
        line_lower = line.lower()
        # 跳过问候语和联系方式行
        if any(w in line_lower for w in skip_words):
            continue
        # 全大写公司名（至少4个字符）
        if line.isupper() and len(line) >= 4:
            return line
        # 带后缀的公司名
        if re.search(r'\b(Ltd|LLC|Inc|GmbH|Co|Corp|Limited|SA|SAS|BV|AG)\b', line, re.IGNORECASE):
            return line
    return None


# ==================== 地址解析 ====================

def extract_postal_city(text: str) -> Dict:
    """提取邮编和城市"""
    result = {'postal_code': None, 'city': None}
    # 欧洲格式: 28109 Alcobendas 或 74210 Faverges-Seythenex
    match = re.search(r'\b(\d{4,5})\s+([A-Za-zÀ-ÿ\-]+(?:\s+[A-Za-zÀ-ÿ\-]+)?)\b', text)
    if match:
        result['postal_code'] = match.group(1)
        result['city'] = match.group(2)
    return result


def extract_country(text: str) -> Optional[str]:
    """提取国家"""
    countries = {
        'spain': 'ES', 'españa': 'ES', 'france': 'FR', 'germany': 'DE', 'deutschland': 'DE',
        'netherlands': 'NL', 'holland': 'NL', 'uk': 'GB', 'united kingdom': 'GB', 'britain': 'GB',
        'italy': 'IT', 'italia': 'IT', 'denmark': 'DK', 'danmark': 'DK', 'sweden': 'SE',
        'usa': 'US', 'united states': 'US', 'america': 'US', 'canada': 'CA',
        'india': 'IN', 'china': 'CN', 'japan': 'JP', 'korea': 'KR',
    }
    text_lower = text.lower()
    for name, code in countries.items():
        if name in text_lower:
            return code
    # 检查国家代码 /FR /ES 等
    match = re.search(r'[/\-]\s*([A-Z]{2})\b', text)
    if match:
        return match.group(1)
    return None


def get_region(country_code: str) -> Optional[str]:
    """根据国家代码获取区域"""
    regions = {
        'EU': ['ES', 'FR', 'DE', 'NL', 'GB', 'IT', 'DK', 'SE', 'NO', 'FI', 'BE', 'AT', 'CH', 'PL', 'CZ', 'PT', 'IE'],
        'AM': ['US', 'CA', 'MX', 'BR', 'AU', 'NZ'],
        'SEA': ['SG', 'MY', 'TH', 'VN', 'ID', 'PH', 'JP', 'KR', 'CN', 'TW', 'HK'],
        'RIMEA': ['IN', 'RU', 'TR', 'AE', 'SA', 'IL', 'ZA', 'EG'],
    }
    for region, codes in regions.items():
        if country_code in codes:
            return region
    return None


# ==================== 日期解析 ====================

def extract_date(text: str) -> Optional[str]:
    """提取邮件日期"""
    # 中文格式: 2026年3月9日
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    # ISO格式
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if match:
        return match.group(0)
    return None


# ==================== 主解析函数 ====================

def parse_inquiry_email(email_content: str) -> Dict:
    """解析询盘邮件，返回提取的字段"""
    result = {}

    # 基础信息
    result['email'] = extract_email(email_content)
    result['inquiry_date'] = extract_date(email_content)

    # 从邮箱推断
    if result['email']:
        result['company_name'] = extract_company_from_domain(result['email'])
        email_name = extract_name_from_email(result['email'])
    else:
        email_name = None

    # 签名块解析
    sig = find_signature_block(email_content)
    sig_name = extract_name_from_signature(sig)
    sig_position = extract_position_from_signature(sig)
    sig_company = extract_company_from_signature(sig)

    # 合并结果（签名块优先）
    result['contact_name'] = sig_name or email_name
    result['contact_position'] = sig_position
    if sig_company:
        result['company_name'] = sig_company

    # 联系方式
    result['phone'] = extract_phone(email_content)
    result['website'] = extract_website(email_content)

    # 地址
    addr = extract_postal_city(email_content)
    result['postal_code'] = addr['postal_code']
    result['city'] = addr['city']
    result['country'] = extract_country(email_content)
    result['region'] = get_region(result['country']) if result['country'] else None

    # 过滤空值
    return {k: v for k, v in result.items() if v}


# ==================== 测试 ====================

if __name__ == "__main__":
    test1 = """maribelmontero@c95creative.com
Procurement Manager
C/ Caléndula 95
Edoif. O, plta. 1ª, Oficina 10
28109 Alcobendas Madrid
Spain
+34 91 658 5210"""

    test2 = """GROSJEAN Gaetan<g.grosjean@staubli.com> 在 2026年3月9日 写道：
Regards

Gaëtan GROSJEAN
Fluid Connectors System – Global Manufacturing Engineering Coordinator

STAUBLI FAVERGES
Place Robert Staubli CS 30070
74210 Faverges-Seythenex / FR
Mobile: +33 6 72 14 71 70
www.staubli.com"""

    for i, test in enumerate([test1, test2], 1):
        print(f"\n=== Test {i} ===")
        result = parse_inquiry_email(test)
        for k, v in sorted(result.items()):
            print(f"  {k}: {v}")
