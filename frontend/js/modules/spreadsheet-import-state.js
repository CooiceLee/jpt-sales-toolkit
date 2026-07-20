/** Mutable state for the two-step spreadsheet import workflow. */
(function() {
    const state = {
        fileSignature: '',
        report: null,
        dirty: false,
        resolutions: emptyResolutions()
    };

    function emptyResolutions() {
        return { member_mappings: {}, customer_mappings: {}, excluded_records: [] };
    }

    function signature(file) {
        return file ? `${file.name}:${file.size}:${file.lastModified}` : '';
    }

    function useFile(file, forceReset = false) {
        const next = signature(file);
        if (forceReset || state.fileSignature !== next) {
            state.fileSignature = next;
            state.report = null;
            state.dirty = false;
            state.resolutions = emptyResolutions();
        }
    }

    function setReport(file, report) {
        useFile(file);
        state.report = report;
        state.dirty = false;
    }

    function setMember(sourceName, userId) {
        setMapping(state.resolutions.member_mappings, sourceName, userId);
    }

    function setCustomer(externalKey, customerId) {
        setMapping(state.resolutions.customer_mappings, externalKey, customerId);
    }

    function setMapping(target, key, value) {
        if (value) target[key] = value;
        else delete target[key];
        state.dirty = true;
    }

    function toggleExcluded(recordKey, excluded) {
        const values = new Set(state.resolutions.excluded_records);
        if (excluded) values.add(recordKey);
        else values.delete(recordKey);
        state.resolutions.excluded_records = [...values];
        state.dirty = true;
    }

    function canCommit(file) {
        return signature(file) === state.fileSignature && !state.dirty && Boolean(state.report?.can_commit);
    }

    function isSpreadsheet(file) {
        return Boolean(file?.name?.toLowerCase().endsWith('.xlsx'));
    }

    window.SpreadsheetImportState = {
        useFile, setReport, setMember, setCustomer, toggleExcluded, canCommit, isSpreadsheet,
        hasReport: () => Boolean(state.report),
        isDirty: () => state.dirty,
        report: () => state.report,
        resolutions: () => JSON.parse(JSON.stringify(state.resolutions)),
        sourceHash: () => state.report?.source_hash || state.report?.source_sha256 || ''
    };
})();
