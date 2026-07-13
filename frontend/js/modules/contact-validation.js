// ===== Contact Validation =====
function setupContactValidation() {
    const nameInput = document.querySelector('input[name="contact_name"]');
    const emailInput = document.querySelector('input[name="email"]');

    if (!nameInput || !emailInput) return;

    // Email format validation
    emailInput.addEventListener('blur', () => {
        validateEmail(emailInput);
    });

    emailInput.addEventListener('input', () => {
        // Clear error on input
        clearFieldError('email');
    });

    // Contact name validation
    nameInput.addEventListener('blur', () => {
        validateContactFields(nameInput, emailInput);
    });

    emailInput.addEventListener('blur', () => {
        validateContactFields(nameInput, emailInput);
    });
}

function validateEmail(input) {
    const email = input.value.trim();
    if (!email) {
        clearFieldError('email');
        return true;
    }

    // Match backend is_valid_email logic
    if (!email.includes('@')) {
        showFieldError('email', '邮箱格式错误：缺少 @ 符号');
        return false;
    }

    const parts = email.split('@');
    if (parts.length !== 2) {
        showFieldError('email', '邮箱格式错误：@ 符号使用不正确');
        return false;
    }

    const [local, domain] = parts;
    if (!local || !domain) {
        showFieldError('email', '邮箱格式错误：缺少本地部分或域名');
        return false;
    }

    if (!domain.includes('.')) {
        showFieldError('email', '邮箱格式错误：域名缺少 . 符号');
        return false;
    }

    const domainParts = domain.split('.');
    if (domainParts.some(part => !part)) {
        showFieldError('email', '邮箱格式错误：域名格式不正确');
        return false;
    }

    clearFieldError('email');
    return true;
}

function validateContactFields(nameInput, emailInput) {
    const name = nameInput.value.trim();
    const email = emailInput.value.trim();

    // At least one must be filled
    if (!name && !email) {
        showFieldError('contact_name', '联系人姓名和邮箱至少填写一项');
        return false;
    }

    clearFieldError('contact_name');
    return true;
}

function showFieldError(fieldName, message) {
    const errorEl = document.getElementById(`error-${fieldName}`);
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
        errorEl.style.color = 'var(--danger, #dc3545)';
        errorEl.style.fontSize = '13px';
        errorEl.style.marginTop = '4px';
    }
}

function clearFieldError(fieldName) {
    const errorEl = document.getElementById(`error-${fieldName}`);
    if (errorEl) {
        errorEl.style.display = 'none';
        errorEl.textContent = '';
    }
}

