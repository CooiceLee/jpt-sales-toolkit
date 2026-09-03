/** Trip Planner visit execution surface. */
(function() {
    const h = value => window.TripVisitState.escape(value);
    const t = (key, params = {}) => I18n.t(key, params);

    function renderVisitExecution(plan) {
        const container = document.getElementById('trip-visit-execution');
        if (!container) return;
        if (!plan) {
            container.innerHTML = window.JPTRender?.empty(t('Create or select a plan')) || '';
            return;
        }
        const days = window.TripVisitState.planDays(plan);
        const activeDate = window.TripVisitState.currentDateForPlan(plan);
        const customerStops = (plan.stops || []).filter(stop => stop?.stop_kind !== 'free');
        const stops = customerStops.filter(stop => window.TripVisitState.stopMatchesDay(stop, activeDate))
            .sort(window.TripVisitState.compareStops || ((left, right) => Number(left.sequence_no || 0) - Number(right.sequence_no || 0)));
        if (!customerStops.length) {
            container.innerHTML = window.JPTRender?.empty(
                t(plan.stops?.length ? 'This plan has personal stops but no customer visits.' : 'Add stops before using visit execution')
            ) || '';
            return;
        }

        container.innerHTML = `
            <div class="visit-day-toolbar">
                <select class="form-input" id="trip-execution-date" onchange="TripVisitState.setVisitDate(this.value)" ${days.length ? '' : 'disabled'}>
                    ${days.length
                        ? days.map(day => `<option value="${day}" ${day === activeDate ? 'selected' : ''}>${day}</option>`).join('')
                        : `<option value="">${h(t('Unscheduled stops'))}</option>`}
                </select>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripPlannerModule.exportVisitDay()">${h(t('Export day report'))}</button>
            </div>
            ${stops.length ? stops.map(renderStopExecution).join('') : `<div class="empty-state compact">${h(t('No stops on this date'))}</div>`}
        `;
    }

    function renderStopExecution(stop) {
        const customerPersonnel = window.TripVisitState.customerPersonnelLine(stop);
        const channelPartners = window.TripVisitState.channelPartnerLine(stop);
        const internalParticipants = window.TripVisitState.internalParticipantsLine(stop);
        const address = window.TripVisitState.addressLine(stop);
        const lead = [stop.lead_display_id, stop.lead_title, stop.sales_stage].filter(Boolean).join(' · ');
        return `
            <div class="visit-card" id="visit-card-${h(stop.id)}" data-stop-id="${h(stop.id)}"
                oninput="TripVisitDraft.mark('${h(stop.id)}')" onchange="TripVisitDraft.mark('${h(stop.id)}')">
                <div class="visit-card-head">
                    <div>
                        <strong>${h(stop.sequence_no)}. ${h(stop.customer_name)}</strong>
                        <small>${h(TripVisitState.scheduleLabel?.(stop)
                            || [stop.planned_date, stop.planned_end_date].filter(Boolean).join(' to ')
                            || t('No scheduled date'))}</small>
                    </div>
                    <span class="score-pill">${h(t(stop.result_status || 'Planned'))}</span>
                </div>
                <div class="visit-prep-head">
                    <span>${h(t('From visit preparation'))}</span>
                    <button type="button" class="btn btn-secondary btn-sm"
                        onclick="TripBriefingActions.open('${h(stop.id)}')">${h(t(
                        customerPersonnel || channelPartners || internalParticipants
                            ? 'Edit visit preparation' : 'Fill in visit preparation'
                    ))}</button>
                </div>
                <div class="visit-info-grid">
                    ${window.JPTRender.field(t('Customer personnel'), customerPersonnel)}
                    ${window.JPTRender.field(t('Channel partner companions'), channelPartners)}
                    ${window.JPTRender.field(t('JPT internal participants'), internalParticipants)}
                    ${window.JPTRender.field(t('Address'), address)}
                    ${window.JPTRender.field(t('Lead'), lead)}
                    ${window.JPTRender.field(t('Visit topics'), window.TripVisitState.agendaLine(stop))}
                </div>
                <div class="visit-template-grid">
                    <textarea class="form-input" rows="2" id="visit-needs-${h(stop.id)}" placeholder="${h(t('Customer needs'))}">${h(stop.visit_customer_needs || '')}</textarea>
                    <input type="text" class="form-input" id="visit-competitor-${h(stop.id)}" value="${h(stop.visit_competitor || '')}" placeholder="${h(t('Competitor'))}">
                    <input type="text" class="form-input" id="visit-budget-${h(stop.id)}" value="${h(stop.visit_budget || '')}" placeholder="${h(t('Budget'))}">
                    <input type="text" class="form-input" id="visit-decision-${h(stop.id)}" value="${h(stop.visit_decision_maker || '')}" placeholder="${h(t('Decision maker'))}">
                    <textarea class="form-input" rows="2" id="visit-next-${h(stop.id)}" placeholder="${h(t('Next action'))}">${h(stop.visit_next_action || '')}</textarea>
                    <input type="date" class="form-input" id="visit-due-${h(stop.id)}" value="${h(stop.visit_followup_due_date || '')}">
                    <select class="form-input" id="visit-status-${h(stop.id)}">
                        ${['Planned', 'Visited', 'Follow-up Needed', 'Skipped'].map(status =>
                            `<option value="${status}" ${stop.result_status === status ? 'selected' : ''}>${h(t(status))}</option>`
                        ).join('')}
                    </select>
                    <textarea class="form-input" rows="2" id="visit-result-${h(stop.id)}" placeholder="${h(t('Meeting notes'))}">${h(stop.result_notes || '')}</textarea>
                </div>
                <div class="visit-check-row">
                    <label class="trip-field"><span>${h(t('Actually visited on'))}</span>
                        <input type="date" class="form-input" id="visit-actual-date-${h(stop.id)}" value="${h(stop.actual_visit_date || '')}">
                    </label>
                    <label class="trip-field"><span>${h(t('Half-day'))}</span>
                        ${TripVisitAnswer.period(stop)}
                    </label>
                    <label class="trip-field"><span>${h(t('Sample needed'))}</span>
                        ${TripVisitAnswer.answer(`visit-sample-${stop.id}`, stop.visit_sample_needed)}
                    </label>
                    <label class="trip-field"><span>${h(t('Quote needed'))}</span>
                        ${TripVisitAnswer.answer(`visit-quote-${stop.id}`, stop.visit_quote_needed)}
                    </label>
                </div>
                <div class="visit-action-row">
                    <button type="button" class="btn btn-primary btn-sm" onclick="TripPlannerModule.saveVisitExecution('${h(stop.id)}')">${h(t('Save visit'))}</button>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="TripVisitDraft.discard('${h(stop.id)}')">${h(t('Discard edits'))}</button>
                    <input type="file" class="form-input visit-file-input" id="visit-file-${h(stop.id)}" multiple ${stop.lead_id ? '' : 'disabled'}>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="TripPlannerModule.uploadVisitAttachment('${h(stop.id)}')" ${stop.lead_id ? '' : 'disabled'}>${h(t('Upload files'))}</button>
                </div>
            </div>
        `;
    }

    function refreshVisitCard(plan, stopId) {
        const card = document.getElementById(`visit-card-${stopId}`);
        const stop = (plan?.stops || []).find(item => item.id === stopId);
        if (!card || !stop) {
            renderVisitExecution(plan);
            return;
        }
        card.outerHTML = renderStopExecution(stop);
    }

    window.TripPlannerModule = { renderVisitExecution, refreshVisitCard };
})();
