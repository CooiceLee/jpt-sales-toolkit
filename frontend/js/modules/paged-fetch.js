/** Read a whole list from a paged endpoint, and say so when it could not.
 *
 * A queue that asks for one page and then works out the whole picture from it
 * reports whatever happened to be on that page: 105 tasks came back as 100,
 * and the five customers they belonged to came back as one. Reading every page
 * is what makes a count a count. Asking for an enormous limit instead only
 * moves the cliff somewhere nobody is looking.
 */
(function () {
    'use strict';

    const PAGE_SIZE = 500;
    // Far above anything this tool holds, and it is reported rather than
    // silently applied: a list that stops early must never read as complete.
    const CEILING = 20000;

    async function all(fetchPage, options = {}) {
        const pageSize = Number(options.pageSize) || PAGE_SIZE;
        const ceiling = Number(options.ceiling) || CEILING;
        const items = [];
        let offset = 0;
        while (offset < ceiling) {
            const page = await fetchPage({ limit: pageSize, offset });
            const rows = Array.isArray(page) ? page : (page?.items || []);
            // The end is a page with nothing on it. Treating a short page as
            // the end assumes the endpoint honoured the size we asked for; an
            // endpoint that caps it at a smaller number would hand back a full
            // page that looks short, and the rest of the list would vanish
            // while the read reported itself complete. Advancing by the rows
            // actually received holds whatever the cap turns out to be.
            if (!rows.length) {
                return { items, complete: true, total: items.length };
            }
            items.push(...rows);
            offset += rows.length;
        }
        return { items, complete: false, total: items.length };
    }

    // Said once, in one voice: a list that stopped short must never be read as
    // the whole of anything, and every consumer says so the same way.
    function note(...pages) {
        const partial = pages.some(page => page && page.complete === false);
        if (!partial) return '';
        return window.I18n?.t
            ? window.I18n.t('Showing the first {count} records. Narrow the filters to see the rest.',
                { count: pages.reduce((total, page) => total + (page?.items?.length || 0), 0) })
            : 'Showing the first records only. Narrow the filters to see the rest.';
    }

    function isComplete(...pages) {
        return pages.every(page => !page || page.complete !== false);
    }

    window.PagedFetch = Object.freeze({ all, note, isComplete, PAGE_SIZE, CEILING });
})();
