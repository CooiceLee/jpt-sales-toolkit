function renderFormField(name, def, value) {
    const type = def.type;
    const safeValue = escapeHtml(value);

    if (type === 'contact_select') {
        return renderPrimaryContactSelect(value);
    }
    if (type === 'select' && def.options) {
        return `
            <select class="form-select" name="${name}">
                <option value="">Select...</option>
                ${def.options.map(o => `<option value="${escapeHtml(o)}" ${value === o ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('')}
            </select>
        `;
    }
    if (type === 'text') {
        return `<textarea class="form-textarea" name="${name}" rows="3">${safeValue}</textarea>`;
    }
    if (type === 'boolean') {
        return `
            <select class="form-select" name="${name}">
                <option value="">Select...</option>
                <option value="true" ${value === true ? 'selected' : ''}>Yes</option>
                <option value="false" ${value === false ? 'selected' : ''}>No</option>
            </select>
        `;
    }
    if (type === 'date') {
        let dateVal = '';
        if (value) {
            try { dateVal = new Date(value).toISOString().split('T')[0]; } catch {}
        }
        return `<input type="date" class="form-input" name="${name}" value="${dateVal}">`;
    }
    if (type === 'datetime') {
        let dtVal = '';
        if (value) {
            try { dtVal = new Date(value).toISOString().slice(0, 16); } catch {}
        }
        return `<input type="datetime-local" class="form-input" name="${name}" value="${dtVal}">`;
    }
    if (type === 'number') {
        return `<input type="number" class="form-input" name="${name}" value="${safeValue}" step="any">`;
    }
    if (type === 'email') {
        return `<input type="email" class="form-input" name="${name}" value="${safeValue}" placeholder="example@company.com">`;
    }
    return `<input type="text" class="form-input" name="${name}" value="${safeValue}">`;
}
