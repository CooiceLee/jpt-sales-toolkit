/** The manual entry form: reading it, filling it, and showing who was matched. */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const value = id => String(document.getElementById(id)?.value || '').trim();

    function read() {
        return {
            companyName: value('new-inquiry-company'),
            country: value('new-inquiry-country'),
            city: value('new-inquiry-city'),
            contactEmail: value('new-inquiry-email'),
            title: value('new-inquiry-title'),
            productCategory: value('new-inquiry-product'),
            application: value('new-inquiry-application'),
            inquiryDate: value('new-inquiry-date'),
            requirements: value('new-inquiry-requirements'),
        };
    }

    // Said before the request goes out, so nobody waits on a save that the
    // server was always going to refuse.
    function missingFields(form, customer) {
        const missing = [];
        if (!customer && !form.companyName) missing.push(tr('Company name'));
        if (!form.title) missing.push(tr('What this enquiry is about'));
        return missing;
    }

    function describe(customer) {
        return [
            customer.display_name,
            [customer.city, customer.country].filter(Boolean).join(', '),
            customer.website,
        ].filter(Boolean).join(' · ');
    }

    // Enough to tell two customers of the same name apart. A list that shows
    // only the name is a list somebody guesses from.
    function renderMatches(matches, chosenId) {
        if (!matches.length) {
            return `<p class="empty-state compact">${escapeHtml(
                tr('No existing customer matches. Saving will create one from the details above.')
            )}</p>`;
        }
        return `
            <p class="form-hint">${escapeHtml(tr('Existing customers that may be the same company:'))}</p>
            <ul class="new-inquiry-matches">
                ${matches.map((customer, index) => `
                    <li>
                        <label>
                            <input type="radio" name="new-inquiry-customer" value="${escapeHtml(customer.id)}"
                                ${customer.id === chosenId ? 'checked' : ''}
                                onchange="NewInquiryActions.pickCustomer(${index})">
                            <span data-business>${escapeHtml(describe(customer))}</span>
                        </label>
                    </li>`).join('')}
                <li>
                    <label>
                        <input type="radio" name="new-inquiry-customer" value=""
                            ${chosenId ? '' : 'checked'}
                            onchange="NewInquiryActions.pickCustomer(-1)">
                        <span>${escapeHtml(tr('None of these — create a new customer'))}</span>
                    </label>
                </li>
            </ul>`;
    }

    function setStatus(message, kind = '') {
        const target = document.getElementById('new-inquiry-status');
        if (!target) return;
        target.className = kind ? `new-inquiry-status ${kind}` : 'new-inquiry-status';
        target.textContent = message || '';
    }

    function clear() {
        [
            'new-inquiry-company', 'new-inquiry-country', 'new-inquiry-city',
            'new-inquiry-email', 'new-inquiry-title', 'new-inquiry-product',
            'new-inquiry-application', 'new-inquiry-date', 'new-inquiry-requirements',
        ].forEach(id => {
            const field = document.getElementById(id);
            if (field) field.value = '';
        });
        const matches = document.getElementById('new-inquiry-matches');
        if (matches) matches.innerHTML = '';
        setStatus('');
    }

    // The form stays exactly as typed while a save is in flight, and comes back
    // if it fails: retyping a lost enquiry is how people stop using a form.
    function freeze(frozen) {
        const body = document.getElementById('new-inquiry-body');
        body?.querySelectorAll('input, select, textarea, button').forEach(field => {
            field.disabled = frozen;
        });
        const save = document.getElementById('new-inquiry-save');
        if (save) save.disabled = frozen;
    }

    window.NewInquiryForm = Object.freeze({
        read, missingFields, renderMatches, setStatus, clear, freeze, describe,
    });
})();
