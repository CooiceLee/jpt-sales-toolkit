/** Only the newest thing the reader asked for is allowed to win.

Several actions decide which plan is on screen - opening one, creating one,
reloading the planner, saving something that has to be read back. They all take
time, and while one is in flight the reader can start another. Whichever answer
happens to arrive last would otherwise win, putting them on a plan they did not
choose with nothing on screen saying why.

So each of them takes a number first. Answering with a number that is no longer
the newest means the reader has moved on, and the answer is dropped.
*/
(function() {
    let newest = 0;
    let shown = 0;

    /** Claim the screen for what is about to be asked for. */
    function intend() {
        newest += 1;
        return newest;
    }

    function isCurrent(token) {
        return token === newest;
    }

    /** The number in force now: the newest thing anyone has asked for. */
    function current() {
        return newest;
    }

    /** The number the plan on screen arrived under.

    Not the same as the newest: the reader can ask for another plan and still
    be looking at this one while it loads. A refresh that happens because
    something else finished - results imported, a save read back - belongs to
    what is on screen, so it carries this number. Carrying the newest instead
    would borrow the identity of the plan they are waiting for, and this
    refresh would then be allowed to answer in its place.
    */
    function accepted() {
        return shown;
    }

    /** Show a plan the server sent, unless the reader has moved on. */
    function accept(token, plan) {
        if (!plan || !isCurrent(token)) return false;
        shown = token;
        State.currentTripPlan = plan;
        return true;
    }

    /** Clear the plan on screen, unless the reader has moved on. */
    function clear(token) {
        if (!isCurrent(token)) return false;
        shown = token;
        State.currentTripPlan = null;
        return true;
    }

    window.TripPlanIdentity = Object.freeze({
        intend, current, accepted, isCurrent, accept, clear,
    });
})();
