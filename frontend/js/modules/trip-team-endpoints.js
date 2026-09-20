/** Where one member leaves from and returns to, when it is not the plan's.
 *
 * A member's own departure point wins over the plan's - that is what lets a
 * colleague already in Berlin join a trip that starts in Shenzhen. The card
 * showed that value and nothing could change it: a member who had one (set by
 * an import, a returned data package, or the API) kept it forever, and the
 * plan's departure field silently did not apply to them. Removing them from
 * the trip and adding them back was the only way out, and it threw away the
 * route already worked out for them.
 *
 * Choosing "follows the plan" clears the member's own points rather than
 * copying today's plan value in: copied, they would stop following the plan
 * the next time the plan's own departure point changed.
 */
(function () {
    'use strict';

    const t = (key, params = {}) => window.I18n?.t(key, params) || key;
    const h = value => window.escapeHtml(String(value ?? ''));
    const el = id => document.getElementById(id);
    const value = id => String(el(id)?.value ?? '').trim();
    const form = () => window.TripTeamEndpointForm;
    const editorId = userId => `trip-team-endpoints-${userId}`;
    const FOLLOW = 'plan';

    // Which editor is open, and whether anything has been typed into it. The
    // bar, the redraw paths and the save ask this rather than the DOM: an
    // editor that exists only as fields on screen is one a redraw takes away.
    let openFor = null;
    let dirty = false;

    function touched() {
        if (!openFor) return;
        dirty = true;
        window.TripRouteBar?.render?.();
    }

    function openEditor() {
        if (!openFor) return null;
        const member = window.TripTeamActions?.memberOf?.(openFor);
        return { userId: openFor, dirty, name: member?.display_name || openFor };
    }

    const BOXES = ['origin', 'destination'].flatMap(kind =>
        ['preset', 'name', 'lat', 'lng'].map(field => `${kind}-${field}`));

    /** The values on screen, so a redraw can put them back. */
    function capture() {
        if (!openFor) return null;
        const held = { userId: openFor, dirty, values: {} };
        BOXES.forEach(box => {
            const input = el(`trip-team-${box}-${openFor}`);
            if (input) held.values[box] = input.value;
        });
        return held;
    }

    function restore(held) {
        if (!held?.userId) return;
        open(held.userId);
        Object.entries(held.values || {}).forEach(([key, value]) => {
            const input = el(`trip-team-${key}-${held.userId}`);
            if (input) input.value = value;
        });
        ['origin', 'destination'].forEach(kind => modeChanged(held.userId, kind));
        dirty = Boolean(held.dirty);
    }

    function setBusy(userId, busy) {
        const host = el(editorId(userId));
        if (!host) return;
        host.querySelectorAll('input, select, button')
            .forEach(field => { field.disabled = Boolean(busy); });
        host.setAttribute('aria-busy', String(Boolean(busy)));
    }

    function open(userId) {
        const host = el(editorId(userId));
        const member = window.TripTeamActions?.memberOf?.(userId);
        if (!host || !member) return;
        openFor = userId;
        dirty = false;
        host.innerHTML = `${form().section(userId, 'origin', member)}
            ${form().section(userId, 'destination', member)}
            <div class="trip-team-endpoint-actions">
                <button type="button" class="btn btn-primary btn-sm"
                    onclick="TripTeamEndpoints.save('${h(userId)}')">${h(t('Save'))}</button>
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripTeamEndpoints.close('${h(userId)}')">${h(t('Cancel'))}</button>
            </div>`;
        host.hidden = false;
    }

    function close(userId) {
        const host = el(editorId(userId));
        if (openFor === userId) { openFor = null; dirty = false; }
        window.TripRouteBar?.render?.();
        if (!host) return;
        host.hidden = true;
        host.innerHTML = '';
    }

    function toggle(userId) {
        const host = el(editorId(userId));
        if (host && !host.hidden) return close(userId);
        open(userId);
    }

    function modeChanged(userId, kind) {
        const box = el(`trip-team-${kind}-custom-${userId}`);
        if (box) box.hidden = value(`trip-team-${kind}-preset-${userId}`) !== 'custom';
    }

    // Nulls, not "no key": the request must say the member has no point of
    // their own, and a field the payload leaves out is a field left unchanged.
    function read(userId, kind) {
        const mode = value(`trip-team-${kind}-preset-${userId}`);
        if (mode === FOLLOW) return { name: null, lat: null, lng: null };
        const hub = form().hubs()[mode];
        if (hub) return { name: hub.name, lat: hub.lat, lng: hub.lng };
        // Empty is not zero. `Number('')` is 0, so a name with both boxes left
        // empty passed as a place at 0,0. A latitude that really is 0 must
        // still be accepted, so the text is checked before the number.
        const rawLat = value(`trip-team-${kind}-lat-${userId}`);
        const rawLng = value(`trip-team-${kind}-lng-${userId}`);
        const name = value(`trip-team-${kind}-name-${userId}`);
        const [lat, lng] = [Number(rawLat), Number(rawLng)];
        if (!name || rawLat === '' || rawLng === ''
            || !Number.isFinite(lat) || Math.abs(lat) > 90
            || !Number.isFinite(lng) || Math.abs(lng) > 180) return null;
        return { name, lat, lng };
    }

    async function save(userId) {
        const origin = read(userId, 'origin');
        const destination = read(userId, 'destination');
        if (!origin || !destination) {
            alert(t('Enter a place name and coordinates, or choose a location.'));
            return;
        }
        const done = await window.TripTeamActions?.saveEndpoints?.(userId, {
            origin_name_override: origin.name,
            origin_lat_override: origin.lat,
            origin_lng_override: origin.lng,
            destination_name_override: destination.name,
            destination_lat_override: destination.lat,
            destination_lng_override: destination.lng,
        });
        // Only this editor's own session ends, and only when it succeeded: a
        // refused save keeps what was typed where it was typed.
        if (done) close(userId);
    }

    window.TripTeamEndpoints = Object.freeze({
        toggle, open, close, modeChanged, save,
        modeOf: (...args) => form().modeOf(...args),
        touched, openEditor, capture, restore, setBusy,
        isDirty: () => dirty,
    });
})();
