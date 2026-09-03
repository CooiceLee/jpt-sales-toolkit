/** One colour per traveller, the same one everywhere they appear.

Three people on one map is three routes over the same continent. Drawn in a
single colour the only way to tell whose is whose is to hover every line, so
each member gets a colour and the map says which is which.
*/
(function() {
    // Chosen to stay apart for the common forms of colour blindness, and to sit
    // against the map's muted background rather than on top of it.
    const PALETTE = Object.freeze([
        '#1f5135', '#8B1A1A', '#1c4f78', '#9a6212',
        '#5b3a86', '#0f6b6b', '#8a3f6b', '#4a5a1e',
    ]);
    const UNASSIGNED = '#8a8a8a';

    function order(plan) {
        return (plan?.members || []).map(member => member.user_id);
    }

    function colorOf(plan, userId) {
        const index = order(plan).indexOf(userId);
        return index < 0 ? UNASSIGNED : PALETTE[index % PALETTE.length];
    }

    /** The colours of everybody on a journey, widest band first. */
    function bandsFor(plan, memberIds) {
        const ids = (memberIds || []).filter(Boolean);
        if (!ids.length) return [{ color: UNASSIGNED, weight: 3 }];
        // Travelling together is one line, so the colours are drawn as nested
        // bands rather than side by side: the shape of the journey stays one
        // journey while still naming everyone on it.
        return ids.map((userId, index) => ({
            color: colorOf(plan, userId),
            weight: Math.max(3, 3 + (ids.length - 1 - index) * 3),
        }));
    }

    function legend(plan) {
        return (plan?.members || []).map(member => ({
            user_id: member.user_id,
            name: member.display_name || member.user_id,
            color: colorOf(plan, member.user_id),
        }));
    }

    window.TripTeamColors = Object.freeze({ colorOf, bandsFor, legend });
})();
