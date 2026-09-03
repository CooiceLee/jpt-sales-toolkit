/** How one visit's changes are drawn, and how a choice is offered. */
(function() {
    const tr = (text, params = {}) => Object.entries(params).reduce(
        (value, [key, item]) => value.replace(`{${key}}`, item),
        window.I18n?.t(text) || text);
    const esc = value => window.escapeHtml?.(value ?? '') || String(value ?? '');

    function value(item) {
        if (item === null || item === undefined || item === '') return '—';
        // Whether a sample or a quote is needed comes back as an answer, not
        // as a machine's true and false.
        if (item === true) return esc(tr('Yes'));
        if (item === false) return esc(tr('No'));
        return esc(item);
    }

    // A visit is named the way the plan names it, not by the identifier the
    // workbook uses to find it again.
    function visitLabel(row) {
        const when = [row.planned_date, row.planned_period].filter(Boolean).join(' ');
        return [row.customer, when].filter(Boolean).join(' · ') || tr('This visit');
    }

    function stateLabel(name) {
        return tr(TripWorkingImportText.STATES[name] || name);
    }

    function fieldRow(row, item, resolutions) {
        const conflict = item.state === 'conflict';
        const chosen = resolutions[row.token]?.[item.field] || '';
        const warn = '';
        const choice = conflict ? `<select data-trip-working-token="${esc(row.token)}"
            data-trip-working-field="${esc(item.field)}" aria-label="${esc(tr('Which one to keep'))}">
            <option value="">${esc(tr('Choose'))}</option>
            <option value="workbook"${chosen === 'workbook' ? ' selected' : ''}>${esc(tr('Use the workbook'))}</option>
            <option value="current"${chosen === 'current' ? ' selected' : ''}>${esc(tr('Keep what is in the app'))}</option>
        </select>` : '';
        return `<tr class="${conflict ? 'trip-working-conflict' : ''}">
            <td>${esc(item.label)}</td><td>${value(item.baseline)}</td>
            <td>${value(item.uploaded)}</td><td>${value(item.current)}</td>
            <td>${esc(stateLabel(item.state))}${choice}${warn}</td></tr>`;
    }

    // Whether what is chosen right now would leave a row that cannot be saved.
    // The server works out every mixture; this only looks up the one in front
    // of the reader, so the rule itself lives in one place.
    function unsaveable(row, resolutions) {
        const chosen = resolutions[row.token] || {};
        return (row.unsaveable_combinations || []).find(item =>
            Object.entries(item.choices).every(([field, take]) => chosen[field] === take));
    }

    function visitBlock(row, resolutions) {
        const changed = (row.comparisons || []).filter(item => item.state !== 'unchanged');
        const fields = changed.map(item => fieldRow(row, item, resolutions)).join('');
        const blocked = unsaveable(row, resolutions);
        const warning = blocked
            ? `<div class="trip-working-warning">${esc(tr(
                'These choices leave this visit unsaveable: {why}',
                { why: tr(blocked.message) }))}</div>`
            : '';
        const impacts = (row.impacts || []).map(item =>
            `<li><strong>${esc(tr(item.label))}</strong>: ${esc(tr(item.detail))}</li>`).join('');
        const headers = TripWorkingImportText.COLUMNS
            .map(header => `<th>${esc(tr(header))}</th>`).join('');
        return `<details class="trip-working-row" open><summary>${esc(visitLabel(row))}</summary>
            ${fields ? `<table><thead><tr>${headers}</tr></thead><tbody>${fields}</tbody></table>`
                : `<p>${esc(tr('Nothing was recorded for this visit.'))}</p>`}
            ${warning}
            ${impacts ? `<div class="trip-working-impact"><strong>${esc(tr('What else this changes'))}</strong><ul>${impacts}</ul></div>` : ''}
        </details>`;
    }

    window.TripWorkingImportView = { visitBlock, value, unsaveable };
})();
