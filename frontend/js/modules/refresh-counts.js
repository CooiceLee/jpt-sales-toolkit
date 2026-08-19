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

async function refreshAllCounts() {
    try {
        if (RoleCapabilities.isTech()) {
            try {
                await refreshTechNavigationCounts();
            } catch (error) {
                console.error('Tech navigation count refresh failed:', error);
            }
            const active = document.querySelector('.module.active')?.id?.replace('module-', '');
            if (active) await loadModuleData(active);
            return;
        }
        const stats = await ApiClient.getDashboard();
        applyNavigationCounts(stats);

        // Refresh current module data
        const activeModule = document.querySelector('.module.active');
        if (activeModule) {
            const moduleId = activeModule.id.replace('module-', '');
            await loadModuleData(moduleId);
        }
    } catch (err) {
        console.error('Refresh counts error:', err);
    }
}
