/**
 * PlannerView — Intent-intercept process recorder.
 *
 * Phases: idle → capturing → parameterize → done
 *
 * The browser opens in a Playwright window. Each user interaction is
 * captured as a pending intent (with screenshot). The user confirms or
 * discards each intent. After all steps are captured, a parameterization
 * pass lets the user swap literal values for {{ template }} variables.
 * Finally, YAML steps are generated and displayed for copying.
 */
const PlannerView = (() => {
  let _sessionId  = null;
  let _pollTimer  = null;
  let _container  = null;
  let _phase      = 'idle'; // idle | capturing | parameterize | done

  // ── Entry point ─────────────────────────────────────────────────────────────

  async function render(container) {
    _stop();
    _container  = container;
    _phase      = 'idle';
    _sessionId  = null;
    _renderIdle();
  }

  function _stop() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  }

  // ── Phase: idle ─────────────────────────────────────────────────────────────

  function _renderIdle() {
    _container.innerHTML = `
      <div class="view planner-view">
        <div class="view-header">
          <h2>Process Planner</h2>
          <p class="text-muted">
            Open an automation browser, navigate to any page, then interact
            naturally. Each action is captured as a YAML step — without
            executing it.
          </p>
        </div>
        <div class="planner-start-area">
          <button class="btn btn-primary btn-lg" id="planner-start">
            Start Planning Session
          </button>
          <div class="planner-start-hint text-muted">
            A Chromium window will open. Every click, text entry, and form
            selection is intercepted and shown here for review.
          </div>
        </div>
      </div>
    `;
    _container.querySelector('#planner-start').addEventListener('click', _startSession);
  }

  // ── Phase: capturing ─────────────────────────────────────────────────────────

  async function _startSession() {
    const btn = _container.querySelector('#planner-start');
    btn.textContent = 'Opening browser…';
    btn.disabled = true;

    const result = await api.startPlannerSession();
    if (!result.ok) {
      btn.textContent = 'Start Planning Session';
      btn.disabled = false;
      alert('Failed to start session: ' + (result.error || 'unknown error'));
      return;
    }
    _sessionId = result.session_id;
    _phase = 'capturing';
    _renderCapturing([], null);
    _pollTimer = setInterval(_poll, 2000);
  }

  async function _poll() {
    if (!_sessionId || _phase !== 'capturing') return;
    try {
      const state = await api.getPlannerState(_sessionId);
      if (!state.ok) return;
      _renderCapturing(state.intents || [], state.pending || null);
    } catch (_) {}
  }

  function _renderCapturing(intents, pending) {
    _container.innerHTML = `
      <div class="view planner-view">
        <div class="planner-cap-header">
          <div>
            <h2 style="margin:0 0 2px">Process Planner</h2>
            <span class="run-indicator running" style="font-size:12px">● RECORDING</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center">
            <button class="btn btn-sm btn-secondary" id="planner-manual-btn">+ Manual Step</button>
            <button class="btn btn-success" id="planner-finish"
              ${intents.length === 0 ? 'disabled' : ''}>
              Finish &amp; Parameterize
              <span class="planner-step-count">(${intents.length})</span>
            </button>
            <button class="btn btn-sm btn-danger" id="planner-cancel">Cancel</button>
          </div>
        </div>

        <div class="planner-instructions text-muted">
          Interact with the browser window. Each action appears below — confirm
          or discard before the next one is captured.
        </div>

        <div id="planner-pending-area">
          ${pending ? _pendingCardHtml(pending) : ''}
        </div>

        <div id="planner-confirmed-list">
          ${intents.length
            ? intents.map((intent, idx) => _confirmedRowHtml(intent, idx)).join('')
            : '<div class="planner-empty text-muted">No steps confirmed yet — interact with the browser.</div>'
          }
        </div>

        <div id="planner-manual-form" class="planner-manual-form hidden"></div>
      </div>
    `;

    // Wire pending card
    if (pending) {
      const capIdx = pending.capture_index;
      _container.querySelector('#planner-confirm')?.addEventListener('click', async () => {
        await api.confirmPlannerIntent(_sessionId, capIdx);
      });
      _container.querySelector('#planner-discard')?.addEventListener('click', async () => {
        await api.discardPlannerIntent(_sessionId, capIdx);
      });
      if (pending.screenshot_path) {
        api.getScreenshot(pending.screenshot_path).then(r => {
          const img = _container.querySelector('#planner-pending-shot');
          if (img && r && r.b64) img.src = 'data:image/png;base64,' + r.b64;
        }).catch(() => {});
      }
    }

    _container.querySelector('#planner-finish')?.addEventListener('click', _openParamPass);
    _container.querySelector('#planner-cancel')?.addEventListener('click', _cancelSession);
    _container.querySelector('#planner-manual-btn')?.addEventListener('click', _showManualForm);
  }

  function _pendingCardHtml(intent) {
    const hasShot = !!intent.screenshot_path;
    return `
      <div class="planner-pending-card">
        <div class="planner-card-badge">Captured — confirm or discard</div>
        <div class="planner-intent-grid">
          <span class="planner-label">Action</span>
          <span class="planner-evt-badge planner-evt-${_esc(intent.event_type)}">${_esc(intent.event_type)}</span>
          <span class="planner-label">Selector</span>
          <code class="planner-selector">${_esc(intent.selector || '')}</code>
          ${intent.text_content ? `<span class="planner-label">Text</span>
          <span>"${_esc(intent.text_content)}"</span>` : ''}
          ${intent.value ? `<span class="planner-label">Value</span>
          <span>"${_esc(intent.value)}"</span>` : ''}
        </div>
        ${hasShot
          ? `<div class="planner-shot-wrap">
               <img id="planner-pending-shot" class="planner-screenshot" src="" alt="screenshot" />
             </div>`
          : ''}
        <div class="planner-card-actions">
          <button class="btn btn-success btn-sm" id="planner-confirm">✓ Confirm</button>
          <button class="btn btn-secondary btn-sm" id="planner-discard">✗ Discard</button>
        </div>
      </div>
    `;
  }

  function _confirmedRowHtml(intent, idx) {
    const hasShot = !!intent.screenshot_path;
    return `
      <div class="planner-confirmed-row">
        <span class="planner-row-num">${idx + 1}</span>
        <span class="planner-evt-badge planner-evt-${_esc(intent.event_type)}">${_esc(intent.event_type)}</span>
        <code class="planner-selector-sm">${_esc(intent.selector || '')}</code>
        ${intent.value ? `<span class="planner-value-sm">"${_esc(intent.value)}"</span>` : ''}
        ${hasShot ? '<span class="planner-has-shot" title="Has screenshot">⬜</span>' : ''}
      </div>
    `;
  }

  function _showManualForm() {
    const formEl = _container.querySelector('#planner-manual-form');
    formEl.classList.remove('hidden');
    formEl.innerHTML = `
      <div class="planner-manual-inner">
        <span class="planner-label" style="font-size:12px">Action</span>
        <select id="manual-event-type" class="planner-manual-select">
          <option value="click">click</option>
          <option value="type">type</option>
          <option value="select">select</option>
          <option value="submit">submit</option>
        </select>
        <span class="planner-label" style="font-size:12px;margin-left:8px">Selector</span>
        <input id="manual-selector" class="planner-manual-input" type="text" placeholder="#my-button" />
        <span class="planner-label" style="font-size:12px;margin-left:8px">Value</span>
        <input id="manual-value" class="planner-manual-input" type="text"
               placeholder="(for type/select)" style="width:140px" />
        <button class="btn btn-sm btn-primary" id="manual-add" style="margin-left:8px">Add</button>
        <button class="btn btn-sm btn-secondary" id="manual-cancel-btn" style="margin-left:4px">Cancel</button>
      </div>
    `;
    formEl.querySelector('#manual-add').addEventListener('click', async () => {
      const evtType  = formEl.querySelector('#manual-event-type').value;
      const selector = formEl.querySelector('#manual-selector').value.trim();
      const value    = formEl.querySelector('#manual-value').value.trim();
      if (!selector) { alert('Selector is required'); return; }
      await api.addManualPlannerIntent(_sessionId, {
        event_type: evtType, selector, value: value || null,
        tag: '', text_content: '', aria_label: null,
        placeholder: null, input_type: null,
      });
      formEl.classList.add('hidden');
    });
    formEl.querySelector('#manual-cancel-btn').addEventListener('click', () => {
      formEl.classList.add('hidden');
    });
  }

  async function _cancelSession() {
    _stop();
    if (_sessionId) {
      await api.cancelPlannerSession(_sessionId).catch(() => {});
      _sessionId = null;
    }
    _phase = 'idle';
    _renderIdle();
  }

  // ── Phase: parameterize ──────────────────────────────────────────────────────

  function _openParamPass() {
    _stop();
    _phase = 'parameterize';
    api.getPlannerState(_sessionId).then(state => {
      _renderParamPass(state.intents || []);
    });
  }

  function _renderParamPass(intents) {
    _container.innerHTML = `
      <div class="view planner-view">
        <div class="view-header">
          <h2>Review &amp; Parameterize</h2>
          <p class="text-muted">
            Replace literal values with <code>{{ template }}</code> variables
            where the flow should substitute profile or context data at runtime.
          </p>
        </div>
        ${intents.length === 0
          ? '<div class="planner-empty text-muted">No steps captured.</div>'
          : `<div id="planner-param-list">
               ${intents.map((intent, idx) => _paramCardHtml(intent, idx)).join('')}
             </div>`
        }
        <div class="planner-actions">
          <button class="btn btn-primary" id="planner-generate">Generate YAML</button>
          <button class="btn btn-secondary" id="planner-back" style="margin-left:8px">← Back</button>
        </div>
      </div>
    `;

    // Load screenshots asynchronously
    intents.forEach((intent, idx) => {
      if (intent.screenshot_path) {
        api.getScreenshot(intent.screenshot_path).then(r => {
          const img = document.getElementById(`planner-shot-${idx}`);
          if (img && r && r.b64) img.src = 'data:image/png;base64,' + r.b64;
        }).catch(() => {});
      }
    });

    // Wire radio toggles: show/hide template input
    _container.querySelectorAll('.planner-param-card').forEach((card, idx) => {
      card.querySelectorAll(`input[name="param-${idx}"]`).forEach(radio => {
        radio.addEventListener('change', () => {
          const tplInput = document.getElementById(`planner-tpl-${idx}`);
          if (tplInput) {
            tplInput.style.display = (radio.value === 'template') ? 'inline-block' : 'none';
          }
        });
      });
    });

    _container.querySelector('#planner-generate')?.addEventListener('click',
      () => _generateYaml(intents));
    _container.querySelector('#planner-back')?.addEventListener('click', () => {
      _phase = 'capturing';
      _renderCapturing(intents, null);
      _pollTimer = setInterval(_poll, 2000);
    });
  }

  function _paramCardHtml(intent, idx) {
    const canParam = (intent.event_type === 'type' || intent.event_type === 'select')
                     && intent.value;
    const hasShot  = !!intent.screenshot_path;
    return `
      <div class="planner-param-card" data-idx="${idx}">
        <div class="planner-param-header">
          <span class="planner-row-num">${idx + 1}</span>
          <span class="planner-evt-badge planner-evt-${_esc(intent.event_type)}">${_esc(intent.event_type)}</span>
          <code class="planner-selector-sm">${_esc(intent.selector || '')}</code>
        </div>
        ${hasShot
          ? `<div class="planner-shot-wrap-sm">
               <img id="planner-shot-${idx}" class="planner-screenshot-sm" src="" alt="" />
             </div>`
          : ''}
        ${canParam ? `
        <div class="planner-param-value-row">
          <span class="planner-label">Value</span>
          <label class="planner-radio-lbl">
            <input type="radio" name="param-${idx}" value="literal" checked />
            Literal — <code class="planner-lit-val">"${_esc(intent.value)}"</code>
          </label>
          <label class="planner-radio-lbl" style="margin-top:4px">
            <input type="radio" name="param-${idx}" value="template" />
            Template —
            <input type="text" id="planner-tpl-${idx}" class="planner-tpl-input"
                   value="{{ ${_templateGuess(intent)} }}" style="display:none" />
          </label>
        </div>
        ` : intent.value ? `
        <div class="planner-param-value-row">
          <span class="planner-label">Value</span>
          <code class="planner-lit-val">"${_esc(intent.value)}"</code>
        </div>
        ` : ''}
      </div>
    `;
  }

  function _templateGuess(intent) {
    const val = (intent.value || '').toLowerCase();
    const ph  = (intent.placeholder || '').toLowerCase();
    if (ph.includes('first') || val.includes('first')) return 'profile.first_name';
    if (ph.includes('last')  || val.includes('last'))  return 'profile.last_name';
    if (ph.includes('email') || val.includes('@'))      return 'profile.email';
    if (ph.includes('phone') || ph.includes('tel'))    return 'profile.phone';
    if (ph.includes('address'))                        return 'profile.address';
    return 'profile.field_name';
  }

  // ── Phase: done ─────────────────────────────────────────────────────────────

  async function _generateYaml(intents) {
    const parameterized = intents.map((intent, idx) => {
      const result = Object.assign({}, intent);
      const radioEl = _container.querySelector(
        `input[name="param-${idx}"]:checked`);
      if (radioEl && radioEl.value === 'template') {
        const tplInput = document.getElementById(`planner-tpl-${idx}`);
        if (tplInput) result.value = tplInput.value;
      }
      return result;
    });

    const r = await api.finishPlannerSession(_sessionId, parameterized);
    if (!r.ok) {
      alert('Failed to generate YAML: ' + (r.error || 'unknown error'));
      return;
    }
    _sessionId = null;
    _phase = 'done';
    _renderDone(r.yaml, r.steps);
  }

  function _renderDone(yaml, steps) {
    _container.innerHTML = `
      <div class="view planner-view">
        <div class="view-header">
          <h2>Generated YAML</h2>
          <p class="text-muted">
            ${steps.length} step${steps.length !== 1 ? 's' : ''} generated.
            Copy and paste into your flow YAML file.
          </p>
        </div>
        <pre class="planner-yaml-output">${_esc(yaml)}</pre>
        <div class="planner-actions">
          <button class="btn btn-secondary" id="planner-copy">Copy to Clipboard</button>
          <button class="btn btn-primary" id="planner-new" style="margin-left:8px">New Session</button>
        </div>
      </div>
    `;

    const copyBtn = _container.querySelector('#planner-copy');
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(yaml).then(() => {
        copyBtn.textContent = 'Copied!';
        setTimeout(() => { copyBtn.textContent = 'Copy to Clipboard'; }, 1500);
      }).catch(() => {});
    });

    _container.querySelector('#planner-new').addEventListener('click', () => {
      _phase = 'idle';
      _renderIdle();
    });
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function _esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return { render, stop: _stop };
})();
