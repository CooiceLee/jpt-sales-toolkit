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
    start = index.index('class="trip-export-panel"')
    panel = index[start:index.index("</section>", start)]
    for file_format in ("xlsx", "html", "ics", "md", "csv"):
        assert f'data-trip-export-format="{file_format}"' in panel
    for file_format in ("ics", "md", "csv"):
        assert f"exportCurrentTripPlan('{file_format}')" in panel
    # The two documents each come in two versions, so each is its own download.
    for file_format in ("xlsx", "html"):
        for variant in ("shared", "full"):
            call = f"exportCurrentTripPlan('{file_format}', '{variant}')"
            assert call in panel, (
                f"the page has no {variant} {file_format} download"
            )
    # And the page says which group a download belongs to before it is clicked,
    # so nothing carrying visit preparation sits under the forwardable heading.
    for heading in ("Shared itinerary &#183;", "For the people making the visits"):
        assert heading in panel, (
            f"the page no longer groups its downloads under {heading!r}"
        )
    shared_group = panel[panel.index("Shared itinerary &#183;"):
                         panel.index("For the people making the visits")]
    assert "'shared'" in shared_group and "'full'" not in shared_group
    visitors_group = panel[panel.index("For the people making the visits"):]
    assert "'full'" in visitors_group and "'shared'" not in visitors_group
    assert "No visit preparation inside." in shared_group
    assert "Data formats, with visit preparation" in panel, (
        "Markdown and CSV always carry visit preparation and have to say so"
    )
    assert "trip-export-status" in panel
    assert index.index("trip-itinerary-actions.js") < index.index("trip-export-actions.js")
    for meta_word in ("endpoint", "contract", "compatibility", "正式格式"):
        assert meta_word not in panel

    i18n = _source("frontend/js/i18n.js")
    labels = {
        "Trip files": "行程文件",
        "Share your itinerary": "分享行程",
        "Add to calendar": "添加到日历",
        "Shared itinerary": "共享行程",
        "Shared web itinerary": "共享网页行程单",
        "Itinerary with visit preparation": "行程 + 拜访准备",
        "Web itinerary with visit preparation": "网页行程单 + 拜访准备",
        "Field workbook": "现场执行工作簿",
        "Choose a file to download.": "选择要下载的文件。",
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
const planA={id:'p1',title:'Europe September',itinerary_summary:{valid:true}};
const planB={id:'p2',title:'Korea October',itinerary_summary:{valid:true}};
const context={console:{error(){}},Date,State:{currentTripPlan:planA},
 document:{getElementById:id=>id==='trip-export-status'?status:null,
  querySelector:selector=>selector==='.trip-export-panel'?panel:null,
  createElement:()=>({style:{},setAttribute(){},click(){},remove(){}}),
  querySelectorAll:()=>buttons.map(button=>({...button,
    getAttribute:()=>'xlsx',set disabled(v){button.disabled=v},
    get disabled(){return button.disabled},set title(v){button.title=v},
    get title(){return button.title}}))},
 I18n:{t:(text,params={})=>Object.entries(params).reduce((value,[key,item])=>value.replace(`{${key}}`,item),text)},
 TripBriefingDraft:{guard(){return false}},TripVisitDraft:{guard(){return false}},
 TripFreeStopDraft:{guardRouteAction(){return false}},TripPlanningDraft:{get(){return{dirty:false}}},
 ApiClient:{exportTripPlan(planId,format,variant){requests.push([planId,format,variant]);
  return new Promise(resolve=>{resolveRequest=resolve})}},
 downloadBlob(blob,filename){downloads.push(filename)},notify(message){messages.push(message)},alert(message){alerts.push(message)}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-export-naming.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-export-actions.js','utf8'),context);
(async()=>{
 const pending=context.exportCurrentTripPlan('xlsx','shared');
 assert(status.textContent.includes('Generating Shared itinerary'),status.textContent);
 assert(status.textContent.includes('Europe September'),'the reader is not told which plan is being generated');
 assert(buttons.every(button=>button.disabled));assert.strictEqual(panel.attrs['aria-busy'],'true');

 // Opening another plan while the file is still being made must not rename it.
 context.State.currentTripPlan=planB;
 resolveRequest({blob:{},filename:'trip-plan-p1-shared.xlsx'});await pending;
 assert.deepStrictEqual(requests,[['p1','xlsx','shared']]);
 assert.strictEqual(downloads.length,1);
 assert(downloads[0].startsWith('Europe-September-shared-'),
  `the file was named after whichever plan was open when it arrived: ${downloads[0]}`);
 assert(downloads[0].endsWith('.xlsx'),downloads[0]);
 assert(status.textContent.includes(downloads[0]));
 assert.strictEqual(status.className,'trip-export-status success');
 assert.strictEqual(panel.attrs['aria-busy'],'false');

 // Each of the eight documents names itself, so two of them never collide.
 context.State.currentTripPlan=planA;
 const named=[['xlsx','shared'],['xlsx','full'],['html','shared'],['html','full'],
  ['ics',''],['working',''],['md',''],['csv','']]
  .map(([format,variant])=>context.TripExportNaming.filename(planA,format,variant,'fallback'));
 assert.strictEqual(new Set(named).size,named.length,`two documents share a name: ${named}`);

 // A panel that cannot produce a file says so instead of waiting to refuse.
 context.State.currentTripPlan=null;context.TripExportActions.refresh(null);
 assert(buttons.every(button=>button.disabled),'the buttons invite a click that will be refused');
 assert(buttons.every(button=>button.title.includes('Select a saved itinerary')),buttons[0].title);
 assert(status.textContent.includes('Select a saved itinerary'),
  `the previous plan's download is still reported: ${status.textContent}`);

 const stale={id:'p3',title:'Stale',itinerary_summary:{stale:true}};
 context.TripExportActions.refresh(stale);
 assert(buttons.every(button=>button.disabled&&button.title.includes('out of date')),buttons[0].title);
 context.TripExportActions.refresh(planA);
 assert(buttons.every(button=>!button.disabled&&!button.title),'a usable plan left the buttons off');

 context.State.currentTripPlan=planA;
 context.TripPlanningDraft.get=()=>({dirty:true});await context.exportCurrentTripPlan('html','shared');
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
    assert "/review/trip-plans/${planId}/${path}" in export_source
    assert "export.${format}${query}" in export_source
    # The field workbook is a document of its own, not a version of the others.
    assert "working.xlsx" in export_source
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
