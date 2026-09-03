/** Keep the reader's place when the visit preparation editor is redrawn.

Every button in the editor - add a row, remove one, move one - rebuilds the
whole form, and a rebuilt element starts at the top. In a panel taller than the
window that throws the reader back to the beginning on every click, so the work
of the click is done somewhere they can no longer see.
*/
(function() {
    const pane = root => root?.querySelector?.('.trip-briefing-scroll');

    function replace(root, html) {
        const place = pane(root)?.scrollTop || 0;
        root.innerHTML = html;
        const next = pane(root);
        if (next) next.scrollTop = place;
    }

    function focusRow(kind, index) {
        // A row that was just added is what the reader wants to fill in, so it
        // is brought to them rather than left below the fold.
        const rows = document.querySelectorAll(
            `[data-briefing-array-key="${kind}"] [data-row-index]`
        );
        const field = rows[index]?.querySelector('select, input, textarea');
        if (!field) return;
        field.scrollIntoView({ behavior: 'smooth', block: 'center' });
        field.focus({ preventScroll: true });
    }

    window.TripBriefingScroll = Object.freeze({ replace, focusRow });
})();
