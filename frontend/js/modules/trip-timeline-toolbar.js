/** The three questions asked above the timeline, and nothing else.
 *
 * Whose trip am I reading, am I reading the whole thing or only the travel,
 * and which day do I want to be at. Transport modes, confirmation states and
 * stop kinds are not here: they are properties of single objects, and putting
 * six equal-weight filters across the top of a reading surface made choosing
 * how to look harder than reading.
 *
 * All three are ways of looking. None of them marks anything unsaved, changes
 * the order the plan is stored in, or asks for a route to be worked out again.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);

    function memberOptions(plan) {
        const model = window.TripTimelineModel;
        const chosen = model.member();
        const people = model.members(plan);
        if (people.length < 2) return '';
        const options = [['all', t('Everyone')], ...people.map(person => [person.id, person.name])]
            .map(([value, label]) => `<option value="${h(value)}" ${
                value === chosen ? 'selected' : ''}>${h(label)}</option>`).join('');
        return `<label class="trip-timeline-pick"><span>${h(t('Traveller'))}</span>
            <select class="form-input" id="trip-timeline-member"
                onchange="TripTimelineModel.setMember(this.value)">${options}</select></label>`;
    }

    function modeButtons() {
        const model = window.TripTimelineModel;
        return `<div class="trip-timeline-modes" role="group" aria-label="${h(t('Timeline view'))}">
            ${[['full', 'Whole trip'], ['travel', 'Travel only']].map(([value, label]) =>
                `<button type="button" class="trip-timeline-mode${
                    model.mode() === value ? ' is-active' : ''}" aria-pressed="${model.mode() === value}"
                    onclick="TripTimelineModel.setMode('${value}')">${h(t(label))}</button>`).join('')}
        </div>`;
    }

    // One line - the day being read, and the step either side of it. Thirty-one
    // date buttons filled three rows and then scrolled away; see trip-day-nav.js.
    const dayNav = () => '<div id="trip-day-nav" class="trip-day-nav" role="group"></div>';

    function summary(plan) {
        const counts = window.TripTimelineModel.counts(plan);
        const parts = [
            t('{count} days', { count: counts.days }),
            counts.stops === counts.allStops
                ? t('{count} stops', { count: counts.stops })
                : t('Showing {count} of {total} stops', { count: counts.stops, total: counts.allStops }),
            counts.legs === counts.allLegs
                ? t('{count} legs', { count: counts.legs })
                : t('Showing {count} of {total} legs', { count: counts.legs, total: counts.allLegs }),
            counts.unscheduled ? t('{count} not scheduled', { count: counts.unscheduled }) : '',
        ].filter(Boolean);
        return `<span class="trip-timeline-summary">${h(parts.join(' · '))}</span>`;
    }

    // Arranging a time with a customer is the most frequent thing done to a
    // trip, so it is one click from the navigation rather than a search by eye
    // through a month of days.
    function actions() {
        const open = window.TripCandidatePanel?.isOpen?.();
        const finding = window.TripVisitFinder?.isOpen?.();
        return `<button type="button" class="btn btn-secondary btn-sm trip-timeline-arrange${
                finding ? ' is-open' : ''}" aria-expanded="${!!finding}" aria-controls="trip-visit-finder"
                onclick="TripVisitFinder.${finding ? 'close' : 'open'}()">
                <span aria-hidden="true">🗓</span> ${h(t('Set agreed visit time'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" aria-pressed="${!!open}"
                onclick="TripCandidatePanel.toggle()">${h(t(open ? 'Hide customers' : 'Add customers'))}</button>`;
    }

    function render(plan = State.currentTripPlan) {
        const root = document.getElementById('trip-timeline-toolbar');
        if (!root) return;
        if (!plan?.id) { root.innerHTML = ''; return; }
        root.innerHTML = `${memberOptions(plan)}${modeButtons()}${dayNav()}${actions()}${summary(plan)}`;
        window.TripDayNav?.render?.();
        window.TripVisitFinder?.render?.();
    }

    window.TripTimelineToolbar = Object.freeze({ render });
})();
