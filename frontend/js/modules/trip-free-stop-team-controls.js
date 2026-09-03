/** Who stops here, and when, for a personal stop on a team trip. */
(function() {
    const el = id => document.getElementById(id);
    const h = value => escapeHtml(value ?? '');
    const isTeam = () => State.currentTripPlan?.planning_mode === 'team';

    function renderPeople(stop) {
        const list = el('trip-free-stop-people-list');
        if (!list) return;
        const chosen = new Set(stop?.participant_user_ids || []);
        list.innerHTML = (State.currentTripPlan?.members || []).map(member =>
            `<label class="trip-free-stop-person">
                <input type="checkbox" value="${h(member.user_id)}"
                    ${chosen.has(member.user_id) ? 'checked' : ''}
                    onchange="TripFreeStopDraft.mark()">
                <span>${h(member.display_name || member.user_id)}</span>
            </label>`).join('');
    }

    function render(stop) {
        const team = isTeam();
        ['trip-free-stop-people', 'trip-free-stop-team-timing'].forEach(id => {
            if (el(id)) el(id).hidden = !team;
        });
        if (!team) return;
        if (el('trip-free-stop-start-date')) {
            el('trip-free-stop-start-date').value = stop?.planned_date || '';
        }
        if (el('trip-free-stop-start-period')) {
            el('trip-free-stop-start-period').value =
                stop?.planned_start_period === 'PM' ? 'PM' : 'AM';
        }
        renderPeople(stop);
    }

    function chosenPeople() {
        return Array.from(el('trip-free-stop-people-list')
            ?.querySelectorAll('input:checked') || []).map(node => node.value);
    }

    function payload() {
        if (!isTeam()) return {};
        const day = String(el('trip-free-stop-start-date')?.value || '').trim();
        return {
            // Nobody ticked means the whole team, which is what the card says.
            participant_user_ids: chosenPeople(),
            // A stop with a day of its own holds that place in the lanes of the
            // people who stop there. Without one it is fitted around the
            // appointments, which is what an unscheduled rest stop should do.
            planned_date: day || null,
            planned_start_period: day
                ? (el('trip-free-stop-start-period')?.value === 'PM' ? 'PM' : 'AM')
                : null,
            schedule_locked: Boolean(day),
        };
    }

    window.TripFreeStopTeamControls = Object.freeze({ render, payload });
})();
