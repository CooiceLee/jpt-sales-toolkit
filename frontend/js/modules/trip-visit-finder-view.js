/** The part of the visit finder that changes while somebody types.
 *
 * Split from the finder so the search box is written once and only this is
 * redrawn: replacing the input on every keystroke took the caret with it, and
 * with it any half-typed Chinese still in the input method.
 *
 * What each row says about a time comes from the fields that hold it - a date
 * the calculation produced is marked as a reference, never as an appointment.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const nameOf = stop => stop.customer_name || stop.location_name || t('Untitled');
    const agreementOf = stop => window.TripStopTimes?.agreement?.(stop) || 'none';

    function row(stop, index) {
        const facts = [stop.lead_display_id, [stop.city, stop.country].filter(Boolean).join(' · ')]
            .filter(Boolean).join(' · ');
        const agreement = agreementOf(stop);
        return `<button type="button" class="trip-finder-row${
            window.TripSelection?.is?.('stop', stop.id) ? ' is-selected' : ''}"
            onclick="TripVisitFinder.choose('${h(stop.id)}')">
            <span class="trip-finder-seq">${h(stop.sequence_no ?? index + 1)}</span>
            <span class="trip-finder-name" data-business>${h(nameOf(stop))}</span>
            <span class="trip-finder-facts" data-business>${h(facts || '-')}</span>
            <span class="trip-finder-when is-${h(agreement)}">${
                h(window.TripStopTimes?.agreementLabel?.(stop) || '')}</span>
            <span class="trip-finder-do">${h(t(agreement === 'confirmed'
                ? 'Change the time' : 'Set the time'))}</span>
        </button>`;
    }

    // Once a visit is chosen the list folds to one line: which visit is being
    // edited, and the way back to the search that found it.
    function editing(stop) {
        return stop
            ? `<p class="trip-finder-editing"><span data-business>${h(t('Now editing: {name}', {
                name: nameOf(stop) }))}</span>
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripVisitFinder.change()">${h(t('Choose another visit'))}</button></p>`
            : '';
    }

    function results(state, all = [], matches = () => true) {
        const root = document.getElementById('trip-finder-results');
        if (!root) return;
        if (state.editing) {
            root.innerHTML = editing(all.find(item => String(item.id) === state.editing));
            return;
        }
        const shown = all.filter(matches);
        root.innerHTML = `<div class="trip-finder-list">${shown.length
            ? shown.map(row).join('')
            : `<p class="trip-finder-empty">${h(t('No visit in this plan matches that.'))}
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripVisitFinder.clearFilters()">${h(t('Clear the search'))}</button></p>`}</div>
            <p class="trip-finder-count">${h(shown.length === all.length
                ? t('{count} customer visits', { count: all.length })
                : t('Showing {count} of {total} customer visits', {
                    count: shown.length, total: all.length }))}</p>`;
    }

    window.TripVisitFinderView = Object.freeze({ results, row });
})();
