// ===== Refresh All Counts =====
async function refreshAllCounts() {
    try {
        if (RoleCapabilities.isTech()) {
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
