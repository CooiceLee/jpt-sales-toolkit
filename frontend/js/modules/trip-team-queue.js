/** One travel-team change at a time.

Every row in the team card saves on its own. Sent together, their answers come
back in whatever order the server produces them, and the earlier answer
overwrites the later change - while the box goes on showing the newer value, so
the reader has no way to know the trip does not agree with the screen.
*/
(function() {
    let tail = Promise.resolve();

    function run(task) {
        const next = tail.then(task, task);
        // A rejected task must not stop everything queued behind it.
        tail = next.then(() => undefined, () => undefined);
        return next;
    }

    window.TripTeamQueue = Object.freeze({ run });
})();
