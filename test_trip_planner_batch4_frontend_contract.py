"""Batch 4 browser-contract regressions for half-day schedules and visit briefings.

The checks deliberately exercise small public browser modules in Node.  They do
not open the installed desktop profile or write application data.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _node(script: str) -> None:
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def check_batch4_assets_and_dom_contract() -> None:
    index = _source("frontend/index.html")
    expected_scripts = (
        "trip-duration.js",
        "trip-schedule-view.js",
        "trip-briefing-draft.js",
        "trip-briefing-rows.js",
        "trip-briefing-form.js",
        "trip-briefing-actions.js",
        "trip-visit-draft.js",
    )
    for script in expected_scripts:
        assert f'/static/js/modules/{script}' in index, f"missing {script} asset"
    assert index.index("trip-duration.js") < index.index("trip-form.js")
    assert index.index("trip-briefing-draft.js") < index.index("trip-briefing-actions.js")
    assert index.index("trip-briefing-actions.js") < index.index("trip-visit-actions.js")

    for selector in (
        'id="trip-schedule-panel"',
        'id="trip-schedule-list"',
        'id="trip-briefing-editor"',
    ):
        assert selector in index, f"missing Batch 4 DOM contract: {selector}"
    assert "data-stop-duration-half-days" in index
    assert 'id="trip-free-stop-stay"' in index

    # A closed briefing must release its grid column so the schedule does not
    # leave a large empty panel on the right.
    css = _source("frontend/css/style.css")
    actions = _source("frontend/js/modules/trip-briefing-actions.js")
    assert ".trip-schedule-workspace:not(.has-open-briefing)" in css
    assert "classList.toggle('has-open-briefing'" in actions

    # The editor contents are intentionally generated only after a customer
    # stop is opened.  Lock those controls to the form modules, not index.html.
    form = _source("frontend/js/modules/trip-briefing-form.js")
    rows = _source("frontend/js/modules/trip-briefing-rows.js")
    for selector in ('id="trip-briefing-save"', 'id="trip-briefing-refresh"'):
        assert selector in rows
    assert "if (model[key].length) keptExisting" in form
    assert "Suggestions filled only empty sections" in form
    draft = _source("frontend/js/modules/trip-briefing-draft.js")
    assert "channel_partner_companions: () => ({ company_name: '', name: '', position: '', phone: '', email: '', role: '', notes: '' })" in draft
    for key in ("contacts", "channel_partner_companions", "participants", "equipment", "agenda_items"):
        assert f"renderSection('{key}'" in rows
    for field_name in ("company_name", "name", "position", "phone", "email", "role", "notes"):
        assert f"'{field_name}', item.{field_name}" in rows
    assert 'data-briefing-array-key="${h(kind)}"' in rows
    assert "kind === 'agenda_items' ? 'agenda' : kind" in rows


def check_api_and_language_contract() -> None:
    api = _source("frontend/js/api-client.js")
    assert "getTripBriefing" in api
    assert "putTripBriefing" in api
    assert "/briefing`" in api or "/briefing'" in api
    assert "method: 'PUT'" in api

    i18n = _source("frontend/js/i18n.js")
    visible_labels = {
        "Half day": "半天",
        "Morning (AM)": "上午（AM）",
        "Afternoon (PM)": "下午（PM）",
        "Visit briefing": "拜访准备",
        "Customer departments / teams": "客户部门 / 团队",
        "Customer personnel": "客户人员",
        "Channel partner companions (if any)": "渠道代理公司陪同人员（如有）",
        "Channel partner companions": "渠道代理公司陪同人员",
        "JPT internal participants": "JPT 内部参会人员",
        "Demo equipment": "演示设备",
        "PO equipment": "订单设备",
        "Preparation": "准备事项",
        "Expected outcome": "预期结果",
        "Needs reconfirmation": "需重新确认",
        "Unsaved visit briefing": "未保存的拜访准备",
        "Visit purpose": "拜访目的",
        "Result notes": "结果备注",
        "Unscheduled stops": "未排程拜访",
        "Export day report": "导出当日拜访报告",
        "No scheduled date": "尚未排定日期",
        "Customer personnel": "客户人员",
        "Channel partner companions": "渠道代理公司陪同人员",
        "JPT internal participants": "JPT 内部参会人员",
        "Lead": "商机",
        "Customer needs": "客户需求",
        "Budget": "预算",
        "Sample needed": "需要样品",
        "Quote needed": "需要报价",
        "Meeting notes": "会议记录",
        "Upload files": "上传文件",
    }
    for english, chinese in visible_labels.items():
        assert f"['{english}', '{chinese}']" in i18n, (
            f"missing final bilingual UI label: {english} / {chinese}"
        )
    planner = _source("frontend/js/modules/trip-planner.js")
    itinerary = _source("frontend/js/modules/trip-itinerary-view.js")
    schedule = _source("frontend/js/modules/trip-schedule-view.js")
    for label in (
        "Unscheduled stops", "Export day report", "No scheduled date", "Customer personnel",
        "Channel partner companions", "JPT internal participants", "Lead",
        "Customer needs", "Budget", "Sample needed", "Quote needed", "Meeting notes", "Upload files",
    ):
        assert f"t('{label}')" in planner, f"Trip execution must localize {label} at render time"
    assert "I18n.t('Visit purpose')" in itinerary
    assert "I18n.t('Result notes')" in itinerary
    assert "transportModeLabel(item.selected_mode" in schedule


def check_duration_conversion_and_route_payload() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const fields=new Map([
 ['trip-route-order-mode',{value:'manual'}],
 ['duration-s1',{value:'1',dataset:{stopDurationHalfDays:'1',stopId:'s1'}}],
 ['duration-s2',{value:'2',dataset:{stopDurationHalfDays:'2',stopId:'s2'}}],
 ['duration-s3',{value:'3',dataset:{stopDurationHalfDays:'3',stopId:'s3'}}],
]);
const context={console,document:{getElementById:id=>fields.get(id)||null,
 querySelectorAll(selector){return selector==='[data-stop-duration-half-days]'?Array.from(fields.values()).slice(1):[]}},
 State:{currentTripPlan:{id:'p1',stops:[{id:'s1'},{id:'s2'},{id:'s3'}]}},
 numericOrNull:v=>v===''?null:Number(v),parseHolidayInput:()=>[],tripDateTimeLocalValue:v=>v||'',
 TripPlanningDraft:{get(){return{stopDurations:{
   s1:{half_days:1,preferred_period:'AM',locked:false},
   s2:{half_days:2,preferred_period:'auto',locked:false},
   s3:{half_days:3,preferred_period:'PM',locked:true}}}}}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js','utf8'),context);
assert.strictEqual(context.TripDuration.normalizeHalfDays(1),1);
assert.strictEqual(context.TripDuration.normalizeHalfDays(60),60);
assert.strictEqual(context.TripDuration.toDisplayDays(1),0.5);
assert.strictEqual(context.TripDuration.toDisplayDays(2),1);
assert.strictEqual(context.TripDuration.toDisplayDays(3),1.5);
assert.strictEqual(context.TripDuration.fromDisplayDays('0.5'),1);
assert.strictEqual(context.TripDuration.fromDisplayDays('1'),2);
assert.strictEqual(context.TripDuration.fromDisplayDays('1.5'),3);
assert.strictEqual(context.TripDuration.parseDisplayDays(''),null);
assert.strictEqual(context.TripDuration.parseDisplayDays('0.25'),null);
assert.strictEqual(context.TripDuration.parseDisplayDays('0.5'),1);
assert.strictEqual(context.TripDuration.parseDisplayDays('1.5'),3);
assert.strictEqual(context.TripDuration.parseDisplayTravelDays(''),null);
assert.strictEqual(context.TripDuration.parseDisplayTravelDays('0'),0);
assert.strictEqual(context.TripDuration.parseDisplayTravelDays('0.5'),1);
assert.strictEqual(context.TripDuration.parseDisplayTravelDays('1'),2);
assert.strictEqual(context.TripDuration.parseDisplayTravelDays('0.25'),null);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-form.js','utf8'),context);
const payload=context.readTripItineraryPayload();
assert(!Object.prototype.hasOwnProperty.call(payload,'stop_stays'),
  'Batch 4 route writes must not send the legacy whole-day map');
assert.deepStrictEqual(JSON.parse(JSON.stringify(payload.stop_durations)),{
 s1:{half_days:1,preferred_period:'AM',locked:false},
 s2:{half_days:2,preferred_period:'auto',locked:false},
 s3:{half_days:3,preferred_period:'PM',locked:true},
});
""")


