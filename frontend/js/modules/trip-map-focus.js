/** "Show me this on the map", done to the end.
 *
 * Moving the map's centre is not showing somebody anything. The map was often
 * a thousand pixels above the reader, so a click on "Map" recentred a view
 * nobody could see, opened nothing, and named no customer: the only evidence
 * that the right object had been found was that setView had been called.
 *
 * A map request now finishes: the map is brought into view below the pinned
 * bar, re-measured for its new position, the marker for *that* object is
 * emphasised, and its own information box opens - with the customer, the visit
 * it belongs to, the address and the three times. Several customers on one
 * coordinate are listed there and switched between by id, because on a map
 * they are one dot and the name alone cannot tell them apart.
 *
 * Choosing something on the timeline is not this. That only highlights, so a
 * reader working in the editor is not thrown at the map every time they click.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    let request = 0;                       // A then B must end on B
    let active = null;                     // { kind, id, planId } to restore after a redraw
    const planNow = () => State.currentTripPlan?.id || null;

    const registry = () => (State.tripMapMarkers instanceof Map ? State.tripMapMarkers : null);
    const keyOf = (kind, id) => `${kind}:${id}`;

    function entry(kind, id) {
        return registry()?.get(keyOf(kind, id)) || null;
    }

    /** Everything else standing on the same coordinate. */
    function neighbours(found) {
        const all = [...(registry()?.values() || [])];
        return all.filter(item => item !== found
            && item.point && found.point
            && item.point[0] === found.point[0] && item.point[1] === found.point[1]);
    }

    function precision(item) {
        if (item.exact === false) {
            return `<p class="map-popup-warning">${h(t(
                'This is a city-level position, not the customer address. Open coordinate review to place it.'))}</p>`;
        }
        return '';
    }

    function hiddenByFilter(item) {
        if (item.kind !== 'stop') return '';
        const view = window.TripTeamMap?.view?.() || 'all';
        if (view === 'all') return '';
        const shown = (window.TripTeamMap?.visibleStops?.(State.currentTripPlan) || [])
            .some(stop => String(stop.id) === String(item.id));
        if (shown) return '';
        return `<p class="map-popup-warning">${h(t(
            'This stop belongs to a traveller who is filtered out of the map right now.'))}
            <button type="button" class="btn btn-secondary btn-sm"
                onclick="TripTeamMap.setView('all')">${h(t('Show everyone'))}</button></p>`;
    }

    function others(found) {
        const list = neighbours(found);
        if (!list.length) return '';
        return `<div class="map-popup-others">
            <div>${h(t('{count} objects at this position', { count: list.length + 1 }))}</div>
            ${list.map(item => `<button type="button" class="btn btn-secondary btn-sm"
                onclick="TripMapFocus.show('${h(item.kind)}', '${h(item.id)}')"
                data-business>${h(item.name)}${item.detail ? ` · ${h(item.detail)}` : ''}</button>`).join('')}
        </div>`;
    }

    function stopPopup(item) {
        const stop = (State.currentTripPlan?.stops || [])
            .find(entry => String(entry.id) === String(item.id));
        if (!stop) return `<div class="map-popup">${h(t('This stop is no longer part of the plan.'))}</div>`;
        const times = window.TripStopTimes;
        return `<div class="map-popup">
            <div class="map-popup-title" data-business>${h(stop.customer_name || stop.location_name || t('Untitled'))}</div>
            <div class="map-popup-meta" data-business>${h([stop.lead_display_id,
                stop.address, stop.city, stop.country].filter(Boolean).join(' · ') || '-')}</div>
            <dl class="map-popup-times">
                <div><dt>${h(t('Planned slot'))}</dt><dd>${h(times?.scheduled?.(stop) || '-')}</dd></div>
                <div><dt>${h(t('Agreed with customer'))}</dt><dd>${h(times?.agreed?.(stop) || '-')}</dd></div>
                <div><dt>${h(t('Actually visited'))}</dt><dd>${h(times?.visited?.(stop) || '-')}</dd></div>
            </dl>
            ${precision(item)}${hiddenByFilter(item)}${others(item)}
            <div class="trip-popup-actions">
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripSelection.select('stop', '${h(stop.id)}')">${h(t('Open this stop'))}</button>
            </div>
        </div>`;
    }

    // The map only needs re-measuring and bringing into view; the candidate's
    // own popup is already built where the candidates are drawn.
    function reveal() {
        const zone = document.querySelector('.trip-map-zone');
        if (!zone) return;
        zone.scrollIntoView({ block: 'start', behavior: 'smooth' });
        window.setTimeout(() => State.tripMap?.invalidateSize?.(), 260);
    }

    /**
     * Show one object, and stop if the question has changed by the time we get
     * there.
     *
     * The map has to be brought into view before it can be pointed at, and that
     * wait is long enough for the reader to open another plan or for the
     * markers to be drawn again. Three things are therefore checked when the
     * wait ends, not when the request is made: that this is still the newest
     * request, that it is still the same plan, and that the marker for this
     * object is the one currently on the map - the captured one may belong to a
     * layer that has since been cleared.
     */
    function show(kind, id) {
        const mine = ++request;
        const planId = planNow();
        if (!entry(kind, id)) {
            notify(t('That object is not on the map right now.'));
            return false;
        }
        active = { kind, id: String(id), planId };
        reveal();
        window.setTimeout(() => {
            if (mine !== request || planNow() !== planId) return;
            const found = entry(kind, id);      // looked up again, never reused
            if (!found) return;
            State.tripMap?.setView(found.point, Math.max(State.tripMap.getZoom() || 0, 8));
            if (kind === 'stop') found.marker.setPopupContent(stopPopup(found));
            found.marker.openPopup();
        }, 320);
        return true;
    }

    /** After a redraw, the object the reader asked for is still the one shown. */
    function restore() {
        if (!active) return false;
        if (planNow() !== active.planId) { active = null; return false; }
        const found = entry(active.kind, active.id);
        if (!found) { active = null; return false; }
        if (active.kind === 'stop') found.marker.setPopupContent(stopPopup(found));
        found.marker.openPopup();
        return true;
    }

    // Clearing is also an answer: a request still on its way must not arrive
    // after it, so the counter moves and the one in flight loses.
    function clear() {
        request += 1;
        active = null;
    }

    window.TripMapFocus = Object.freeze({
        show, reveal, restore, clear, stopPopup,
        active: () => active,
    });
})();
