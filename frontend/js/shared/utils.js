// ===== Modal Helpers =====
const modalFocusOrigins = new Map();

function modalFocusableElements(modal) {
    return [...modal.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), '
        + 'textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    )].filter(element => !element.hidden && element.offsetParent !== null);
}

function showModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    if (!modal.classList.contains('show')) {
        modalFocusOrigins.set(id, document.activeElement);
    }
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    const app = document.getElementById('app');
    if (app) app.inert = true;
    requestAnimationFrame(() => {
        const preferred = modal.querySelector(
            '[autofocus], #login-username, #activation-file, #coord-address'
        );
        (preferred || modalFocusableElements(modal)[0])?.focus();
    });
}

function hideModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    if (!document.querySelector('.modal.show')) {
        const app = document.getElementById('app');
        if (app) app.inert = false;
    }
    const origin = modalFocusOrigins.get(id);
    modalFocusOrigins.delete(id);
    if (origin?.isConnected) origin.focus();
}

document.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const openModals = [...document.querySelectorAll('.modal.show')];
    const modal = openModals.at(-1);
    if (!modal) return;
    const focusable = modalFocusableElements(modal);
    if (!focusable.length) {
        event.preventDefault();
        return;
    }
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
    }
});

// ===== Utility Functions =====
function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setPanelLoading(id, text = 'Loading...') {
    const el = document.getElementById(id);
    if (el) {
        el.innerHTML = `<div class="loading-state">${escapeHtml(text)}</div>`;
    }
}

function setPanelError(id, text = 'Unable to load') {
    const el = document.getElementById(id);
    if (el) {
        el.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(text)}</div>`;
    }
}

function formatLabel(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function formatDate(str) {
    if (!str) return '-';
    try {
        const calendarParts = String(str).match(/^(\d{4})-(\d{2})-(\d{2})$/);
        const date = calendarParts
            ? new Date(Number(calendarParts[1]), Number(calendarParts[2]) - 1, Number(calendarParts[3]))
            : new Date(str);
        if (Number.isNaN(date.getTime())) return str;
        const locale = window.I18n?.locale?.()
            || (String(navigator.language || '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US');
        return date.toLocaleDateString(locale, {
            year: 'numeric', month: 'short', day: 'numeric'
        });
    } catch { return str; }
}

function toDateInput(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function formatMoney(value) {
    const amount = Number(value || 0);
    if (!amount) return '-';
    return `$${amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function formatK(value) {
    return Math.round(Number(value || 0) / 1000).toLocaleString();
}

function formatFileSize(bytes) {
    const size = Number(bytes || 0);
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function notify(message) {
    const toast = document.createElement('div');
    toast.className = 'app-toast';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 180);
    }, 1800);
}

function debounce(fn, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn.apply(this, args), wait);
    };
}
