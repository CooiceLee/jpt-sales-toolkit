/** One row of the travel list: one journey, and everybody whose journey it is.
 *
 * The map draws one line per connection and merges colleagues onto it on
 * purpose - splitting that line per person and per day would draw the same road
 * four times. A list is read differently: a row carries dates, distances and
 * hours, and those are facts about one person's journey. Merged by connection
 * alone, two colleagues driving Lyon → Porto two days apart became one row
 * showing the first one's day and the first one's distance, and the second
 * journey was not on the page at all.
 *
 * So the list gets its own rule, and the map keeps the one it draws with: a row
 * may speak for several people only when every fact it shows is the same for
 * all of them. Anything else is two rows.
 *
 * It is also the one place that answers "which legs is this row", so the list,
 * the travel options rendered into it and whatever a search then applies to all
 * mean the same journey. They used to count in two different lists - the merged
 * one on screen and the unmerged one underneath - and from the first merge
 * onwards the results were one row out.
 */
(function () {
    'use strict';

    const text = value => (value == null ? '' : String(value));

    function modeOf(leg, draft) {
        const override = draft?.legOverrides?.[leg?.leg_key] || {};
        return text(override.selected_mode || leg?.selected_mode
            || leg?.travel_mode || leg?.mode);
    }

    /** Every fact the row puts on screen, in one string. */
    function identityOf(leg, draft) {
        return [
            leg?.leg_key, modeOf(leg, draft),
            leg?.from_label ?? leg?.from_name, leg?.to_label ?? leg?.to_name,
            leg?.planned_start_date, leg?.planned_start_period,
            leg?.planned_end_date, leg?.planned_end_period,
            leg?.distance_km, leg?.time_hours,
            leg?.travel_half_days ?? leg?.travel_days,
            leg?.departure_airport_lat, leg?.departure_airport_lng,
            leg?.arrival_airport_lat, leg?.arrival_airport_lng,
            // Where the numbers came from is part of what the row claims.
            leg?.estimate_source, leg?.approximate, leg?.online,
        ].map(text).join('|');
    }

    function rows(plan, draft) {
        const legs = plan?.legs || [];
        if (plan?.planning_mode !== 'team') {
            return legs.map(leg => ({ key: text(leg.leg_key), leg, legs: [leg], members: [], memberIds: [] }));
        }
        const merged = new Map();
        legs.forEach(leg => {
            const key = identityOf(leg, draft);
            const row = merged.get(key) || { key, leg, legs: [], members: [], memberIds: [] };
            row.legs.push(leg);
            if (leg.member_id && !row.memberIds.includes(leg.member_id)) {
                row.memberIds.push(leg.member_id);
                const name = window.TripTeamJourneys?.memberName?.(plan, leg.member_id);
                if (name) row.members.push(name);
            }
            merged.set(key, row);
        });
        return [...merged.values()];
    }

    /**
     * Whose journeys a row stands for.
     *
     * A leg override is stored per member but the browser can only send one
     * keyed by the connection, and the server then applies it to everybody on
     * the team (review_service._team_leg_settings). So an edit made on a row
     * reaches these members - which is what the row has to say out loud rather
     * than pretending each name can be edited on its own.
     */
    function legsAt(plan, draft, index) {
        return rows(plan, draft)[index]?.legs || [];
    }

    /**
     * Which row a connection is on, from the timeline's point of view.
     *
     * The timeline entry knows the connection and who is on it; the row model
     * may have split that connection into one row per set of facts, so the
     * traveller is what picks between them. Without the member it is the first
     * row for that connection - which is the only row a single-traveller plan
     * has anyway.
     */
    function indexOf(plan, draft, legKey, members) {
        const list = rows(plan, draft);
        const wanted = text(legKey);
        const asked = (Array.isArray(members) ? members : [members]).filter(Boolean).map(text);
        const key = list_ => [...new Set(list_.map(text))].sort().join(',');
        // The row for exactly these travellers first: a shared journey is one
        // row naming them all, and a colleague on the same connection a day
        // later is a different row with the same key.
        const exact = list.findIndex(row => text(row.leg.leg_key) === wanted
            && key(row.memberIds) === key(asked));
        if (exact >= 0 || asked.length) return exact;
        // No travellers named - a plan with one of them, where the connection
        // is the whole identity.
        return list.findIndex(row => text(row.leg.leg_key) === wanted);
    }

    window.TripLegRows = Object.freeze({ identityOf, modeOf, rows, legsAt, indexOf });
})();
