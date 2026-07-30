function handleContactValidationError(message) {
    // Parse error message and show in relevant field
    if (message.toLowerCase().includes('email') && message.toLowerCase().includes('exists')) {
        showContactTabFieldError('email', I18n.t('This email already exists among this customer\'s contacts.'));
    } else if (message.toLowerCase().includes('email') && message.toLowerCase().includes('format')) {
        showContactTabFieldError('email', I18n.t('Invalid email format.'));
    } else if (message.includes('name') && message.includes('email')) {
        showContactTabFieldError('contact_name', I18n.t('Enter at least a contact name or email address.'));
    } else {
        alert(I18n.t('Error saving contact: {error}', { error: I18n.t(message) }));
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
