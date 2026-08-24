/** Render manually reviewable transport suggestions without mutating route data. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const MODE_LABELS = { flight: 'Flight', drive: 'Drive', ground_public: 'Ground public', other: 'Other' };
    function safeUrl(value) {
        try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; }
        catch { return null; }
    }
    function freshness(value) {
        const date = new Date(value || '');
        return Number.isNaN(date.getTime()) ? t('Time unavailable') : date.toLocaleString(I18n.locale());
    }
    function confidence(value) {
        const number = Number(value);
        if (Number.isFinite(number)) return `${Math.round(number <= 1 ? number * 100 : number)}%`;
        const labels = { low: 'Low', medium: 'Medium', high: 'High' };
        return value ? t(labels[String(value).toLowerCase()] || String(value)) : t('Unknown confidence');
    }
    function renderItem(item, stale) {
        const url = safeUrl(item.search_url);
        const metrics = [
            item.distance_km != null ? t('{count} km', { count: item.distance_km }) : '',
            item.time_hours != null ? t('{count} hours', { count: item.time_hours }) : '',
            item.travel_half_days != null
                ? t('{count} travel days', { count: TripDuration.toDisplayTravelDays(item.travel_half_days) })
                : (item.travel_days != null ? t('{count} travel days', { count: item.travel_days }) : ''),
        ].filter(Boolean).join(' · ');
        const applicable = item.mode !== 'other' || Number(item.time_hours) > 0
            || Number(item.travel_half_days) > 0 || Number(item.travel_days) > 0;
        const token = h(encodeURIComponent(item.suggestion_id));
        return `<article class="trip-suggestion-card ${stale ? 'stale' : ''}">
            <div class="trip-suggestion-head"><strong>${h(t(MODE_LABELS[item.mode] || item.mode))}</strong>
                <span>${h(item.approximate ? t('Approximate') : t('Exact'))} · ${h(t(item.online === true ? 'Online source' : 'Local estimate'))}${item.cached ? ` · ${h(t('Cached'))}` : ''}</span></div>
            <div class="trip-suggestion-metrics">${h(metrics || t('Estimate pending'))}</div>
            <div class="trip-suggestion-source">${h(t('Source'))}: ${h(item.provider || t('Local estimate'))}
                · ${h(t('Updated'))}: ${h(freshness(item.fetched_at))}
                · ${h(t('Confidence'))}: ${h(confidence(item.confidence))}</div>
            ${item.online === false ? `<div class="trip-suggestion-note">${h(t('This is a local approximate estimate. Open the source link to check live details.'))}</div>` : ''}
            ${item.warning ? `<div class="trip-suggestion-warning">${h(t(item.warning))}</div>` : ''}
            ${item.attribution ? `<div class="trip-suggestion-note">${h(item.attribution)}</div>` : ''}
            <div class="trip-suggestion-actions">
                ${url ? `<a class="btn btn-secondary btn-sm" href="${h(url)}" target="_blank" rel="noopener noreferrer">${h(t('Open source'))}</a>` : ''}
                <button type="button" class="btn btn-primary btn-sm" onclick="TripSuggestionActions.apply('${token}')" ${stale || !applicable ? 'disabled' : ''}>${h(t(applicable ? 'Apply to draft' : 'Enter manually'))}</button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripSuggestionActions.ignore('${token}')">${h(t('Ignore'))}</button>
            </div>
        </article>`;
    }
    function renderLeg(leg, index) {
        const root = document.getElementById(`trip-leg-suggestions-${index}`);
        if (!root) return;
        const state = TripSuggestionState.get();
        const items = TripSuggestionState.forLeg(leg.leg_key);
        const stale = TripSuggestionState.stale();
        if (state.status === 'loading') root.innerHTML = `<div class="trip-suggestion-note">${h(t('Searching travel options...'))}</div>`;
        else if (state.status === 'ready' && items.length) root.innerHTML = `${stale ? `<div class="trip-suggestion-warning">${h(t('Route changed after this search. Search again before applying.'))}</div>` : ''}${items.map(item => renderItem(item, stale)).join('')}`;
        else if (state.status === 'ready' && state.focusLegKey === leg.leg_key) root.innerHTML = `<div class="trip-suggestion-note">${h(t('No travel options were returned for this leg.'))}</div>`;
        else root.innerHTML = '';
    }
    function render(plan) {
        const state = TripSuggestionState.get();
        const button = document.getElementById('trip-suggest-route');
        const status = document.getElementById('trip-suggestion-status');
        if (button) {
            button.disabled = state.status === 'loading' || !plan?.legs?.length;
            button.setAttribute('aria-busy', String(state.status === 'loading'));
            button.textContent = t(state.status === 'loading' ? 'Searching...' : 'Search travel options');
        }
        if (status) {
            const ready = [t('{count} suggestions require manual review.', { count: state.suggestions.length }),
                state.privacyNotice ? t(state.privacyNotice) : '', ...(state.warnings || []).map(item => t(item))].filter(Boolean).join(' ');
            status.textContent = state.status === 'error' ? t(state.error) : state.status === 'ready' ? ready : '';
        }
        (plan?.legs || []).forEach(renderLeg);
    }
    window.TripSuggestionView = Object.freeze({ render });
})();
