/** Setting the time a customer agreed to, without reading a month of days.
 *
 * It is the most frequent thing anybody does to a trip, and after the long stop
 * list went away the only way to that field was to find the visit by eye among
 * fifty-three timeline entries - where two visits to the same customer look
 * identical. So: search this plan's own customer visits, choose one, and the
 * editor that already exists opens on the agreed-time fields.
 *
 * It creates nothing and saves nothing itself. Personal stops - hotels, rest,
 * transit - are not here: they have no customer to agree anything with, and
 * they keep the editor they already had on the timeline.
 *
 * The search box is written once and never replaced; only the answers are
 * redrawn (trip-visit-finder-view.js). Rebuilding the input on every keystroke
 * threw away the caret, and with it any half-typed Chinese still in the input
 * method.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const FILTERS = [['all', 'All visits'], ['pending', 'Time not agreed'], ['agreed', 'Time agreed']];
    const state = { open: false, query: '', filter: 'all', editing: null };

    const visits = () => (State.currentTripPlan?.stops || [])
        .filter(stop => stop.stop_kind !== 'free');
    const nameOf = stop => stop.customer_name || stop.location_name || t('Untitled');
    const agreementOf = stop => window.TripStopTimes?.agreement?.(stop) || 'none';

    function matches(stop) {
        const agreed = agreementOf(stop) === 'confirmed';
        if (state.filter === 'agreed' && !agreed) return false;
        if (state.filter === 'pending' && agreed) return false;
        const needle = state.query.trim().toLowerCase();
        if (!needle) return true;
        return [nameOf(stop), stop.lead_display_id, stop.city, stop.country]
            .filter(Boolean).some(value => String(value).toLowerCase().includes(needle));
    }

    const results = () => window.TripVisitFinderView?.results?.(state, visits(), matches);

    function shell() {
        const root = document.getElementById('trip-visit-finder');
        if (!root) return;
        root.innerHTML = `<div class="trip-finder-head">
                <div>
                    <h3 class="trip-finder-title">${h(t('Set the time agreed with the customer'))}</h3>
                    <p class="trip-finder-help">${h(t('Choose a visit, then enter the date and half-day you agreed.'))}</p>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripVisitFinder.close()">${h(t('Close'))}</button>
            </div>
            <div class="trip-finder-tools">
                <label class="trip-finder-search"><span class="sr-only">${h(t('Search this plan'))}</span>
                    <input type="search" class="form-input" id="trip-finder-query" value="${h(state.query)}"
                        placeholder="${h(t('Customer, lead number or city'))}"
                        oninput="TripVisitFinder.search(this.value)"></label>
                <div class="trip-finder-filters" role="group" aria-label="${h(t('Filter visits'))}">
                    ${FILTERS.map(([value, label]) => `<button type="button" class="trip-finder-filter${
                        state.filter === value ? ' is-active' : ''}" aria-pressed="${state.filter === value}"
                        onclick="TripVisitFinder.setFilter('${value}')">${h(t(label))}</button>`).join('')}
                </div>
            </div>
            <div id="trip-finder-results"></div>`;
        results();
    }

    function render() {
        const root = document.getElementById('trip-visit-finder');
        if (!root) return;
        root.hidden = !state.open;
        if (!state.open) { root.innerHTML = ''; return; }
        // Already built: only the answers change, so the caret stays where the
        // reader left it - input method and all.
        if (document.getElementById('trip-finder-query')) return results();
        shell();
        document.getElementById('trip-finder-query')?.focus();
    }

    function open(options = {}) {
        state.open = true;
        if (options.query !== undefined) state.query = String(options.query || '');
        if (options.filter) state.filter = options.filter;
        state.editing = null;
        const root = document.getElementById('trip-visit-finder');
        if (root) root.hidden = false;
        shell();
        document.getElementById('trip-finder-query')?.focus();
        window.TripTimelineToolbar?.render?.();
        root?.scrollIntoView({ block: 'nearest' });
    }

    function close() {
        state.open = false;
        state.editing = null;
        render();
        window.TripTimelineToolbar?.render?.();
    }

    function search(value) { state.query = String(value || ''); results(); }

    function setFilter(value) {
        state.filter = FILTERS.some(([key]) => key === value) ? value : 'all';
        shell();
    }

    function clearFilters() { state.query = ''; state.filter = 'all'; shell(); }

    /** Back to the list, with the search that led here still in it. */
    function change() { state.editing = null; shell(); }

    /**
     * The visit the reader picked, opened where it is edited.
     *
     * The same selection every other entry point uses - one editor, one save
     * path - carrying the intent, so the panel opens on the agreed-time fields
     * instead of the top of the form.
     */
    function choose(stopId) {
        state.editing = String(stopId);
        window.TripSelection?.select?.('stop', stopId, { intent: 'agree' });
        results();
    }

    window.TripVisitFinder = Object.freeze({
        open, close, search, setFilter, clearFilters, choose, change, render,
        isOpen: () => state.open,
        editing: () => state.editing,
    });
})();
