(function () {
    'use strict';

    const ACTIVE_SAMPLE = new Set(['Open', 'In Progress']);
    const ACTIVE_SERVICE = ACTIVE_SAMPLE;
    function dateKey(value) {
        if (!value) return null;
        const text = String(value).trim();
        const match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/);
        if (!match) return null;
        const [year, month, day] = match.slice(1, 4).map(Number);
        const calendar = new Date(Date.UTC(year, month - 1, day));
        const valid = calendar.getUTCFullYear() === year
            && calendar.getUTCMonth() === month - 1 && calendar.getUTCDate() === day;
        if (!valid) return null;
        let normalized = text.replace(' ', 'T');
        if (normalized.length === 10) normalized += 'T00:00:00Z';
        else if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(normalized)) normalized += 'Z';
        const parsed = Date.parse(normalized);
        return Number.isFinite(parsed) ? parsed : null;
    }
    function firstDate(item, fields) {
        for (const field of fields) {
            const value = dateKey(item?.[field]);
            if (value !== null) return value;
        }
        return null;
    }
    function compareValues(left, right, direction = 1) {
        if (left === null) return right === null ? 0 : 1;
        if (right === null) return -1;
        return direction * (left - right);
    }
    const compareDates = (left, right, fields, direction = 1) =>
        compareValues(firstDate(left, fields), firstDate(right, fields), direction);
    const textKey = value =>
        String(value || '').normalize('NFKC').trim().toLowerCase();
    function tie(left, right) {
        for (const field of ['inquiry_id', 'display_id', 'id']) {
            const a = textKey(left?.[field]);
            const b = textKey(right?.[field]);
            if (a !== b) return a < b ? -1 : 1;
        }
        return 0;
    }
    function sorted(items, compare) {
        return items.map((item, index) => ({ item, index }))
            .sort((left, right) =>
                compare(left.item, right.item) || tie(left.item, right.item)
                || left.index - right.index
            )
            .map(entry => entry.item);
    }

    function taskDate(item, statuses, field, useLatest = false) {
        const values = (item?._afterSalesTasks || [])
            .filter(task => !statuses || statuses.has(task.status))
            .map(task => dateKey(task[field]))
            .filter(value => value !== null);
        return values.length ? (useLatest ? Math.max(...values) : Math.min(...values)) : null;
    }

    function handler(items) {
        return sorted(items, (a, b) => compareDates(a, b, ['inquiry_date', 'created_at']));
    }

    function followup(items, options = {}) {
        const activityFirst = options.activityMode && options.activityMode !== 'all';
        return sorted(items, (a, b) => activityFirst
            ? compareDates(a, b, ['activity_date'])
                || compareDates(a, b, ['next_followup_date'])
            : compareDates(a, b, ['next_followup_date'])
                || compareDates(a, b, ['activity_date']));
    }

    function sampling(items) {
        return sorted(items, (a, b) => {
            const leftActive = ACTIVE_SAMPLE.has(a.sample_status);
            const rightActive = ACTIVE_SAMPLE.has(b.sample_status);
            if (leftActive !== rightActive) return leftActive ? -1 : 1;
            return leftActive
                ? compareDates(a, b, ['sample_due_date'])
                    || compareDates(a, b, ['sample_task_updated_at'], -1)
                : compareDates(a, b, ['sample_task_updated_at'], -1);
        });
    }

    function deal(items) {
        return sorted(items, (a, b) => {
            if (a.stage !== b.stage) return a.stage === 'Quoted' ? -1 : 1;
            const direction = a.stage === 'Lost' ? -1 : 1;
            return compareDates(a, b, ['quotation_date'], direction)
                || compareDates(a, b, ['inquiry_date', 'created_at'], direction);
        });
    }

    function fulfillment(items) {
        return sorted(items, (a, b) => {
            const leftDone = a.fulfillment_status === 'Completed';
            const rightDone = b.fulfillment_status === 'Completed';
            if (leftDone !== rightDone) return leftDone ? 1 : -1;
            return compareDates(a, b, ['po_date'], leftDone ? -1 : 1)
                || compareDates(a, b, ['inquiry_date', 'created_at'], leftDone ? -1 : 1);
        });
    }

    function aftersales(items) {
        return sorted(items, (a, b) => {
            const leftActive = ACTIVE_SERVICE.has(a.service_status);
            const rightActive = ACTIVE_SERVICE.has(b.service_status);
            if (leftActive !== rightActive) return leftActive ? -1 : 1;
            if (leftActive) return compareValues(
                taskDate(a, ACTIVE_SERVICE, 'due_date'),
                taskDate(b, ACTIVE_SERVICE, 'due_date')
            ) || compareValues(
                taskDate(a, ACTIVE_SERVICE, 'created_at'),
                taskDate(b, ACTIVE_SERVICE, 'created_at')
            );
            return compareValues(taskDate(a, null, 'updated_at', true),
                taskDate(b, null, 'updated_at', true), -1);
        });
    }

    window.WorklistSort = { aftersales, deal, followup, fulfillment, handler, sampling };
})();
