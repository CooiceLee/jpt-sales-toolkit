"""Focused frontend contracts for Batch 3 free stops and transport suggestions."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def _node(script: str) -> None:
    subprocess.run(["node", "-e", script], cwd=ROOT, env=os.environ.copy(), check=True, text=True)


def check_static_contract() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    itinerary = (MODULES / "trip-itinerary-view.js").read_text(encoding="utf-8")
    planner = (MODULES / "trip-planner.js").read_text(encoding="utf-8")
    suggestions = (MODULES / "trip-suggestion-actions.js").read_text(encoding="utf-8")
    itinerary_actions = (MODULES / "trip-itinerary-actions.js").read_text(encoding="utf-8")
    export_actions = (MODULES / "trip-export-actions.js").read_text(encoding="utf-8")
    suggestion_view = (MODULES / "trip-suggestion-view.js").read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")

    for module in ("trip-free-stop-draft.js", "trip-free-stop-form.js", "trip-free-stop-actions.js", "trip-stop-removal-actions.js", "trip-suggestion-state.js",
                   "trip-suggestion-view.js", "trip-suggestion-actions.js"):
        assert module in index, module
    for field in ("trip-free-stop-category", "trip-free-stop-name", "trip-free-stop-address",
                  "trip-free-stop-city", "trip-free-stop-country", "trip-free-stop-lat",
                  "trip-free-stop-lng", "trip-free-stop-stay", "trip-free-stop-purpose",
                  "trip-free-stop-notes"):
        assert f'id="{field}"' in index, field
    assert "/free-stops`" in api and "/free-stops/${stopId}/archive" in api
    assert "method: 'DELETE'" not in api[api.index("async function addTripFreeStop"):api.index("async function updateTripStop")]
    assert "/transport-suggestions" in api
    assert "stop.stop_kind === 'free'" in itinerary
    assert "TripFreeStopActions.archive" in itinerary
    assert itinerary.count('oninput="TripTransportActions.stayChanged') == 2
    assert 'onchange="TripTransportActions.stayChanged' not in itinerary
    assert "stop?.stop_kind !== 'free'" in planner
    assert "force_refresh" in suggestions and "TripPlanningDraft.change" in suggestions
    assert suggestions.count("TripFreeStopDraft?.guardRouteAction") >= 2
    assert "generateTripItinerary" not in suggestions and "updateTripPlan" not in suggestions
    assert (itinerary_actions + export_actions).count("TripFreeStopDraft?.guardRouteAction") >= 2
    assert "TripFreeStopForm.payload" not in itinerary_actions
    assert 'target="_blank" rel="noopener noreferrer"' in suggestion_view
    for text in ("Add personal stop", "Personal stop", "Apply to draft", "Search travel options",
                 "Personal stop changes are not saved.",
                 "Save or cancel personal stop changes before continuing with the route.",
                 "This personal stop changed elsewhere. Latest data was loaded; reopen the editor and try again."):
        assert text in i18n


def check_free_stop_form_requires_explicit_location_confirmation() -> None:
    _node(r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert');
const ids = ['trip-free-stop-editor','trip-free-stop-editor-title','trip-free-stop-id','trip-free-stop-row-version',
 'trip-free-stop-category','trip-free-stop-stay','trip-free-stop-name','trip-free-stop-address','trip-free-stop-city',
 'trip-free-stop-country','trip-free-stop-postal','trip-free-stop-lat','trip-free-stop-lng','trip-free-stop-purpose',
 'trip-free-stop-notes','trip-free-stop-geocode-status','trip-free-stop-geocode-candidates','trip-free-stop-save','trip-free-stop-geocode'];
const elements = new Map(ids.map(id => [id, { id, value: '', hidden: false, innerHTML: '', textContent: '',
 className: '', disabled: false, tagName: id === 'trip-free-stop-category' ? 'SELECT' : 'INPUT',
 setAttribute(){}, addEventListener(event, callback){ this[`on${event}`] = callback; }, focus(){} }]));
elements.get('trip-free-stop-category').value = 'rest'; elements.get('trip-free-stop-stay').value = '1';
const context = { console, State: { currentTripPlan: { id: 'p1', stops: [] } },
 document: { readyState: 'complete', getElementById: id => elements.get(id) || null },
 I18n: { t: (text, params={}) => Object.entries(params).reduce((v,[k,x]) => v.replace(`{${k}}`,x),text) },
 escapeHtml: value => String(value ?? ''), confirm(){ return true; }, alert(message){ throw new Error(message); } };
context.window=context; vm.createContext(context);
for(const file of ['trip-duration.js','trip-free-stop-draft.js','trip-free-stop-form.js'])
 vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`,'utf8'),context);
context.TripFreeStopForm.open();
elements.get('trip-free-stop-name').value='Rest day in Lyon';
elements.get('trip-free-stop-city').value='Lyon'; elements.get('trip-free-stop-country').value='France';
assert.throws(() => context.TripFreeStopForm.payload(), /latitude and longitude/,
  'blank coordinates must not be coerced to 0,0');
context.TripFreeStopForm.renderCandidates([{lat:45.764,lng:4.8357,normalized_address:'Lyon, France',confidence:'medium'}],'Test');
assert.strictEqual(elements.get('trip-free-stop-lat').value,'','search must not silently choose a result');
context.TripFreeStopForm.chooseCandidate(0);
const payload=context.TripFreeStopForm.payload();
assert.strictEqual(payload.location_name,'Rest day in Lyon'); assert.strictEqual(payload.lat,45.764);
assert.strictEqual(payload.duration_half_days,2); assert.strictEqual(payload.category,'rest');
assert.strictEqual(context.TripFreeStopDraft.isDirty(),true,'choosing a candidate must dirty the editor');
const editable = ['trip-free-stop-category','trip-free-stop-stay','trip-free-stop-name','trip-free-stop-address',
 'trip-free-stop-city','trip-free-stop-country','trip-free-stop-postal','trip-free-stop-lat','trip-free-stop-lng',
 'trip-free-stop-purpose','trip-free-stop-notes'];
for (const id of editable) {
 context.TripFreeStopDraft.reset();
 const field = elements.get(id); const handler = field.tagName === 'SELECT' ? field.onchange : field.oninput;
 assert.strictEqual(typeof handler,'function',`${id} must have a dirty listener`); handler();
 assert.strictEqual(context.TripFreeStopDraft.isDirty(),true,`${id} must dirty the editor`);
}
assert.strictEqual(elements.get('trip-free-stop-lat').value, '');
assert.strictEqual(elements.get('trip-free-stop-lng').value, '');
assert.throws(() => context.TripFreeStopForm.payload(), /latitude and longitude/,
  'editing the searched address must invalidate the old coordinates');
assert.strictEqual(context.TripFreeStopForm.close(),true);
assert.strictEqual(context.TripFreeStopDraft.isDirty(),false,'cancel/close must clear dirty state');
""")


