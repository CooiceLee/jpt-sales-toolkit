/** Global-role UI capability matrix. Backend authorization remains authoritative. */
(function() {
    const TECH_MODULES = new Set(['sampling', 'aftersales']);

    function isTech() {
        return State.user?.role === 'tech';
    }

    function canAccessModule(module) {
        return !isTech() || TECH_MODULES.has(module);
    }

    function initialModule() {
        return isTech() ? 'sampling' : 'dashboard';
    }

    function applyNavigation() {
        document.querySelectorAll('.rail-btn[data-module], .nav-item[data-module]').forEach(item => {
            item.classList.toggle('hidden', !canAccessModule(item.dataset.module));
        });
        if (isTech()) {
            document.querySelectorAll('.nav-section, .rail-separator').forEach(item => item.classList.add('hidden'));
        }
        const spreadsheetAllowed = State.user?.role === 'leader';
        document.querySelectorAll('[data-leader-spreadsheet]').forEach(item => {
            item.classList.toggle('hidden', !spreadsheetAllowed);
        });
        const importInput = document.getElementById('import-file');
        if (importInput) importInput.disabled = !spreadsheetAllowed;
        document.querySelectorAll('[data-task-manager]').forEach(item => {
            item.classList.toggle('hidden', !window.RoleCapabilities.canManageTaskRequests());
        });
        window.DataTransferWorkspace?.ensureAccessible?.();
    }

    window.RoleCapabilities = {
        isTech,
        canAccessModule,
        canImportSpreadsheet: () => State.user?.role === 'leader',
        initialModule,
        applyNavigation,
        canManageTaskRequests: () => !isTech()
    };
})();
