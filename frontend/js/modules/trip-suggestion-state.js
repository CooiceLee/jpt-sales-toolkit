/** Ephemeral transport-search results. Suggestions are never persisted here. */
(function() {
    const MODES = new Set(['flight', 'drive', 'ground_public', 'other']);
    let epoch = 0;
    let state = { planId: null, status: 'idle', suggestions: [], revision: 0, error: null };
    function normalized(response = {}) {
        const flat = Array.isArray(response.suggestions) ? response.suggestions : [];
        const grouped = (response.legs || []).flatMap(leg => (leg.recommendations || leg.suggestions || [])
            .map(item => ({ ...item, leg_key: item.leg_key || leg.leg_key,
                from_label: item.from_label || leg.from_label, to_label: item.to_label || leg.to_label })));
        return (flat.length ? flat : grouped).map((item, index) => ({
            ...item,
            suggestion_id: String(item.suggestion_id || `${item.leg_key || 'unknown'}:${index}`),
            leg_key: String(item.leg_key || ''),
            mode: MODES.has(item.mode) ? item.mode : null,
            approximate: item.approximate !== false,
            requires_manual_confirmation: true,
        })).filter(item => item.leg_key && item.mode);
    }
    function resetForPlan(planId) {
        if (state.planId === (planId || null)) return;
        epoch += 1;
        state = { planId: planId || null, status: 'idle', suggestions: [], revision: 0, error: null };
    }
    function begin(planId, revision, focusLegKey = null) {
        resetForPlan(planId);
        const requestEpoch = ++epoch;
        state = { ...state, status: 'loading', error: null, revision, focusLegKey, requestEpoch };
        return requestEpoch;
    }
    function succeed(requestEpoch, response = {}) {
        if (requestEpoch !== epoch) return false;
        state = { ...state, status: 'ready', suggestions: normalized(response), error: null,
            generatedAt: response.generated_at || response.fetched_at || null,
            privacyNotice: response.privacy_notice || null,
            warnings: response.warnings || [] };
        return true;
    }
    function fail(requestEpoch, message) {
        if (requestEpoch !== epoch) return false;
        state = { ...state, status: 'error', error: message || 'Travel option search failed.' };
        return true;
    }
    function ignore(suggestionId) {
        state = { ...state, suggestions: state.suggestions.filter(item => item.suggestion_id !== suggestionId) };
    }
    function markApplied() { state = { ...state, revision: window.TripPlanningDraft?.revision?.() || state.revision }; }
    function stale() { return state.status === 'ready' && state.revision !== (window.TripPlanningDraft?.revision?.() || 0); }
    window.TripSuggestionState = Object.freeze({ resetForPlan, begin, succeed, fail, ignore, markApplied, stale,
        get: () => state, forLeg: key => state.suggestions.filter(item => item.leg_key === key) });
})();
