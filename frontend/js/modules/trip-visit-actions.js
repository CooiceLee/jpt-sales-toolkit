/** Mutations and exports for trip visit execution. */
(function() {
    function readStopPayload(stopId) {
        return {
            row_version: (State.currentTripPlan?.stops || []).find(stop => stop.id === stopId)?.row_version || null,
            result_status: document.getElementById(`visit-status-${stopId}`)?.value || 'Planned',
            result_notes: document.getElementById(`visit-result-${stopId}`)?.value?.trim() || null,
            visit_customer_needs: document.getElementById(`visit-needs-${stopId}`)?.value?.trim() || null,
            visit_competitor: document.getElementById(`visit-competitor-${stopId}`)?.value?.trim() || null,
            visit_budget: document.getElementById(`visit-budget-${stopId}`)?.value?.trim() || null,
            visit_decision_maker: document.getElementById(`visit-decision-${stopId}`)?.value?.trim() || null,
            visit_next_action: document.getElementById(`visit-next-${stopId}`)?.value?.trim() || null,
            visit_followup_due_date: document.getElementById(`visit-due-${stopId}`)?.value || null,
            visit_sample_needed: Boolean(document.getElementById(`visit-sample-${stopId}`)?.checked),
            visit_quote_needed: Boolean(document.getElementById(`visit-quote-${stopId}`)?.checked),
        };
    }

    async function saveVisitExecution(stopId) {
        if (State.tripBusy || !State.currentTripPlan?.id) return;
        try {
            setTripBusy(true);
            State.currentTripPlan = await ApiClient.updateTripStop(
                State.currentTripPlan.id,
                stopId,
                readStopPayload(stopId)
            );
            notify(I18n.t('Visit saved'));
            TripPlannerModule.renderVisitExecution(State.currentTripPlan);
            renderCurrentTripPlan();
            renderTripMap();
        } catch (err) {
            console.error('Save visit execution error:', err);
            await handleTripError(err, 'Save visit');
        } finally {
            setTripBusy(false);
        }
    }

    async function uploadVisitAttachment(stopId) {
        const stop = (State.currentTripPlan?.stops || []).find(item => item.id === stopId);
        const input = document.getElementById(`visit-file-${stopId}`);
        const files = Array.from(input?.files || []);
        if (!stop?.lead_id || !files.length) {
            alert(I18n.t('Choose one or more files for a stop linked to a Lead.'));
            return;
        }
        let uploaded = 0;
        try {
            setTripBusy(true);
            for (const file of files) {
                await ApiClient.uploadAttachment(stop.lead_id, 'other', file);
                uploaded += 1;
            }
            notify(I18n.t('Visit files uploaded'));
        } catch (err) {
            console.error('Upload visit files error:', err);
            const remaining = files.slice(uploaded).map(file => file.name).join(', ');
            alert(I18n.t('{count} files uploaded. Reselect only the files not uploaded: {files}. Error: {error}', {
                count: uploaded,
                files: remaining || '-',
                error: I18n.t(err.message || 'Unknown error'),
            }));
        } finally {
            // Always clear the selection so a retry cannot duplicate files that
            // were already committed before a later file failed.
            if (input) input.value = '';
            setTripBusy(false);
        }
    }

    async function exportVisitDay() {
        if (!State.currentTripPlan?.id) {
            alert(I18n.t('Select a trip plan first'));
            return;
        }
        try {
            const result = await ApiClient.exportTripExecution(
                State.currentTripPlan.id,
                TripVisitState.getSelectedDate()
            );
            downloadBlob(result.blob, result.filename);
        } catch (err) {
            console.error('Export visit day error:', err);
            alert(I18n.t('Error exporting visit day: {error}', {
                error: I18n.t(err.message || 'Unknown error')
            }));
        }
    }

    Object.assign(window.TripPlannerModule, {
        saveVisitExecution,
        uploadVisitAttachment,
        exportVisitDay,
    });
})();
