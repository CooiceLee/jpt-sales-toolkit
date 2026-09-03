/** Shared date and formatting state for trip visit execution. */
(function() {
    let selectedDate = null;
    const escape = value => window.JPTRender?.escape(value) || String(value ?? '');

    function normalizeDay(value) {
        const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (!match) return '';
        const year = Number(match[1]);
        const month = Number(match[2]);
        const day = Number(match[3]);
        const probe = new Date(Date.UTC(year, month - 1, day));
        if (probe.getUTCFullYear() !== year || probe.getUTCMonth() !== month - 1 || probe.getUTCDate() !== day) return '';
        return `${match[1]}-${match[2]}-${match[3]}`;
    }

    function addDay(value, amount = 1) {
        const day = normalizeDay(value);
        if (!day) return '';
        const [year, month, date] = day.split('-').map(Number);
        const probe = new Date(Date.UTC(year, month - 1, date + amount));
        return [
            String(probe.getUTCFullYear()).padStart(4, '0'),
            String(probe.getUTCMonth() + 1).padStart(2, '0'),
            String(probe.getUTCDate()).padStart(2, '0'),
        ].join('-');
    }

    function localToday() {
        const today = new Date();
        return [
            String(today.getFullYear()).padStart(4, '0'),
            String(today.getMonth() + 1).padStart(2, '0'),
            String(today.getDate()).padStart(2, '0'),
        ].join('-');
    }

    function stopDays(stop) {
        const start = normalizeDay(stop.planned_date);
        if (!start) return [];
        const end = normalizeDay(stop.planned_end_date) || start;
        const days = [];
        for (let cursor = start; cursor && cursor <= end; cursor = addDay(cursor)) {
            days.push(cursor);
        }
        return days;
    }

    function planDays(plan) {
        const days = new Set();
        (plan?.stops || []).filter(stop => stop?.stop_kind !== 'free')
            .forEach(stop => stopDays(stop).forEach(day => days.add(day)));
        return Array.from(days).sort();
    }

    function currentDateForPlan(plan) {
        const days = planDays(plan);
        if (!days.length) return '';
        const today = localToday();
        if (selectedDate && days.includes(selectedDate)) return selectedDate;
        selectedDate = days.includes(today) ? today : days[0];
        return selectedDate;
    }

    function setVisitDate(value) {
        if (window.TripBriefingDraft?.guard?.() || window.TripVisitDraft?.guard?.()) {
            const select = document.getElementById('trip-execution-date');
            if (select) select.value = selectedDate || '';
            return;
        }
        selectedDate = value || null;
        window.TripPlannerModule.renderVisitExecution(State.currentTripPlan);
    }

    function compareStops(left, right) {
        const period = value => String(value?.planned_start_period || value?.preferred_period || 'AM').toUpperCase() === 'PM' ? 1 : 0;
        return period(left) - period(right) || Number(left.sequence_no || 0) - Number(right.sequence_no || 0);
    }

    function scheduleLabel(stop) {
        const start = [stop.planned_date, stop.planned_start_period].filter(Boolean).join(' ');
        const end = [stop.planned_end_date, stop.planned_end_period].filter(Boolean).join(' ');
        return start && end && start !== end
            ? I18n.t('{start} to {end}', { start, end }) : start || end;
    }

    function visitLocation(stop = {}) {
        return stop.visit_location || stop.briefing?.location || stop;
    }

    function peopleLine(items, fields) {
        return (items || []).map(item => fields.map(key => item[key]).filter(Boolean).join(' / '))
            .filter(Boolean).join('; ');
    }

    function customerPersonnelLine(stop = {}) {
        const briefing = stop.briefing || {};
        const line = [
            peopleLine(briefing.customer_team, ['name', 'title', 'phone', 'email']),
            peopleLine(briefing.contacts, ['name', 'position', 'role', 'phone', 'email']),
        ].filter(Boolean).join('; ');
        return line || [stop.contact_name, stop.contact_position, stop.contact_phone || stop.contact_email]
            .filter(Boolean).join(' / ');
    }

    function channelPartnerLine(stop = {}) {
        return peopleLine(stop.briefing?.channel_partner_companions,
            ['company_name', 'name', 'position', 'role', 'phone', 'email']);
    }

    function internalParticipantsLine(stop = {}) {
        const named = stop.briefing?.participants;
        if (!named?.length && State.currentTripPlan?.planning_mode === 'team') {
            // Naming nobody means the whole team goes, so say who that is
            // rather than showing a dash that reads as nobody.
            return (State.currentTripPlan.members || [])
                .map(member => member.display_name || member.user_id).join(' · ');
        }
        return peopleLine(named, ['display_name', 'role', 'responsibility']);
    }

    function agendaLine(stop = {}) {
        // What the traveller actually wrote beats the label the system attached
        // when the customer was added to the plan.
        const items = stop.briefing?.agenda_items || [];
        const written = items
            .map(item => [item.topic, item.expected_outcome].filter(Boolean).join(' → '))
            .filter(Boolean)
            .join('; ');
        return written || stop.visit_purpose || '';
    }

    function addressLine(stop = {}) {
        const location = visitLocation(stop);
        return [location.address, location.city, location.postal_code, location.country]
            .filter(Boolean).join(', ');
    }

    window.TripVisitState = {
        escape,
        normalizeDay,
        addDay,
        planDays,
        currentDateForPlan,
        stopMatchesDay: (stop, day) => !day || stopDays(stop).includes(day),
        visitLocation,
        contactLine: customerPersonnelLine,
        customerPersonnelLine,
        agendaLine,
        channelPartnerLine,
        internalParticipantsLine,
        addressLine,
        getSelectedDate: () => selectedDate,
        setVisitDate,
        compareStops,
        scheduleLabel,
    };
})();
