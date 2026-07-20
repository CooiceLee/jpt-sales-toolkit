(() => {
    const TILE_SOURCES = {
        light: {
            url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
            attribution: '&copy; OpenStreetMap, CARTO'
        },
        standard: {
            url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            attribution: '&copy; OpenStreetMap contributors'
        }
    };

    function isBlank(value) {
        return value === null || value === undefined ||
            (typeof value === 'string' && value.trim() === '');
    }

    function coordinatePair(lat, lng) {
        if (isBlank(lat) || isBlank(lng)) return null;
        const latitude = Number(lat);
        const longitude = Number(lng);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
        if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return null;
        return [latitude, longitude];
    }

    function translate(text) {
        return window.I18n?.t ? I18n.t(text) : text;
    }

    function ensureNetworkStatus(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return null;
        let status = container.querySelector('.map-network-status');
        if (status) return status;
        status = document.createElement('div');
        status.className = 'map-network-status hidden';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        container.appendChild(status);
        return status;
    }

    function setNetworkStatus(status, message) {
        if (!status) return;
        status.textContent = message ? translate(message) : '';
        status.classList.toggle('hidden', !message);
    }

    function addTileLayer(map, options = {}) {
        const source = TILE_SOURCES[options.style || 'light'] || TILE_SOURCES.light;
        const status = ensureNetworkStatus(options.containerId);
        const layer = L.tileLayer(source.url, { attribution: source.attribution });
        const unavailable = () => setNetworkStatus(
            status,
            typeof navigator !== 'undefined' && navigator.onLine === false
                ? 'Map background unavailable while offline. Points and lists still work.'
                : 'Map background could not load. Points and lists still work.'
        );
        const restored = () => setNetworkStatus(status, '');
        const reconnect = () => {
            setNetworkStatus(status, 'Reconnecting map background...');
            layer.redraw();
        };

        layer.on('load', restored);
        layer.on('tileerror', unavailable);
        layer.addTo(map);

        if (typeof window.addEventListener === 'function') {
            window.addEventListener('offline', unavailable);
            window.addEventListener('online', reconnect);
            map.on('unload', () => {
                window.removeEventListener('offline', unavailable);
                window.removeEventListener('online', reconnect);
            });
        }
        if (typeof navigator !== 'undefined' && navigator.onLine === false) unavailable();
        return layer;
    }

    window.MapSupport = Object.freeze({
        addTileLayer,
        coordinatePair
    });
})();