def check_free_stop_dirty_blocks_route_actions_and_clean_save_resyncs() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
let dirty=true,writes=0,closed=0,freePayloadReads=0,alerts=[];
const saved={id:'p1',row_version:8,stops:[{id:'f1',stop_kind:'free',row_version:4,stay_days:1}],legs:[]};
const context={console,State:{tripBusy:false,currentTripPlan:{...saved,row_version:7}},
 I18n:{t:value=>value},TripFreeStopDraft:{guardRouteAction(){if(!dirty)return false;alerts.push('blocked');return true}},
 TripFreeStopForm:{isOpen(){return true},close(options){assert.strictEqual(options.force,true);closed+=1},
  payload(){freePayloadReads+=1;throw new Error('free-stop payload must remain independent')}},
 TripTransportActions:{cancelScheduledPreview(){}},TripPlanningDraft:{revision(){return 1},get(){return{dirty:false}}},
 TripRouteForm:{validationError(){return null}},readTripItineraryPayload(){return{title:'Route only'}},
 setTripBusy(value){context.State.tripBusy=value},populateTripPlanForm(){},renderCurrentTripPlan(){},
 renderTripPlans(){},renderTripMap(){},TripPlannerModule:{renderVisitExecution(){}},notify(){},
 alert(message){alerts.push(message)},downloadBlob(){},handleTripError(){throw new Error('unexpected error')},
 ApiClient:{async generateTripItinerary(planId,payload){writes+=1;assert.strictEqual(planId,'p1');
   assert.strictEqual(payload.title,'Route only');assert.strictEqual('location_name' in payload,false);return saved},
  async exportTripPlan(){writes+=1;return{blob:{},filename:'route.csv'}}}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-itinerary-actions.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-export-actions.js','utf8'),context);
(async()=>{
 await context.generateCurrentTripItinerary();await context.exportCurrentTripPlan('csv');
 assert.strictEqual(writes,0,'dirty personal-stop editor must block route save and export');
 dirty=false;await context.generateCurrentTripItinerary();
 assert.strictEqual(writes,1);assert.strictEqual(closed,1,'successful route save must close a clean editor');
 assert.strictEqual(freePayloadReads,0,'route save must never read or merge the personal-stop form');
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_free_stop_conflict_reloads_and_closes_editor() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
let updates=0,reloads=0,closed=0,message='';
const conflict=new Error('conflict');conflict.name='ConflictError';
const context={console:{error(){},log(){}},State:{tripBusy:false,currentTripPlan:{id:'p1',stops:[{id:'f1',stop_kind:'free'}]},tripPlans:[]},
 I18n:{t:value=>value},TripFreeStopDraft:{isDirty(){return true},confirmDiscard(){return true}},
 TripFreeStopForm:{payload(){return{location_name:'Hotel',lat:1,lng:2,stay_days:1}},editingId(){return'f1'},
  rowVersion(){return 2},setBusy(){},close(options){assert.strictEqual(options.force,true);closed+=1}},
 ApiClient:{async updateTripFreeStop(){updates+=1;throw conflict}},async loadTripPlanner(){reloads+=1},
 setTripBusy(value){context.State.tripBusy=value},renderTripPlans(){},renderCurrentTripPlan(){},renderTripMap(){},
 populateTripPlanForm(){},TripPlannerModule:{renderVisitExecution(){}},TripTransportActions:{schedulePreview(){}},
 notify(){},alert(value){message=value},handleTripError(){throw new Error('ConflictError must use recovery path')}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-free-stop-actions.js','utf8'),context);
(async()=>{await context.TripFreeStopActions.save();
 assert.strictEqual(updates,1);assert.strictEqual(reloads,1);assert.strictEqual(closed,1);
 assert(message.includes('reopen the editor'),'conflict must instruct the user to reopen fresh data');
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_successful_plan_switch_clears_free_stop_dirty() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');let dirty=true,closed=0;
const p1={id:'p1',title:'One',stops:[],legs:[]},p2={id:'p2',title:'Two',stops:[],legs:[]};
const context={console,State:{currentTripPlan:p1,tripPlans:[p1,p2]},document:{getElementById(){return null}},
 I18n:{t:value=>value},TripTransportView:{render(){}},TripSuggestionState:{resetForPlan(){}},
 TripFreeStopDraft:{isDirty(){return dirty},confirmDiscard(){return true}},
 TripFreeStopForm:{close(options){assert.strictEqual(options.force,true);dirty=false;closed+=1}},confirm(){return true},
 ApiClient:{async getTripPlan(){return p2}},renderCurrentTripPlan(){},renderTripMap(){},
 TripPlannerModule:{renderVisitExecution(){}}};context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-planning-draft.js','utf8'),context);
context.TripPlanningDraft.hydrate(p1,{committed:true});closed=0;
context.populateTripPlanForm=(plan,options={})=>context.TripPlanningDraft.hydrate(plan,options);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plans.js','utf8'),context);
(async()=>{await context.selectTripPlan('p2');assert.strictEqual(context.State.currentTripPlan.id,'p2');
 assert.strictEqual(dirty,false);assert.strictEqual(closed,1,'successful plan switch must close and clear the editor');
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_suggestion_apply_is_draft_only() -> None:
    _node(r"""
const fs=require('fs'); const vm=require('vm'); const assert=require('assert');
const roots={ 'trip-suggest-route':{disabled:false,textContent:'',setAttribute(){}},
 'trip-suggestion-status':{textContent:''}, 'trip-leg-suggestions-0':{innerHTML:''} };
let writes=0; const plan={id:'p1',stops:[{id:'a',stay_days:1}],legs:[{leg_key:'origin>a',from_label:'PVG',to_label:'Lyon'}]};
const context={console,Date,URL,encodeURIComponent,decodeURIComponent,
 State:{currentTripPlan:plan}, document:{getElementById:id=>roots[id]||null},
 I18n:{t:(text,params={})=>{const zh={Low:'低','Local estimate':'本地估算'};let value=zh[text]||text;
   return Object.entries(params).reduce((v,[k,x])=>v.replace(`{${k}}`,x),value)},locale:()=> 'zh-CN'},
 escapeHtml:value=>String(value??'').replaceAll('&','&amp;').replaceAll('"','&quot;'),
 TripTransportView:{render(){}}, notify(){}, alert(message){throw new Error(message)},
 ApiClient:new Proxy({}, {get(){return ()=>{writes+=1}}}), readTripItineraryPayload(){return{};} };
context.window=context; vm.createContext(context);
for(const file of ['trip-duration.js','trip-suggestion-state.js','trip-planning-draft.js','trip-suggestion-view.js','trip-suggestion-actions.js'])
 vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`,'utf8'),context);
context.TripPlanningDraft.hydrate(plan,{committed:true}); const rev=context.TripPlanningDraft.revision();
const req=context.TripSuggestionState.begin('p1',rev,'origin>a');
context.TripSuggestionState.succeed(req,{generated_at:'2026-08-21T08:00:00Z',suggestions:[{
 suggestion_id:'s1',leg_key:'origin>a',mode:'flight',distance_km:9200,time_hours:12.5,travel_days:1,
 provider:'Local estimate',online:false,approximate:true,confidence:'low',fetched_at:'2026-08-21T08:00:00Z',
 search_url:'https://www.google.com/travel/flights',requires_manual_confirmation:true}]});
context.TripSuggestionView.render(plan);
assert(roots['trip-leg-suggestions-0'].innerHTML.includes('rel="noopener noreferrer"'));
assert(roots['trip-leg-suggestions-0'].innerHTML.includes('低'),'lowercase backend confidence must render through the bilingual enum');
context.TripSuggestionActions.apply(encodeURIComponent('s1'));
const override=context.TripPlanningDraft.get().legOverrides['origin>a'];
assert.strictEqual(override.selected_mode,'flight'); assert.strictEqual(override.mode_locked,true);
assert.strictEqual(override.manual_time_hours,12.5); assert.strictEqual(context.TripPlanningDraft.get().dirty,true);
assert.strictEqual(writes,0,'Apply must not call any API write');
const before=JSON.stringify(context.TripPlanningDraft.get().legOverrides);
context.TripFreeStopDraft={guardRouteAction(){return true}};
context.TripSuggestionActions.apply(encodeURIComponent('s1'));
assert.strictEqual(JSON.stringify(context.TripPlanningDraft.get().legOverrides),before,
 'dirty personal-stop editor must block applying a stale route suggestion');
""")


def check_removing_final_free_stop_does_not_strand_dirty_draft() -> None:
    _node(r"""
const fs=require('fs'); const vm=require('vm'); const assert=require('assert');
const stop={id:'f1',stop_kind:'free',location_name:'Rest',stay_days:1,row_version:2};
const plan={id:'p1',row_version:4,stops:[stop],legs:[]}; let previews=0;
const context={console, State:{currentTripPlan:plan,tripPlans:[{id:'p1',stop_count:1}],tripBusy:false},
 document:{getElementById(){return null;}}, TripTransportView:{render(){}},
 I18n:{t:(text,params={})=>Object.entries(params).reduce((v,[k,x])=>v.replace(`{${k}}`,x),text)},
 confirm(){return true}, notify(){}, setTripBusy(){}, renderTripPlans(){}, renderCurrentTripPlan(){}, renderTripMap(){},
 TripPlannerModule:{renderVisitExecution(){}}, TripTransportActions:{schedulePreview(){previews+=1}},
 TripFreeStopForm:{setBusy(){},close(){},editingId(){return''}},
 TripFreeStopDraft:{isDirty(){return false},confirmDiscard(){return true}}, handleTripError(){},
 ApiClient:{async archiveTripFreeStop(){return{id:'p1',row_version:5,stops:[],legs:[]}}} };
context.window=context; vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-planning-draft.js','utf8'),context);
context.populateTripPlanForm=(next,options={})=>context.TripPlanningDraft.hydrate(next,options);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-free-stop-actions.js','utf8'),context);
context.TripPlanningDraft.hydrate(plan,{committed:true}); context.TripPlanningDraft.change(d=>{d.header.title='Unsaved'});
(async()=>{await context.TripFreeStopActions.archive('f1');
 assert.strictEqual(context.State.currentTripPlan.stops.length,0);
 assert.strictEqual(context.TripPlanningDraft.get().dirty,false,'empty plan must return to a clean state');
 assert.strictEqual(previews,0,'empty plan cannot be previewed');
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_closed_geocode_request_cannot_lock_or_overwrite_new_editor() -> None:
    _node(r"""
const fs=require('fs'); const vm=require('vm'); const assert=require('assert');
const ids=['trip-free-stop-editor','trip-free-stop-editor-title','trip-free-stop-id','trip-free-stop-row-version',
 'trip-free-stop-category','trip-free-stop-stay','trip-free-stop-name','trip-free-stop-address','trip-free-stop-city',
 'trip-free-stop-country','trip-free-stop-postal','trip-free-stop-lat','trip-free-stop-lng','trip-free-stop-purpose',
 'trip-free-stop-notes','trip-free-stop-geocode-status','trip-free-stop-geocode-candidates','trip-free-stop-save','trip-free-stop-geocode'];
const elements=new Map(ids.map(id=>[id,{value:'',hidden:false,innerHTML:'',textContent:'',className:'',disabled:false,
 setAttribute(){},addEventListener(){},focus(){}}])); elements.get('trip-free-stop-stay').value='1';
let resolveSearch; const deferred=new Promise(resolve=>{resolveSearch=resolve});
const context={console,navigator:{onLine:true},State:{currentTripPlan:{id:'p1',stops:[]},tripBusy:false},
 document:{readyState:'complete',getElementById:id=>elements.get(id)||null},
 I18n:{t:value=>value},escapeHtml:value=>String(value??''),alert(message){throw new Error(message)},
 ApiClient:{searchGeocode(){return deferred}},setTripBusy(){},handleTripError(){},confirm(){return true}};
context.window=context; vm.createContext(context);
for(const file of ['trip-duration.js','trip-free-stop-form.js','trip-free-stop-actions.js'])
 vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`,'utf8'),context);
context.TripFreeStopForm.open(); elements.get('trip-free-stop-city').value='Lyon';
(async()=>{const pending=context.TripFreeStopActions.searchPosition();
 assert.strictEqual(elements.get('trip-free-stop-save').disabled,true);
 context.TripFreeStopForm.close(); context.TripFreeStopForm.open();
 assert.strictEqual(elements.get('trip-free-stop-save').disabled,false,'new editor must not inherit old request lock');
 resolveSearch({provider:'Old',candidates:[{lat:45.7,lng:4.8,normalized_address:'Old Lyon'}]}); await pending;
 assert.strictEqual(elements.get('trip-free-stop-geocode-candidates').innerHTML,'','old result must not overwrite new editor');
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_removing_final_customer_stop_does_not_strand_dirty_draft() -> None:
    _node(r"""
const fs=require('fs'); const vm=require('vm'); const assert=require('assert');
const stop={id:'c1',stop_kind:'customer',customer_name:'Demo customer',stay_days:1,row_version:2};
const plan={id:'p1',row_version:4,stops:[stop],legs:[]}; let previews=0,archives=0,closed=0,blocked=true;
const context={console,State:{currentTripPlan:plan,tripBusy:false,tripCandidatePagination:{offset:0}},
 document:{getElementById(){return null;}},TripTransportView:{render(){}},
 TripTransportActions:{cancelScheduledPreview(){},schedulePreview(){}},I18n:{t:(text,params={})=>Object.entries(params).reduce((v,[k,x])=>v.replace(`{${k}}`,x),text)},
 confirm(){return true},notify(){},setTripBusy(){},handleTripError(){},async loadTripPlanner(){},
 TripFreeStopDraft:{guardRouteAction(){return blocked}},
 TripFreeStopForm:{isOpen(){return true},close(options){assert.strictEqual(options.force,true);closed+=1}},
 ApiClient:{async archiveTripStop(){archives+=1;return{id:'p1',row_version:5,stops:[],legs:[]}}},
 previewCurrentTripItinerary(){previews+=1}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js','utf8'),context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-planning-draft.js','utf8'),context);
context.populateTripPlanForm=(next,options={})=>context.TripPlanningDraft.hydrate(next,options);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-stop-removal-actions.js','utf8'),context);
context.TripPlanningDraft.hydrate(plan,{committed:true});closed=0;
context.TripPlanningDraft.change(d=>{d.header.title='Unsaved'});
(async()=>{await context.removeTripStop('c1');
 assert.strictEqual(archives,0,'dirty personal-stop editor must block customer-stop removal');
 blocked=false;await context.removeTripStop('c1');
 assert.strictEqual(context.State.currentTripPlan.stops.length,0);
 assert.strictEqual(context.TripPlanningDraft.get().dirty,false,'empty customer plan must return clean');
 assert.strictEqual(previews,0);assert.strictEqual(closed,1,'successful removal must close a clean stale editor');
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_dynamic_schedule_is_bilingual() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const pairs={'{start} to {end}':'{start} 至 {end}','From {location}: {mode}, {distance} km, {hours}h':'从 {location} 出发：{mode}，{distance} 公里，{hours} 小时','Drive':'驾车','Not scheduled':'尚未排程'};
const context={console,document:{getElementById(){return null},querySelectorAll(){return[]}},escapeHtml:v=>String(v??''),
 I18n:{t:(text,params={})=>Object.entries(params).reduce((value,[key,item])=>value.replace(`{${key}}`,item),pairs[text]||text)}};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-itinerary-view.js','utf8'),context);
const output=context.formatTripStopSchedule({planned_date:'2026-09-15',planned_end_date:'2026-09-16',travel_from_label:'巴黎',travel_mode:'drive',travel_distance_km:20,travel_time_hours:1});
assert(output.includes('2026-09-15 至 2026-09-16'));assert(output.includes('从 巴黎 出发：驾车，20 公里，1 小时'));
assert(!output.includes('From ')&&!output.includes(' to '));
""")


def check_inline_stays_survive_preview_reorder_and_same_plan_refresh() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const elements=new Map([
 ['trip-current-plan',{innerHTML:''}],['trip-route-order-mode',{value:'auto'}],
 ['stop-stay-c1',{value:'3'}],['stop-stay-f1',{value:'2'}],['stop-stay-c2',{value:'1'}],
]);
const initial={id:'p1',row_version:1,route_order_mode:'auto',legs:[],stops:[
 {id:'c1',stop_kind:'customer',sequence_no:1,customer_name:'Customer one',stay_days:1},
 {id:'f1',stop_kind:'free',sequence_no:2,location_name:'Rest stop',category:'hotel',stay_days:1},
 {id:'c2',stop_kind:'customer',sequence_no:3,customer_name:'Customer two',stay_days:1},
]};
const context={console,State:{tripBusy:false,currentTripPlan:initial,tripCandidatePagination:{limit:25,offset:0}},
 document:{getElementById:id=>elements.get(id)||null,querySelectorAll(){return[]}},
 I18n:{t:(text,params={})=>Object.entries(params).reduce((value,[key,item])=>value.replace(`{${key}}`,item),text)},
 escapeHtml:value=>String(value??''),TripTransportView:{render(){}},TripTransportActions:{schedulePreview(){}},
 TripPlannerModule:{renderVisitExecution(){}},notify(){},renderTripMap(){},
 setInputValue(id,value){const item=elements.get(id);if(item)item.value=value;},
 numericOrNull(value){if(value===''||value==null)return null;const number=Number(value);return Number.isFinite(number)?number:null;},
 parseHolidayInput(){return[]},tripDateTimeLocalValue(value){return value||''}};
context.window=context;vm.createContext(context);
for(const file of ['trip-duration.js','trip-stop-schedule-controls.js','trip-form.js','trip-stop-duration-payload.js','trip-planning-draft.js','trip-itinerary-view.js','trip-itinerary-actions.js'])
 vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`,'utf8'),context);
context.populateTripPlanForm(initial,{committed:true});

// Playwright fill/input semantics: the visible value changed, but no onchange
// callback is invoked before the explicit preview action reads the form.
const payload=context.readTripItineraryPayload();
assert.strictEqual(payload.stop_durations.c1.half_days,6);assert.strictEqual(payload.stop_durations.f1.half_days,4);
assert.strictEqual(context.TripPlanningDraft.get().stopDurations.c1.half_days,6);
assert.strictEqual(context.TripPlanningDraft.get().stopDurations.f1.half_days,4,
 'preview form read must synchronize the durable in-memory route draft');

const revision=context.TripPlanningDraft.revision();
const preview={...initial,itinerary_preview:true,stops:initial.stops.map(stop=>({
 ...stop,stay_days:stop.id==='c1'?3:stop.id==='f1'?2:1,
 planned_date:'2026-09-20',planned_end_date:stop.id==='f1'?'2026-09-21':'2026-09-20'}))};
context.State.currentTripPlan=preview;
assert.strictEqual(context.TripPlanningDraft.previewApplied(preview,revision),true);
context.populateTripPlanForm(preview);
context.renderCurrentTripPlan();
assert(elements.get('trip-current-plan').innerHTML.includes('id="stop-stay-c1" value="3"'));
assert(elements.get('trip-current-plan').innerHTML.includes('id="stop-stay-f1"\n                value="2"'));

(async()=>{
 await context.moveTripStop('f1',1);
 assert.deepStrictEqual(context.State.currentTripPlan.stops.map(stop=>stop.id),['c1','c2','f1']);
 assert.strictEqual(context.TripPlanningDraft.get().stopDurations.f1.half_days,4,'free-stop stay must survive move');
 await context.moveTripStop('c1',1);
 assert.deepStrictEqual(context.State.currentTripPlan.stops.map(stop=>stop.id),['c2','c1','f1']);
 assert.strictEqual(context.TripPlanningDraft.get().stopDurations.c1.half_days,6,'customer-stop stay must survive move');

 // A same-plan server refresh can still contain the saved value 1. Reconcile
 // must retain the unsaved draft values and the next route-card render.
 const stale={...context.State.currentTripPlan,stops:context.State.currentTripPlan.stops.map(stop=>({...stop,stay_days:1}))};
 context.State.currentTripPlan=stale;context.populateTripPlanForm(stale);context.renderCurrentTripPlan();
 assert.strictEqual(context.TripPlanningDraft.get().stopDurations.c1.half_days,6);
 assert.strictEqual(context.TripPlanningDraft.get().stopDurations.f1.half_days,4);
 const html=elements.get('trip-current-plan').innerHTML;
 assert(html.includes('id="stop-stay-c1" value="3"'));
 assert(html.includes('id="stop-stay-f1"\n                value="2"'));
})().catch(error=>{console.error(error);process.exit(1)});
""")


def check_visible_route_header_wins_before_save() -> None:
    _node(r"""
const fs=require('fs');const vm=require('vm');const assert=require('assert');
const elements=new Map([
 ['trip-title',{value:'Visible title'}],['trip-start-date',{value:'2026-09-15'}],
 ['trip-end-date',{value:'2026-09-30'}],['trip-plan-region',{value:'EU'}],
 ['trip-origin-name',{value:'PVG'}],['trip-origin-lat',{value:'31.1443'}],
 ['trip-origin-lng',{value:'121.8083'}],['trip-destination-name',{value:'PVG'}],
 ['trip-destination-lat',{value:'31.1443'}],['trip-destination-lng',{value:'121.8083'}],
 ['trip-avoid-weekends',{checked:true}],['trip-holidays',{value:''}],
 ['trip-description',{value:'Visible unsaved planning note'}],
 ['trip-route-order-mode',{value:'auto'}],['trip-departure-window-start',{value:''}],
 ['trip-departure-window-end',{value:''}],['trip-return-window-start',{value:''}],
 ['trip-return-window-end',{value:''}],
]);
const context={console,State:{currentTripPlan:{stops:[]}},document:{getElementById:id=>elements.get(id)||null},
 numericOrNull:value=>value===''?null:Number(value),parseHolidayInput:()=>[]};
context.window=context;context.TripPlanningDraft={get:()=>({header:{title:'Stale title',description:null},routeOrderMode:'auto',transportModePriority:['flight'],departureWindowStart:'',departureWindowEnd:'',returnWindowStart:'',returnWindowEnd:''}),itineraryPayload:()=>({title:'Stale title',description:null,route_order_mode:'auto',transport_mode_priority:['flight']})};
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/js/modules/trip-form.js','utf8'),context);vm.runInContext(fs.readFileSync('frontend/js/modules/trip-stop-duration-payload.js','utf8'),context);
const payload=context.readTripItineraryPayload();
assert.strictEqual(payload.title,'Visible title');
assert.strictEqual(payload.description,'Visible unsaved planning note');
assert.strictEqual(payload.start_date,'2026-09-15');
""")


def main() -> None:
    check_static_contract()
    check_free_stop_form_requires_explicit_location_confirmation()
    check_free_stop_dirty_blocks_route_actions_and_clean_save_resyncs()
    check_free_stop_conflict_reloads_and_closes_editor()
    check_successful_plan_switch_clears_free_stop_dirty()
    check_suggestion_apply_is_draft_only()
    check_removing_final_free_stop_does_not_strand_dirty_draft()
    check_closed_geocode_request_cannot_lock_or_overwrite_new_editor()
    check_removing_final_customer_stop_does_not_strand_dirty_draft()
    check_dynamic_schedule_is_bilingual()
    check_inline_stays_survive_preview_reorder_and_same_plan_refresh()
    check_visible_route_header_wins_before_save()
    print("PASS: Batch 3 free-stop and transport-suggestion frontend contracts")


if __name__ == "__main__":
    main()
