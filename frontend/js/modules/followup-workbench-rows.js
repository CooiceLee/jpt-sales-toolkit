/** One follow-up lead, as a row in the selector and as a row in the table.
 *
 * Both views show the same lead and open the same panel: they carry the same
 * [data-inquiry-card] contract the cards used, so selection, the keyboard and
 * the panel's own draft protection are the production ones.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const h = value => escapeHtml(value ?? '');
    const BUCKETS = [
        { key: 'overdue', label: 'Overdue' },
        { key: 'today', label: 'Due today' },
        { key: 'week', label: 'Next 7 days' },
        { key: 'beyond', label: 'Later than a week' },
        { key: 'later', label: 'No date set' },
    ];

    function shortDate(value) {
        if (!value) return '';
        const date = new Date(String(value).length <= 10 ? `${value}T00:00:00` : value);
        if (Number.isNaN(date.getTime())) return String(value);
        return new Intl.DateTimeFormat(window.I18n?.locale?.() || 'en-US',
            { month: '2-digit', day: '2-digit' }).format(date);
    }

    // The same calendar-day comparison filterPlanned() uses, on the same
    // objects: calendarDay() answers with a local Date, and turning it into a
    // string to compare with "2026-09-09" made every valid date look like it
    // was inside the next seven days - overdue, today and a month away alike.
    // `now` is a Date, never a UTC slice of one: in Shanghai mornings and
    // European evenings that slice is yesterday or tomorrow.
    function bucketOf(item, now = new Date()) {
        const model = window.FollowupFilterModel;
        const due = model?.calendarDay?.(item.next_followup_date);
        const today = model?.calendarDay?.(now);
        if (!due || !today) return 'later';
        if (due < today) return 'overdue';
        if (due.getTime() === today.getTime()) return 'today';
        const weekEnd = new Date(today);
        weekEnd.setDate(weekEnd.getDate() + 6);
        // Later than a week is its own group: a customer due next month is not
        // a task for this week, and is not "no date set" either.
        return due <= weekEnd ? 'week' : 'beyond';
    }

    function stageDot(stage) {
        const known = { Following: 'following', Quoted: 'quoted' };
        return known[stage] || 'other';
    }

    // One amount rule for both views, and it is the shared one: a deal priced
    // at zero is a different fact from a deal nobody priced, and a missing
    // currency is said out loud rather than filled in with dollars.
    function amountOf(item) {
        const first = item.deal_amount ?? null;
        const booked = !(first === null || first === '');
        const value = booked ? first : item.estimated_value ?? null;
        if (value === null || value === '' || !Number.isFinite(Number(value))) return null;
        const code = String(item.currency || '').trim().toUpperCase() || 'UNSPECIFIED';
        return { code, value: Number(value), kind: booked ? 'deal' : 'estimate' };
    }

    // Which of the two numbers this is, said out loud: an estimate printed the
    // way a signed amount is printed reads as money already agreed.
    function moneyText(item) {
        const amount = amountOf(item);
        if (!amount) return tr('not quoted');
        const figure = window.MoneyTotals.text({ [amount.code]: amount.value });
        return `${tr(amount.kind === 'deal' ? 'Deal' : 'Est.')} ${figure}`;
    }

    function row(item) {
        const grade = item.quality_rating;
        const money = moneyText(item);
        const priced = amountOf(item) !== null;
        const next = item.next_followup_date
            ? shortDate(item.next_followup_date) : tr('not set');
        const last = item.latest_follow_up_at
            ? shortDate(item.latest_follow_up_at) : tr('No formal follow-up');
        return `
            <article class="wb-row" data-inquiry-card tabindex="0"
                data-inquiry-id="${h(item.id)}" data-card-context="followup"
                role="button" aria-pressed="false"
                aria-label="${h(tr('Open lead {id} for {company}', {
                    id: item.inquiry_id || item.id,
                    company: item.company_name || tr('Unknown Company'),
                }))}">
                <div class="wb-main">
                    <span class="wb-company" data-business>${h(item.company_name || tr('Unknown Company'))}</span>
                    <span class="wb-id" data-business>${h(item.inquiry_id || '')}</span>
                    <span class="wb-flags">
                        <span class="quality-badge ${item.quality_issue_count ? '' : 'hidden'}"
                            >${h(tr('{count} to review', { count: Number(item.quality_issue_count) || 0 }))}</span>
                        <span class="grade-badge grade-${grade ? String(grade).toLowerCase() : 'none'}"
                            title="${h(grade ? tr('Lead quality grade') : tr('Not graded yet'))}"
                            >${h(grade || '–')}</span>
                    </span>
                </div>
                <div class="wb-meta" data-business>${h([item.contact_name, item.country].filter(Boolean).join(' · '))}</div>
                <div class="wb-stage"><i class="wb-dot wb-dot-${stageDot(item.stage)}"></i><span>${h(tr(item.stage || 'Following'))}</span></div>
                <div class="wb-last"><span class="wb-lead">${h(tr('Last follow-up '))}</span><b>${h(last)}</b>
                    <span class="wb-text" data-business>${h(item.latest_follow_up_summary || '')}</span></div>
                <div class="wb-next"><span class="wb-lead">${h(tr('Next step '))}</span><b class="${item.next_followup_date ? '' : 'wb-muted'}">${h(next)}</b></div>
                <div class="wb-amount"><b class="${priced ? '' : 'wb-muted'}" data-business>${h(money)}</b></div>
            </article>`;
    }

    function tableRow(item) {
        return `
            <tr data-inquiry-card tabindex="0" data-inquiry-id="${h(item.id)}"
                data-card-context="followup" aria-pressed="false">
                <td class="wb-cell-name" data-business>${h(item.company_name || tr('Unknown Company'))}</td>
                <td class="wb-cell-id" data-business>${h(item.inquiry_id || '')}</td>
                <td class="wb-cell-stage">${h(tr(item.stage || 'Following'))}</td>
                <td class="wb-cell-date">${h(item.latest_follow_up_at ? formatDate(item.latest_follow_up_at) : tr('No formal follow-up'))}</td>
                <td class="wb-cell-note" data-business>${h(item.latest_follow_up_summary || '')}</td>
                <td class="wb-cell-date">${h(item.next_followup_date ? formatDate(item.next_followup_date) : tr('not set'))}</td>
                <td class="num wb-cell-money" data-business>${h(moneyText(item))}</td>
                <td data-business>${h(item.owner_name || '')}</td>
            </tr>`;
    }

    window.FollowupRows = Object.freeze({
        BUCKETS, bucketOf, row, tableRow, moneyText, amountOf,
    });
})();
