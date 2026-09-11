/** What the manual entry form knows: which customer, and how the save is going.
 *
 * Somebody with no spreadsheet to import and no email to paste had no way in:
 * the "New Inquiry" button opened the email parser and asked them for a
 * document they did not have. This holds the small amount of state that entry
 * needs - the customer they picked or are about to create, and whether a save
 * is in flight - so the form, the search and the submit can each stay small.
 */
(function () {
    'use strict';

    let state = null;

    function reset() {
        state = {
            // The existing customer they chose, if any. Null means the details
            // typed in the form describe a customer nobody has recorded yet.
            customer: null,
            matches: [],
            searched: false,
            busy: false,
            // One save, one lead. A second click while the first is in flight
            // must not create a second record.
            submitEpoch: 0,
            // Searching and saving are separate jobs with separate ordering.
            // A search that comes back late must not clear a customer the
            // reader has since chosen, and must not cancel a save.
            searchEpoch: 0,
        };
        return state;
    }

    function get() {
        return state || reset();
    }

    function chooseCustomer(customer) {
        get().customer = customer || null;
        return get().customer;
    }

    function beginSearch() {
        const current = get();
        current.searchEpoch += 1;
        return current.searchEpoch;
    }

    function isCurrentSearch(epoch) {
        return get().searchEpoch === epoch;
    }

    // A late answer to an earlier search is discarded whole: applying only
    // part of it left the list from one query beside a customer chosen from
    // another.
    function setMatches(matches, epoch) {
        const current = get();
        if (epoch !== undefined && current.searchEpoch !== epoch) return null;
        current.matches = Array.isArray(matches) ? matches : [];
        current.searched = true;
        current.customer = null;
        return current.matches;
    }

    function begin() {
        const current = get();
        if (current.busy) return null;
        current.busy = true;
        current.submitEpoch += 1;
        return current.submitEpoch;
    }

    function end(epoch) {
        const current = get();
        if (current.submitEpoch !== epoch) return false;
        current.busy = false;
        return true;
    }

    window.NewInquiryState = Object.freeze({
        reset, get, chooseCustomer, setMatches, begin, end,
        beginSearch, isCurrentSearch,
    });
})();
