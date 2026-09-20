/** One journey on the travel list: when it leaves, when it arrives, who is on
 *  it - and, when opened, the two choices a reader actually makes about it.
 *
 * The row used to carry endpoints, distance, hours and "0.5 travel days". None
 * of that answers the question somebody scanning a trip has: which day does
 * this leave, which visit does it feed, and who is travelling. The backend has
 * been writing the half-days onto the leg since the schedule was built
 * (_record_travel), so the row reads them rather than working a date out of a
 * distance.
 *
 * The controls are two lines on purpose - the mode on its own, then the lock
 * and the search - and they wrap on the width of this card, not the width of
 * the window: inside a 280px column a single no-wrap row squeezed the lock
 * label into one character per line.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const MODE_LABELS = {
        flight: 'Flight', drive: 'Drive', ground_public: 'Ground public', other: 'Other',
    };

    function modeOptions(value) {
        const options = [['', 'Use plan preference'],
            ...(window.TripPlanningDraft?.MODES || []).map(mode => [mode, MODE_LABELS[mode]])];
        return options.map(([key, label]) =>
            `<option value="${h(key)}" ${key === value ? 'selected' : ''}>${h(t(label))}</option>`).join('');
    }

    /** Which half-days this journey occupies, as the schedule placed it. */
    function schedule(leg) {
        const period = value => t(value === 'PM' ? 'PM' : 'AM');
        const start = leg.planned_start_date
            ? `${leg.planned_start_date}${leg.planned_start_period ? ` ${period(leg.planned_start_period)}` : ''}` : '';
        const end = leg.planned_end_date
            ? `${leg.planned_end_date}${leg.planned_end_period ? ` ${period(leg.planned_end_period)}` : ''}` : '';
        // Thirteen of this plan's legs are twenty-minute hops the schedule
        // fits inside a half-day it has already placed: they have no date of
        // their own, and saying "not scheduled" reads as a hole in the trip.
        if (!start) {
            return Number(leg.travel_half_days) === 0
                ? t('Within the same half-day') : t('Not on the schedule yet');
        }
        return !end || end === start ? start : `${start} → ${end}`;
    }

    function metrics(leg) {
        return [
            leg.distance_km != null ? t('{count} km', { count: leg.distance_km }) : '',
            leg.time_hours != null ? t('{count} hours', { count: leg.time_hours }) : '',
            leg.travel_half_days != null
                ? t('{count} travel days', { count: TripDuration.toDisplayTravelDays(leg.travel_half_days) })
                : (leg.travel_days != null ? t('{count} travel days', { count: leg.travel_days }) : ''),
        ].filter(Boolean).join(' · ');
    }

    function controls(index, override, selected, hasManual) {
        return `<div class="trip-leg-controls">
                <label class="trip-field-label"><span>${h(t('Transport mode'))}</span>
                    <select class="form-input" id="trip-leg-mode-${index}" onchange="TripTransportActions.legChanged(${index})">${modeOptions(selected)}</select></label>
                <div class="trip-leg-control-row">
                    <label class="trip-check"><input type="checkbox" id="trip-leg-lock-${index}" ${override.mode_locked ? 'checked' : ''} onchange="TripTransportActions.legChanged(${index})"> <span>${h(t('Fix the transport mode'))}</span></label>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="TripSuggestionActions.searchLeg(${index})">${h(t('Search this leg'))}</button>
                </div>
            </div>
            <div class="trip-leg-manual ${selected === 'other' || hasManual ? '' : 'hidden'}" id="trip-leg-manual-${index}">
                <label class="trip-field-label"><span>${h(t('Distance km'))}</span>
                    <input type="number" min="0" step="0.1" class="form-input" id="trip-leg-distance-${index}" value="${h(override.manual_distance_km ?? '')}" placeholder="${h(t('Distance km'))}" onchange="TripTransportActions.legChanged(${index})"></label>
                <label class="trip-field-label"><span>${h(t('Travel hours'))}</span>
                    <input type="number" min="0.1" step="0.1" class="form-input" id="trip-leg-hours-${index}" value="${h(override.manual_time_hours ?? '')}" placeholder="${h(t('Travel hours'))}" onchange="TripTransportActions.legChanged(${index})"></label>
                <label class="trip-field-label"><span>${h(t('Travel duration (days, 0.5 steps)'))}</span>
                    <input type="number" min="0" max="30" step="0.5" class="form-input" data-leg-duration-half-days id="trip-leg-days-${index}"
                        value="${h(override.manual_travel_half_days != null ? TripDuration.toDisplayTravelDays(override.manual_travel_half_days) : '')}"
                        placeholder="${h(t('Travel duration (days, 0.5 steps)'))}" onchange="TripTransportActions.legChanged(${index})"></label>
                <textarea class="form-input" rows="2" id="trip-leg-notes-${index}" placeholder="${h(t('Transport notes'))}" onchange="TripTransportActions.legChanged(${index})">${h(override.notes || '')}</textarea>
            </div>`;
    }

    function render(row, index, draft) {
        const leg = row.leg;
        const override = draft?.legOverrides?.[leg.leg_key] || {};
        const selected = override.selected_mode || '';
        const hasManual = override.manual_distance_km != null || override.manual_time_hours != null
            || override.manual_travel_half_days != null || override.manual_travel_days != null || override.notes;
        const shownMode = window.TripLegRows?.modeOf?.(leg, draft)
            || selected || leg.selected_mode || leg.travel_mode || leg.mode || '-';
        const from = leg.from_label || leg.from_name || leg.travel_from_label || t('Origin');
        const to = leg.to_label || leg.to_name || t('Destination');
        const metric = metrics(leg);
        return `<div class="trip-leg-card is-open" data-leg-key="${h(leg.leg_key)}"
            data-leg-mode="${h(shownMode)}" data-leg-needs="${metric ? '0' : '1'}">
            ${row.members.length ? `<p class="trip-leg-members">${h(row.members.join(' · '))}</p>` : ''}
            <div class="trip-leg-head"><strong>${h(index + 1)}. ${h(from)} → ${h(to)}</strong><span>${h(t(MODE_LABELS[shownMode] || shownMode))}${override.mode_locked ? ` · ${h(t('Mode fixed'))}` : ''}</span></div>
            <div class="trip-leg-when">${h(schedule(leg))}</div>
            <div class="trip-leg-metric">${h(metric || t('Estimate pending'))}</div>
            <div class="trip-leg-body" id="trip-leg-body-${index}">
            ${controls(index, override, selected, hasManual)}
            ${row.members.length > 1 ? `<p class="trip-leg-shared">${h(t(
                'This journey is shared. A change here applies to everybody on it: {names}.',
                { names: row.members.join(' · ') }))}</p>` : ''}
            ${window.TripLegAirportsView?.render?.(index, override, shownMode) || ''}
            </div>
            <div class="trip-leg-suggestions" id="trip-leg-suggestions-${index}"></div>
        </div>`;
    }

    window.TripLegCard = Object.freeze({ render, schedule, metrics, MODE_LABELS });
})();
