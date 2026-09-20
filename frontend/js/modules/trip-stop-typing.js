/** The visit purpose somebody has typed and not saved yet.
 *
 * It is the one field on the route card that is neither saved on change nor
 * held in the route draft, and two things went wrong with carrying it across a
 * redraw by reading the input and putting it back:
 *
 * Choosing another visit removed the field, so there was nothing to read and
 * nothing to put back - the text was simply gone, and coming back to that visit
 * showed the stored value as though nothing had been typed. A draft belongs to
 * the visit it was typed for, not to whichever card happens to be on screen.
 *
 * And "unsaved" was decided by comparing the input against the plan in memory.
 * Once a response had updated that plan, a field nobody had touched no longer
 * matched it, so the old value was treated as somebody's work and written back
 * over the newer one - and the next save would have sent it. What makes a field
 * unsaved is that it differs from what it was *loaded with*, so that is what is
 * remembered when it is drawn.
 *
 * Keyed by plan and stop, so another plan's work never appears on this one.
 */
(function () {
    'use strict';

    const drafts = new Map();              // `${planId}:${stopId}` -> typed value
    const baselines = new Map();           // the same key -> value it was drawn with
    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const planId = () => (typeof State === 'undefined' ? null : State?.currentTripPlan?.id) || 'none';
    const key = stopId => `${planId()}:${stopId}`;

    /** What the plan in memory currently holds for this visit. */
    const stored = stopId => String(((typeof State === 'undefined' ? null : State?.currentTripPlan?.stops) || [])
        .find(item => String(item.id) === String(stopId))?.visit_purpose ?? '');

    function changed(edit) {
        const before = firstDirty()?.id || null;
        edit();
        if ((firstDirty()?.id || null) !== before) window.TripRouteBar?.render?.();
    }

    /**
     * What the field was drawn with - the thing "edited" is measured against.
     *
     * While something is being typed this must not move. A redraw arriving
     * with a newer stored value would otherwise re-baseline the draft against
     * it, and then two things would be wrong at once: typing the text back to
     * what it was first loaded with would still read as unsaved, and saving
     * would carry the newest row_version - writing over a purpose somebody
     * else had just changed, with nothing said about it.
     */
    function baseline(stopId, value) {
        const id = key(stopId);
        if (drafts.has(id)) return;        // being edited: the baseline is the edit's
        baselines.set(id, String(value ?? ''));
    }

    /** What the card should draw: the reader's unsaved text, or the stored value. */
    function valueFor(stopId, value) {
        const draft = drafts.get(key(stopId));
        baseline(stopId, value);
        return draft === undefined ? String(value ?? '') : draft;
    }

    /**
     * Something was typed. Whether there is anything left to save is asked of
     * what is *stored* - not of the baseline.
     *
     * Typing back to the value this edit started from, after somebody else has
     * changed it, is still a change to the stored purpose. Calling that "no
     * pending work" would hand the save a value it must not write and nothing
     * to warn about: the old text would go back over the newer one.
     */
    function note(stopId, value) {
        const id = key(stopId);
        const text = String(value ?? '');
        changed(() => {
            if (text !== stored(stopId)) { drafts.set(id, text); return; }
            drafts.delete(id);             // it now says what the record says
            baselines.set(id, text);
        });
    }

    /** Saved, or deliberately given up: only now may the baseline move. */
    function markClean(stopId) {
        changed(() => drafts.delete(key(stopId)));
        baselines.set(key(stopId), stored(stopId));
    }

    function reset() { changed(() => drafts.clear()); }

    function isDirty(stopId = null) {
        if (stopId == null) return [...drafts.keys()].some(id => id.startsWith(`${planId()}:`));
        return drafts.has(key(stopId));
    }

    function firstDirty() {
        const prefix = `${planId()}:`;
        const id = [...drafts.keys()].find(entry => entry.startsWith(prefix));
        if (!id) return null;
        const stopId = id.slice(prefix.length);
        const stop = ((typeof State === 'undefined' ? null : State?.currentTripPlan?.stops) || [])
            .find(item => String(item.id) === stopId);
        return { id: stopId, name: stop?.customer_name || stop?.location_name || '' };
    }

    /** Put back what was typed, for the in-place redraw of this same card. */
    function restore(stopId) {
        const draft = drafts.get(key(stopId));
        if (draft === undefined) return;
        const field = document.getElementById(`stop-purpose-${stopId}`);
        if (field) field.value = draft;
    }

    function discard(stopId) {
        markClean(stopId);                  // the draft goes first, so the
        const value = stored(stopId);       // baseline may move to the stored value
        const field = document.getElementById(`stop-purpose-${stopId}`);
        if (field) field.value = value;
        window.renderCurrentTripPlan?.();
    }

    /**
     * Leaving a visit with something typed into it.
     *
     * Same contract as every other local editor here: say which visit is
     * holding it and refuse to move, rather than letting the text disappear
     * behind a click on something else.
     */
    function guard(nextStopId = null) {
        const open = firstDirty();
        if (!open || String(open.id) === String(nextStopId)) return false;
        alert(tr('Save or discard the visit purpose for {name} before moving on.', {
            name: open.name || tr('this visit'),
        }));
        return true;
    }

    window.TripStopTyping = Object.freeze({
        baseline, valueFor, note, markClean, reset, isDirty, firstDirty,
        restore, discard, guard, stored,
        baselineOf: stopId => baselines.get(key(stopId)) ?? '',
        hasDraft: stopId => drafts.has(key(stopId)),
        draftOf: stopId => drafts.get(key(stopId)),
        // Which version survives is asked and answered in trip-purpose-conflict.js
        conflict: (...args) => window.TripPurposeConflict?.of?.(...args) || null,
        blockSave: (...args) => window.TripPurposeConflict?.blockSave?.(...args) || false,
        keepMine: (...args) => window.TripPurposeConflict?.keepMine?.(...args),
        takeTheirs: stopId => discard(stopId),
        rebaseline: (stopId, value) => baselines.set(key(stopId), String(value ?? '')),
    });
})();
