/* ============================================================
   auth.js — Role-based authentication module for Kumbh Reunite
   Usage:
     <script src="/static/auth.js"></script>

     const auth = createAuthModule('admin', {
       overlayId:    'login-overlay',   // default
       overlayClass: 'show',            // default; use 'hidden' for control.html
       userEl:       'current-user',
       logoutBtnEl:  'logout-btn',
       onSuccess:    (username) => { ... },
       allowGuest:   false,             // true for family portal
     });

     auth.checkAuth();   // call on page load
   ============================================================ */

(function(global) {
  'use strict';

  /**
   * Factory that creates a self-contained auth module for a portal.
   *
   * @param {string} requiredRole  - Role string that /api/login must return
   *                                 e.g. 'admin', 'volunteer', 'family'
   * @param {object} opts
   * @param {string}   [opts.overlayId='login-overlay']   - id of overlay element
   * @param {string}   [opts.overlayClass='show']         - CSS class toggled to show overlay
   *                                                         Use 'show' (family/volunteer) or
   *                                                         invert with opts.hiddenClass
   * @param {string}   [opts.hiddenClass='hidden']        - CSS class toggled to HIDE overlay
   *                                                         (control.html pattern). Mutually
   *                                                         exclusive with overlayClass.
   * @param {string}   [opts.userInputId='login-username']- id of username <input>
   * @param {string}   [opts.passInputId='login-password']- id of password <input>
   * @param {string}   [opts.errorElId='login-error']     - id of error message element
   * @param {string}   [opts.userDisplayElId]             - id of element showing "Logged in as X"
   * @param {string}   [opts.logoutBtnId='logout-btn']    - id of logout button element
   * @param {string}   [opts.logoutBtnVisibleClass='visible'] - class added to show logout btn
   * @param {boolean}  [opts.allowGuest=false]            - if true, unauthenticated users can
   *                                                         browse in read-only guest mode
   * @param {Function} [opts.onSuccess]                   - called with (username) after login
   * @param {Function} [opts.onGuest]                     - called when guest mode is activated
   *
   * @returns {{ checkAuth, showLoginOverlay, hideLoginOverlay, doLogin, doLogout }}
   */
  function createAuthModule(requiredRole, opts) {
    opts = opts || {};

    /* ── Resolved options ──────────────────────────────── */
    const overlayId           = opts.overlayId          || 'login-overlay';
    const overlayClass        = opts.overlayClass       || 'show';
    const hiddenClass         = opts.hiddenClass        || null;   // null = not used
    const userInputId         = opts.userInputId        || 'login-username';
    const passInputId         = opts.passInputId        || 'login-password';
    const errorElId           = opts.errorElId          || 'login-error';
    const userDisplayElId     = opts.userDisplayElId    || null;
    const logoutBtnId         = opts.logoutBtnId        || 'logout-btn';
    const logoutBtnVisClass   = opts.logoutBtnVisibleClass || 'visible';
    const allowGuest          = opts.allowGuest         || false;
    const onSuccess           = typeof opts.onSuccess === 'function' ? opts.onSuccess : null;
    const onGuest             = typeof opts.onGuest === 'function'   ? opts.onGuest   : null;

    /* ── DOM helpers ───────────────────────────────────── */
    function el(id) { return document.getElementById(id); }

    /* ── Overlay show/hide ─────────────────────────────── */
    function showLoginOverlay() {
      const overlay = el(overlayId);
      if (!overlay) return;
      if (hiddenClass) {
        // control.html pattern: remove 'hidden' to reveal
        overlay.classList.remove(hiddenClass);
      } else {
        // volunteer / family pattern: add 'show'
        overlay.classList.add(overlayClass);
      }
    }

    function hideLoginOverlay() {
      const overlay = el(overlayId);
      if (!overlay) return;
      if (hiddenClass) {
        overlay.classList.add(hiddenClass);
      } else {
        overlay.classList.remove(overlayClass);
      }
    }

    /* ── Internal: mark user as authenticated ──────────── */
    function _onLoginSuccess(username) {
      hideLoginOverlay();

      // Show username in header/nav
      if (userDisplayElId && el(userDisplayElId)) {
        el(userDisplayElId).textContent = username;
      }

      // Show logout button
      const logoutBtn = el(logoutBtnId);
      if (logoutBtn) {
        logoutBtn.classList.add(logoutBtnVisClass);
        // Also handle the .shown pattern used in some portals
        logoutBtn.style.display = 'flex';
      }

      if (onSuccess) onSuccess(username);
    }

    /* ── checkAuth — call on page load ─────────────────── */
    async function checkAuth() {
      try {
        const res = await fetch('/api/me', { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          // Accept if role matches OR if allowGuest and no role required
          if (data.username && (data.role === requiredRole || requiredRole === '*')) {
            _onLoginSuccess(data.username);
            return;
          }
        }
      } catch(e) {
        // Network error — treat as unauthenticated
      }

      // Not authenticated
      if (allowGuest) {
        // Family portal: show overlay but do NOT block — guest can browse
        showLoginOverlay();
        if (onGuest) onGuest();
      } else {
        // Gated portals: show overlay and block access
        showLoginOverlay();
      }
    }

    /* ── doLogin — call on form submit ─────────────────── */
    async function doLogin() {
      const usernameEl = el(userInputId);
      const passwordEl = el(passInputId);
      const errorEl   = el(errorElId);

      if (!usernameEl || !passwordEl) return;

      const username = usernameEl.value.trim();
      const password = passwordEl.value;

      if (errorEl) errorEl.textContent = '';

      if (!username || !password) {
        if (errorEl) {
          errorEl.textContent = (typeof t === 'function')
            ? t('loginError')
            : 'Please enter username and password.';
        }
        return;
      }

      try {
        const res = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ username, password, role: requiredRole }),
        });

        if (res.ok) {
          const data = await res.json();
          if (data.success || data.username) {
            const user = data.username || username;
            if (passwordEl) passwordEl.value = '';
            _onLoginSuccess(user);
          } else {
            _showLoginError(errorEl, data.error || null);
          }
        } else {
          _showLoginError(errorEl, null);
        }
      } catch(e) {
        _showLoginError(errorEl, 'Network error. Please try again.');
      }
    }

    /* ── doLogout ───────────────────────────────────────── */
    async function doLogout() {
      try {
        await fetch('/api/logout', {
          method: 'POST',
          credentials: 'include',
        });
      } catch(e) {
        // Ignore network errors — proceed with client-side logout anyway
      }

      // Hide logout button
      const logoutBtn = el(logoutBtnId);
      if (logoutBtn) {
        logoutBtn.classList.remove(logoutBtnVisClass);
        logoutBtn.style.display = 'none';
      }

      // Clear username display
      if (userDisplayElId && el(userDisplayElId)) {
        el(userDisplayElId).textContent = '';
      }

      showLoginOverlay();
    }

    /* ── doGuest — family portal only ──────────────────── */
    function doGuest() {
      if (!allowGuest) return;
      hideLoginOverlay();
      if (onGuest) onGuest();
    }

    /* ── Internal: show login error ─────────────────────── */
    function _showLoginError(errorEl, msg) {
      if (!errorEl) return;
      errorEl.textContent = msg || (typeof t === 'function'
        ? t('loginError')
        : 'Invalid credentials. Please try again.');
    }

    /* ── Public interface ───────────────────────────────── */
    return {
      checkAuth,
      showLoginOverlay,
      hideLoginOverlay,
      doLogin,
      doLogout,
      doGuest,
    };
  }

  /* ----------------------------------------------------------
     Export
  ---------------------------------------------------------- */
  global.createAuthModule = createAuthModule;

}(window));
