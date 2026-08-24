"""Self-contained print-friendly HTML trip export."""

from __future__ import annotations

from html import escape

from .trip_export_model import LEG_HEADERS, TIMELINE_HEADERS, VISIT_HEADERS


def _table(title: str, headers: list[str], rows: list[dict]) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(
            f"<td>{escape(str(row.get(header) or '')).replace(chr(10), '<br>')}</td>"
            for header in headers
        ) + "</tr>"
        for row in rows
    )
    if not body:
        body = f'<tr><td class="empty" colspan="{len(headers)}">暂无内容 / No entries</td></tr>'
    return f"<section><h2>{escape(title)}</h2><div class=table-wrap><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>"


def render_trip_html(model: dict) -> bytes:
    metadata = "".join(
        f"<div><dt>{escape(str(label))}</dt><dd>{escape(str(value or '—'))}</dd></div>"
        for label, value in model["metadata"]
    )
    body = "".join((
        _table("拜访计划 / Visit Schedule", VISIT_HEADERS, model["visits"]),
        _table("完整日程 / Full Itinerary", TIMELINE_HEADERS, model["timeline"]),
        _table("交通行程 / Travel Legs", LEG_HEADERS, model["legs"]),
    ))
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(model['title'])} · 行程表</title><style>
:root{{--wine:#8b2347;--wine-dark:#4a1225;--paper:#f7f3ed;--line:#ded7ce;--ink:#251f1c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}}
main{{max-width:1500px;margin:auto;padding:36px}}header{{border-top:6px solid var(--wine);padding:24px 28px;background:#fff;border-radius:0 0 14px 14px;position:relative}}
h1{{margin:0 0 18px;font-family:Georgia,"Songti SC",serif;font-size:30px}}h2{{margin:30px 0 12px;color:var(--wine-dark)}}
button{{position:absolute;right:28px;top:24px;border:0;border-radius:8px;padding:9px 16px;background:var(--wine);color:#fff;font:inherit;font-weight:600;cursor:pointer}}
dl{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px 24px;margin:0}}dl div{{border-bottom:1px solid var(--line);padding:6px 0}}dt{{color:#776f68;font-size:12px}}dd{{margin:2px 0 0;font-weight:600}}
.table-wrap{{overflow-x:auto;background:#fff;border:1px solid var(--line);border-radius:12px}}table{{border-collapse:collapse;width:100%;min-width:1050px}}th,td{{border:1px solid var(--line);padding:9px 10px;vertical-align:top;text-align:left}}th{{background:var(--wine);color:#fff;position:sticky;top:0}}tbody tr:nth-child(even){{background:#fbf8f4}}.empty{{text-align:center;color:#776f68;padding:24px}}
footer{{margin:28px 0 8px;color:#776f68;text-align:right}}@media(max-width:760px){{main{{padding:12px}}dl{{grid-template-columns:1fr}}}}
@media print{{@page{{size:A4 landscape;margin:10mm}}body{{background:#fff}}main{{max-width:none;padding:0}}button{{display:none}}header,.table-wrap{{border-color:#aaa}}section{{break-before:page}}section:first-of-type{{break-before:auto}}th{{position:static;-webkit-print-color-adjust:exact;print-color-adjust:exact}}}}
</style></head><body><main><header><h1>{escape(model['title'])}</h1><button type="button" onclick="window.print()">打印 / Print</button><dl>{metadata}</dl></header>{body}<footer>JPT Sales Toolkit</footer></main></body></html>"""
    return document.encode("utf-8")
