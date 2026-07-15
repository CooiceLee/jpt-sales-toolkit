(function() {
    const ROLES = ['leader', 'sales', 'tech'];
    const ROLE_LABELS = {
        leader: 'Leader',
        sales: 'Sales',
        tech: 'Tech'
    };

    function status(raw = {}) {
        const authorization = raw.authorization || null;
        const issuer = raw.issuer || {};
        return {
            mode: raw.mode || 'legacy',
            activated: raw.activated === true,
            deviceId: raw.device_id || '',
            trustRequired: raw.trust_required === true,
            member: raw.member || null,
            authorization: authorization ? {
                packageId: authorization.package_id || '',
                status: authorization.status || 'unknown',
                issuedAt: authorization.issued_at || null,
                expiresAt: authorization.expires_at || null,
                daysRemaining: authorization.days_remaining ?? null
            } : null,
            issuer: {
                initialized: issuer.initialized === true,
                trusted: issuer.trusted === true,
                canInitialize: issuer.can_initialize === true,
                fingerprint: issuer.fingerprint || ''
            }
        };
    }

    function members(raw = {}) {
        const items = Array.isArray(raw) ? raw : (raw.items || []);
        return items.map(item => ({
            id: item.id,
            username: item.username || '',
            displayName: item.display_name || item.username || '',
            role: ROLES.includes(item.role) ? item.role : 'sales',
            region: item.region || '',
            active: item.is_active !== false,
            authorizationCount: item.authorization_count || 0,
            activeDevice: item.active_device || null,
            expiresAt: item.expires_at || null
        }));
    }

    function events(raw = {}) {
        const items = Array.isArray(raw) ? raw : (raw.items || []);
        return items.map(item => ({
            id: item.id,
            type: item.event_type || 'unknown',
            userId: item.user_id || '',
            deviceId: item.device_id || '',
            details: item.details || {},
            createdAt: item.created_at || null,
            actorId: item.actor_id || ''
        }));
    }

    function deviceLabel(value) {
        if (!value) return 'Not bound';
        if (typeof value === 'string') return value;
        return value.device_name || value.device_id || value.id || 'Bound device';
    }

    function detailLabel(details) {
        if (!details) return '-';
        if (typeof details === 'string') return details;
        return Object.entries(details)
            .slice(0, 4)
            .map(([key, value]) => `${formatLabel(key)}: ${value}`)
            .join(' · ') || '-';
    }

    window.AuthorizationModel = {
        ROLES,
        ROLE_LABELS,
        status,
        members,
        events,
        deviceLabel,
        detailLabel,
        requiresActivation(value) {
            const normalized = value?.deviceId !== undefined ? value : status(value);
            return normalized.mode === 'setup' || (normalized.mode === 'offline' && !normalized.activated);
        }
    };
})();
