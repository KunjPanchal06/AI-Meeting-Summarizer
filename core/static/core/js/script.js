/* ============================================================
   MEETINGLY — Global JavaScript
   Theme, Command Palette, Sidebar, Toasts, Helpers
   ============================================================ */

// ── Theme ───────────────────────────────────────────────────
const Theme = {
  key: 'meetingly-theme',
  get() { return localStorage.getItem(this.key) || 'light'; },
  set(t) {
    localStorage.setItem(this.key, t);
    document.documentElement.setAttribute('data-theme', t);
    this._updateIcon(t);
  },
  toggle() { this.set(this.get() === 'dark' ? 'light' : 'dark'); },
  init() {
    const t = this.get();
    document.documentElement.setAttribute('data-theme', t);
    this._updateIcon(t);
  },
  _updateIcon(t) {
    document.querySelectorAll('[data-theme-icon]').forEach(el => {
      el.innerHTML = t === 'dark'
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
    });
  }
};

// ── Sidebar ─────────────────────────────────────────────────
const Sidebar = {
  key: 'meetingly-sidebar',
  el: null,
  overlay: null,
  isMobile() { return window.innerWidth <= 768; },

  init() {
    this.el = document.getElementById('sidebar');
    this.overlay = document.getElementById('sidebar-overlay');
    if (!this.el) return;

    // Restore collapsed state on desktop
    if (!this.isMobile() && localStorage.getItem(this.key) === 'collapsed') {
      this.el.classList.add('collapsed');
    }

    // Overlay click closes sidebar on mobile
    if (this.overlay) {
      this.overlay.addEventListener('click', () => this.closeMobile());
    }
  },

  toggle() {
    if (this.isMobile()) {
      this.el.classList.toggle('mobile-open');
      this.overlay?.classList.toggle('visible');
    } else {
      this.el.classList.toggle('collapsed');
      localStorage.setItem(this.key, this.el.classList.contains('collapsed') ? 'collapsed' : 'open');
    }
  },

  closeMobile() {
    this.el.classList.remove('mobile-open');
    this.overlay?.classList.remove('visible');
  }
};

// ── Command Palette ──────────────────────────────────────────
const Cmd = {
  overlay: null,
  input: null,
  items: [],
  selectedIndex: -1,

  nav: [
    { label: 'Dashboard',    icon: 'layout-dashboard', href: '/'              },
    { label: 'Upload Meeting',icon: 'upload',           href: '/upload/'       },
    { label: 'Process Text',  icon: 'file-text',        href: '/process/'      },
    { label: 'All Meetings',  icon: 'list',             href: '/meetings/'     },
    { label: 'Settings',      icon: 'settings',         href: '/settings/'     },
  ],

  init() {
    this.overlay = document.getElementById('cmd-overlay');
    this.input   = document.getElementById('cmd-input');
    if (!this.overlay) return;

    document.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        this.toggle();
      }
      if (e.key === 'Escape') this.close();
      if (this.overlay.classList.contains('open')) {
        if (e.key === 'ArrowDown') { e.preventDefault(); this.move(1); }
        if (e.key === 'ArrowUp')   { e.preventDefault(); this.move(-1); }
        if (e.key === 'Enter')     { e.preventDefault(); this.confirm(); }
      }
    });

    this.overlay.addEventListener('click', e => {
      if (e.target === this.overlay) this.close();
    });

    document.querySelectorAll('[data-cmd-open]').forEach(el =>
      el.addEventListener('click', () => this.open())
    );

    if (this.input) {
      this.input.addEventListener('input', () => this.render(this.input.value));
    }

    this.render('');
  },

  toggle() { this.overlay.classList.contains('open') ? this.close() : this.open(); },
  open() {
    this.overlay.classList.add('open');
    this.input?.focus();
    this.render('');
  },
  close() {
    this.overlay.classList.remove('open');
    if (this.input) this.input.value = '';
    this.selectedIndex = -1;
  },

  move(dir) {
    const els = document.querySelectorAll('.cmd-item');
    this.selectedIndex = Math.max(0, Math.min(els.length - 1, this.selectedIndex + dir));
    els.forEach((el, i) => el.classList.toggle('selected', i === this.selectedIndex));
  },

  confirm() {
    const sel = document.querySelector('.cmd-item.selected');
    if (sel) sel.click();
  },

  render(q) {
    const results = document.getElementById('cmd-results');
    if (!results) return;
    const query = q.toLowerCase();
    const filtered = this.nav.filter(n => n.label.toLowerCase().includes(query));

    results.innerHTML = filtered.length
      ? `<div class="cmd-group-label">Navigation</div>` + filtered.map(n =>
          `<a class="cmd-item" href="${n.href}">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
             ${n.label}
           </a>`).join('')
      : `<div style="padding:24px;text-align:center;color:var(--text-subtle);font-size:13px;">No results for "${q}"</div>`;
    this.selectedIndex = -1;
  }
};

