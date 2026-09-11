// ===== Business actions that create the first record, not only the next one =====
//
// These used to switch module and ask the reader to pick a card. The card lists
// they were sent to only held leads that already carried the record being
// created, so the first quote, the first pre-sales task and the first
// after-sales issue could not be started from the button at all. Each action
// now names what it is about, chooses the lead, opens that lead's panel on the
// right tab, and opens the form there.

window.logFollowUp = function () {
    BusinessActionPicker.open({
        title: 'Record a follow-up on which lead?',
        context: 'followup',
        then: () => window.showFollowUpForm?.(),
    });
};

window.newSampleRequest = function () {
    if (!RoleCapabilities.canManageTaskRequests()) return;
    BusinessActionPicker.open({
        title: 'Create a pre-sales task on which lead?',
        context: 'sampling',
        then: () => window.showSampleTaskForm?.(-1),
    });
};

window.createQuote = function () {
    BusinessActionPicker.open({
        title: 'Record a quotation on which lead?',
        context: 'deal',
    });
};

window.logIssue = function () {
    if (!RoleCapabilities.canManageTaskRequests()) return;
    BusinessActionPicker.open({
        title: 'Log an after-sales issue on which lead?',
        context: 'aftersales',
        then: () => window.showAfterSalesForm?.(),
    });
};

// Fulfillment updates an order that already exists; it is not a creation and
// does not pretend to be one.
window.logStatus = function () {
    BusinessActionPicker.open({
        title: 'Update fulfillment on which order?',
        context: 'fulfillment',
    });
};
