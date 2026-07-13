(function () {
    'use strict';

    let parsedData = null;

    function getParsedData() {
        return parsedData;
    }

    function initParser() {
        const textarea = document.getElementById('email-content');
        textarea?.addEventListener('input', () => {
            setText('char-count', textarea.value.length);
        });
    }

    async function pasteFromClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            const textarea = document.getElementById('email-content');
            if (textarea) {
                textarea.value = text;
                setText('char-count', text.length);
            }
        } catch (err) {
            alert('Cannot access clipboard. Please paste manually.');
        }
    }

    function clearParser() {
        const textarea = document.getElementById('email-content');
        const result = document.getElementById('parsed-result');
        const fields = document.getElementById('parsed-fields-list');
        if (textarea) textarea.value = '';
        if (result) result.style.display = 'none';
        if (fields) fields.innerHTML = '';
        setText('char-count', '0');
        parsedData = null;
    }

    async function parseEmail() {
        const content = document.getElementById('email-content')?.value?.trim();
        if (!content) {
            alert('Please paste email content first');
            return;
        }

        try {
            const result = await ApiClient.parseEmail(content);
            parsedData = { ...result, original_email: content };
            const list = document.getElementById('parsed-fields-list');
            const fields = Object.entries(parsedData).filter(([key]) => key !== 'original_email');
            setText('parsed-count', `${fields.length} fields`);
            list.innerHTML = fields.map(([key, value]) => `
                <div class="field-row">
                    <span class="field-name">${escapeHtml(formatLabel(key))}</span>
                    <input type="text" class="form-input" data-field="${escapeHtml(key)}" value="${escapeHtml(value || '')}">
                </div>
            `).join('');
            document.getElementById('parsed-result').style.display = 'block';
        } catch (err) {
            console.error('Parse error:', err);
            alert('Error parsing email');
        }
    }

    window.JptIntake = { getParsedData };
    window.initParser = initParser;
    window.pasteFromClipboard = pasteFromClipboard;
    window.clearParser = clearParser;
    window.discardParsed = clearParser;
    window.parseEmail = parseEmail;
})();
