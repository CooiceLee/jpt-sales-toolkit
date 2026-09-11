/** Bring the visit preparation editor to the reader who asked for it.

The editor is one panel, inside the daily schedule. The buttons that open it are
spread down the page - the schedule itself, the team timeline, visit execution,
the flexible-visit suggestions. Opening it without moving the reader leaves them
looking at the button they just pressed, which reads as a button that does
nothing, and pressing it again does even less.
*/
(function() {
    const editor = () => document.getElementById('trip-briefing-editor');

    // The editor belongs to one zone; the buttons that open it are spread
    // across the others, and a zone that is not the open one is display:none.
    // Taking `hidden` off the editor there shows nobody anything: the request
    // succeeded, the form was filled in, and the reader was still looking at
    // the button they pressed. So making it visible means opening its zone,
    // and every way in goes through here rather than through `hidden`.
    function open(root = editor()) {
        if (!root) return null;
        root.hidden = false;
        const zone = root.closest?.('[data-trip-zone]')?.dataset?.tripZone;
        if (zone && window.TripZones?.current?.() !== zone) {
            window.TripZones?.show?.(zone);
        }
        return root;
    }

    // And bringing the reader to it, for the buttons that are a request to
    // look at it now. Re-drawing the form they are already looking at is not.
    function show(root = editor()) {
        const target = open(root);
        target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return target;
    }

    window.TripBriefingReveal = Object.freeze({ editor, open, show });
})();
