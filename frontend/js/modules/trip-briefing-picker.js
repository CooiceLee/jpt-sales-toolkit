/** Which visit is being prepared, chosen beside the editor that prepares it.
 *
 * The preparation editor used to sit inside the daily schedule, so choosing a
 * visit meant reading a timetable - travel legs, personal stops, half-day
 * boxes - to find the one customer whose preparation was unfinished. The
 * schedule answers "what does the trip look like"; this answers "which visit
 * am I preparing", and the two are different questions.
 *
 * It lists only customer visits: personal stops are arranged in the route, not
 * prepared for. Each row says the four things a reader picks on - who, when,
 * who from JPT is going, and whether the visit is confirmed - and selection
 * goes through TripBriefingActions.open, which owns the draft guard.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const h = value => escapeHtml(value ?? '');

    const STATUS = Object.freeze({
        unconfirmed: 'Unconfirmed', tentative: 'Tentative', confirmed: 'Confirmed',
        needs_reconfirmation: 'Needs reconfirmation', cancelled: 'Cancelled',
    });

    function visits(plan) {
        return (plan?.stops || []).filter(stop => (stop.stop_kind || 'customer') !== 'free');
    }

    function when(stop) {
        const start = [stop.planned_date, stop.planned_start_period].filter(Boolean).join(' ');
        return start || tr('Not scheduled');
    }

    // Who is going, in the words the rest of the page uses: naming nobody means
    // the whole team goes, which is not the same as nobody going.
    function going(stop) {
        return window.TripVisitState?.internalParticipantsLine?.(stop) || tr('Whole team');
    }

    function status(stop) {
        const key = stop.briefing?.confirmation_status || stop.confirmation_status;
        return tr(STATUS[key] || STATUS.unconfirmed);
    }

    function row(stop, openStopId) {
        const active = stop.id === openStopId;
        return `
            <button type="button" class="trip-briefing-pick${active ? ' active' : ''}"
                data-briefing-pick="${h(stop.id)}" ${active ? 'aria-current="true"' : ''}
                onclick="TripBriefingPicker.choose('${h(stop.id)}')">
                <strong data-business>${h(stop.customer_name || tr('Customer'))}</strong>
                <span class="trip-briefing-pick-when" data-business>${h(when(stop))}</span>
                <span class="trip-briefing-pick-people" data-business>${h(going(stop))}</span>
                <em>${h(status(stop))}</em>
            </button>`;
    }

    function render() {
        const host = document.getElementById('trip-briefing-picker');
        if (!host) return;
        const plan = typeof State === 'undefined' ? null : State.currentTripPlan;
        const rows = visits(plan);
        if (!plan) {
            host.innerHTML = `<div class="empty-state compact">${h(tr('Create or select a plan'))}</div>`;
            return;
        }
        if (!rows.length) {
            host.innerHTML = `<div class="empty-state compact">${h(tr(
                'No customer visits in this plan yet. Add stops in Route & Schedule.'))}</div>`;
            return;
        }
        const open = window.TripBriefingDraft?.getStopId?.() || null;
        host.innerHTML = `
            <div class="trip-briefing-pick-head">
                <strong>${h(tr('Visits to prepare'))}</strong>
                <span>${h(tr('{count} visits', { count: rows.length }))}</span>
            </div>
            ${rows.map(stop => row(stop, open)).join('')}`;
    }

    // Only the highlight changes when the reader moves between visits; redrawing
    // the whole list from here would fight the editor for the same click.
    function markSelection(stopId) {
        const host = document.getElementById('trip-briefing-picker');
        if (!host) return;
        host.querySelectorAll('[data-briefing-pick]').forEach(node => {
            const chosen = node.dataset.briefingPick === stopId;
            node.classList.toggle('active', chosen);
            if (chosen) node.setAttribute('aria-current', 'true');
            else node.removeAttribute('aria-current');
        });
    }

    // The draft guard lives in one place - the action - so choosing here asks
    // the same question a schedule row or the team timeline would.
    function choose(stopId) {
        window.TripBriefingActions?.open?.(stopId);
    }

    window.TripBriefingPicker = Object.freeze({ render, markSelection, choose });
})();
