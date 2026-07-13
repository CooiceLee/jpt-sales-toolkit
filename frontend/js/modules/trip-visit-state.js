/** Shared date and formatting state for trip visit execution. */
(function() {
    let selectedDate = null;
    const escape = value => window.JPTRender?.escape(value) || String(value ?? '');

    function parseDay(value) {
        if (!value) return null;
        const date = new Date(`${String(value).slice(0, 10)}T00:00:00`);
        return Number.isNaN(date.getTime()) ? null : date;
    }

    function formatDay(date) {
        return date.toISOString().slice(0, 10);
    }

    function stopDays(stop) {
        const start = parseDay(stop.planned_date);
        if (!start) return [];
        const end = parseDay(stop.planned_end_date) || start;
        const days = [];
        for (let cursor = start; cursor <= end; cursor = new Date(cursor.getTime() + 86400000)) {
            days.push(formatDay(cursor));
        }
        return days;
    }

    function planDays(plan) {
        const days = new Set();
        (plan?.stops || []).forEach(stop => stopDays(stop).forEach(day => days.add(day)));
        return Array.from(days).sort();
    }

    function currentDateForPlan(plan) {
        const days = planDays(plan);
        if (!days.length) return '';
        const today = new Date().toISOString().slice(0, 10);
        if (selectedDate && days.includes(selectedDate)) return selectedDate;
        selectedDate = days.includes(today) ? today : days[0];
        return selectedDate;
    }

    function setVisitDate(value) {
        selectedDate = value || null;
        window.TripPlannerModule.renderVisitExecution(State.currentTripPlan);
    }

    window.TripVisitState = {
        escape,
        planDays,
        currentDateForPlan,
        stopMatchesDay: (stop, day) => !day || stopDays(stop).includes(day),
        contactLine: stop => [stop.contact_name, stop.contact_position, stop.contact_phone || stop.contact_email].filter(Boolean).join(' / '),
        addressLine: stop => [stop.address, stop.city, stop.country].filter(Boolean).join(', '),
        getSelectedDate: () => selectedDate,
        setVisitDate,
    };
})();
