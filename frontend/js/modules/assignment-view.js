// ===== Assignment Section =====
function renderAssignmentSection(inq) {
    const lead = inq._lead;
    const assignments = lead?.assignments || [];

    // Group by type
    const owner = assignments.find(a => a.assignment_type === 'owner');
    const watchers = assignments.filter(a => a.assignment_type === 'watcher');
    const collaborators = assignments.filter(a => a.assignment_type === 'collaborator');

    return `
        <div style="border-top:1px solid var(--cream-300);margin-top:24px;padding-top:24px;">
            <h3 style="font-size:16px;font-weight:600;margin-bottom:16px;">Team & Assignments</h3>

            <!-- Owner -->
            <div class="form-group">
                <label class="form-label">Owner (负责人)</label>
                <div style="display:flex;gap:8px;align-items:center;">
                    <select class="form-select" id="lead-owner-select" style="flex:1;">
                        <option value="">Select owner...</option>
                    </select>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="changeLeadOwner()">Change</button>
                </div>
            </div>

            <!-- Watchers -->
            <div class="form-group">
                <label class="form-label">Watchers (关注者)</label>
                <div id="watcher-list" style="margin-bottom:8px;">
                    ${watchers.length === 0 ? '<div style="color:var(--ink-500);font-size:14px;">No watchers</div>' :
                      watchers.map(w => `
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px;background:var(--cream-100);border-radius:4px;margin-bottom:4px;">
                            <span>${escapeHtml(w.user_name || w.user_id)}</span>
                            <button type="button" class="btn btn-text btn-sm" onclick="removeAssignment('${w.id}')" style="color:var(--danger);">Remove</button>
                        </div>
                      `).join('')
                    }
                </div>
                <div style="display:flex;gap:8px;">
                    <select class="form-select" id="watcher-select" style="flex:1;">
                        <option value="">Add watcher...</option>
                    </select>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="addWatcher()">Add</button>
                </div>
            </div>

            <!-- Collaborators -->
            <div class="form-group">
                <label class="form-label">Collaborators (协作者)</label>
                <div id="collaborator-list" style="margin-bottom:8px;">
                    ${collaborators.length === 0 ? '<div style="color:var(--ink-500);font-size:14px;">No collaborators</div>' :
                      collaborators.map(c => `
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px;background:var(--cream-100);border-radius:4px;margin-bottom:4px;">
                            <span>${escapeHtml(c.user_name || c.user_id)}</span>
                            <button type="button" class="btn btn-text btn-sm" onclick="removeAssignment('${c.id}')" style="color:var(--danger);">Remove</button>
                        </div>
                      `).join('')
                    }
                </div>
                <div style="display:flex;gap:8px;">
                    <select class="form-select" id="collaborator-select" style="flex:1;">
                        <option value="">Add collaborator...</option>
                    </select>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="addCollaborator()">Add</button>
                </div>
            </div>
        </div>
    `;
}

