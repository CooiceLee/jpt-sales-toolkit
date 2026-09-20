/** The two dropdowns and three boxes one member's places are edited with.
 *
 * Only the markup: which editor is open, what has been typed into it and what
 * happens to it while a save is in flight are the session's business, not the
 * form's. Split because the two together outgrew what one file should hold.
 */
(function () {
    'use strict';

    const t = (key, params = {}) => window.I18n?.t(key, params) || key;
    const h = value => window.escapeHtml(String(value ?? ''));
    const FOLLOW = 'plan';

    function hubs() {
        return window.TripChinaHubs?.HUBS || {};
    }

    // "Follows the plan", the known airports, or somewhere typed in.
    function modeOf(member, kind) {
        if (member?.[`${kind}_lat_override`] == null) return FOLLOW;
        return window.TripChinaHubs?.detect?.(
            member[`${kind}_lat_override`], member[`${kind}_lng_override`]
        ) || 'custom';
    }

    function choices(userId, kind, member) {
        const chosen = modeOf(member, kind);
        const options = [[FOLLOW, kind === 'origin'
            ? t('Plan departure point') : t('Plan return point')]]
            .concat(Object.entries(hubs()).map(([code, hub]) => [code, hub.name]))
            .concat([['custom', t('Custom location')]]);
        return `<select class="form-input" id="trip-team-${kind}-preset-${h(userId)}"
            onchange="TripTeamEndpoints.modeChanged('${h(userId)}', '${kind}')">
            ${options.map(([code, label]) => `<option value="${h(code)}" ${
                code === chosen ? 'selected' : ''}>${h(label)}</option>`).join('')}
        </select>`;
    }

    function fields(userId, kind, member) {
        const own = modeOf(member, kind) === 'custom';
        return `<div class="trip-team-endpoint-custom" id="trip-team-${kind}-custom-${h(userId)}"
            ${own ? '' : 'hidden'}>
            <label><span>${h(t(kind === 'origin'
                ? 'Departure place' : 'Return place'))}</span>
                <input type="text" class="form-input" id="trip-team-${kind}-name-${h(userId)}"
                    value="${h(own ? member[`${kind}_name_override`] || '' : '')}"></label>
            <label><span>${h(t('Latitude'))}</span>
                <input type="number" step="any" class="form-input" id="trip-team-${kind}-lat-${h(userId)}"
                    value="${h(own ? member[`${kind}_lat_override`] ?? '' : '')}"></label>
            <label><span>${h(t('Longitude'))}</span>
                <input type="number" step="any" class="form-input" id="trip-team-${kind}-lng-${h(userId)}"
                    value="${h(own ? member[`${kind}_lng_override`] ?? '' : '')}"></label>
        </div>`;
    }

    function section(userId, kind, member) {
        return `<div class="trip-team-endpoint-block"
            oninput="TripTeamEndpoints.touched()"
            onchange="TripTeamEndpoints.touched()">
            <span class="trip-team-endpoint-title">${h(t(
                kind === 'origin' ? 'Leaves from' : 'Returns to'))}</span>
            ${choices(userId, kind, member)}
            ${fields(userId, kind, member)}
        </div>`;
    }

    window.TripTeamEndpointForm = Object.freeze({
        FOLLOW, hubs, modeOf, section,
    });
})();
