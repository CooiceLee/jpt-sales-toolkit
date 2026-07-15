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
    }

    window.RoleCapabilities = {
        isTech,
        canAccessModule,
        initialModule,
        applyNavigation,
        canManageTaskRequests: () => !isTech()
    };
})();
