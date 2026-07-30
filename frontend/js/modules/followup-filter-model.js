(function () {
    'use strict';

    const DAY_MS = 24 * 60 * 60 * 1000;
    const ACTIVITY_SOURCES = [
        ['latest_follow_up_at', 'follow_up'],
        ['inquiry_date', 'inquiry'],
        ['created_at', 'created'],
    ];

    function dayNumber(date) {
        return Math.floor(Date.UTC(
            date.getFullYear(), date.getMonth(), date.getDate()
        ) / DAY_MS);
    }

    function calendarDay(value) {
        if (!value) return null;
        if (value instanceof Date) {
            if (Number.isNaN(value.getTime())) return null;
            return new Date(value.getFullYear(), value.getMonth(), value.getDate());
        }
        const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (!match) return null;
        const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
        return date.getFullYear() === Number(match[1])
            && date.getMonth() === Number(match[2]) - 1
            && date.getDate() === Number(match[3]) ? date : null;
    }

    function effectiveActivity(item) {
        for (const [field, source] of ACTIVITY_SOURCES) {
            const date = calendarDay(item[field]);
            if (date) return { date, source, value: item[field] };
        }
        return { date: null, source: 'unknown', value: null };
    }

    function annotate(items, now = new Date()) {
        const today = calendarDay(now);
        return items.map(item => {
            const activity = effectiveActivity(item);
            const age = activity.date && today
                ? Math.max(0, dayNumber(today) - dayNumber(activity.date))
                : null;
            return {
                ...item,
                activity_date: activity.value,
                activity_date_source: activity.source,
                activity_age_days: age,
                has_formal_follow_up: Boolean(calendarDay(item.latest_follow_up_at)),
            };
        });
    }

    function filterPlanned(items, mode = 'all', now = new Date()) {
        const today = calendarDay(now);
        if (!today || mode === 'all') return items.slice();
        const weekEnd = new Date(today);
        weekEnd.setDate(weekEnd.getDate() + 6);
        return items.filter(item => {
            const due = calendarDay(item.next_followup_date);
            if (!due) return false;
            if (mode === 'overdue') return due < today;
            if (mode === 'today') return due.getTime() === today.getTime();
            if (mode === 'week') return due >= today && due <= weekEnd;
            return true;
        });
    }

    function customRangeStatus(options = {}) {
        const from = calendarDay(options.from);
        const to = calendarDay(options.to);
        if (!from && !to) return { valid: false, reason: 'missing' };
        if (from && to && from > to) return { valid: false, reason: 'reversed' };
        return { valid: true, from, to };
    }

    function filterActivity(items, options = {}, now = new Date()) {
        const mode = options.mode || 'all';
        if (mode === 'all') return items.slice();
        if (mode === 'never') return items.filter(item => !item.has_formal_follow_up);
        if (mode === 'custom') {
            const range = customRangeStatus(options);
            if (!range.valid) return [];
            return items.filter(item => {
                const date = calendarDay(item.activity_date);
                return date && (!range.from || date >= range.from) && (!range.to || date <= range.to);
            });
        }
        const threshold = Number(mode);
        if (!Number.isFinite(threshold) || threshold < 0) return items.slice();
        return items.filter(item => Number.isFinite(item.activity_age_days)
            && item.activity_age_days >= threshold);
    }

    window.FollowupFilterModel = {
        annotate,
        calendarDay,
        customRangeStatus,
        effectiveActivity,
        filterActivity,
        filterPlanned,
    };
})();