def check_schedule_items_are_sorted_and_all_kinds_render() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const target={innerHTML:''};
const context={console,document:{getElementById:id=>id==='trip-schedule-list'?target:null},
 I18n:{t:v=>v==='Flight'?'航班':v},escapeHtml:v=>String(v??'')};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-schedule-view.js','utf8'),context);
const items=[
 {slot_key:'2026-09-15:PM',date:'2026-09-15',period:'PM',schedule_index:2,item_type:'free',source_id:'f1',title:'Hotel'},
 {slot_key:'2026-09-16:AM',date:'2026-09-16',period:'AM',schedule_index:3,item_type:'leg',source_id:'l1',title:'Paris to Lyon',selected_mode:'flight'},
 {slot_key:'2026-09-15:AM',date:'2026-09-15',period:'AM',schedule_index:1,item_type:'customer',source_id:'s1',title:'Rayxion'},
];
const sorted=context.TripScheduleView.sortItems(items);
assert.deepStrictEqual(Array.from(sorted,x=>x.slot_key),['2026-09-15:AM','2026-09-15:PM','2026-09-16:AM']);
context.TripScheduleView.render(items,target);
for(const text of ['Rayxion','Hotel','Paris to Lyon','AM','PM']) assert(target.innerHTML.includes(text),text);
assert(target.innerHTML.includes('航班'),'canonical transport mode must be localized');
for(const kind of ['customer','free','leg']) assert(target.innerHTML.includes(kind),kind);
""")


def check_half_day_summary_and_visit_location_linkage() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const context={console,Date,document:{getElementById(){return null},querySelectorAll(){return[]}},
 I18n:{t:(text,params={})=>Object.entries(params).reduce((value,[key,item])=>value.replace(`{${key}}`,item),text)},
 escapeHtml:value=>String(value??''),TripCandidateState:{warningText:value=>value},
 JPTRender:{escape:value=>String(value??'')}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-itinerary-view.js','utf8'),context);
const summary=context.renderTripItinerarySummary({itinerary_summary:{calculated_end_date:'2026-09-18',
 calculated_end_period:'PM',total_business_days:2,total_stay_days:1.5,total_travel_days:0.5,total_distance_km:0}});
assert(summary.includes('2026-09-18 · PM'));
assert(summary.includes('1.5 days'));assert(summary.includes('0.5 days'));
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-visit-state.js','utf8'),context);
const stop={address:'Old customer address',city:'Old city',contact_name:'Old contact',
 visit_location:{name:'Paris meeting room',address:'12 Rue Demo',city:'Paris',postal_code:'75001',country:'France',lat:48.86,lng:2.35},
 briefing:{customer_team:[{name:'Process Team',title:'Production'}],contacts:[{name:'Kim',position:'Manager',phone:'+33 1 23'}],
 channel_partner_companions:[{company_name:'Euro Partner',name:'Anna',position:'Sales'}],
 participants:[{display_name:'Eric',role:'Tech',responsibility:'Demo'}]}};
assert.strictEqual(context.TripVisitState.addressLine(stop),'12 Rue Demo, Paris, 75001, France');
assert.strictEqual(context.TripVisitState.customerPersonnelLine(stop),'Process Team / Production; Kim / Manager / +33 1 23');
assert.strictEqual(context.TripVisitState.contactLine(stop),context.TripVisitState.customerPersonnelLine(stop));
assert.strictEqual(context.TripVisitState.channelPartnerLine(stop),'Euro Partner / Anna / Sales');
assert.strictEqual(context.TripVisitState.internalParticipantsLine(stop),'Eric / Tech / Demo');
""")


