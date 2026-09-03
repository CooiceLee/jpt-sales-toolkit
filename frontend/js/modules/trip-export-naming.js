/** What a downloaded trip file is called, and why a download is refused. */
(function() {
    // Each download is one of eight documents, and the name has to say which
    // plan and which of the eight it is: a folder of files named only by the
    // plan's identifier is a folder nobody can forward from safely.
    const DOCUMENTS = Object.freeze({
        'xlsx:shared': { label: 'Shared itinerary', slug: 'shared', extension: 'xlsx' },
        'xlsx:full': { label: 'Itinerary with visit preparation', slug: 'with-visit-prep', extension: 'xlsx' },
        'html:shared': { label: 'Shared web itinerary', slug: 'shared', extension: 'html' },
        'html:full': { label: 'Web itinerary with visit preparation', slug: 'with-visit-prep', extension: 'html' },
        'ics:': { label: 'Calendar file', slug: 'calendar', extension: 'ics' },
        'working:': { label: 'Field workbook', slug: 'field-workbook', extension: 'xlsx' },
        'md:': { label: 'Markdown', slug: 'with-visit-prep', extension: 'md' },
        'csv:': { label: 'CSV', slug: 'with-visit-prep', extension: 'csv' },
    });

    function document_(format, variant = '') {
        return DOCUMENTS[`${format}:${variant}`] || DOCUMENTS[`${format}:`]
            || { label: String(format).toUpperCase(), slug: String(format), extension: format };
    }

    function slug(title) {
        return String(title || '')
            .replace(/[\\/:*?"<>|]/g, ' ')
            .replace(/\s+/g, '-')
            .replace(/^-+|-+$/g, '')
            .slice(0, 60);
    }

    function today() {
        const now = new Date();
        const month = String(now.getMonth() + 1).padStart(2, '0');
        return `${now.getFullYear()}${month}${String(now.getDate()).padStart(2, '0')}`;
    }

    function filename(plan, format, variant, fallback) {
        const document = document_(format, variant);
        const name = slug(plan?.title);
        if (!name) return fallback;
        return `${name}-${document.slug}-${today()}.${document.extension}`;
    }

    // Why the panel is not usable, in the reader's own terms. Null means it is.
    function blockedReason(plan) {
        if (!plan?.id) return 'Select a saved itinerary to download.';
        if (window.TripPlanningDraft?.get?.()?.dirty) {
            return 'Save the current route draft before exporting it.';
        }
        const summary = plan.itinerary_summary || {};
        if (summary.stale === true || summary.valid === false) {
            return 'This route is out of date. Recalculate and save it before exporting.';
        }
        return null;
    }

    window.TripExportNaming = { document: document_, filename, blockedReason };
})();
