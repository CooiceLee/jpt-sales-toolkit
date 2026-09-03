/** How long the airport parts of a flown leg take, when somebody knows.

A flown connection is a drive to the airport, the wait there, the flight, and a
drive at the other end. Only the flight's own hours were ever askable, so the
transfers stayed estimates the reader could see were wrong and could not
correct. Each of these writes one number and asks for a fresh preview.
*/
(function() {
    const leg = index => TripLegAirports.legFor(index);
    const say = (index, side, message, kind) =>
        TripLegAirports.status(index, side, message, kind);

    function write(index, side, field, halfDays) {
        const target = leg(index);
        if (!target) return;
        TripPlanningDraft.change(draft => {
            draft.legOverrides[target.leg_key] = {
                ...(draft.legOverrides[target.leg_key] || {}),
                [`${side}_${field}`]: halfDays,
            };
        });
        TripTransportActions.schedulePreview();
    }

    function stayChanged(index, side, raw) {
        const halfDays = TripDuration.parseDisplayTravelDays(raw);
        if (raw !== '' && halfDays == null) {
            say(index, side, 'Stay must be 0 to 30 days in 0.5-day steps.', 'error');
            return;
        }
        write(index, side, 'airport_stay_half_days', halfDays || 0);
    }

    function transferChanged(index, side, raw) {
        // Empty is not zero: it means nobody has said, so the estimate stands.
        const halfDays = raw === '' ? null
            : TripDuration.parseDisplayTravelDays(raw);
        if (raw !== '' && halfDays == null) {
            say(index, side,
                'Drive time must be 0 to 30 days in 0.5-day steps.', 'error');
            return;
        }
        write(index, side, 'transfer_half_days', halfDays);
    }

    function modeChanged(index, side, value) {
        // Empty means the plan's own ground preference decides, which is what
        // it did before either end could be told apart.
        write(index, side, 'transfer_mode', value || null);
    }

    function hoursChanged(index, side, raw) {
        const hours = raw === '' ? null : Number(raw);
        if (raw !== '' && !(Number.isFinite(hours) && hours >= 0)) {
            say(index, side, 'Transfer time must be 0 hours or more.', 'error');
            return;
        }
        write(index, side, 'transfer_time_hours', hours);
    }

    window.TripLegAirportDurations = Object.freeze({
        stayChanged, transferChanged, modeChanged, hoursChanged,
    });
})();
