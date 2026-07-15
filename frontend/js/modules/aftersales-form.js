window.showAfterSalesForm = function() {
    if (!RoleCapabilities.canManageTaskRequests()) return;
    document.getElementById('aftersales-form').classList.remove('hidden');
    document.getElementById('as-index').value = '-1';
    document.getElementById('as-date').value = new Date().toISOString().slice(0, 16);
    document.getElementById('as-type').value = 'Technical';
    document.getElementById('as-description').value = '';
    document.getElementById('as-tech').value = '';
    document.getElementById('as-status').value = 'Open';
    document.getElementById('as-solution').value = '';
    document.getElementById('as-satisfaction').value = '';
    document.getElementById('as-lessons').value = '';
    document.getElementById('as-remarks').value = '';
    const saveBtn = document.getElementById('as-save-btn');
    if (saveBtn) saveBtn.textContent = 'Save';
};

window.hideAfterSalesForm = function() {
    document.getElementById('aftersales-form').classList.add('hidden');
};

window.editAfterSales = function(index) {
    const issue = State.currentInquiry?.after_sales?.[index];
    if (!issue) return;

    document.getElementById('aftersales-form').classList.remove('hidden');
    document.getElementById('as-index').value = index;
    document.getElementById('as-date').value = issue.issue_date?.slice(0, 16) || '';
    document.getElementById('as-type').value = issue.issue_type || 'Technical';
    document.getElementById('as-description').value = issue.issue_description || '';
    document.getElementById('as-tech').value = issue.technician || '';
    document.getElementById('as-status').value = issue.status || 'Open';
    document.getElementById('as-solution').value = issue.solution || '';
    document.getElementById('as-satisfaction').value = issue.customer_satisfaction || '';
    document.getElementById('as-lessons').value = issue.lessons_learned || '';
    document.getElementById('as-remarks').value = issue.remarks || '';
    ['as-date', 'as-type', 'as-description'].forEach(id => {
        const field = document.getElementById(id);
        if (field) field.disabled = RoleCapabilities.isTech();
    });
    const saveBtn = document.getElementById('as-save-btn');
    if (saveBtn) saveBtn.textContent = 'Update';
    document.getElementById('aftersales-form')?.scrollIntoView({ block: 'nearest' });
};
