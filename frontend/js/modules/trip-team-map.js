/** Team routes on the map: the journeys the plan contains, and whose they are. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const modeLabel = value =>
        window.TripScheduleView?.transportModeLabel?.(value) || value || '';

    function view() {
        const current = State.tripTeamMapView || 'all';
        if (current === 'all') return 'all';
        const members = (State.currentTripPlan?.members || [])
            .map(item => item.user_id);
        return members.includes(current) ? current : 'all';
    }

    function setView(value) {
        State.tripTeamMapView = value || 'all';
        renderToolbar(State.currentTripPlan);
        window.renderTripMap?.();
    }

    function renderToolbar(plan) {
        const target = document.getElementById('trip-map-lanes');
        if (!target) return;
        const members = plan?.members || [];
        target.hidden = plan?.planning_mode !== 'team' || !members.length;
        if (target.hidden) {
            target.innerHTML = '';
            return;
        }
        const active = view();
        const button = (value, label, color = '') => `<button type="button"
            class="btn btn-sm trip-map-lane ${value === active ? 'btn-primary' : 'btn-secondary'}"
            aria-pressed="${value === active}"
            onclick="TripTeamMap.setView('${h(value)}')">${color
                ? `<i class="trip-lane-swatch" style="background:${h(color)}"></i>` : ''
            }${h(label)}</button>`;
        target.innerHTML = button('all', t('All team')) + members
            .map(member => button(
                member.user_id, member.display_name || member.user_id,
                TripTeamColors.colorOf(plan, member.user_id)
            )).join('');
    }

    /** Draw the journeys, and say whose route could not be worked out. */
    function draw(plan, layer, bounds) {
        const active = view();
        const drawn = window.TripTeamJourneys.journeys(plan, active);
        drawn.forEach(journey => {
            journey.points.forEach(point => bounds.push(point));
            const who = journey.members.length
                ? journey.members.join(' · ') : t('Unassigned');
            const tooltip = h(`${who} · ${journey.label} · ${
                modeLabel(journey.mode)}`);
            TripTeamColors.bandsFor(plan, journey.memberIds).forEach(band => {
                L.polyline(journey.points, { ...band, opacity: 0.8 })
                    .bindTooltip(tooltip).addTo(layer);
            });
        });
        const stranded = window.TripTeamJourneys.incompleteMembers(plan, active);
        const notice = document.getElementById('trip-map-notice');
        if (notice) {
            notice.hidden = !stranded.length;
            notice.textContent = stranded.length
                ? t('No route is drawn for {members} yet: the plan cannot say where they are.',
                    { members: stranded.join(' · ') })
                : '';
        }
        return drawn.length;
    }

    /** Which stops belong on the map for the current view. */
    function visibleStops(plan) {
        const active = view();
        if (active === 'all') return plan?.stops || [];
        const attended = new Set(
            (plan?.schedule_items || [])
                .filter(item => item.member_id === active
                    && item.item_type !== 'leg')
                .map(item => item.source_id)
        );
        return (plan?.stops || []).filter(stop => attended.has(stop.id));
    }

    function focusStop(stopId) {
        const stop = (State.currentTripPlan?.stops || [])
            .find(item => item.id === stopId);
        const location = window.TripVisitState?.visitLocation?.(stop) || stop;
        const point = MapSupport.coordinatePair(location?.lat, location?.lng);
        if (point) State.tripMap?.setView(point, 8);
    }

    /**
     * Show one journey on the map.
     *
     * Two members can hold the same leg key and the same mode and still be on
     * different journeys - two flights to the same customer through different
     * airports - so whose line was chosen decides which one is shown.
     */
    function focusLeg(legKey, mode, memberId) {
        const plan = State.currentTripPlan;
        const journey = window.TripTeamJourneys.journeys(plan, view())
            .find(item => item.legKey === legKey
                && (!mode || item.mode === mode)
                && (!memberId || item.memberIds.includes(memberId)));
        if (journey?.points?.length && State.tripMap) {
            State.tripMap.fitBounds(journey.points, { padding: [40, 40] });
        }
    }

    window.TripTeamMap = Object.freeze({
        view, setView, renderToolbar, draw, visibleStops, focusStop, focusLeg,
    });
})();