def check_map_uses_effective_visit_location() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const points=[];const tooltips=[];
const marker=()=>({bindTooltip(value){tooltips.push(value);return this},bindPopup(){return this},addTo(){return this}});
const stop={sequence_no:1,stop_kind:'customer',customer_name:'Customer default',lat:1,lng:2,
 visit_location:{name:'Paris meeting room',address:'12 Rue Demo',city:'Paris',country:'France',lat:48.86,lng:2.35}};
const context={console,State:{tripMap:{fitBounds(){}},tripMapLayer:{clearLayers(){}},tripCandidates:[],currentTripPlan:{stops:[stop]}},
 MapSupport:{coordinatePair(lat,lng){if(lat==null||lng==null)return null;const pair=[Number(lat),Number(lng)];points.push(pair);return pair}},
 L:{circleMarker:marker,polyline:marker},I18n:{t:value=>value},escapeHtml:value=>String(value??''),formatMoney(){return''},
 TripVisitState:{visitLocation:item=>item.visit_location||item}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-candidates-map.js','utf8'),context);
context.renderTripMap();
assert(points.some(pair=>pair[0]===48.86&&pair[1]===2.35));
assert(!points.some(pair=>pair[0]===1&&pair[1]===2));
assert(tooltips.some(value=>value.includes('Paris meeting room')&&value.includes('12 Rue Demo')));
""")


def check_trip_execution_renders_final_chinese_labels() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const target={innerHTML:''};
const zh={
 'Unscheduled stops':'未排程拜访','Export day report':'导出当日拜访报告','No scheduled date':'尚未排定日期',
 'Customer personnel':'客户人员','Channel partner companions':'渠道代理公司陪同人员',
 'JPT internal participants':'JPT 内部参会人员','Address':'地址','Lead':'商机','Purpose':'目的','Customer needs':'客户需求',
 'Competitor':'竞争对手','Budget':'预算','Decision maker':'客户决策人','Next action':'下一步行动',
 'Meeting notes':'会议记录','Sample needed':'需要样品','Quote needed':'需要报价','Save visit':'保存拜访记录',
 'Discard edits':'放弃编辑','Upload files':'上传文件','Planned':'已计划','Visited':'已拜访',
 'Follow-up Needed':'需要跟进','Skipped':'已跳过',
};
const stop={id:'s1',sequence_no:1,customer_name:'Customer GmbH',result_status:'Planned',lead_id:'l1'};
const plan={id:'p1',stops:[stop]};
const context={console,State:{currentTripPlan:plan},I18n:{t:key=>zh[key]||key},
 document:{getElementById:id=>id==='trip-visit-execution'?target:null},
 TripVisitState:{escape:value=>String(value??''),planDays(){return[]},currentDateForPlan(){return''},
  stopMatchesDay(){return true},compareStops(){return 0},scheduleLabel(){return''},customerPersonnelLine(){return'客户甲'},
  channelPartnerLine(){return'代理乙'},internalParticipantsLine(){return'内部丙'},addressLine(){return''},
  agendaLine(stop){return (stop&&stop.visit_purpose)||''}},
 TripVisitDraft:{mark(){},discard(){}},JPTRender:{field:(label,value)=>`<div>${label}:${value||''}</div>`,empty:value=>value}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-planner.js','utf8'),context);
context.TripPlannerModule.renderVisitExecution(plan);
for(const label of ['未排程拜访','导出当日拜访报告','尚未排定日期','客户人员','渠道代理公司陪同人员','JPT 内部参会人员','商机','客户需求','预算','会议记录','需要样品','需要报价','上传文件']) {
 assert(target.innerHTML.includes(label),label);
}
for(const pair of ['客户人员:客户甲','渠道代理公司陪同人员:代理乙','JPT 内部参会人员:内部丙']) assert(target.innerHTML.includes(pair),pair);
for(const raw of ['Unscheduled stops','Export day report','No scheduled date','Customer needs','Meeting notes','Sample needed','Quote needed','Upload files']) {
 assert(!target.innerHTML.includes(raw),raw);
}
""")


