/** Coordinate, duplicate and error rules shared by Trip candidate surfaces. */
(function() {
    function hasExactCoordinates(candidate) {
        return Boolean(
            MapSupport.coordinatePair(candidate?.lat, candidate?.lng)
            && candidate?.coordinate_quality === 'exact'
            && !candidate?.needs_coordinate_review
        );
    }

    function alreadyInPlan(candidate) {
        return (State.currentTripPlan?.stops || [])
            .some(stop => stop.customer_id === candidate?.customer_id);
    }

    async function openCoordinateReview(index) {
        const candidate = State.tripCandidates?.[index];
        if (!candidate) return;
        if (switchModule('coordinate-review') === false) {
            alert(I18n.t('Coordinate Review is not available for this account.'));
            return;
        }
        await loadCoordinateReview();
        const query = candidate.customer_name || '';
        setInputValue('coordinate-review-search', query);
        searchCoordinateReview(query);
        document.getElementById('coordinate-review-list')?.scrollIntoView({ block: 'start' });
        notify(I18n.t('Coordinate Review opened for {customer}.', { customer: query || I18n.t('Customer') }));
    }

    function errorCode(error) {
        const details = error?.details;
        return String(details?.code || details?.error || error?.code || '').toLowerCase();
    }

    function friendlyError(error) {
        const raw = String(error?.message || 'Unknown error');
        const code = errorCode(error);
        const halfDayOverrun = raw.match(/\bby\s+(\d+)\s+half-day slot(?:s|\(s\))?/i);
        if (halfDayOverrun) {
            return I18n.t('The route exceeds the plan end date by {count} days. Shorten stays, remove stops, or extend the date range.', {
                count: Number(halfDayOverrun[1]) / 2
            });
        }
        const overrun = raw.match(/\bby\s+(\d+)\s+(?:calendar\s+)?day(?:s|\(s\))?/i)
            || raw.match(/(?:overrun|beyond)[^\d]*(\d+)\s*days?/i);
        if (overrun || /end_date_exceeded|date_window_exceeded|itinerary_overrun/.test(code)) {
            return overrun
                ? I18n.t('The route exceeds the plan end date by {count} days. Shorten stays, remove stops, or extend the date range.', { count: overrun[1] })
                : I18n.t('The route exceeds the plan end date. Shorten stays, remove stops, or extend the date range.');
        }
        if (/stale|out[ -]of[ -]date/i.test(raw) || /stale.*itinerary|itinerary.*stale/.test(code)) {
            return I18n.t('This route is out of date. Recalculate the preview before saving or exporting.');
        }
        if (/duplicate|already (?:exists|in (?:the )?(?:trip )?plan|added)/i.test(raw) || /duplicate.*(?:stop|customer)|customer.*duplicate/.test(code)) {
            return I18n.t('This customer is already in the plan. Confirm another visit instance before adding it again.');
        }
        if (/latitude|longitude|coordinates?/i.test(raw) || /missing.*coordinates?/.test(code)) {
            return I18n.t('Precise coordinates are required. Open Coordinate Review and save the location first.');
        }
        return I18n.t(raw);
    }

    function warningText(warning) {
        const raw = String(warning || '');
        const invalidHoliday = raw.match(/^Ignored invalid holiday dates:\s*(.+)$/i);
        if (invalidHoliday) return I18n.t('Ignored invalid holiday dates: {dates}', { dates: invalidHoliday[1] });
        const overrun = raw.match(/\bby\s+(\d+)\s+(?:calendar\s+)?day(?:s|\(s\))?/i);
        if (overrun) {
            return I18n.t('The route exceeds the plan end date by {count} days. Shorten stays, remove stops, or extend the date range.', { count: overrun[1] });
        }
        return friendlyError({ message: raw });
    }

    window.openTripCandidateCoordinateReview = openCoordinateReview;
    window.TripCandidateState = Object.freeze({
        hasExactCoordinates,
        alreadyInPlan,
        friendlyError,
        warningText,
    });
})();
