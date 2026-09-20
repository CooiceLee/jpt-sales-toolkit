/** Somebody else changed this visit purpose while it was being typed.
 *
 * The draft keeps the value the field was loaded with, so "did the stored one
 * move" is answerable: only about this field, because a response that changed
 * the dates or the duration leaves the purpose exactly as it was and there is
 * nothing to ask about.
 *
 * When it has moved, the save stops. Carrying the draft on the newest row
 * version would write over what somebody else had just entered and report
 * nothing - the optimistic check cannot see it, because the record as a whole
 * really is the one that was read. Which version survives is the reader's
 * decision, and both are put in front of them to make it.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const typing = () => window.TripStopTyping;

    function of(stopId) {
        const draft = typing();
        if (!draft?.hasDraft?.(stopId)) return null;
        const base = draft.baselineOf(stopId);
        const theirs = draft.stored(stopId);
        return theirs === base ? null : { mine: draft.draftOf(stopId), theirs, base };
    }

    /** Refuse a save that would carry the draft over somebody else's change. */
    function blockSave(stopId) {
        if (!of(stopId)) return false;
        alert(tr('The visit purpose changed while you were editing it. Choose which '
            + 'version to keep before saving.'));
        window.renderCurrentTripPlan?.();
        return true;
    }

    /** Keep what was typed - an overwrite, made on purpose and on the record. */
    function keepMine(stopId) {
        typing()?.rebaseline?.(stopId, typing().stored(stopId));
        window.renderCurrentTripPlan?.();
    }

    window.TripPurposeConflict = Object.freeze({ of, blockSave, keepMine });
})();
