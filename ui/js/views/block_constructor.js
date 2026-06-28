/**
 * BlockConstructor — contract-first block authoring.
 *
 * Screen 1: Define id, name, input schema, output schema.
 * Screen 2: Implementation placeholder (steps added via YAML / Phase J planner).
 *
 * Usage: BlockConstructor.open(container, { onDone })
 */
const BlockConstructor = (() => {
  let _container = null;
  let _onDone    = null;
  let _inputs    = [];
  let _outputs   = [];
  let _meta      = { id: '', name: '', description: '' };

  const TYPES = ['str', 'bool', 'int', 'float', 'dict', 'list', 'any'];

  function _esc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Screen 1 helpers ────────────────────────────────────────────────────────

  function _fieldRowHTML(f, schema, idx) {
    return `<div class="bc-field-row">
      <span class="bc-field-name">${_esc(f.name)}</span>
      <span class="bc-field-type">${_esc(f.type)}</span>
      <span class="bc-field-req">${f.required ? 'req' : 'opt'}</span>
      <button class="bc-field-remove" data-schema="${schema}" data-idx="${idx}">×</button>
    </div>`;
  }

  function _schemaHTML(schema, fields) {
    const isEmpty = !fields.length;
    return `<div class="bc-schema-panel" data-schema="${schema}">
      <div class="bc-schema-header">${schema.toUpperCase()} SCHEMA</div>
      <div class="bc-fields-list" id="bc-${schema}-fields">
        ${isEmpty
          ? '<div class="bc-fields-empty">No fields yet.</div>'
          : fields.map((f, i) => _fieldRowHTML(f, schema, i)).join('')}
      </div>
      <button class="bc-add-btn" data-schema="${schema}">+ Add field</button>
    </div>`;
  }

  function _renderScreen1() {
    const canContinue = _inputs.length > 0 && _outputs.length > 0;
    _container.innerHTML = `
      <div class="view bc-view">
        <div class="bc-header">
          <span class="bc-back" id="bc-back1">← Blocks</span>
          <h2 class="bc-title">New Block</h2>
        </div>
        <div class="bc-meta-row">
          <input class="bc-meta-input" id="bc-id"   placeholder="block_id (lowercase)"
            type="text" autocomplete="off" value="${_esc(_meta.id)}" />
          <input class="bc-meta-input" id="bc-name" placeholder="Block Name"
            type="text" autocomplete="off" value="${_esc(_meta.name)}" />
          <input class="bc-meta-input bc-meta-desc" id="bc-desc" placeholder="Description (optional)"
            type="text" autocomplete="off" value="${_esc(_meta.description)}" />
        </div>
        <div class="bc-schemas">
          ${_schemaHTML('input', _inputs)}
          ${_schemaHTML('output', _outputs)}
        </div>
        <div class="bc-footer">
          <button class="btn btn-primary" id="bc-continue" ${canContinue ? '' : 'disabled'}>
            Continue to Implementation →
          </button>
          ${!canContinue
            ? '<span class="bc-footer-hint">Add at least one input and one output field to continue.</span>'
            : ''}
        </div>
      </div>`;

    _container.querySelector('#bc-back1').addEventListener('click', () => {
      if (_onDone) _onDone();
    });

    _container.querySelectorAll('.bc-add-btn').forEach(btn =>
      btn.addEventListener('click', () => _showAddForm(btn.dataset.schema))
    );

    _container.querySelectorAll('.bc-field-remove').forEach(btn =>
      btn.addEventListener('click', () => {
        _saveMeta();
        const { schema, idx } = btn.dataset;
        if (schema === 'input') _inputs.splice(+idx, 1);
        else                    _outputs.splice(+idx, 1);
        _renderScreen1();
      })
    );

    _container.querySelector('#bc-continue').addEventListener('click', () => {
      _saveMeta();
      _renderScreen2();
    });

    ['#bc-id', '#bc-name', '#bc-desc'].forEach(sel => {
      const el = _container.querySelector(sel);
      if (el) el.addEventListener('input', _saveMeta);
    });
  }

  function _saveMeta() {
    _meta.id          = (_container.querySelector('#bc-id')?.value   || '').trim();
    _meta.name        = (_container.querySelector('#bc-name')?.value  || '').trim();
    _meta.description = (_container.querySelector('#bc-desc')?.value  || '').trim();
  }

  function _showAddForm(schema) {
    const panel = _container.querySelector(`.bc-schema-panel[data-schema="${schema}"]`);
    if (panel.querySelector('.bc-add-form')) return;
    const addBtn = panel.querySelector('.bc-add-btn');
    addBtn.style.display = 'none';

    const form = document.createElement('div');
    form.className = 'bc-add-form';
    form.innerHTML = `
      <input class="bc-add-name" placeholder="field_name" type="text" autocomplete="off" />
      <select class="bc-add-type">
        ${TYPES.map(t => `<option value="${t}">${t}</option>`).join('')}
      </select>
      <label class="bc-add-req-label">
        <input type="checkbox" class="bc-add-req-check" checked />
        req
      </label>
      <button class="bc-add-confirm">Add</button>
      <button class="bc-add-cancel">Cancel</button>`;
    panel.insertBefore(form, addBtn);
    form.querySelector('.bc-add-name').focus();

    form.querySelector('.bc-add-confirm').addEventListener('click', () => {
      const fieldName = form.querySelector('.bc-add-name').value.trim();
      if (!fieldName) { form.querySelector('.bc-add-name').focus(); return; }
      const type     = form.querySelector('.bc-add-type').value;
      const required = form.querySelector('.bc-add-req-check').checked;
      _saveMeta();
      if (schema === 'input') _inputs.push({ name: fieldName, type, required });
      else                    _outputs.push({ name: fieldName, type, required });
      _renderScreen1();
    });

    form.querySelector('.bc-add-cancel').addEventListener('click', () => {
      _saveMeta();
      _renderScreen1();
    });

    form.querySelector('.bc-add-name').addEventListener('keydown', e => {
      if (e.key === 'Enter') form.querySelector('.bc-add-confirm').click();
      if (e.key === 'Escape') form.querySelector('.bc-add-cancel').click();
    });
  }

  // ── Screen 2 ────────────────────────────────────────────────────────────────

  function _schemaTag(f) {
    return `<span class="bc-summary-tag">${_esc(f.name)}<em> ${_esc(f.type)}</em>${f.required ? '' : '<span class="bc-summary-opt"> opt</span>'}</span>`;
  }

  function _renderScreen2() {
    _container.innerHTML = `
      <div class="view bc-view">
        <div class="bc-header">
          <span class="bc-back" id="bc-back2">← Contract</span>
          <h2 class="bc-title">${_esc(_meta.name || _meta.id || 'New Block')} — Implementation</h2>
        </div>
        <div class="bc-contract-summary">
          <div class="bc-summary-row">
            <span class="bc-summary-label">Inputs</span>
            <span>${_inputs.map(_schemaTag).join('')}</span>
          </div>
          <div class="bc-summary-row">
            <span class="bc-summary-label">Outputs</span>
            <span>${_outputs.map(_schemaTag).join('')}</span>
          </div>
        </div>
        <div class="bc-impl-placeholder">
          <div class="bc-impl-icon">⧉</div>
          <div class="bc-impl-msg">No steps yet.</div>
          <div class="bc-impl-hint">
            After saving, add steps by editing<br>
            <code>sources/blocks/${_esc(_meta.id || 'your_block')}.yaml</code><br>
            or use the Process Planner when available (Phase J).
          </div>
        </div>
        <div class="bc-footer">
          <button class="btn btn-primary" id="bc-save-btn">Save Block</button>
          <span class="bc-save-msg" id="bc-save-msg" style="display:none"></span>
        </div>
      </div>`;

    _container.querySelector('#bc-back2').addEventListener('click', () => _renderScreen1());

    _container.querySelector('#bc-save-btn').addEventListener('click', async () => {
      const btn = _container.querySelector('#bc-save-btn');
      const msg = _container.querySelector('#bc-save-msg');
      btn.disabled = true;
      btn.textContent = 'Saving…';
      try {
        const result = await api.saveBlock({
          id:            _meta.id,
          name:          _meta.name,
          description:   _meta.description,
          input_schema:  _inputs,
          output_schema: _outputs,
        });
        if (result && result.ok) {
          msg.style.display  = '';
          msg.style.color    = 'var(--success)';
          msg.textContent    = `Saved as ${result.block_id}.yaml`;
          setTimeout(() => { if (_onDone) _onDone(); }, 900);
        } else {
          msg.style.display  = '';
          msg.style.color    = 'var(--danger)';
          msg.textContent    = result?.error || 'Save failed.';
          btn.disabled       = false;
          btn.textContent    = 'Save Block';
        }
      } catch (e) {
        msg.style.display  = '';
        msg.style.color    = 'var(--danger)';
        msg.textContent    = e.message || 'Unexpected error.';
        btn.disabled       = false;
        btn.textContent    = 'Save Block';
      }
    });
  }

  // ── Public ──────────────────────────────────────────────────────────────────

  function open(container, { onDone } = {}) {
    _container = container;
    _onDone    = onDone;
    _inputs    = [];
    _outputs   = [];
    _meta      = { id: '', name: '', description: '' };
    _renderScreen1();
  }

  return { open };
})();
