/** Offline China airport presets for Trip Planner origin and return fields. */
(function() {
    const HUBS = Object.freeze({
        PVG: Object.freeze({ name: 'Shanghai Pudong International Airport (PVG)', lat: 31.1443, lng: 121.8083 }),
        PEK: Object.freeze({ name: 'Beijing Capital International Airport (PEK)', lat: 40.0799, lng: 116.6031 }),
        CAN: Object.freeze({ name: 'Guangzhou Baiyun International Airport (CAN)', lat: 23.3924, lng: 113.2988 }),
        SZX: Object.freeze({ name: "Shenzhen Bao'an International Airport (SZX)", lat: 22.6393, lng: 113.8107 }),
    });

    function fieldId(kind, field) {
        return `trip-${kind}-${field}`;
    }

    function apply(kind, code) {
        const hub = HUBS[code];
        if (!hub || !['origin', 'destination'].includes(kind)) return false;
        const values = { name: hub.name, lat: hub.lat, lng: hub.lng };
        Object.entries(values).forEach(([field, value]) => {
            const input = document.getElementById(fieldId(kind, field));
            if (input) input.value = value;
        });
        return true;
    }

    function detect(lat, lng) {
        const latitude = Number(lat);
        const longitude = Number(lng);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return 'custom';
        return Object.entries(HUBS).find(([, hub]) => (
            Math.abs(latitude - hub.lat) < 0.0005 && Math.abs(longitude - hub.lng) < 0.0005
        ))?.[0] || 'custom';
    }

    function markCustomForField(id) {
        const kind = String(id).startsWith('trip-origin-') ? 'origin'
            : String(id).startsWith('trip-destination-') ? 'destination' : null;
        const select = kind && document.getElementById(`trip-${kind}-preset`);
        if (select) select.value = 'custom';
    }

    window.TripChinaHubs = Object.freeze({ HUBS, apply, detect, markCustomForField });
})();
