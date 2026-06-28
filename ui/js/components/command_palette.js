/**
 * CommandPalette — global Cmd+K search surface.
 * Dispatches jig:* CustomEvents for actions; other modules listen for what they need.
 */
const CommandPalette = (() => {
  // ── State ──────────────────────────────────────────────────────────────────
  let _allItems  = [];   // full item list loaded on each open
  let _rendered  = [];   // items currently shown (filtered + sliced)
  let _activeIdx = -1;
  let _visible   = false;

  let _el, _input, _results;

  // ── Constants ──────────────────────────────────────────────────────────────
  const FREQ_KEY  = 'jig_palette_freq';
  const CAT_ORDER = { command: 0, flow: 1, block: 2, step: 3, history: 4 };
  const CAT_LABEL = {
    command: 'Commands',
    flow:    'Flows',
    block:   'Blocks',
    step:    'Steps',
    history: 'Recent Runs',
  };
  const STATUS_COLOR = {
    completed: 'var(--success)',
    failed:    'var(--danger)',
    running:   'var(--info)',
    cancelled: 'var(--muted)',
  };

  // ── Frequency helpers ──────────────────────────────────────────────────────
  function _getFreq() {
    try { return JSON.parse(localStorage.getItem(FREQ_KEY) || '{}'); } catch { return {}; }
  }
  function _bump(id) {
    const f = _getFreq();
    f[id] = (f[id] || 0) + 1;
    try { localStorage.setItem(FREQ_KEY, JSON.stringify(f)); } catch {}
  }

  // ── Filtering & ranking ────────────────────────────────────────────────────
  function _matchItem(item, q) {
    const haystack = `${item.label} ${item.subtitle || ''} ${item.id || ''}`.toLowerCase();
    return q.split(/\s+/).filter(Boolean).every(word => haystack.includes(word));
  }

  function _filter(q) {
    const freq = _getFreq();
    const result = [];

    for (const cat of ['command', 'flow', 'block', 'step', 'history']) {
      let group = _allItems.filter(it => it.category === cat);

      if (!q) {
        // Default view: commands + flows + last 3 history; skip steps/blocks
        if (cat === 'step' || cat === 'block') continue;
        if (cat === 'history') group = group.slice(0, 3);
      } else {
        group = group.filter(it => _matchItem(it, q));
      }

      if (!group.length) continue;

      // Sort within group: prefix match > frequency > label
      group.sort((a, b) => {
        if (q) {
          const ap = a.label.toLowerCase().startsWith(q) ? 0 : 1;
          const bp = b.label.toLowerCase().startsWith(q) ? 0 : 1;
          if (ap !== bp) return ap - bp;
        }
        const af = freq[a.id] || 0;
        const bf = freq[b.id] || 0;
        if (af !== bf) return bf - af;
        return a.label.localeCompare(b.label);
      });

      result.push(...group);
    }

    return result.slice(0, 48);
  }

  // ── Rendering ──────────────────────────────────────────────────────────────
  function _esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function _statusDot(status) {
    const color = STATUS_COLOR[status] || 'var(--muted)';
    return `<span style="width:6px;height:6px;border-radius:50%;background:${color};display:inline-block;flex-shrink:0"></span>`;
  }

  const COMPAT_COLOR = { green: 'var(--success)', yellow: 'var(--warning)', red: 'var(--danger)' };
  const COMPAT_TITLE = { green: 'Full contract', yellow: 'Partial contract', red: 'Missing required fields' };

  function _compatBadge(compat) {
    if (!compat || compat === 'none') return '';
    const color = COMPAT_COLOR[compat] || 'var(--muted)';
    const title = COMPAT_TITLE[compat] || '';
    return `<span class="palette-compat-dot" style="background:${color}" title="${title}"></span>`;
  }

  function _render() {
    const q = (_input.value || '').trim().toLowerCase();
    _rendered  = _filter(q);
    _activeIdx = _rendered.length ? 0 : -1;

    if (!_rendered.length) {
      _results.innerHTML = `<div class="palette-empty">${_allItems.length ? 'No results' : 'Loading…'}</div>`;
      return;
    }

    let html     = '';
    let lastCat  = null;

    for (let i = 0; i < _rendered.length; i++) {
      const item = _rendered[i];

      if (item.category !== lastCat) {
        html += `<div class="palette-category">${CAT_LABEL[item.category] || item.category}</div>`;
        lastCat = item.category;
      }

      const active      = i === 0 ? ' active' : '';
      const dot         = item.status ? _statusDot(item.status) : '';
      const compatBadge = item.category === 'block' ? _compatBadge(item.compat) : '';

      html += `<div class="palette-item${active}" data-idx="${i}">
        <span class="palette-item-label">${dot}${_esc(item.label)}</span>
        <span class="palette-item-sub">${_esc(item.subtitle || '')}${compatBadge}</span>
      </div>`;
    }

    _results.innerHTML = html;

    _results.querySelectorAll('.palette-item').forEach(el => {
      const idx = +el.dataset.idx;
      el.addEventListener('click', () => { _activeIdx = idx; _commit(); });
      el.addEventListener('mousemove', () => {
        _results.querySelectorAll('.palette-item').forEach(e => e.classList.remove('active'));
        el.classList.add('active');
        _activeIdx = idx;
      });
    });
  }

  // ── Navigation ─────────────────────────────────────────────────────────────
  function _move(delta) {
    const els = _results.querySelectorAll('.palette-item');
    if (!els.length) return;
    els[_activeIdx]?.classList.remove('active');
    _activeIdx = Math.max(0, Math.min(els.length - 1, _activeIdx + delta));
    const el = els[_activeIdx];
    el?.classList.add('active');
    el?.scrollIntoView({ block: 'nearest' });
  }

  function _commit() {
    if (_activeIdx < 0 || _activeIdx >= _rendered.length) return;
    const item = _rendered[_activeIdx];
    if (!item) return;
    _bump(item.id);
    _dispatch(item.action);
  }

  // ── Action dispatch ────────────────────────────────────────────────────────
  function _dispatch(action) {
    close();
    const { type } = action;

    if (type === 'navigate') {
      App.navigate(action.view);

    } else if (type === 'navigate_flow') {
      App.navigate('flows');
      setTimeout(() => document.dispatchEvent(
        new CustomEvent('jig:open-flow', { detail: { flow_id: action.flow_id } })
      ), 60);

    } else if (type === 'open_run') {
      App.navigate('flows');
      setTimeout(() => document.dispatchEvent(
        new CustomEvent('jig:open-run', { detail: action })
      ), 60);

    } else if (type === 'set_mode') {
      document.dispatchEvent(new CustomEvent('jig:set-mode', { detail: { mode: action.mode } }));

    } else if (type === 'insert_step' || type === 'insert_block') {
      document.dispatchEvent(new CustomEvent('jig:insert-step', { detail: action }));

    } else if (type === 'command') {
      document.dispatchEvent(new CustomEvent('jig:command', { detail: action }));
    }
  }

  // ── Open / Close ───────────────────────────────────────────────────────────
  async function open() {
    if (_visible) { _input.select(); return; }
    _visible     = true;
    _allItems    = [];
    _rendered    = [];
    _el.classList.remove('hidden');
    _input.value = '';
    _results.innerHTML = '<div class="palette-empty">Loading…</div>';
    _input.focus();

    try {
      _allItems = await api.searchPalette() || [];
    } catch (_) {
      _allItems = [];
    }
    _render();
  }

  function close() {
    if (!_visible) return;
    _visible = false;
    _el.classList.add('hidden');
    _input.value = '';
    _allItems    = [];
    _rendered    = [];
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    const overlay = document.createElement('div');
    overlay.id        = 'palette-overlay';
    overlay.className = 'palette-overlay hidden';
    overlay.innerHTML = `
      <div class="palette-box" role="dialog" aria-modal="true" aria-label="Command palette">
        <div class="palette-search-row">
          <span class="palette-search-icon" aria-hidden="true">⌘K</span>
          <input
            id="palette-input"
            class="palette-input"
            type="text"
            placeholder="Search flows, blocks, steps, commands…"
            autocomplete="off"
            spellcheck="false"
            aria-label="Search"
          />
        </div>
        <div id="palette-results" class="palette-results" role="listbox"></div>
        <div class="palette-footer">
          <span>↑↓ navigate</span>
          <span>⏎ select</span>
          <span>Esc close</span>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    _el      = overlay;
    _input   = overlay.querySelector('#palette-input');
    _results = overlay.querySelector('#palette-results');

    // Close on backdrop click
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

    // Input: re-render on every keystroke
    _input.addEventListener('input', _render);

    // Keyboard nav inside input
    _input.addEventListener('keydown', e => {
      if      (e.key === 'Escape')    { e.preventDefault(); close(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); _move(1); }
      else if (e.key === 'ArrowUp')   { e.preventDefault(); _move(-1); }
      else if (e.key === 'Enter')     { e.preventDefault(); _commit(); }
    });

    // Global trigger: Cmd+K / Ctrl+K
    document.addEventListener('keydown', e => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        _visible ? close() : open();
      }
    });
  }

  return { init, open, close };
})();
