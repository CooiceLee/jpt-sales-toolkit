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
    // The dialog was display:none a moment ago, and focusing something that
    // has no box yet quietly does nothing: the first time a dialog was opened
    // focus stayed on the page behind it. Try again on the next frame, and
    // only while focus is still outside - a reader who has already clicked
    // into a field keeps it.
    const focusInside = (attemptsLeft) => {
        if (modal.contains(document.activeElement)) return;
        const preferred = modal.querySelector(
            '[autofocus], #login-username, #activation-file, #coord-address'
        );
        (preferred || modalFocusableElements(modal)[0])?.focus();
        if (attemptsLeft > 0 && !modal.contains(document.activeElement)) {
            requestAnimationFrame(() => focusInside(attemptsLeft - 1));
        }
    };
    requestAnimationFrame(() => focusInside(2));
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

// Escape leaves a dialog the way its own Cancel button does - and only where
// there is one. The sign-in and activation dialogs are the way into the
// program, not something to dismiss; pressing Escape on those does nothing.
// Routing through the button keeps whatever that dialog checks before closing:
// a save in flight stays uninterrupted, and a draft is discarded only where
// clicking Cancel would have discarded it.
document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const modal = [...document.querySelectorAll('.modal.show')].at(-1);
    const dismiss = modal?.querySelector('[data-modal-dismiss]');
    if (!dismiss || dismiss.disabled) return;
    event.preventDefault();
    dismiss.click();
});

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

function formatMoney(value, currency) {
    const amount = Number(value || 0);
    if (!amount) return '-';
    const number = amount.toLocaleString(undefined, { maximumFractionDigits: 0 });
    const code = String(currency || '').trim().toUpperCase();
    // A number wearing the wrong currency is worse than a number wearing none.
    // Nothing here converts, so nothing here may claim a currency it was not
    // given.
    return code ? `${code} ${number}` : number;
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
