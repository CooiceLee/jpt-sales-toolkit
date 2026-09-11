/** A number you can follow, and only where it leads somewhere exact.
 *
 * A count on the dashboard is a question - "which 193?" - and the answer is a
 * list the app already has. Where that list holds exactly the leads the number
 * counted, the number opens it. Where it does not, the number stays a number:
 * a metric that looks clickable and lands on a different set of rows is worse
 * than one that never offered.
 *
 * "Last 7 days" has no list filtered by seven days, and an amount is not a set
 * of leads. Neither is clickable, and neither pretends to be.
 */
(function () {
    'use strict';

    // metric -> the list that holds exactly those leads.
    //
    // The follow-up queue is two stages by design - Assigned and Following are
    // both "being followed up" - so the module's own count opens it, while the
    // single funnel stage opens the page that can filter to exactly one stage.
    // Sending one stage to the two-stage list was how "Following 193" opened a
    // list that also held the assigned ones.
    const TARGETS = Object.freeze({
        'kpi-total': { module: 'handler', stage: '' },
        'kpi-following': { module: 'followup', tab: 'all' },
        'kpi-won': { module: 'fulfillment', tab: 'all' },
        'stage-New': { module: 'handler', stage: 'New' },
        'stage-Assigned': { module: 'handler', stage: 'Assigned' },
        'stage-Following': { module: 'handler', stage: 'Following' },
        'stage-Quoted': { module: 'deal', tab: 'Quoted' },
        'stage-Won': { module: 'fulfillment', tab: 'all' },
        'stage-Lost': { module: 'deal', tab: 'Lost' },
    });

    function target(key) {
        return TARGETS[key] || null;
    }

    // What the dashboard counted, and nothing else. The queues share a search,
    // an owner, a technical owner, a customer and a region across pages, and
    // the follow-up page adds an activity-time filter of its own. Left in
    // place, "210 inquiries" opened a list of four - the number and the rows
    // no longer describing the same thing.
    //
    // Cleared only after the reader has actually left the page they were on:
    // cancelling an unsaved panel must not quietly wipe their filters.
    function clearQueueFilters() {
        State.stageFilters.search = '';
        State.stageFilters.ownerId = '';
        State.stageFilters.techId = '';
        State.stageFilters.customerId = '';
        State.stageFilters.businessRegion = '';
        window.syncStageFilterInputs?.();
        const activity = document.getElementById('followup-activity-filter');
        if (activity) activity.value = 'all';
        ['followup-activity-from', 'followup-activity-to'].forEach(id => {
            const field = document.getElementById(id);
            if (field) field.value = '';
        });
        window.FollowupFilterControls?.syncCustomVisibility?.();
    }

    async function go(key) {
        const where = target(key);
        if (!where) return false;
        if (window.switchModule(where.module) === false) return false;
        clearQueueFilters();
        const module = document.getElementById(`module-${where.module}`);
        if (where.stage !== undefined) {
            const select = document.getElementById('filter-stage');
            if (select) select.value = where.stage;
        }
        if (where.tab !== undefined) {
            const tab = module?.querySelector(
                `.filter-tabs .filter-tab[data-filter="${where.tab}"]`);
            if (tab) {
                module.querySelectorAll('.filter-tabs .filter-tab')
                    .forEach(item => item.classList.remove('active'));
                tab.classList.add('active');
                State.currentFilters[where.module] = where.tab;
            }
        }
        const loaders = {
            handler: 'loadHandler', followup: 'loadFollowup', deal: 'loadDeal',
            fulfillment: 'loadFulfillment', aftersales: 'loadAftersales',
        };
        const load = window[loaders[where.module]];
        if (typeof load === 'function') await load();
        return true;
    }

    // Only the cards that lead somewhere get the affordance; the rest are left
    // exactly as they were, which is how a reader tells them apart.
    function markCards() {
        Object.keys(TARGETS).filter(key => key.startsWith('kpi-')).forEach(key => {
            const card = document.getElementById(key)?.closest('.kpi-card');
            if (!card || card.dataset.linked) return;
            card.dataset.linked = key;
            card.setAttribute('role', 'button');
            card.setAttribute('tabindex', '0');
            card.classList.add('is-linked');
            card.addEventListener('click', () => go(key));
            card.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    go(key);
                }
            });
        });
    }

    window.DashboardLinks = Object.freeze({ go, target, markCards });
})();