def check_briefing_payload_is_full_replace_with_double_cas() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
let sent=null;
const root={hidden:true,innerHTML:'',setAttribute(){},closest(){return null}};
const status={textContent:'',classList:{toggle(){}}};
const fields={
 'trip-briefing-editor':root,'trip-briefing-draft-status':status,
 'trip-briefing-confirmation':{value:'confirmed'},'trip-briefing-timezone':{value:''},
 'trip-briefing-use-default':{checked:true},
};
const locationFields=['name','address','city','postal_code','country','lat','lng']
 .map(key=>({value:'',dataset:{locationField:key}}));
const emptyRows={querySelectorAll(){return[]}};
const context={console,structuredClone,State:{tripBusy:false,currentTripPlan:{id:'p1',stops:[{id:'s1',row_version:7,customer_name:'Rayxion'}]}},
 document:{getElementById:id=>fields[id]||null,
  querySelector(selector){return selector.startsWith('[data-briefing-array-key=')?emptyRows:null},
  querySelectorAll(selector){return selector==='[data-location-field]'?locationFields:[]}},
 I18n:{t:v=>v},escapeHtml:v=>String(v??''),alert(message){throw new Error(message)},confirm(){return true},
 notify(){},renderCurrentTripPlan(){},handleTripError(error){throw error},
 TripScheduleView:{renderPlan(){}},
 ApiClient:{async putTripBriefing(planId,stopId,payload){sent={planId,stopId,payload};return payload}}};