// ── Toast Notifications ──────────────────────────────────────
const Toast = {
  container: null,
  init() { this.container = document.getElementById('toast-container'); },
  show(msg, type = 'info', duration = 4000) {
    if (!this.container) return;
    const t = document.createElement('div');
    const colors = {
      success: 'var(--green)', error: 'var(--red)', info: 'var(--accent)', warning: 'var(--yellow)'
    };
    t.style.cssText = `
      padding:10px 16px; border-radius:8px; background:var(--surface);
      box-shadow:var(--shadow-md); border:1px solid var(--border);
      font-size:13.5px; color:var(--text); animation:slideDown 200ms ease;
      display:flex; align-items:center; gap:8px; min-width:240px; max-width:360px;
    `;
    t.innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:${colors[type]||colors.info};flex-shrink:0;"></span>${msg}`;
    this.container.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = '300ms'; setTimeout(() => t.remove(), 300); }, duration);
  }
};

// ── Helpers ──────────────────────────────────────────────────
function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  Theme.init();
  Sidebar.init();
  Cmd.init();
  Toast.init();

  // Auto-dismiss alerts after 5s
  document.querySelectorAll('.alert').forEach(el => {
    setTimeout(() => {
      el.style.transition = '400ms';
      el.style.opacity = '0';
      el.style.maxHeight = '0';
      el.style.padding = '0';
      setTimeout(() => el.remove(), 400);
    }, 5000);
  });
});

// ── Tab Indicator ─────────────────────────────────────────────
function initTabs(containerSelector) {
  const tabs = document.querySelector(containerSelector);
  if (!tabs) return;

  const buttons = tabs.querySelectorAll('.tab-btn');
  const indicator = tabs.querySelector('.tab-indicator');
  const contents = document.querySelectorAll('.tab-content');

  function activate(btn) {
    buttons.forEach(b => b.classList.remove('active'));
    contents.forEach(c => c.style.display = 'none');

    btn.classList.add('active');
    const target = document.getElementById('tab-' + btn.dataset.tab);
    if (target) target.style.display = 'block';

    // Move indicator
    if (indicator) {
      indicator.style.left  = btn.offsetLeft + 'px';
      indicator.style.width = btn.offsetWidth + 'px';
    }
  }

  buttons.forEach(btn => btn.addEventListener('click', () => activate(btn)));

  // Init first tab
  const firstActive = tabs.querySelector('.tab-btn.active') || buttons[0];
  if (firstActive) {
    // Show correct content
    contents.forEach(c => c.style.display = 'none');
    const firstTarget = document.getElementById('tab-' + firstActive.dataset.tab);
    if (firstTarget) firstTarget.style.display = 'block';
    // Position indicator after render
    requestAnimationFrame(() => {
      if (indicator) {
        indicator.style.left  = firstActive.offsetLeft + 'px';
        indicator.style.width = firstActive.offsetWidth + 'px';
      }
    });
  }
}
