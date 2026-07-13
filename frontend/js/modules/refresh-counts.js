// ===== Refresh All Counts =====
async function refreshAllCounts() {
    try {
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

