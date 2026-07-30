// ===== Placeholder Functions =====
window.showNewInquiryModal = function() {
    switchModule('parser');
};

window.logFollowUp = function() {
    switchModule('followup');
    notify(I18n.t('Select a follow-up card to add a record.'));
};

window.createQuote = function() {
    switchModule('deal');
    notify(I18n.t('Select a quoted lead card to edit quotation info.'));
};

window.logStatus = function() {
    switchModule('fulfillment');
    notify(I18n.t('Select an order card to update fulfillment status.'));
};

window.logIssue = function() {
    switchModule('aftersales');
    notify(I18n.t('Select an after-sales card to log an issue.'));
};
