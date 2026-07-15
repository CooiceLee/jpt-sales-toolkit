/**
 * JPT Sales Toolkit - API Client v3.3
 * Handles authentication, token management, and error handling
 */

const ApiClient = (function() {
    const API_BASE = '/api';
    const TOKEN_KEY = 'jpt_auth_token';
    const USER_KEY = 'jpt_auth_user';

    // ===== Token Management =====
    function getToken() {
        return localStorage.getItem(TOKEN_KEY);
    }

    function setToken(token) {
        localStorage.setItem(TOKEN_KEY, token);
    }

    function getUser() {
        const user = localStorage.getItem(USER_KEY);
        return user ? JSON.parse(user) : null;
    }

    function setUser(user) {
        localStorage.setItem(USER_KEY, JSON.stringify(user));
    }

    function clearAuth() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    }

    function isLoggedIn() {
        return !!getToken();
    }

    // ===== API Request =====
    async function request(endpoint, options = {}) {
        const token = getToken();
        const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
        const headers = { ...options.headers };
        const hasContentType = Object.keys(headers).some(key => key.toLowerCase() === 'content-type');
        if (!isFormData && !hasContentType) headers['Content-Type'] = 'application/json';

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(API_BASE + endpoint, {
            ...options,
            headers
        });

        // Handle 401 Unauthorized
        if (response.status === 401) {
            clearAuth();
            window.dispatchEvent(new CustomEvent('auth:logout'));
            throw new ApiError('Session expired. Please login again.', 401);
        }

        // Handle 409 Conflict (optimistic locking)
        if (response.status === 409) {
            const data = await response.json();
            throw new ConflictError(data.detail);
        }

        // Handle other errors
        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage = `API Error: ${response.status}`;
            try {
                const errorData = JSON.parse(errorText);
                errorMessage = errorData.detail || errorMessage;
            } catch {
                errorMessage = errorText || errorMessage;
            }
            throw new ApiError(errorMessage, response.status);
        }

        return response.json();
    }

    // ===== Error Classes =====
    class ApiError extends Error {
        constructor(message, status) {
            super(message);
            this.name = 'ApiError';
            this.status = status;
        }
    }

    class ConflictError extends Error {
        constructor(detail) {
            super(detail.message || 'Record was modified by another user');
            this.name = 'ConflictError';
            this.currentVersion = detail.current_version;
            this.yourVersion = detail.your_version;
            this.currentData = detail.current_data;
        }
    }

    // ===== Auth API =====
    async function login(username, password) {
        const data = await request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        setToken(data.token);
        setUser(data.user);
        return data.user;
    }

    async function logout() {
        try {
            await request('/auth/logout', { method: 'POST' });
        } catch (e) {
            // Ignore errors on logout
        }
        clearAuth();
    }

    async function getMe() {
        return request('/auth/me');
    }

    async function listUsers(role = null) {
        const params = role ? `?role=${role}` : '';
        return request(`/auth/users${params}`);
    }

    async function getRuntimeStatus() {
        return request('/health');
    }

    async function shutdownDesktop() {
        return request('/desktop/shutdown', { method: 'POST' });
    }

    // ===== Offline Authorization API =====
    function authorizationForm(fields) {
        const formData = new FormData();
        Object.entries(fields).forEach(([key, value]) => {
            if (value !== undefined && value !== null) formData.append(key, value);
        });
        return formData;
    }

    async function downloadAuthorizationFile(endpoint, options, fallbackFilename) {
        const token = getToken();
        const response = await fetch(API_BASE + endpoint, {
            ...options,
            headers: {
                ...options.headers,
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            }
        });
        if (response.status === 401) {
            clearAuth();
            window.dispatchEvent(new CustomEvent('auth:logout'));
            throw new ApiError('Session expired. Please login again.', 401);
        }
        if (!response.ok) {
            const errorText = await response.text();
            let message = errorText || `API Error: ${response.status}`;
            try { message = JSON.parse(errorText).detail || message; } catch { /* plain text */ }
            throw new ApiError(message, response.status);
        }
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename\*?=(?:UTF-8''|["']?)([^"';]+)/i);
        const filename = match ? decodeURIComponent(match[1].replace(/["']/g, '')) : fallbackFilename;
        return { blob: await response.blob(), filename };
    }

    async function getAuthorizationStatus() {
        return request('/authorization/status');
    }

    async function bootstrapAuthorizationLeader(data) {
        return request('/authorization/bootstrap', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function recoverLeaderAuthorization(data) {
        return request('/authorization/leader/recover', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function createDeviceRequest() {
        return downloadAuthorizationFile('/authorization/device-request', { method: 'POST' }, 'device-request.jptreq');
    }

    async function activateAuthorization(file, password, issuerFingerprint) {
        return request('/authorization/activate', {
            method: 'POST',
            body: authorizationForm({
                authorization_file: file,
                password,
                issuer_fingerprint: issuerFingerprint
            })
        });
    }

    async function listAuthorizationMembers() {
        return request('/authorization/members');
    }

    async function createAuthorizationMember(data) {
        return request('/authorization/members', { method: 'POST', body: JSON.stringify(data) });
    }

    async function updateAuthorizationMember(memberId, data) {
        return request(`/authorization/members/${memberId}`, { method: 'PATCH', body: JSON.stringify(data) });
    }

    async function deactivateAuthorizationMember(memberId) {
        return request(`/authorization/members/${memberId}/deactivate`, { method: 'POST' });
    }

    async function reactivateAuthorizationMember(memberId) {
        return request(`/authorization/members/${memberId}/reactivate`, { method: 'POST' });
    }

    async function initializeAuthorizationIssuer(passphrase) {
        return request('/authorization/issuer/initialize', {
            method: 'POST',
            body: JSON.stringify({ passphrase })
        });
    }

    async function renewLocalLeaderAuthorization(passphrase) {
        return request('/authorization/issuer/renew-local', {
            method: 'POST',
            body: JSON.stringify({ passphrase })
        });
    }

    async function issueAuthorization(memberId, requestFile, passphrase, days) {
        const body = authorizationForm({
            member_id: memberId,
            request_file: requestFile,
            passphrase,
            days
        });
        return downloadAuthorizationFile('/authorization/issue', { method: 'POST', body }, 'member.jptauth');
    }

    async function listAuthorizationEvents() {
        return request('/authorization/events');
    }

    // ===== Customer API =====
    async function createCustomer(data) {
        return request('/customers', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function getCustomer(id) {
        return request(`/customers/${id}`);
    }

    async function listCustomers(params = {}) {
        if (!params.limit) params.limit = 50;
        const query = new URLSearchParams(params).toString();
        return request(`/customers${query ? '?' + query : ''}`);
    }

    async function updateCustomer(id, data, rowVersion) {
        return request(`/customers/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({ ...data, row_version: rowVersion })
        });
    }

    async function createCustomerContact(customerId, data) {
        return request(`/customers/${customerId}/contacts`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function updateCustomerContact(customerId, contactId, data) {
        return request(`/customers/${customerId}/contacts/${contactId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async function archiveCustomerContact(customerId, contactId) {
        return request(`/customers/${customerId}/contacts/${contactId}/archive`, {
            method: 'POST'
        });
    }

    async function matchCustomers(email, companyName) {
        return request('/customers/match', {
            method: 'POST',
            body: JSON.stringify({ email, company_name: companyName })
        });
    }

    async function mergeCustomers(data) {
        return request('/customers/merge', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ===== Lead API =====
    async function listLeads(params = {}) {
        // Default to fetching more records to avoid pagination issues
        if (!params.limit) {
            params.limit = 1000;
        }
        const query = new URLSearchParams(params).toString();
        return request(`/leads${query ? '?' + query : ''}`);
    }

    async function getLead(id) {
        return request(`/leads/${id}`);
    }

    async function createLead(data) {
        return request('/leads', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function updateLead(id, data, rowVersion) {
        return request(`/leads/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({ ...data, row_version: rowVersion })
        });
    }

    async function addAssignment(leadId, userId, assignmentType) {
        return request(`/leads/${leadId}/assignments`, {
            method: 'POST',
            body: JSON.stringify({ user_id: userId, assignment_type: assignmentType })
        });
    }

    async function archiveAssignment(leadId, assignmentId) {
        return request(`/leads/${leadId}/assignments/${assignmentId}/archive`, {
            method: 'POST'
        });
    }

    // ===== Intake API =====
    async function parseEmail(rawEmail) {
        return request('/intake/parse-email', {
            method: 'POST',
            body: JSON.stringify({ raw_email: rawEmail })
        });
    }

    async function submitIntake(data) {
        return request('/intake/submit', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function geocode(address, city, country) {
        return request('/intake/geocode', {
            method: 'POST',
            body: JSON.stringify({ address, city, country })
        });
    }

    // ===== Activity API =====
    async function listActivities(leadId, params = {}) {
        const query = new URLSearchParams(params).toString();
        return request(`/leads/${leadId}/activities${query ? '?' + query : ''}`);
    }

    async function addFollowUp(leadId, data) {
        return request(`/leads/${leadId}/activities`, {
            method: 'POST',
            body: JSON.stringify({
                action_type: 'follow_up',
                ...data
            })
        });
    }

    async function updateActivity(leadId, activityId, data) {
        return request(`/leads/${leadId}/activities/${activityId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async function addComment(leadId, content, visibility = 'all') {
        return request(`/leads/${leadId}/activities`, {
            method: 'POST',
            body: JSON.stringify({
                action_type: 'comment',
                content,
                visibility
            })
        });
    }

    async function archiveActivity(leadId, activityId) {
        return request(`/leads/${leadId}/activities/${activityId}/archive`, {
            method: 'POST'
        });
    }

    // ===== Task API =====
    async function listPreSalesTasks(params = {}) {
        const query = new URLSearchParams(params).toString();
        return request(`/pre-sales-tasks${query ? '?' + query : ''}`);
    }

    async function createPreSalesTask(leadId, data) {
        return request(`/leads/${leadId}/pre-sales-tasks`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function updatePreSalesTask(taskId, data) {
        return request(`/pre-sales-tasks/${taskId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async function archivePreSalesTask(taskId) {
        return request(`/pre-sales-tasks/${taskId}/archive`, { method: 'POST' });
    }

    async function restorePreSalesTask(taskId) {
        return request(`/pre-sales-tasks/${taskId}/restore`, { method: 'POST' });
    }

    async function listAfterSalesTasks(params = {}) {
        const query = new URLSearchParams(params).toString();
        return request(`/after-sales-tasks${query ? '?' + query : ''}`);
    }

    async function createAfterSalesTask(leadId, data) {
        return request(`/leads/${leadId}/after-sales-tasks`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function updateAfterSalesTask(taskId, data) {
        return request(`/after-sales-tasks/${taskId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async function archiveAfterSalesTask(taskId) {
        return request(`/after-sales-tasks/${taskId}/archive`, {
            method: 'POST'
        });
    }

    // ===== Attachment API =====
    async function listAttachments(leadId, category = null) {
        const params = category ? `?category=${category}` : '';
        return request(`/leads/${leadId}/attachments${params}`);
    }

    async function uploadAttachment(leadId, category, file) {
        const token = getToken();
        const formData = new FormData();
        formData.append('category', category);
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/leads/${leadId}/attachments`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new ApiError(errorText, response.status);
        }

        return response.json();
    }

    async function archiveAttachment(leadId, attachmentId) {
        return request(`/leads/${leadId}/attachments/${attachmentId}/archive`, {
            method: 'POST'
        });
    }

    async function updateAttachment(leadId, attachmentId, data) {
        return request(`/leads/${leadId}/attachments/${attachmentId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async function downloadAttachment(leadId, attachmentId) {
        const token = getToken();
        const response = await fetch(`${API_BASE}/leads/${leadId}/attachments/${attachmentId}/download`, {
            headers: {
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new ApiError(errorText || `API Error: ${response.status}`, response.status);
        }

        return response.blob();
    }

    // ===== Review API =====
    async function getDashboard() {
        return request('/review/dashboard');
    }

    async function getAnalysis(filters = {}) {
        const params = new URLSearchParams();
        Object.entries(filters || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                params.set(key, value);
            }
        });
        const query = params.toString();
        return request(`/review/analysis${query ? `?${query}` : ''}`);
    }

    async function getMapData(filters = {}) {
        const params = new URLSearchParams();
        if (typeof filters === 'string') {
            if (filters) params.set('sales_stage', filters);
        } else {
            Object.entries(filters || {}).forEach(([key, value]) => {
                if (value !== undefined && value !== null && value !== '') {
                    params.set(key, value);
                }
            });
        }
        const query = params.toString();
        return request(`/review/map${query ? `?${query}` : ''}`);
    }

    async function getTripCandidates(filters = {}) {
        const params = new URLSearchParams();
        Object.entries(filters || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                params.set(key, value);
            }
        });
        const query = params.toString();
        return request(`/review/trip-candidates${query ? `?${query}` : ''}`);
    }

    async function listTripPlans() {
        return request('/review/trip-plans');
    }

    async function createTripPlan(data) {
        return request('/review/trip-plans', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function getTripPlan(planId) {
        return request(`/review/trip-plans/${planId}`);
    }

    async function updateTripPlan(planId, data) {
        return request(`/review/trip-plans/${planId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async function archiveTripPlan(planId, rowVersion = null) {
        const options = { method: 'POST' };
        if (rowVersion) {
            options.body = JSON.stringify({ row_version: rowVersion });
        }
        return request(`/review/trip-plans/${planId}/archive`, options);
    }

    async function addTripStop(planId, data) {
        return request(`/review/trip-plans/${planId}/stops`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function updateTripStop(planId, stopId, data) {
        return request(`/review/trip-plans/${planId}/stops/${stopId}`, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    async function reorderTripStops(planId, stopIds, rowVersion = null) {
        const body = { stop_ids: stopIds };
        if (rowVersion) body.row_version = rowVersion;
        return request(`/review/trip-plans/${planId}/stops/reorder`, {
            method: 'POST',
            body: JSON.stringify(body)
        });
    }

    async function generateTripItinerary(planId, data) {
        return request(`/review/trip-plans/${planId}/generate-itinerary`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function previewTripItinerary(planId, data) {
        return request(`/review/trip-plans/${planId}/preview-itinerary`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async function archiveTripStop(planId, stopId, rowVersion = null) {
        const options = { method: 'POST' };
        if (rowVersion) {
            options.body = JSON.stringify({ row_version: rowVersion });
        }
        return request(`/review/trip-plans/${planId}/stops/${stopId}/archive`, {
            ...options
        });
    }

    async function exportTripPlan(planId, format = 'md') {
        const token = getToken();
        const response = await fetch(`${API_BASE}/review/trip-plans/${planId}/export.${format}`, {
            headers: {
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new ApiError(errorText || `Export failed: ${response.status}`, response.status);
        }

        const disposition = response.headers.get('Content-Disposition');
        let filename = `trip-plan.${format}`;
        if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename=')[1].replace(/"/g, '');
        }
        const blob = await response.blob();
        return { blob, filename };
    }

    async function getTripExecution(planId, date = null) {
        const params = new URLSearchParams();
        if (date) params.set('date', date);
        const query = params.toString();
        return request(`/review/trip-plans/${planId}/execution${query ? `?${query}` : ''}`);
    }

    async function exportTripExecution(planId, date = null) {
        const token = getToken();
        const params = new URLSearchParams();
        if (date) params.set('date', date);
        const query = params.toString();
        const response = await fetch(`${API_BASE}/review/trip-plans/${planId}/execution.md${query ? `?${query}` : ''}`, {
            headers: {
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new ApiError(errorText || `Export failed: ${response.status}`, response.status);
        }

        const disposition = response.headers.get('Content-Disposition');
        let filename = 'trip-visit.md';
        if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename=')[1].replace(/"/g, '');
        }
        const blob = await response.blob();
        return { blob, filename };
    }

    // ===== Admin API =====
    async function getSystemInfo() {
        return request('/admin/system-info');
    }

    // ===== Data Exchange API =====
    async function exportData(leadIds = null) {
        const token = getToken();
        const response = await fetch(`${API_BASE}/data/export`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            },
            body: JSON.stringify({ lead_ids: leadIds })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new ApiError(errorText || `Export failed: ${response.status}`, response.status);
        }

        // Get filename from Content-Disposition header
        const disposition = response.headers.get('Content-Disposition');
        let filename = 'export.json';
        if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename=')[1].replace(/"/g, '');
        }

        const blob = await response.blob();
        return { blob, filename };
    }

    async function importData(file) {
        const token = getToken();
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/data/import`, {
            method: 'POST',
            headers: {
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            },
            body: formData
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new ApiError(errorText || `Import failed: ${response.status}`, response.status);
        }

        return response.json();
    }

    async function preflightImportData(file) {
        const token = getToken();
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/data/preflight`, {
            method: 'POST',
            headers: {
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            },
            body: formData
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new ApiError(errorText || `Preflight failed: ${response.status}`, response.status);
        }

        return response.json();
    }

    async function normalizeCountries() {
        return request('/data/governance/normalize-countries', { method: 'POST' });
    }

    async function getCoordinateAudit(limit = 100) {
        return request(`/data/governance/coordinate-audit?limit=${limit}`);
    }

    async function batchRepair(data) {
        return request('/data/governance/batch-repair', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // ===== Public Interface =====
    return {
        // Token
        isLoggedIn,
        getUser,
        getToken,
        clearAuth,

        // Auth
        login,
        logout,
        getMe,
        listUsers,
        getRuntimeStatus,
        shutdownDesktop,

        // Offline Authorization
        getAuthorizationStatus,
        bootstrapAuthorizationLeader,
        recoverLeaderAuthorization,
        createDeviceRequest,
        activateAuthorization,
        listAuthorizationMembers,
        createAuthorizationMember,
        updateAuthorizationMember,
        deactivateAuthorizationMember,
        reactivateAuthorizationMember,
        initializeAuthorizationIssuer,
        renewLocalLeaderAuthorization,
        issueAuthorization,
        listAuthorizationEvents,

        // Customer
        createCustomer,
        getCustomer,
        listCustomers,
        updateCustomer,
        createCustomerContact,
        updateCustomerContact,
        archiveCustomerContact,
        matchCustomers,
        mergeCustomers,

        // Lead
        listLeads,
        getLead,
        createLead,
        updateLead,
        addAssignment,
        archiveAssignment,

        // Intake
        parseEmail,
        submitIntake,
        geocode,

        // Activity
        listActivities,
        addFollowUp,
        updateActivity,
        addComment,
        archiveActivity,

        // Task
        listPreSalesTasks,
        createPreSalesTask,
        updatePreSalesTask,
        archivePreSalesTask,
        restorePreSalesTask,
        listAfterSalesTasks,
        createAfterSalesTask,
        updateAfterSalesTask,
        archiveAfterSalesTask,

        // Attachment
        listAttachments,
        uploadAttachment,
        updateAttachment,
        archiveAttachment,
        downloadAttachment,

        // Review
        getDashboard,
        getAnalysis,
        getMapData,
        getTripCandidates,
        listTripPlans,
        createTripPlan,
        getTripPlan,
        updateTripPlan,
        archiveTripPlan,
        addTripStop,
        updateTripStop,
        reorderTripStops,
        generateTripItinerary,
        previewTripItinerary,
        archiveTripStop,
        exportTripPlan,
        getTripExecution,
        exportTripExecution,

        // Admin
        getSystemInfo,

        // Data Exchange
        exportData,
        importData,
        preflightImportData,
        normalizeCountries,
        getCoordinateAudit,
        batchRepair,

        // Error classes
        ApiError,
        ConflictError
    };
})();
