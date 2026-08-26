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

    function itemLabel(item) {
        if (typeOf(item) === 'leg') {
            return item.title || item.label || [item.from_label || item.origin, item.to_label || item.destination]
                .filter(Boolean).join(' → ') || I18n.t('Travel leg');
        }
        return item.title || item.customer_name || item.location_name || item.label || I18n.t('Untitled');
    }

    function renderItem(item) {
        const type = ['customer', 'free', 'leg'].includes(typeOf(item)) ? typeOf(item) : 'free';
        const stopId = item.stop_id || item.source_id || item.id || '';
        const canOpen = type === 'customer' && stopId;
        const slotProgress = item.half_day_count > 1
            ? I18n.t('Half-day {index} of {count}', { index: item.half_day_index || 1, count: item.half_day_count }) : '';
        const details = type === 'leg'
            ? [transportModeLabel(item.selected_mode || item.travel_mode || item.mode),
                item.time_hours != null ? I18n.t('{count} hours', { count: item.time_hours }) : '', slotProgress]
            : [item.city, item.country,
                item.duration_half_days ? TripDuration.label(item.duration_half_days) : slotProgress];
        return `<button type="button" class="trip-schedule-item is-${h(type)}" ${canOpen
            ? `onclick="TripBriefingActions.open('${h(stopId)}')"` : 'disabled'}>
            <span class="trip-schedule-item-type">${h(I18n.t({ customer: 'Customer visit', free: 'Personal stop', leg: 'Travel leg' }[type]))}</span>
            <strong>${h(itemLabel(item))}</strong>
            <small>${h(details.filter(Boolean).join(' · '))}</small>
            ${item.confirmation_status ? `<em>${h(I18n.t(item.confirmation_status))}</em>` : ''}
        </button>`;
    }

    function render(items = [], target = document.getElementById('trip-schedule-list'), plannedDays = []) {
        if (!target) return;
        const sorted = sortItems(items);
        const days = [...new Set([...plannedDays, ...sorted.map(dayOf)].filter(Boolean))].sort();
        if (!days.length) {
            target.innerHTML = `<div class="empty-state compact">${h(I18n.t('Save or preview a route to create the AM/PM schedule.'))}</div>`;
            return;
        }
        target.innerHTML = days.map(day => `<section class="trip-schedule-day">
            <h3>${h(day)}</h3><div class="trip-schedule-periods">
            ${['AM', 'PM'].map(period => `<div class="trip-schedule-period"><h4>${h(I18n.t(period === 'AM' ? 'Morning (AM)' : 'Afternoon (PM)'))}</h4>
                ${sorted.filter(item => dayOf(item) === day && periodOf(item) === period).map(renderItem).join('')
                    || `<div class="trip-schedule-empty">${h(I18n.t('Available'))}</div>`}
            </div>`).join('')}</div></section>`).join('');
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

    function staleNotice(plan) {
        const summary = plan?.itinerary_summary || {};
        if (!(summary.stale === true || summary.valid === false)) return '';
        // An out-of-date itinerary is not an empty one. Say why it went away and
        // offer the way back, instead of showing a grid of empty half-days.
        const reason = (summary.warnings || [])[0]
            || 'The itinerary is out of date. Preview and save it again.';
        return `<div class="empty-state compact trip-schedule-stale">
            <div>${escapeHtml(I18n.t(reason))}</div>
            <button type="button" class="btn btn-primary btn-sm"
                onclick="previewCurrentTripItinerary()">${escapeHtml(I18n.t('Preview route'))}</button>
        </div>`;
    }

    function renderPlan(plan) {
        const root = document.getElementById('trip-schedule-list');
        const notice = staleNotice(plan);
        if (notice) {
            if (root) root.innerHTML = notice;
            const status = document.getElementById('trip-schedule-status');
            if (status) status.textContent = I18n.t('Needs a new preview');
            return;
        }
        render(plan?.schedule_items || [], root, businessDays(plan));
        const status = document.getElementById('trip-schedule-status');
        if (status) status.textContent = I18n.t('{count} schedule items', {
            count: (plan?.schedule_items || []).length,
        });
        const openStopId = window.TripBriefingDraft?.getStopId?.();
        if (!plan?.id || (openStopId && !(plan.stops || []).some(stop => stop.id === openStopId))) {
            window.TripBriefingActions?.close?.({ force: true });
        }
    }

    window.TripScheduleView = Object.freeze({ sortItems, render, renderPlan, businessDays, dayOf, periodOf });
    window.addEventListener?.('language:changed', () => renderPlan(State.currentTripPlan));
})();
