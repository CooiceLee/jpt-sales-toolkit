/** Put a saved plan's own values back on its row in the plan list.

The list is drawn from its own copy of each plan. Saving a plan and redrawing
the list is not enough - the copy still holds what the plan said before, so a
renamed plan kept its old name and a moved one kept its old dates. Every field
a row shows is refreshed in this one place, so the next field added to a row
cannot be forgotten in the several places a plan gets saved.
*/
function syncTripPlanListEntry(plan) {
    if (!plan?.id) return;
    const shown = ['title', 'start_date', 'end_date', 'row_version'];
    State.tripPlans = (State.tripPlans || []).map(item => item.id === plan.id
        ? {
            ...item,
            ...Object.fromEntries(shown.map(field => [field, plan[field]])),
            stop_count: (plan.stops || []).length,
        }
        : item);
}

function formatTripPlanDateRange(plan) {
    const start = plan.start_date ? formatDate(plan.start_date) : '';
    const end = plan.end_date ? formatDate(plan.end_date) : '';
    if (!start && !end) return I18n.t('No dates');
    if (!start || !end) return start || end;
    return I18n.t('{start} to {end}', { start, end });
}

window.syncTripPlanListEntry = syncTripPlanListEntry;
window.formatTripPlanDateRange = formatTripPlanDateRange;
