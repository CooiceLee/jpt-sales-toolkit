/** Bring the rest of the page up to date after results are imported. */
(function() {
    const STALE = 'The results were imported. The page could not be refreshed — reload it to see them.';

    // Just the numbers beside the module names. Nothing is redrawn, so this is
    // safe at any moment - including while the reader is opening another plan.
    // Leaving them stale is what makes a finished import look like a failed one.
    async function countsOnly(tr, refreshed = true) {
        const ok = await window.refreshNavigationCounts?.() !== false;
        return refreshed && ok ? '' : tr(STALE);
    }

    // An import moves more than the visit: the lead activity, the formal
    // follow-up, the stage and the next follow-up date move with it. So the
    // page is brought up to date - but never over the top of the reader. The
    // full refresh reloads the open module, which claims the screen for
    // whichever plan is showing, so it only runs while the plan on screen is
    // still the one the import was submitted from.
    async function after(report, tr, token) {
        if (report?.status !== 'completed') return '';
        const movedOn = () => token !== undefined && !TripPlanIdentity.isCurrent(token);
        if (movedOn()) return countsOnly(tr);

        let refreshed = true;
        try {
            if (State?.currentTripPlan?.id === report.plan_id) {
                await window.TripPlanRefresh?.reread?.(report.plan_id, { token });
            }
        } catch (error) {
            console.error('Trip working import plan refresh failed:', error);
            refreshed = false;
        }
        // Checked again: the re-read above waits, and the reader can open
        // another plan while it does. Reloading the module now would take a
        // newer number than the plan they are waiting for and put them back.
        if (movedOn()) return countsOnly(tr, refreshed);

        // refreshAllCounts keeps its own failures to itself, so it reports
        // whether it managed rather than throwing.
        if (await window.refreshAllCounts?.() === false) refreshed = false;
        return refreshed ? '' : tr(STALE);
    }

    window.TripWorkingImportRefresh = { after };
})();
