function renderReviewTable(containerId, columns, rows) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!rows.length) {
        container.innerHTML = '<div class="empty-state compact">No data</div>';
        return;
    }
    container.innerHTML = `
        <table class="data-table compact-table">
            <thead>
                <tr>${columns.map(([label]) => `<th>${escapeHtml(label)}</th>`).join('')}</tr>
            </thead>
            <tbody>
                ${rows.map(row => `
                    <tr>
                        ${columns.map(([, getter]) => {
                            const value = typeof getter === 'function' ? getter(row) : row[getter];
                            return `<td>${escapeHtml(value ?? '-')}</td>`;
                        }).join('')}
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderLeadReviewTable(containerId, rows, includeReasons) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!rows.length) {
        container.innerHTML = '<div class="empty-state compact">No leads</div>';
        return;
    }
    container.innerHTML = `
        <table class="data-table compact-table">
            <thead>
                <tr>
                    <th>Lead</th>
                    <th>Customer</th>
                    <th>Stage</th>
                    <th>Value</th>
                    <th>${includeReasons ? 'Risk' : 'Owner'}</th>
                </tr>
            </thead>
            <tbody>
                ${rows.map(row => `
                    <tr>
                        <td><button type="button" class="text-link" onclick="openInquiryPanel('${row.id}')">${escapeHtml(row.display_id || '-')}</button></td>
                        <td>
                            <button type="button" class="text-link" onclick="jumpToCustomerStageCards('${row.id}', '${row.stage || ''}', '${row.customer_id || ''}')">${escapeHtml(row.customer_name || '-')}</button>
                            <button type="button" class="table-mini-link" onclick="focusReviewMapCustomer('${row.customer_id || ''}')">Locate</button>
                        </td>
                        <td><button type="button" class="text-link" onclick="jumpToCustomerStageCards('${row.id}', '${row.stage || ''}', '${row.customer_id || ''}')">${escapeHtml(row.stage || '-')}</button></td>
                        <td>${escapeHtml(formatMoney(row.value || 0))}</td>
                        <td>${escapeHtml(includeReasons ? (row.risk_reasons || []).join(', ') : (row.owner_name || '-'))}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

