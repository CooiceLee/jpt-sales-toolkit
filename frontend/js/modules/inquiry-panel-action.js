/** One action on the open panel: whose it is, and whether it is still theirs.
 *
 * Comparing customer ids is not enough. Open A, start saving, look at B, come
 * back to A: the id matches again, so an id-only check hands A's older answer
 * to the panel the reader has since re-opened and typed into. What identifies
 * an edit is the panel session - the customer *and* which visit to them - so
 * that is what an action carries from start to finish.
 *
 * It also separates the two things that can go wrong after a write lands. The
 * write succeeded and the re-read failed: the record exists, and saying "error
 * saving" would send somebody to create it a second time. Or the write itself
 * failed while the reader was elsewhere: that must be recorded, but not thrown
 * across the panel they are working in now.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

    // An action holds the editor and the button it locked, not their ids: after
    // the reader opens somebody else those ids belong to a different form, and
    // releasing them by id unlocks a panel this action never touched.
    function begin(options = {}) {
        const session = window.InquiryPanelSession?.capture?.() || null;
        const leadId = session?.leadId || State.currentInquiry?.id || null;
        const editor = options.editor
            ? document.getElementById(options.editor) : null;
        const button = options.button
            ? document.getElementById(options.button) : null;
        const held = editor ? window.InquiryEditFreeze?.hold?.(editor) : null;
        return Object.freeze({ leadId, session, editor, button, held });
    }

    // Called after every wait that precedes a visible change. The identity was
    // checked once, before the counts were refreshed, and the waits after that
    // let the reader move on while the tail still ran.
    function release(action) {
        if (!action) return;
        window.InquiryEditFreeze?.release?.(action.held);
        if (action.button && isCurrent(action)) action.button.disabled = false;
    }

    function isCurrent(action) {
        if (!action?.leadId) return false;
        if (action.session && window.InquiryPanelSession?.isCurrent) {
            return window.InquiryPanelSession.isCurrent(action.session);
        }
        return State.currentInquiry?.id === action.leadId;
    }

    // Written, then the screen could not be brought up to date. Both halves of
    // that have to be said, or the reader saves again.
    function savedButNotRefreshed(error) {
        console.error('Panel refresh after a successful save failed:', error);
        window.PanelSaveState?.show?.('saved', tr('screen not refreshed'));
        window.notify?.(tr(
            'Saved, but the panel could not be refreshed. Reopen this lead to '
            + 'see the latest data — do not save again.'
        ));
    }

    // Archived, then the screen could not be brought up to date. Same shape as
    // a save: saying "archive failed" sends somebody to archive it again.
    function archivedButNotRefreshed(error) {
        console.error('Panel refresh after a successful archive failed:', error);
        window.notify?.(tr(
            'Archived, but the panel could not be refreshed. Reopen this lead '
            + 'to see the latest data — do not archive again.'
        ));
    }

    // Written, and the counts beside the modules could not be re-read. The
    // record is there; the numbers on the left may be yesterday's.
    function countsNotRefreshed() {
        return tr('Saved. The navigation counts could not be refreshed, so '
            + 'they may be out of date — reopen JPT to reload them.');
    }

    // Failed, and the reader has moved on. Their panel is not ours to
    // interrupt; the failure still has to be findable.
    function failedAfterMovingOn(error) {
        console.error('Panel action failed after the reader moved on:', error);
        window.notify?.(tr('An earlier change could not be saved: {error}', {
            error: error?.message || tr('Unknown error'),
        }));
    }

    window.InquiryPanelAction = Object.freeze({
        begin, isCurrent, release, savedButNotRefreshed, failedAfterMovingOn,
        archivedButNotRefreshed, countsNotRefreshed,
    });
})();
