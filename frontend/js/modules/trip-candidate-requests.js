/** Which answer from the customer list may be shown.

Filtering and paging both take a round trip, and both can be asked again before
the last answer arrives. Whichever came back last would otherwise write - so a
page of one filter lands in the list of another, or two pages land out of the
order they were asked for, and nothing on screen says which is which.

Only the newest request may write. Every way of changing what is being asked
for - a filter, a page - starts one, so the newest request is always the
question the reader is actually waiting on.
*/
(function() {
    let newest = 0;
    let paging = 0;

    /** Claim the list for a request about to be made. */
    function start() {
        newest += 1;
        return newest;
    }

    /** Whether this request is still the one the reader is waiting for. */
    function mayWrite(request) {
        return request === newest;
    }

    /** Ask to be the one page being fetched.

    One page at a time, but only among requests for the same question. A page
    still on its way for a filter the reader has left must not keep them from
    paging the list they are looking at now - and when it finally answers it
    must not free a lock somebody else is holding.

    Returns the new request, or 0 when a page for this question is already on
    its way.
    */
    function claimPaging() {
        if (paging !== 0 && paging === newest) return 0;
        paging = start();
        return paging;
    }

    function releasePaging(request) {
        if (paging === request) paging = 0;
    }

    window.TripCandidateRequests = Object.freeze({
        start, mayWrite, claimPaging, releasePaging,
    });
})();
