/** Hold an edit area still while the save it belongs to is in flight.
 *
 * A save takes the values as they were when the button was pressed. While the
 * request was out the fields stayed editable, so anything typed next was
 * neither sent nor kept: the response redrew the tab and the newer text was
 * gone with no warning. Holding the fields for the length of the request makes
 * what was submitted the same as what is on screen.
 */
(function () {
    'use strict';

    const HELD = 'data-edit-held';

    function hold(container) {
        if (!container?.querySelectorAll) return null;
        const held = [];
        container.querySelectorAll('input, select, textarea, button').forEach(field => {
            if (field.disabled) return;
            field.disabled = true;
            field.setAttribute?.(HELD, '');
            held.push(field);
        });
        return held;
    }

    function release(held) {
        if (!Array.isArray(held)) return;
        held.forEach(field => {
            // The response usually redraws the tab, and a field that is no
            // longer on the page has nothing to give back.
            if (!field.hasAttribute?.(HELD)) return;
            field.disabled = false;
            field.removeAttribute?.(HELD);
        });
    }

    window.InquiryEditFreeze = Object.freeze({ hold, release });
})();
