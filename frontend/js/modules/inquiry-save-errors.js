function handleContactValidationError(message) {
    // Parse error message and show in relevant field
    if (message.toLowerCase().includes('email') && message.toLowerCase().includes('exists')) {
        showContactTabFieldError('email', '该邮箱已存在于此客户的联系人中');
    } else if (message.toLowerCase().includes('email') && message.toLowerCase().includes('format')) {
        showContactTabFieldError('email', '邮箱格式错误');
    } else if (message.includes('name') && message.includes('email')) {
        showContactTabFieldError('contact_name', '联系人姓名和邮箱至少填写一项');
    } else {
        alert('联系人保存错误: ' + message);
    }
}

function showContactTabFieldError(fieldName, message) {
    const customerTab = document.querySelector('.panel-tab[data-tab="customer"]');
    if (customerTab && !customerTab.classList.contains('active')) {
        customerTab.click();
        requestAnimationFrame(() => showFieldError(fieldName, message));
        return;
    }

    showFieldError(fieldName, message);
}

