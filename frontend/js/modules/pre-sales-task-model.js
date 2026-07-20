/** Normalize imported and app-created pre-sales task payloads without losing source fields. */
(function () {
    'use strict';

    function parsePayload(value) {
        if (!value) return { data: {}, valid: true };
        if (typeof value === 'object' && !Array.isArray(value)) {
            return { data: { ...value }, valid: true };
        }
        try {
            const parsed = JSON.parse(value);
            const valid = Boolean(parsed && typeof parsed === 'object' && !Array.isArray(parsed));
            return { data: valid ? parsed : {}, valid };
        } catch {
            return { data: {}, valid: false };
        }
    }

    const parseObject = value => parsePayload(value).data;

    function first(...values) {
        return values.find(value => value !== undefined && value !== null && value !== '') ?? '';
    }

    function toView(task) {
        const requestPayload = parsePayload(task.request_json);
        const resultPayload = parsePayload(task.result_json);
        const request = requestPayload.data;
        const result = resultPayload.data;
        const requestDescription = first(
            request.request_description, request.sample_params, request.requirements
        );
        return {
            ...task,
            _request: request,
            _result: result,
            _request_valid: requestPayload.valid,
            _result_valid: resultPayload.valid,
            request_description: requestDescription,
            sample_params: requestDescription,
            request_date: first(request.request_date),
            request_date_raw: first(request.request_date_raw),
            due_date_raw: first(request.due_date_raw),
            customer_decision_maker: first(request.customer_decision_maker),
            quantity_text: first(request.quantity_text),
            competitor: first(request.competitor),
            key_points: first(request.key_points),
            concerns: first(request.concerns),
            progress_text: first(result.progress_text, result.current_progress),
            result_summary: first(result.result_summary),
            next_action: first(result.next_action),
            supplemental_notes: first(result.supplemental_notes),
            sample_result: first(result.sample_result, result.result, 'Pending'),
            report_link: first(result.report_link, result.report_attachment_id),
            confirmed_date: first(result.confirmed_date, result.sample_confirmed_date)
        };
    }

    function mergePayload(original, changes) {
        const payload = parsePayload(original);
        if (!payload.valid) {
            throw new Error('This task contains damaged JSON data. Repair or re-import it before saving.');
        }
        const merged = { ...payload.data };
        Object.entries(changes).forEach(([key, value]) => {
            if (value !== undefined) merged[key] = value;
        });
        return merged;
    }

    function mergeRequest(task, changes) {
        const original = task?._request_valid === false
            ? task.request_json
            : (task?._request || task?.request_json);
        const merged = mergePayload(original, changes);
        if (!task && changes.request_description && !merged.sample_params) {
            merged.sample_params = changes.request_description;
        }
        return merged;
    }

    function mergeResult(task, changes) {
        const original = task?._result_valid === false
            ? task.result_json
            : (task?._result || task?.result_json);
        return mergePayload(original, changes);
    }

    window.PreSalesTaskModel = {
        parseObject,
        parsePayload,
        toView,
        mergeRequest,
        mergeResult
    };
})();
