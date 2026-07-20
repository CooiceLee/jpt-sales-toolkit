(function () {
    'use strict';
    const tr = text => window.I18n?.t(text) || text;
    const FIELD_LABELS = {
        website: 'Website',
        industry: 'Industry',
        customer_type: 'Customer type',
        company_size: 'Company size',
        language: 'Language',
        country: 'Country',
        city: 'City',
        postal_code: 'Postal code',
        address: 'Address',
        region: 'Region',
        lat: 'Latitude',
        lng: 'Longitude',
        normalized_address: 'Normalized address',
        geocode_source: 'Geocode source',
        geocode_confidence: 'Geocode confidence',
        geocode_locked: 'Geocode locked',
        company_description: 'Company description',
        extra_json: 'Additional data',
    };

    function value(item) {
        if (item === null || item === undefined || item === '') return '—';
        return typeof item === 'object' ? JSON.stringify(item) : String(item);
    }

    function row(label, source, target, resolution) {
        return `<li class="merge-conflict-row">
            <strong>${escapeHtml(label)}</strong>
            <span><b>${escapeHtml(tr('Source value'))}:</b> ${escapeHtml(value(source))}</span>
            <span><b>${escapeHtml(tr('Target value'))}:</b> ${escapeHtml(value(target))}</span>
            <span><b>${escapeHtml(tr('Resolution'))}:</b> ${escapeHtml(tr(resolution))}</span>
        </li>`;
    }

    function section(label, rows, open = false) {
        if (!rows.length) return '';
        return `<details class="governance-details merge-conflict-details"${open ? ' open' : ''}>
            <summary>${escapeHtml(tr(label))} (${rows.length})</summary>
            <ul>${rows.join('')}</ul>
        </details>`;
    }

    function render(preview) {
        const fields = (preview.field_conflicts || []).map(item => row(
            `${tr('Field')}: ${tr(FIELD_LABELS[item.field] || item.field)}`,
            item.source,
            item.target,
            item.resolution === 'preserved_in_audit_manifest'
                ? 'Preserve source value in audit record'
                : 'Keep target value'
        ));
        const contacts = (preview.contact_conflicts || []).map(item => row(
            tr('Duplicate contact email'),
            [item.source?.name, item.source?.email].filter(Boolean).join(' · '),
            [item.target?.name, item.target?.email].filter(Boolean).join(' · '),
            'Fill missing target fields, keep target conflicts, archive source duplicate'
        ));
        const labels = [
            ...(preview.domain_conflicts || []).map(item => row(
                tr('Duplicate domain'), item.domain, item.domain,
                'Keep target and archive source duplicate'
            )),
            ...(preview.alias_conflicts || []).map(item => row(
                tr('Duplicate alias'), item.alias_name || item.normalized_alias,
                item.alias_name || item.normalized_alias,
                'Keep target and archive source duplicate'
            )),
        ];
        const sections = [
            section('Field conflicts', fields, true),
            section('Contact conflicts', contacts),
            section('Domain and alias conflicts', labels),
        ].filter(Boolean);
        return sections.length
            ? `<div class="merge-conflict-list">${sections.join('')}</div>`
            : `<p class="merge-no-conflicts">${escapeHtml(tr('No conflicting values were found.'))}</p>`;
    }

    window.CustomerMergeConflictView = { render };
})();
