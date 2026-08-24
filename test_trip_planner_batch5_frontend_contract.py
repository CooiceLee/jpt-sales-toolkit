"""Batch 5 contracts for trip-file downloads and their product UI."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _node(script: str) -> None:
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr or result.stdout


def check_export_surface_and_language() -> None:
    index = _source("frontend/index.html")
    panel = index[index.index('class="trip-export-panel"'):index.index('class="trip-export-panel"') + 5000]
    for file_format in ("xlsx", "html", "ics", "md", "csv"):
        assert f'data-trip-export-format="{file_format}"' in panel
        assert f"exportCurrentTripPlan('{file_format}')" in panel
    assert "trip-export-status" in panel
    assert index.index("trip-itinerary-actions.js") < index.index("trip-export-actions.js")
    for meta_word in ("endpoint", "contract", "compatibility", "正式格式"):
        assert meta_word not in panel

    i18n = _source("frontend/js/i18n.js")
    labels = {
        "Trip files": "行程文件",
        "Share your itinerary": "分享行程",
        "Excel itinerary": "Excel 行程表",
        "Web itinerary": "网页行程单",
        "Add to calendar": "添加到日历",
        "Select a saved itinerary to download.": "选择已保存的行程后即可下载。",
        "Downloaded: {filename}": "已下载：{filename}",
        "Download failed: {error}": "下载失败：{error}",
    }
    for english, chinese in labels.items():
        assert f"['{english}', '{chinese}']" in i18n

    css = _source("frontend/css/style.css")
    for selector in (".trip-export-panel", ".trip-export-grid", ".trip-export-option"):
        assert selector in css
    assert "var(--wine-700)" in css[css.index(".trip-export-panel"):]


def check_download_boundaries_and_status() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const status={textContent:'',className:''};const buttons=[{disabled:false},{disabled:false},{disabled:false}];
const panel={attrs:{},setAttribute(k,v){this.attrs[k]=v},querySelectorAll(){return buttons}};
let alerts=[],downloads=[],requests=[],messages=[],resolveRequest;
const context={console:{error(){}},State:{currentTripPlan:{id:'p1',itinerary_summary:{valid:true}}},
 document:{getElementById:id=>id==='trip-export-status'?status:null,
  querySelector:selector=>selector==='.trip-export-panel'?panel:null},
 I18n:{t:(text,params={})=>Object.entries(params).reduce((value,[key,item])=>value.replace(`{${key}}`,item),text)},
 TripBriefingDraft:{guard(){return false}},TripVisitDraft:{guard(){return false}},
 TripFreeStopDraft:{guardRouteAction(){return false}},TripPlanningDraft:{get(){return{dirty:false}}},
 ApiClient:{exportTripPlan(planId,format){requests.push([planId,format]);return new Promise(resolve=>{resolveRequest=resolve})}},
 downloadBlob(blob,filename){downloads.push(filename)},notify(message){messages.push(message)},alert(message){alerts.push(message)}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-export-actions.js','utf8'),context);
(async()=>{
 const pending=context.exportCurrentTripPlan('xlsx');
 assert(status.textContent.includes('Generating Excel itinerary'));
 assert(buttons.every(button=>button.disabled));assert.strictEqual(panel.attrs['aria-busy'],'true');
 resolveRequest({blob:{},filename:'Europe_Visit.xlsx'});await pending;
 assert.deepStrictEqual(requests,[['p1','xlsx']]);assert.deepStrictEqual(downloads,['Europe_Visit.xlsx']);
 assert.strictEqual(status.textContent,'Downloaded: Europe_Visit.xlsx');
 assert.strictEqual(status.className,'trip-export-status success');
 assert(buttons.every(button=>!button.disabled));assert.strictEqual(panel.attrs['aria-busy'],'false');

 context.TripPlanningDraft.get=()=>({dirty:true});await context.exportCurrentTripPlan('html');
 assert(alerts.at(-1).includes('Save the current route draft'));assert.strictEqual(requests.length,1);
 context.TripPlanningDraft.get=()=>({dirty:false});context.State.currentTripPlan.itinerary_summary={stale:true};
 await context.exportCurrentTripPlan('ics');assert(alerts.at(-1).includes('out of date'));assert.strictEqual(requests.length,1);
 context.State.currentTripPlan=null;await context.exportCurrentTripPlan('ics');
 assert(alerts.at(-1).includes('Select a trip plan'));assert.strictEqual(requests.length,1);
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_api_contract_and_module_size() -> None:
    api = _source("frontend/js/api-client.js")
    export_source = api[api.index("async function exportTripPlan"):api.index("async function getTripExecution")]
    assert "/review/trip-plans/${planId}/export.${format}" in export_source
    assert "readErrorResponse(response)" in export_source
    assert "filename\\*?=" in export_source

    for path in (ROOT / "frontend/js/modules").glob("trip-*.js"):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 160, f"{path.name} grew to {len(lines)} lines"


def main() -> None:
    check_export_surface_and_language()
    check_download_boundaries_and_status()
    check_api_contract_and_module_size()
    print("PASS: Batch 5 trip export frontend contract")


if __name__ == "__main__":
    main()
