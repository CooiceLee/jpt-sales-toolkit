/** Bring the visit preparation editor to the reader who asked for it.

The editor is one panel, inside the daily schedule. The buttons that open it are
spread down the page - the schedule itself, the team timeline, visit execution,
the flexible-visit suggestions. Opening it without moving the reader leaves them
looking at the button they just pressed, which reads as a button that does
nothing, and pressing it again does even less.
*/
(function() {
    function show(root) {
        if (!root) return;
        root.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    window.TripBriefingReveal = Object.freeze({ show });
})();
