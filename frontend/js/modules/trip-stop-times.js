/** The three times a visit has, kept apart.
 *
 * What the route worked out, what the customer agreed to, and what actually
 * happened are three different facts. Showing the first as if it were the third
 * turns a plan into a report of visits nobody has made yet, so each is read
 * from its own field and a trip with no field record says "not recorded"
 * rather than borrowing the planned date.
 */
(function () {
    'use strict';

    const t = (key, params = {}) => (window.I18n?.t ? I18n.t(key, params) : key);
    const halfDay = value => t(value === 'PM' ? 'Afternoon (PM)' : 'Morning (AM)');

    /** Where the route put it. */
    function scheduled(stop) {
        if (!stop?.planned_date) return t('Not scheduled yet');
        const start = `${stop.planned_date} ${halfDay(stop.planned_start_period)}`;
        const end = stop.planned_end_date && stop.planned_end_date !== stop.planned_date
            ? ` → ${stop.planned_end_date} ${halfDay(stop.planned_end_period)}` : '';
        return `${start}${end}`;
    }

    /** What the customer said yes to - only when somebody confirmed it. */
    function agreed(stop) {
        if (!stop?.schedule_locked || !stop.planned_date) return t('Not agreed yet');
        const status = stop.confirmation_status && stop.confirmation_status !== 'unconfirmed'
            ? ` · ${t(stop.confirmation_status)}` : '';
        return `${stop.planned_date} ${halfDay(stop.planned_start_period)}${status}`;
    }

    /** What came back from the field. */
    function visited(stop) {
        if (stop?.actual_visit_date) {
            return `${stop.actual_visit_date}${stop.actual_visit_period
                ? ` ${halfDay(stop.actual_visit_period)}` : ''}${
                stop.result_status ? ` · ${t(stop.result_status)}` : ''}`;
        }
        return stop?.result_status && stop.result_status !== 'Planned'
            ? t(stop.result_status) : t('Not recorded yet');
    }

    /**
     * Who decided this visit's time - in the app's own words.
     *
     * schedule_locked is a time the customer confirmed; planned_time_accepted
     * is one somebody here accepted and the calculation must keep; a bare
     * planned_date is the calculation's own output and decides nothing. The
     * difference matters here because "预计 09-14" must never be read as an
     * appointment (backend: trip_team_export.schedule_state).
     */
    function agreement(stop) {
        if (stop?.schedule_locked && stop.planned_date) return 'confirmed';
        if (stop?.planned_time_accepted && stop?.planned_date) return 'accepted';
        return stop?.planned_date ? 'calculated' : 'none';
    }

    function agreementLabel(stop) {
        const state = agreement(stop);
        if (state === 'confirmed') {
            return t('Agreed {date} {period}', {
                date: stop.planned_date, period: halfDay(stop.planned_start_period) });
        }
        if (state === 'accepted') {
            return t('Entered {date}, waiting for the customer', { date: stop.planned_date });
        }
        if (state === 'calculated') {
            return t('Planned {date} (for reference)', { date: stop.planned_date });
        }
        return t('No agreed time yet');
    }

    window.TripStopTimes = Object.freeze({
        halfDay, scheduled, agreed, visited, agreement, agreementLabel,
    });
})();
