// ===== Placeholder Functions =====
window.showNewInquiryModal = function() {
    switchModule('parser');
};

window.logFollowUp = function() {
    switchModule('followup');
    notify('Select a follow-up card to add a record.');
};

window.createQuote = function() {
    switchModule('deal');
    notify('Select a quoted lead card to edit quotation info.');
};

window.logStatus = function() {
    switchModule('fulfillment');
    notify('Select an order card to update fulfillment status.');
};

window.logIssue = function() {
    switchModule('aftersales');
    notify('Select an after-sales card to log an issue.');
};
