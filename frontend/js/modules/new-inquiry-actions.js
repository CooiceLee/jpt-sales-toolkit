/** Recording an enquiry by hand: find the customer, then save the lead.
 *
 * Everything here goes through the endpoints that already exist. The customer
 * is matched before anything is created, so a second enquiry from a company
 * already on file attaches to that company rather than making a second copy of
 * it, and nothing is merged on a name alone - the reader chooses.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

    window.showNewInquiryModal = function () {
        if (!RoleCapabilities.canCreateLeads()) {
            return notify(tr('Technical accounts cannot create leads. Ask a leader to assign the work.'));
        }
        NewInquiryState.reset();
        NewInquiryForm.clear();
        showModal('new-inquiry-modal');
        document.getElementById('new-inquiry-company')?.focus();
    };

    window.closeNewInquiryModal = function () {
        // Cancelling leaves nothing behind: no customer, no lead, no draft on
        // another panel.
        if (NewInquiryState.get().busy) return;
        hideModal('new-inquiry-modal');
        NewInquiryState.reset();
        NewInquiryForm.clear();
    };

    // The email typed into the form is the only way back to this customer. It
    // was used to look them up and then dropped: the enquiry saved, and
    // reopening it showed a company with nobody to write to.
    //
    // Whoever wrote in becomes this enquiry's contact. On a company already on
    // file that is only the enquiry's own contact - the reader's choice of who
    // the company's main contact is stays theirs.
    async function resolveContact(customer, email) {
        const address = (email || '').trim();
        if (!address) return null;
        const contacts = customer.contacts || [];
        const known = contacts.find(contact =>
            String(contact.email || '').toLowerCase() === address.toLowerCase());
        if (known) return known;
        const contact = await ApiClient.createCustomerContact(customer.id, {
            email: address,
            is_primary: !contacts.length,
        });
        customer.contacts = [...contacts, contact];
        return contact;
    }

    window.NewInquiryActions = Object.freeze({
        findCustomers: async function () {
            const form = NewInquiryForm.read();
            if (!form.companyName && !form.contactEmail) {
                return NewInquiryForm.setStatus(
                    tr('Enter a company name or an email address to search.'), 'error');
            }
            const search = NewInquiryState.beginSearch();
            NewInquiryForm.setStatus(tr('Searching…'));
            try {
                const matches = await ApiClient.matchCustomers(
                    form.contactEmail || null, form.companyName || null);
                // A slower answer to an earlier search must not replace the
                // list the reader is looking at, nor clear the customer they
                // have since chosen from it.
                if (NewInquiryState.setMatches(matches, search) === null) return;
                document.getElementById('new-inquiry-matches').innerHTML =
                    NewInquiryForm.renderMatches(NewInquiryState.get().matches, null);
                NewInquiryForm.setStatus('');
            } catch (error) {
                if (!NewInquiryState.isCurrentSearch(search)) return;
                NewInquiryForm.setStatus(
                    tr('Could not search for customers: {error}',
                        { error: error?.message || tr('Unknown error') }), 'error');
            }
        },

        pickCustomer: function (index) {
            const { matches } = NewInquiryState.get();
            NewInquiryState.chooseCustomer(index >= 0 ? matches[index] : null);
        },

        save: async function () {
            const state = NewInquiryState.get();
            const form = NewInquiryForm.read();
            const missing = NewInquiryForm.missingFields(form, state.customer);
            if (missing.length) {
                return NewInquiryForm.setStatus(
                    tr('Still needed: {fields}', { fields: missing.join(', ') }), 'error');
            }
            const epoch = NewInquiryState.begin();
            if (!epoch) return;
            NewInquiryForm.freeze(true);
            NewInquiryForm.setStatus(tr('Saving…'));
            try {
                const customer = state.customer || await ApiClient.createCustomer({
                    display_name: form.companyName,
                    country: form.country || undefined,
                    city: form.city || undefined,
                });
                // The customer is real from here on, whatever happens next: a
                // failed lead leaves a company on file, not a half-written
                // record nobody can explain.
                NewInquiryState.chooseCustomer(customer);
                const contact = await resolveContact(customer, form.contactEmail);
                const lead = await ApiClient.createLead({
                    customer_id: customer.id,
                    primary_contact_id: contact?.id || undefined,
                    owner_id: State.user.id,
                    title: form.title,
                    source_channel: 'manual',
                    product_category: form.productCategory || undefined,
                    application: form.application || undefined,
                    inquiry_date: form.inquiryDate || undefined,
                    special_requirements: form.requirements || undefined,
                });
                hideModal('new-inquiry-modal');
                NewInquiryForm.clear();
                NewInquiryState.reset();
                notify(tr('Enquiry {id} created for {company}.', {
                    id: lead.display_id || '', company: customer.display_name,
                }));
                // Refreshing the counts takes a moment, and the reader may
                // open something else in it. Opening the new enquiry then
                // would take the screen away from the choice they just made.
                const openedBefore = State.currentInquiry?.id || null;
                await refreshAllCounts();
                if ((State.currentInquiry?.id || null) === openedBefore) {
                    await openInquiryPanel(lead.id);
                }
                return lead;
            } catch (error) {
                NewInquiryForm.setStatus(
                    tr('Could not save: {error}',
                        { error: error?.message || tr('Unknown error') }), 'error');
                return null;
            } finally {
                NewInquiryState.end(epoch);
                NewInquiryForm.freeze(false);
            }
        },
    });
})();
