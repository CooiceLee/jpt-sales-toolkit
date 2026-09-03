/** Render transport preferences, route draft status and per-leg overrides. */
(function() {
    let shown = [];
    const modeLabels = {
        flight: 'Flight', drive: 'Drive', ground_public: 'Ground public', other: 'Other',
    };
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);

    function renderPriority(draft) {
        const root = document.getElementById('trip-transport-priority');
        if (!root) return;
        if (!draft) {
            root.innerHTML = `<div class="empty-state compact">${h(t('Create or select a plan'))}</div>`;
            return;
        }
        const enabled = draft.transportModePriority;
        const ordered = [...enabled, ...TripPlanningDraft.MODES.filter(mode => !enabled.includes(mode))];
        root.innerHTML = ordered.map(mode => {
            const index = enabled.indexOf(mode);
            const checked = index >= 0;
            return `<div class="trip-mode-row ${checked ? 'enabled' : ''}">
                <label><input type="checkbox" ${checked ? 'checked' : ''} onchange="TripTransportActions.toggleMode('${mode}', this.checked)"> <span>${h(t(modeLabels[mode]))}</span></label>
                <span class="trip-mode-rank">${checked ? h(t('Priority {count}', { count: index + 1 })) : h(t('Disabled'))}</span>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripTransportActions.moveMode('${mode}', -1)" ${!checked || index === 0 ? 'disabled' : ''} aria-label="${h(t('Move up'))}">↑</button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripTransportActions.moveMode('${mode}', 1)" ${!checked || index === enabled.length - 1 ? 'disabled' : ''} aria-label="${h(t('Move down'))}">↓</button>
            </div>`;
        }).join('');
    }

    function legModeOptions(value) {
        const options = [['', 'Use plan preference'], ...TripPlanningDraft.MODES.map(mode => [mode, modeLabels[mode]])];
        return options.map(([key, label]) => `<option value="${key}" ${key === value ? 'selected' : ''}>${h(t(label))}</option>`).join('');
    }

    function renderLeg(leg, index, draft) {
        const override = draft?.legOverrides?.[leg.leg_key] || {};
        const selected = override.selected_mode || '';
        const hasManualMetrics = override.manual_distance_km != null || override.manual_time_hours != null
            || override.manual_travel_half_days != null || override.manual_travel_days != null || override.notes;
        const shownMode = selected || leg.selected_mode || leg.travel_mode || leg.mode || '-';
        const from = leg.from_label || leg.from_name || leg.travel_from_label || t('Origin');
        const to = leg.to_label || leg.to_name || t('Destination');
        const metric = [
            leg.distance_km != null ? t('{count} km', { count: leg.distance_km }) : '',
            leg.time_hours != null ? t('{count} hours', { count: leg.time_hours }) : '',
            leg.travel_half_days != null
                ? t('{count} travel days', { count: TripDuration.toDisplayTravelDays(leg.travel_half_days) })
                : (leg.travel_days != null ? t('{count} travel days', { count: leg.travel_days }) : ''),
        ].filter(Boolean).join(' · ');
        return `<div class="trip-leg-card" data-leg-key="${h(leg.leg_key)}">
            <div class="trip-leg-head"><strong>${h(index + 1)}. ${h(from)} → ${h(to)}</strong><span>${h(t(modeLabels[shownMode] || shownMode))}</span></div>
            <div class="trip-leg-metric">${h(metric || t('Estimate pending'))}</div>
            <div class="trip-leg-controls">
                <select class="form-input" id="trip-leg-mode-${index}" onchange="TripTransportActions.legChanged(${index})">${legModeOptions(selected)}</select>
                <label class="trip-check"><input type="checkbox" id="trip-leg-lock-${index}" ${override.mode_locked ? 'checked' : ''} onchange="TripTransportActions.legChanged(${index})"> <span>${h(t('Lock this leg'))}</span></label>
                <button type="button" class="btn btn-secondary btn-sm" onclick="TripSuggestionActions.searchLeg(${index})">${h(t('Search this leg'))}</button>
            </div>
            <div class="trip-leg-manual ${selected === 'other' || hasManualMetrics ? '' : 'hidden'}" id="trip-leg-manual-${index}">
                <label class="trip-field-label"><span>${h(t('Distance km'))}</span>
                    <input type="number" min="0" step="0.1" class="form-input" id="trip-leg-distance-${index}" value="${h(override.manual_distance_km ?? '')}" placeholder="${h(t('Distance km'))}" onchange="TripTransportActions.legChanged(${index})"></label>
                <label class="trip-field-label"><span>${h(t('Travel hours'))}</span>
                    <input type="number" min="0.1" step="0.1" class="form-input" id="trip-leg-hours-${index}" value="${h(override.manual_time_hours ?? '')}" placeholder="${h(t('Travel hours'))}" onchange="TripTransportActions.legChanged(${index})"></label>
                <label class="trip-field-label"><span>${h(t('Travel duration (days, 0.5 steps)'))}</span>
                    <input type="number" min="0" max="30" step="0.5" class="form-input" data-leg-duration-half-days id="trip-leg-days-${index}"
                        value="${h(override.manual_travel_half_days != null ? TripDuration.toDisplayTravelDays(override.manual_travel_half_days) : '')}"
                        placeholder="${h(t('Travel duration (days, 0.5 steps)'))}" onchange="TripTransportActions.legChanged(${index})"></label>
                <textarea class="form-input" rows="2" id="trip-leg-notes-${index}" placeholder="${h(t('Transport notes'))}" onchange="TripTransportActions.legChanged(${index})">${h(override.notes || '')}</textarea>
            </div>
            ${window.TripLegAirportsView?.render?.(index, override, shownMode) || ''}
            <div class="trip-leg-suggestions" id="trip-leg-suggestions-${index}"></div>
        </div>`;
    }

    /**
     * One entry per journey, saying whose it is.
     *
     * In team planning every member has their own legs, so three colleagues
     * travelling together produce three identical rows for each hop. Listed
     * flat and unattributed that reads as legs appearing out of nowhere - the
     * same journey is shown once, naming everybody on it.
     */
    function legEntries(plan) {
        const legs = plan?.legs || [];
        if (plan?.planning_mode !== 'team') {
            return legs.map(leg => ({ leg, members: [] }));
        }
        const merged = new Map();
        legs.forEach(leg => {
            const key = window.TripTeamJourneys?.identityOf?.(leg)
                || `${leg.leg_key}|${leg.selected_mode}`;
            const entry = merged.get(key) || { leg, members: [] };
            const name = window.TripTeamJourneys?.memberName?.(plan, leg.member_id);
            if (name && !entry.members.includes(name)) entry.members.push(name);
            merged.set(key, entry);
        });
        return [...merged.values()];
    }

    function renderLegs(plan, draft) {
        const root = document.getElementById('trip-leg-list');
        const count = document.getElementById('trip-leg-count');
        if (!root) return;
        const entries = legEntries(plan);
        // Colleagues travelling together are one row, so a row number is no
        // longer a position in plan.legs. Every action on a row is given by
        // that number, and looking it up in the unmerged list edits somebody
        // else's leg - or writes an airport onto a connection nobody is on.
        shown = entries.map(entry => entry.leg);
        if (count) count.textContent = t('{count} legs', { count: entries.length });
        root.innerHTML = entries.length
            ? entries.map((entry, index) =>
                (entry.members.length
                    ? `<p class="trip-leg-members">${h(entry.members.join(' · '))}</p>`
                    : '')
                + renderLeg(entry.leg, index, draft)).join('')
            : `<div class="empty-state compact">${h(t('Preview the route to calculate transport legs.'))}</div>`;
        window.TripSuggestionView?.render?.(plan);
    }

    function renderStatus(draft) {
        const root = document.getElementById('trip-draft-status');
        if (!root) return;
        root.className = `trip-draft-status ${draft?.dirty ? 'dirty' : 'saved'}`;
        root.textContent = !draft ? t('Create or select a plan')
            : draft.dirty && draft.previewReady ? t('Preview updated. Draft changes are not saved.')
            : draft.dirty ? t('Draft changes are not saved. Preview the route to see their impact.')
            : t('Route settings match the saved plan.');
    }

    /** The leg a rendered row stands for. */
    function legAt(index) { return shown[index] || null; }

    window.TripTransportView = Object.freeze({ legAt,
        render(plan, draft) { renderPriority(draft); renderLegs(plan, draft); renderStatus(draft); },
    });
})();
