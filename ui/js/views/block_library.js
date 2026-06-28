/**
 * BlockLibraryView — searchable catalog of all blocks from sources/blocks/.
 */
const BlockLibraryView = (() => {
  let _blocks = [];
  let _query  = '';

  // ── Helpers ────────────────────────────────────────────────────────────────
  function _esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function _filtered() {
    if (!_query) return _blocks;
    const q = _query.toLowerCase();
    return _blocks.filter(b =>
      b.name.toLowerCase().includes(q) ||
      b.id.toLowerCase().includes(q) ||
      (b.description || '').toLowerCase().includes(q)
    );
  }

  // ── Rendering ──────────────────────────────────────────────────────────────
  function _cardHTML(b) {
    const params = Object.keys(b.params || {});
    const steps  = (b.steps || []).slice(0, 8); // show up to 8 step type badges

    const paramSection = params.length ? `
      <div class="block-param-section">
        <div class="block-param-label">Params</div>
        <div class="block-param-tags">
          ${params.map(p => `<span class="block-param-tag">${_esc(p)}</span>`).join('')}
        </div>
      </div>
    ` : '';

    const stepsSection = steps.length ? `
      <div class="block-steps-list">
        ${steps.map(s => `<span class="block-step-tag">${_esc(s.type)}</span>`).join('')}
        ${(b.steps || []).length > 8 ? `<span class="block-step-tag">+${(b.steps || []).length - 8} more</span>` : ''}
      </div>
    ` : '';

    return `
      <div class="block-card">
        <div class="block-card-name">${_esc(b.name)}</div>
        <div class="block-card-meta">${_esc(b.id)} · v${b.version || 1} · ${b.step_count || 0} steps</div>
        ${b.description ? `<div class="block-card-desc">${_esc(b.description)}</div>` : ''}
        ${stepsSection}
        ${paramSection}
      </div>
    `;
  }

  function _renderList(container) {
    const list     = container.querySelector('#block-grid');
    const filtered = _filtered();

    if (!filtered.length) {
      list.innerHTML = `<div class="text-muted" style="padding:20px;grid-column:1/-1">
        ${_blocks.length ? 'No blocks match.' : 'No blocks found in sources/blocks/.'}
      </div>`;
      return;
    }

    list.innerHTML = filtered.map(_cardHTML).join('');
  }

  // ── Public ─────────────────────────────────────────────────────────────────
  async function render(container) {
    container.innerHTML = `
      <div class="view">
        <div class="bl-header">
          <h2 class="view-title" style="margin:0">Block Library</h2>
          <input
            id="bl-search"
            class="bl-search"
            type="search"
            placeholder="Search blocks…"
            autocomplete="off"
          />
          <button class="btn btn-primary" id="bl-new-block">+ New Block</button>
        </div>
        <div id="block-grid" class="block-grid">
          <div class="loading" style="grid-column:1/-1">Loading blocks…</div>
        </div>
      </div>
    `;

    try {
      _blocks = await api.listBlocks() || [];
    } catch (err) {
      container.querySelector('#block-grid').innerHTML =
        `<div class="alert alert-danger" style="grid-column:1/-1">Failed to load blocks: ${_esc(err.message)}</div>`;
      return;
    }

    container.querySelector('#bl-new-block').addEventListener('click', () => {
      BlockConstructor.open(container, { onDone: () => render(container) });
    });

    const search = container.querySelector('#bl-search');
    search.addEventListener('input', () => {
      _query = search.value.trim();
      _renderList(container);
    });

    _query = '';
    _renderList(container);
  }

  return { render };
})();
