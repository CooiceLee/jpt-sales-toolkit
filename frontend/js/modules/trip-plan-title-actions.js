/** The plan name is saved when it is typed, not when the route is.

A name is not route input: the reader renames the plan and expects it to be
named. Carrying it in the route draft meant it only reached the server on the
next "save route", and any reload before that put the old name back.

Saving it must not disturb anything else. Refilling the whole form from the
server would throw away dates, transport choices and stop durations the reader
had changed and not yet saved - so only the name is touched, in the draft, on
the row in the list, and in the input if the save failed.
*/
(function() {
    const t = (key, params = {}) => I18n.t(key, params);
    const input = () => document.getElementById('trip-title');

    function show(title) {
        const field = input();
        if (field) field.value = title || '';
    }

    async function titleChanged() {
        const plan = State.currentTripPlan;
        const title = String(input()?.value ?? '').trim();
        if (!plan?.id) return;
        if (!title) {
            // An unnamed plan cannot be found again. Say so and put the name
            // back, rather than leaving an empty box over a plan still named.
            notify(t('A plan needs a name. The previous name has been kept.'));
            show(plan.title);
            return;
        }
        if (title === plan.title) return;
        try {
            setTripBusy(true);
            const token = TripPlanIdentity.intend();
            const renamed = await ApiClient.updateTripPlan(plan.id, {
                title, row_version: plan.row_version || null,
            });
            if (!TripPlanIdentity.accept(token, renamed)) return;
            notify(t('Plan renamed to {name}', { name: title }));
        } catch (err) {
            console.error('Rename trip plan error:', err);
            show(plan.title);
            await handleTripError(err, 'Rename trip plan');
            return;
        } finally {
            setTripBusy(false);
        }
        const saved = State.currentTripPlan;
        // The name is already saved, so the route is no less saved than before.
        TripPlanningDraft.adopt(draft => {
            draft.header = { ...draft.header, title: saved.title };
        });
        show(saved.title);
        syncTripPlanListEntry(saved);
        renderTripPlans();
    }

    window.TripPlanTitleActions = Object.freeze({ titleChanged });
})();
