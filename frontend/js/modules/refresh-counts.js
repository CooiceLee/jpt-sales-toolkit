// ===== Role-aware navigation counts =====
function applyTechNavigationCounts(summary) {
    const counts = {
        sampling: summary?.pre_sales_active_lead_count || 0,
        aftersales: summary?.after_sales_active_lead_count || 0,
    };
    setText('nav-sampling-total', counts.sampling);
    setText('nav-aftersales-total', counts.aftersales);
    return counts;
}

async function refreshTechNavigationCounts() {
    try {
        return applyTechNavigationCounts(await ApiClient.getTaskWorkloadSummary());
    } catch (error) {
        setText('nav-sampling-total', '—');
        setText('nav-aftersales-total', '—');
        throw error;
    }
}

/** Just the numbers beside the module names. Nothing is redrawn.

Reloading the open module is usually wanted with them, but not always: a
background refresh that arrives while the reader is opening something would
take the screen from them. The numbers on their own are safe at any moment,
and going stale after an import is what makes a finished import look like a
failed one.
*/
async function refreshNavigationCounts() {
    try {
        if (RoleCapabilities.isTech()) {
            try {
                await refreshTechNavigationCounts();
            } catch (error) {
                console.error('Tech navigation count refresh failed:', error);
            }
            return true;
        }
        applyNavigationCounts(await ApiClient.getDashboard());
        return true;
    } catch (err) {
        console.error('Refresh navigation counts error:', err);
        return false;
    }
}

async function refreshAllCounts() {
    // Swallowed so that a background refresh never breaks the action that
    // triggered it, but said out loud to whoever wants to know: a caller that
    // promised the reader fresh numbers has to be able to tell.
    let refreshed = await refreshNavigationCounts();
    try {
        const active = document.querySelector('.module.active')?.id?.replace('module-', '');
        if (active) await loadModuleData(active);
    } catch (err) {
        console.error('Refresh counts error:', err);
        refreshed = false;
    }
    return refreshed;
}
