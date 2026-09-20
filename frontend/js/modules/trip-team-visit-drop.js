/** Take one person off one visit, from the line that visit is listed on.
 *
 * Doing it before meant leaving the team card, opening the other card, finding
 * the customer down a long list, opening their preparation, finding the
 * attendee rows and deleting one - to say a thing the reader was already
 * looking at: this person is on this visit.
 *
 * It writes through the preparation, exactly as that editor does, so everything
 * built on attendees still holds: the server marks the route out of date when
 * the people change, and the plan is read back so the schedule, the map and the
 * other cards say the same thing afterwards.
 *
 * What it will not do is guess. A visit that names nobody is attended by
 * whoever is travelling, and a visit naming one person cannot lose that person
 * without becoming everybody's - both are refused with the way to do what was
 * meant, rather than done quietly and differently.
 */
(function () {
    'use strict';

    const t = (key, params = {}) => window.I18n?.t(key, params) || key;

    // Exactly the fields the briefing accepts. Echoing back what was read would
    // be refused: the record carries worked-out values the write does not take.
    const KEEP = Object.freeze({
        location: ['name', 'address', 'city', 'postal_code', 'country', 'lat',
            'lng', 'use_customer_default'],
        customer_team: ['name', 'title', 'phone', 'email', 'notes', 'sequence_no'],
        contacts: ['source_contact_id', 'name', 'position', 'email', 'phone',
            'role', 'notes', 'sequence_no'],
        participants: ['user_id', 'display_name', 'role', 'responsibility',
            'notes', 'sequence_no'],
        channel_partner_companions: ['company_name', 'name', 'position', 'phone',
            'email', 'role', 'notes', 'sequence_no'],
        equipment: ['kind', 'model', 'specification', 'quantity', 'owner_team',
            'notes', 'sequence_no'],
        agenda_items: ['topic', 'owner', 'preparation', 'expected_outcome',
            'sequence_no'],
    });

    const pick = (row, fields) => Object.fromEntries(
        fields.filter(field => row?.[field] !== undefined)
            .map(field => [field, row[field]]));

    function payloadFrom(record, participants) {
        const location = pick(record?.location || {}, KEEP.location);
        return {
            row_version: record?.row_version ?? null,
            stop_row_version: record?.stop_row_version,
            confirmation_status: record?.confirmation_status || 'unconfirmed',
            timezone: record?.timezone || null,
            location: { ...location,
                use_customer_default: location.use_customer_default !== false },
            customer_team: (record?.customer_team || [])
                .map(row => pick(row, KEEP.customer_team)),
            contacts: (record?.contacts || []).map(row => pick(row, KEEP.contacts)),
            participants: participants.map(row => pick(row, KEEP.participants)),
            channel_partner_companions: (record?.channel_partner_companions || [])
                .map(row => pick(row, KEEP.channel_partner_companions)),
            equipment: (record?.equipment || []).map(row => pick(row, KEEP.equipment)),
            agenda_items: (record?.agenda_items || [])
                .map(row => pick(row, KEEP.agenda_items)),
        };
    }

    /** Why this cannot be done here, and where it can. */
    function refusal(named, userId) {
        if (!named.length) return 'nobody-named';
        if (!named.includes(userId)) return 'not-named';
        if (named.length === 1) return 'only-one';
        return '';
    }

    function explain(reason, stopId) {
        const message = {
            'nobody-named': t('This visit names nobody, so everybody travelling attends it. Name who goes under Visit preparation first.'),
            'not-named': t('This visit does not name this person, so there is nothing here to take away. Name who goes under Visit preparation.'),
            'only-one': t('This is the only person named on this visit. Taking them off would leave it attended by everybody travelling - name somebody else first, or remove the visit from the route.'),
        }[reason];
        if (!message) return;
        alert(message);
        window.TripBriefingActions?.open?.(stopId);
    }

    async function drop(userId, stopId) {
        const plan = typeof State === 'undefined' ? null : State?.currentTripPlan;
        const planId = plan?.id;
        if (!planId || !userId || !stopId || State.tripBusy) return false;
        // The same guards every other route-affecting action answers to.
        if (window.TripBriefingDraft?.guard?.()) return false;
        if (window.TripVisitDraft?.guard?.()) return false;
        const name = (plan.members || []).find(item => item.user_id === userId)
            ?.display_name || userId;
        const stop = (plan.stops || []).find(item => item.id === stopId);
        const where = stop?.customer_name || stop?.location_name || t('this visit');
        try {
            setTripBusy(true);
            const record = await ApiClient.getTripBriefing(planId, stopId);
            const named = (record?.participants || []).map(row => row.user_id);
            const reason = refusal(named, userId);
            if (reason) { explain(reason, stopId); return false; }
            if (!window.confirm(t('Take {name} off the visit to {where}? The route is worked out again from who is left.',
                { name, where }))) return false;
            const token = TripPlanIdentity.intend();
            await ApiClient.putTripBriefing(planId, stopId, payloadFrom(
                record, (record.participants || [])
                    .filter(row => row.user_id !== userId)));
            await window.TripPlanRefresh?.reread?.(planId, { token });
            // Written, and the reader may have opened another plan while it was
            // in the air. The write stands; their screen is not ours to report
            // into, and the re-read above has already left it alone.
            if (!TripPlanIdentity.isCurrent(token)) return true;
            notify(t('{name} is no longer on the visit to {where}. The route needs recalculating.',
                { name, where }));
            return true;
        } catch (error) {
            console.error('Drop member from visit error:', error);
            await handleTripError(error, 'Take somebody off a visit');
            return false;
        } finally {
            setTripBusy(false);
        }
    }

    window.TripTeamVisitDrop = Object.freeze({ drop, payloadFrom, refusal });
})();
