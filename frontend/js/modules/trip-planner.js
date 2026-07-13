/** Trip Planner visit execution surface. */
(function() {
    const h = value => window.TripVisitState.escape(value);

    function renderVisitExecution(plan) {
        const container = document.getElementById('trip-visit-execution');
        if (!container) return;
        if (!plan) {
            container.innerHTML = window.JPTRender?.empty('Create or select a plan') || '';
            return;
        }
        const days = window.TripVisitState.planDays(plan);
        const activeDate = window.TripVisitState.currentDateForPlan(plan);
        const stops = (plan.stops || []).filter(stop => window.TripVisitState.stopMatchesDay(stop, activeDate));
        if (!plan.stops?.length) {
            container.innerHTML = window.JPTRender?.empty('Add stops before using visit execution') || '';
            return;
        }

        container.innerHTML = `
            <div class="visit-day-toolbar">
                <select class="form-input" id="trip-execution-date" onchange="TripVisitState.setVisitDate(this.value)" ${days.length ? '' : 'disabled'}>
                    ${days.length
                        ? days.map(day => `<option value="${day}" ${day === activeDate ? 'selected' : ''}>${day}</option>`).join('')
                        : '<option value="">Unscheduled stops</option>'}
                </select>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripPlannerModule.exportVisitDay()">Export day report</button>
            </div>
            ${stops.length ? stops.map(renderStopExecution).join('') : '<div class="empty-state compact">No stops on this date</div>'}
        `;
    }

    function renderStopExecution(stop) {
        const contact = window.TripVisitState.contactLine(stop);
        const address = window.TripVisitState.addressLine(stop);
        const lead = [stop.lead_display_id, stop.lead_title, stop.sales_stage].filter(Boolean).join(' · ');
        return `
            <div class="visit-card" data-stop-id="${h(stop.id)}">
                <div class="visit-card-head">
                    <div>
                        <strong>${h(stop.sequence_no)}. ${h(stop.customer_name)}</strong>
                        <small>${h([stop.planned_date, stop.planned_end_date].filter(Boolean).join(' to ') || 'No scheduled date')}</small>
                    </div>
                    <span class="score-pill">${h(stop.result_status || 'Planned')}</span>
                </div>
                <div class="visit-info-grid">
                    ${window.JPTRender.field('Contact', contact)}
                    ${window.JPTRender.field('Address', address)}
                    ${window.JPTRender.field('Lead', lead)}
                    ${window.JPTRender.field('Purpose', stop.visit_purpose)}
                </div>
                <div class="visit-template-grid">
                    <textarea class="form-input" rows="2" id="visit-needs-${h(stop.id)}" placeholder="Customer needs">${h(stop.visit_customer_needs || '')}</textarea>
                    <input type="text" class="form-input" id="visit-competitor-${h(stop.id)}" value="${h(stop.visit_competitor || '')}" placeholder="Competitor">
                    <input type="text" class="form-input" id="visit-budget-${h(stop.id)}" value="${h(stop.visit_budget || '')}" placeholder="Budget">
                    <input type="text" class="form-input" id="visit-decision-${h(stop.id)}" value="${h(stop.visit_decision_maker || '')}" placeholder="Decision maker">
                    <textarea class="form-input" rows="2" id="visit-next-${h(stop.id)}" placeholder="Next action">${h(stop.visit_next_action || '')}</textarea>
                    <input type="date" class="form-input" id="visit-due-${h(stop.id)}" value="${h(stop.visit_followup_due_date || '')}">
                    <select class="form-input" id="visit-status-${h(stop.id)}">
                        ${['Planned', 'Visited', 'Follow-up Needed', 'Skipped'].map(status =>
                            `<option value="${status}" ${stop.result_status === status ? 'selected' : ''}>${status}</option>`
                        ).join('')}
                    </select>
                    <textarea class="form-input" rows="2" id="visit-result-${h(stop.id)}" placeholder="Meeting notes">${h(stop.result_notes || '')}</textarea>
                </div>
                <div class="visit-check-row">
                    <label class="trip-check"><input type="checkbox" id="visit-sample-${h(stop.id)}" ${stop.visit_sample_needed ? 'checked' : ''}> <span>Sample needed</span></label>
                    <label class="trip-check"><input type="checkbox" id="visit-quote-${h(stop.id)}" ${stop.visit_quote_needed ? 'checked' : ''}> <span>Quote needed</span></label>
                </div>
                <div class="visit-action-row">
                    <button type="button" class="btn btn-primary btn-sm" onclick="TripPlannerModule.saveVisitExecution('${h(stop.id)}')">Save visit</button>
                    <input type="file" class="form-input visit-file-input" id="visit-file-${h(stop.id)}" multiple ${stop.lead_id ? '' : 'disabled'}>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="TripPlannerModule.uploadVisitAttachment('${h(stop.id)}')" ${stop.lead_id ? '' : 'disabled'}>Upload files</button>
                </div>
            </div>
        `;
    }

    window.TripPlannerModule = { renderVisitExecution };
})();