context.window=context;vm.createContext(context);
context.addEventListener=()=>{};
for(const file of ['trip-briefing-draft.js','trip-briefing-rows.js','trip-briefing-form.js','trip-briefing-actions.js'])
 vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`,'utf8'),context);
const record={row_version:3,stop_row_version:7,confirmation_status:'confirmed',timezone:'Europe/Paris',
 location:{use_customer_default:false,name:'Rayxion HQ',address:'99 Demo Road',city:'Paris',postal_code:'75001',country:'France',lat:48.86,lng:2.35},
 customer_team:[{name:'Process Team',sequence_no:1}],contacts:[{name:'Kim',sequence_no:1}],
 channel_partner_companions:[{company_name:'Euro Partner',name:'Anna',sequence_no:1}],
 participants:[{user_id:'u1',display_name:'Tech',sequence_no:1}],equipment:[{kind:'demo',model:'CW 2000W',sequence_no:1}],
 agenda_items:[{topic:'Introduce JPT',sequence_no:1}]};
context.TripBriefingDraft.load('s1',record);context.TripBriefingForm.populate(record);
assert(root.innerHTML.includes('id="trip-briefing-save"'));
assert(root.innerHTML.includes('data-briefing-array-key="agenda_items"'));
assert(root.innerHTML.includes('data-briefing-array-key="channel_partner_companions"'));
assert(root.innerHTML.includes('data-field="company_name"'));
assert(root.innerHTML.includes('Euro Partner'));
(async()=>{await context.TripBriefingActions.save();
 assert.strictEqual(sent.planId,'p1');assert.strictEqual(sent.stopId,'s1');
 assert.strictEqual(sent.payload.row_version,3);assert.strictEqual(sent.payload.stop_row_version,7);
 for(const key of ['customer_team','contacts','channel_partner_companions','participants','equipment','agenda_items'])
   assert.deepStrictEqual(sent.payload[key],[],`${key} must be sent when cleared`);
 assert.strictEqual(sent.payload.timezone,null,'cleared timezone must be sent by full-replace save');
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_dirty_briefing_blocks_navigation_and_route_actions() -> None:
    itinerary_actions = _source("frontend/js/modules/trip-itinerary-actions.js")
    export_actions = _source("frontend/js/modules/trip-export-actions.js")
    plans = _source("frontend/js/modules/trip-plans.js")
    visit_state = _source("frontend/js/modules/trip-visit-state.js")
    for source, operation in (
        (itinerary_actions, "route preview/save"),
        (export_actions, "route export"),
        (plans, "plan switch"),
        (visit_state, "visit date/stop switch"),
    ):
        assert "TripBriefingDraft" in source and ".guard" in source, (
            f"dirty visit briefing must block {operation}"
        )

    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
let guarded=true,writes=0,downloads=0;
const p1={id:'p1',row_version:2,stops:[],legs:[]},p2={id:'p2',row_version:1,stops:[],legs:[]};
const context={console,State:{tripBusy:false,currentTripPlan:p1,tripPlans:[p1,p2]},
 document:{getElementById(){return null}},I18n:{t:v=>v},
 TripBriefingDraft:{guard(){return guarded}},TripFreeStopDraft:{guardRouteAction(){return false}},
 TripPlanningDraft:{get(){return{dirty:false}},revision(){return 1}},TripTransportActions:{cancelScheduledPreview(){}},
 TripRouteForm:{validationError(){return null}},readTripItineraryPayload(){return{stop_durations:{}}},
 setTripBusy(){},alert(){},notify(){},downloadBlob(){downloads+=1},handleTripError(error){throw error},
 populateTripPlanForm(){},renderCurrentTripPlan(){},renderTripPlans(){},renderTripMap(){},
 TripPlannerModule:{renderVisitExecution(){}},TripSuggestionState:{resetForPlan(){}},TripFreeStopForm:{isOpen(){return false}},
 ApiClient:{async previewTripItinerary(){writes+=1;return p1},async generateTripItinerary(){writes+=1;return p1},
   async exportTripPlan(){writes+=1;return{blob:{},filename:'x.csv'}},async getTripPlan(){writes+=1;return p2}}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-itinerary-actions.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-export-actions.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plans.js','utf8'),context);
(async()=>{await context.previewCurrentTripItinerary();await context.generateCurrentTripItinerary();
 await context.exportCurrentTripPlan('csv');await context.selectTripPlan('p2');
 assert.strictEqual(writes,0,'dirty briefing must block every route/navigation write or load');
 guarded=false;await context.selectTripPlan('p2');assert.strictEqual(writes,1);
})().catch(error=>{console.error(error);process.exit(1)});
""")


def main() -> None:
    check_batch4_assets_and_dom_contract()
    check_api_and_language_contract()
    check_duration_conversion_and_route_payload()
    check_schedule_items_are_sorted_and_all_kinds_render()
    check_half_day_summary_and_visit_location_linkage()
    check_map_uses_effective_visit_location()
    check_trip_execution_renders_final_chinese_labels()
    check_briefing_payload_is_full_replace_with_double_cas()
    check_dirty_briefing_blocks_navigation_and_route_actions()
    print("PASS: Batch 4 half-day schedule, briefing full replace, and dirty guards")


if __name__ == "__main__":
    main()
