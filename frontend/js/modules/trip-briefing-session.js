/** One save of one visit's preparation: whose it is, and whether it is still.
 *
 * A save takes the values as they were when the button was pressed, and then
 * waits. Two things happened in that gap. The form stayed editable, so what
 * was typed next was neither sent nor kept - the success path cleared the
 * draft and closed the editor. And the reader could close this visit, choose
 * another plan and start writing there, at which point the older answer closed
 * *that* editor and pulled the screen back to the plan they had left.
 *
 * So a save carries the elements it froze and the identity it belongs to -
 * plan, stop, the editor's own request number, and the number the plan on
 * screen arrived under - and the tail only touches the screen while all of
 * them still hold.
 */
(function () {
    'use strict';

    function begin({ planId, stopId, epoch }) {
        const editor = window.TripBriefingReveal?.editor?.() || null;
        return Object.freeze({
            planId, stopId, epoch,
            // The number the plan on screen arrived under, not the newest one:
            // reading the plan back at the end belongs to this save, not to
            // whatever the reader has asked for since.
            token: window.TripPlanIdentity?.accepted?.(),
            editor,
            held: window.InquiryEditFreeze?.hold?.(editor) || null,
        });
    }

    /** Whether the screen still belongs to this save.
     *
     * `epoch` is the editor's own counter: opening another visit or closing
     * this one moves it, which is exactly when the tail must keep its hands
     * off. The plan and stop are checked too, because the reader can leave by
     * changing plans without touching this editor at all.
     */
    function isCurrent(session, epoch) {
        if (!session) return false;
        return session.epoch === epoch
            && window.TripBriefingDraft?.getStopId?.() === session.stopId
            && State.currentTripPlan?.id === session.planId;
    }

    /** Give the form back to the reader - only if it is still their form. */
    function release(session, epoch) {
        if (!session || !isCurrent(session, epoch)) return false;
        window.InquiryEditFreeze?.release?.(session.held);
        return true;
    }

    window.TripBriefingSession = Object.freeze({ begin, isCurrent, release });
})();
