/** Day / half-day itinerary board backed only by plan.schedule_items. */
(function() {
    const PERIOD_ORDER = Object.freeze({ AM: 0, PM: 1 });
    const h = value => escapeHtml(value ?? '');
    const typeOf = item => String(item.item_type || item.type || item.stop_kind || '').toLowerCase();
    const dayOf = item => item.date || item.planned_date || item.start_date || item.planned_start_date || '';
    const periodOf = item => String(
        item.period || item.planned_start_period || item.start_period || 'AM'
    ).toUpperCase() === 'PM' ? 'PM' : 'AM';
    const transportModeLabel = value => {
        const key = ({ flight: 'Flight', drive: 'Drive', ground_public: 'Ground public', other: 'Other' })[
            String(value || '').toLowerCase()
        ];
        return key ? I18n.t(key) : value;
    };

    function sortItems(items = []) {
        return [...items].sort((left, right) => {
            const day = dayOf(left).localeCompare(dayOf(right));
            if (day) return day;
            const period = PERIOD_ORDER[periodOf(left)] - PERIOD_ORDER[periodOf(right)];
            if (period) return period;
            return Number(left.sequence_no ?? left.sequence ?? 0) - Number(right.sequence_no ?? right.sequence ?? 0);
        });
    }

    function businessDays(plan) {
        const start = dayOf({ date: plan?.start_date });
        const end = plan?.itinerary_summary?.calculated_end_date || plan?.end_date || start;
        if (!start || !end || start > end) return [];
        const holidays = new Set(plan?.holiday_dates || []);
        const result = [];
        let cursor = new Date(`${start}T00:00:00Z`);
        const last = new Date(`${end}T00:00:00Z`);
        for (let count = 0; cursor <= last && count < 732; count += 1) {
            const day = cursor.toISOString().slice(0, 10);
            const weekend = cursor.getUTCDay() === 0 || cursor.getUTCDay() === 6;
            if ((!weekend || plan?.avoid_weekends === false) && !holidays.has(day)) result.push(day);
            cursor.setUTCDate(cursor.getUTCDate() + 1);
        }
        return result;
    }

    /**
     * An out-of-date itinerary is not an empty one: say why it went away and
     * offer the way back, instead of a grid of empty half-days.
     *
     * The way back is whatever is actually possible now. While an editor
     * somewhere holds unsaved work, every route action is refused - so a
     * "preview route" button here could only produce the same alert the shared
     * bar is already showing. It offers the thing that has to happen first, and
     * says whose work it is.
     */
    function staleNotice(plan) {
        const summary = plan?.itinerary_summary || {};
        if (!(summary.stale === true || summary.valid === false)) return '';
        const reason = (summary.warnings || [])[0]
            || 'The itinerary is out of date. Preview and save it again.';
        const blocked = (window.TripRouteState?.derive?.(plan)?.editors || [])[0];
        const action = blocked
            ? `<button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripRouteBar.goToBlocker()">${escapeHtml(I18n.t('Go to it'))}</button>`
            : `<button type="button" class="btn btn-primary btn-sm"
                    onclick="previewCurrentTripItinerary()">${escapeHtml(I18n.t('Preview route'))}</button>`;
        return `<div class="empty-state compact trip-schedule-stale">
            <div>${escapeHtml(I18n.t(reason))}</div>
            ${blocked ? `<div class="trip-schedule-blocked">${escapeHtml(I18n.t(
                'Save or cancel first: {what}', { what: blocked.label }))}</div>` : ''}
            ${action}
        </div>`;
    }

    /**
     * One reading surface for every plan.
     *
     * A team plan and a single traveller's plan are the same timeline with a
     * different number of people on it; keeping two renderers meant two answers
     * to "what happens on Tuesday" and only one of them was ever maintained.
     */
    function renderPlan(plan) {
        window.TripTeamView?.render?.(plan);
        window.TripExportActions?.refresh?.(plan);
        window.TripTeamRisks?.render?.(plan);
        window.TripSelection?.reconcile?.(plan);
        const root = document.getElementById('trip-schedule-list');
        const status = document.getElementById('trip-schedule-status');
        const notice = staleNotice(plan);
        if (notice) {
            if (root) root.innerHTML = notice;
            if (status) status.textContent = I18n.t('Needs a new preview');
            window.TripTimelineToolbar?.render?.(plan);
            return;
        }
        window.TripTimelineView?.render?.(plan, root);
        window.TripTimelineToolbar?.render?.(plan);
        window.TripFlexibleSuggestions?.render?.(plan);
        if (status) {
            status.textContent = (plan?.members || []).length > 1
                ? I18n.t('{count} people travelling', { count: plan.members.length })
                : I18n.t('{count} schedule items', { count: (plan?.schedule_items || []).length });
        }
        const openStopId = window.TripBriefingDraft?.getStopId?.();
        if (!plan?.id || (openStopId && !(plan.stops || []).some(stop => stop.id === openStopId))) {
            window.TripBriefingActions?.close?.({ force: true });
        }
    }

    window.TripScheduleView = Object.freeze({ sortItems, renderPlan,
        businessDays, dayOf, periodOf, transportModeLabel, staleNotice });
    window.addEventListener?.('language:changed', () => renderPlan(State.currentTripPlan));
})();
