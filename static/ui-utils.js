/* ============================================================
   ui-utils.js — Shared UI utilities for Kumbh Reunite portals
   Depends on: i18n.js (for t())
   Usage:
     <script src="/static/i18n.js"></script>
     <script src="/static/ui-utils.js"></script>
   ============================================================ */

(function(global) {
  'use strict';

  /* ----------------------------------------------------------
     esc() — XSS-safe HTML escaping
  ---------------------------------------------------------- */
  /**
   * Escape a string so it is safe to inject into innerHTML.
   * @param {*} str - Value to escape (coerced to string)
   * @returns {string}
   */
  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /* ----------------------------------------------------------
     statusBadge() — render a coloured status pill
  ---------------------------------------------------------- */
  /**
   * Returns an HTML string for a status badge span.
   * Covers all status values used across control / volunteer / family portals.
   * @param {string} status
   * @returns {string} HTML string
   */
  function statusBadge(status) {
    const map = {
      'Reunited':               'badge-reunited',
      'Pending':                'badge-pending',
      'Unresolved':             'badge-unresolved',
      'Transferred to hospital':'badge-hospital',
      'In Hospital':            'badge-hospital',
      'Matched':                'badge-matched',
      'Found':                  'badge-found',
      'Searching':              'badge-searching',
    };
    const cls = map[status] || 'badge-pending';
    return `<span class="badge ${cls}">${esc(status)}</span>`;
  }

  /* ----------------------------------------------------------
     photoThumb() — render a thumbnail or SVG placeholder
  ---------------------------------------------------------- */
  /**
   * Returns an HTML img tag for a photo, or an SVG silhouette placeholder.
   * @param {string|null} photo   - base64 data-URI or URL; falsy → placeholder
   * @param {number}      [size=48] - pixel size for placeholder SVG
   * @returns {string} HTML string
   */
  function photoThumb(photo, size) {
    size = size || 48;
    if (photo) {
      return `<img src="${esc(photo)}" width="${size}" height="${size}" `
           + `style="object-fit:cover;border-radius:6px;" alt="photo">`;
    }
    // SVG person silhouette placeholder
    return `<svg width="${size}" height="${size}" viewBox="0 0 40 40"
              xmlns="http://www.w3.org/2000/svg"
              style="border-radius:6px;background:#f0f0f0;">
              <circle cx="20" cy="14" r="7" fill="#bdbdbd"/>
              <ellipse cx="20" cy="32" rx="12" ry="8" fill="#bdbdbd"/>
            </svg>`;
  }

  /* ----------------------------------------------------------
     compressImage() — canvas-based client-side image compression
  ---------------------------------------------------------- */
  /**
   * Compress an image File to a JPEG data-URI via a canvas element.
   * Uses an existing <canvas id="compressCanvas"> if present, or creates
   * a temporary off-screen canvas.
   *
   * @param {File}     file    - Image file from an <input type="file">
   * @param {number}   [maxDim=400]  - Maximum width or height in pixels
   * @param {number}   [quality=0.6] - JPEG quality 0..1
   * @param {Function} cb      - Called with (dataUri:string) when done
   */
  function compressImage(file, maxDim, quality, cb) {
    maxDim  = maxDim  || 400;
    quality = quality !== undefined ? quality : 0.6;

    const reader = new FileReader();
    reader.onload = function(e) {
      const img = new Image();
      img.onload = function() {
        // Reuse existing canvas if available (avoids memory churn)
        let canvas = document.getElementById('compressCanvas');
        const isOwned = !canvas;
        if (isOwned) {
          canvas = document.createElement('canvas');
        }

        let w = img.width, h = img.height;
        if (w > h && w > maxDim) {
          h = Math.round(h * maxDim / w);
          w = maxDim;
        } else if (h > maxDim) {
          w = Math.round(w * maxDim / h);
          h = maxDim;
        }

        canvas.width  = w;
        canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);

        const dataUri = canvas.toDataURL('image/jpeg', quality);

        // Release off-screen canvas
        if (isOwned) {
          canvas.width = 0;
          canvas.height = 0;
        }

        cb(dataUri);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  /* ----------------------------------------------------------
     showToast() — transient notification toast
  ---------------------------------------------------------- */
  /**
   * Display a temporary toast notification.
   * Injects a #toast-container div if it does not already exist.
   *
   * @param {string} message
   * @param {'success'|'error'|'warning'|'info'|''} [type=''] - maps to CSS class
   * @param {number} [duration=3000] - milliseconds before auto-dismiss
   */
  function showToast(message, type, duration) {
    type     = type     || '';
    duration = duration !== undefined ? duration : 3000;

    // Ensure container exists
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast' + (type ? ' ' + type : '');
    toast.textContent = message;
    container.appendChild(toast);

    // Trigger CSS transition on next frame
    requestAnimationFrame(function() {
      requestAnimationFrame(function() {
        toast.classList.add('show');
      });
    });

    setTimeout(function() {
      toast.classList.remove('show');
      toast.addEventListener('transitionend', function() {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, { once: true });
    }, duration);
  }

  /* ----------------------------------------------------------
     loadStats() — fetch /api/stats and populate stat cards
  ---------------------------------------------------------- */
  /**
   * Fetch aggregate stats from /api/stats and render them into
   * a container element. Each stat card is rendered as:
   *
   *   <div class="stat-card">
   *     <div class="stat-value">{value}</div>
   *     <div class="stat-label">{label}</div>
   *   </div>
   *
   * The stats array is configurable so each portal can show
   * the subset it needs.
   *
   * @param {string} containerId - id of the container element
   * @param {Array<{key:string, label:string}>} stats
   *   key   - property name on the API response object
   *   label - display label (use t() before passing for i18n)
   *
   * @example
   *   loadStats('stats-container', [
   *     { key: 'total_reports', label: t('statTotal') },
   *     { key: 'reunited_count', label: t('statReunited') },
   *   ]);
   */
  async function loadStats(containerId, stats) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Show skeleton while loading
    if (stats && stats.length) {
      container.innerHTML = stats.map(function() {
        return '<div class="stat-card skeleton" style="min-height:60px;"></div>';
      }).join('');
    }

    try {
      const res = await fetch('/api/stats');
      if (!res.ok) throw new Error('API error ' + res.status);
      const data = await res.json();

      if (!stats || !stats.length) {
        // No config provided — render all keys returned by the API
        container.innerHTML = Object.keys(data).map(function(k) {
          return '<div class="stat-card">'
               + '<div class="stat-value">' + esc(data[k]) + '</div>'
               + '<div class="stat-label">' + esc(k) + '</div>'
               + '</div>';
        }).join('');
        return;
      }

      container.innerHTML = stats.map(function(s) {
        const raw = data[s.key];
        let val;
        if (raw == null) {
          val = '—';
        } else if (typeof raw === 'number' && !Number.isInteger(raw)) {
          val = raw.toFixed(1);
        } else {
          val = raw;
        }
        return '<div class="stat-card">'
             + '<div class="stat-value">' + esc(val) + '</div>'
             + '<div class="stat-label">' + esc(s.label) + '</div>'
             + '</div>';
      }).join('');

    } catch(e) {
      // On error, render dashes
      if (stats && stats.length) {
        container.innerHTML = stats.map(function(s) {
          return '<div class="stat-card">'
               + '<div class="stat-value">—</div>'
               + '<div class="stat-label">' + esc(s.label) + '</div>'
               + '</div>';
        }).join('');
      }
    }
  }

  /* ----------------------------------------------------------
     Export
  ---------------------------------------------------------- */
  global.esc          = esc;
  global.statusBadge  = statusBadge;
  global.photoThumb   = photoThumb;
  global.compressImage = compressImage;
  global.showToast    = showToast;
  global.loadStats    = loadStats;

}(window));
