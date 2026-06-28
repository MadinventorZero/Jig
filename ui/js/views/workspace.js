/**
 * WorkspaceView — three-mode (Editor / Run / History) workspace for a single flow.
 *
 * render(container, { flowId, runId?, onBack })
 *   flowId  — YAML flow ID to display
 *   runId   — if provided, opens Run mode (live) or History mode (completed)
 *   onBack  — callback to return to the flows list
 */
const WorkspaceView = (() => {
  let _el              = null;
  let _flow            = null;
  let _mode            = 'editor';
  let _runId           = null;
  let _stepStats       = {};     // step_id → 'idle'|'running'|'completed'|'failed'|'skipped'
  let _activeStep      = null;
  let _branchCollapsed = {};     // step_id → bool (true = collapsed)

  async function render(container, { flowId, runId, onBack }) {
    _el              = container;
    _mode            = runId ? 'run' : 'editor';
    _runId           = runId || null;
    _stepStats       = {};
    _activeStep      = null;
    _branchCollapsed = {};
    LiveRunView.stop();

    try {
      _flow = await api.getFlow(flowId);
    } catch (e) {
      container.innerHTML = `<div class="view"><p style="color:var(--danger)">Failed to load flow: ${_esc(e.message)}</p></div>`;
      return;
    }

    _renderShell(onBack);

    if (_runId) {
      // Fetch existing run to determine starting mode
      const run = await api.getRun(_runId).catch(() => null);
      if (run && run.status !== 'running') {
        const evs = await api.getRunEvents(_runId).catch(() => []);
        _applyEvents(evs);
        _refreshStepList();
        _mode = 'history';
        _updateTabs();
      }
      _renderRight();
    }
  }

  // ── Shell ───────────────────────────────────────────────────────────────────

  function _renderShell(onBack) {
    const steps = _flow.steps || [];
    _el.innerHTML = `
      <div class="workspace">
        <div class="workspace-header">
          <span class="workspace-back" id="ws-back">← Flows</span>
          <span class="workspace-title">${_esc(_flow.name)}</span>
          <div class="mode-tabs">
            <span class="mode-tab ${_mode === 'editor'  ? 'active' : ''}" data-mode="editor">Editor</span>
            <span class="mode-tab ${_mode === 'run'     ? 'active' : ''}" data-mode="run">Run <span class="run-dot">●</span></span>
            <span class="mode-tab ${_mode === 'history' ? 'active' : ''}" data-mode="history">History</span>
          </div>
        </div>
        <div class="workspace-body">
          <div id="ws-steps" class="step-list">
            <div class="step-list-label">Steps</div>
            ${steps.map(s => StepCard.render(s, 'idle')).join('')}
          </div>
          <div id="ws-right" class="right-panel">
            <p style="color:var(--muted)">Select a step or switch modes.</p>
          </div>
        </div>
      </div>`;

    // Back
    _el.querySelector('#ws-back').addEventListener('click', () => {
      LiveRunView.stop();
      if (onBack) onBack(); else App.navigate('flows');
    });

    // Mode tabs
    _el.querySelectorAll('.mode-tab').forEach(t =>
      t.addEventListener('click', () => {
        _mode = t.dataset.mode;
        _updateTabs();
        _renderRight();
      })
    );

    // Step click
    _bindStepClicks();
    _renderRight();
    // Update step list with compat connectors once contracts load (fire-and-forget)
    _refreshStepList();
  }

  function _bindStepClicks() {
    const listEl = _el.querySelector('#ws-steps');
    if (!listEl) return;
    listEl.addEventListener('click', e => {
      // Branch toggle — must check before card click
      const toggle = e.target.closest('.sc-toggle');
      if (toggle) {
        e.stopPropagation();
        const sid = toggle.dataset.stepId;
        _branchCollapsed[sid] = !(_branchCollapsed[sid] === false);
        _refreshStepList();
        return;
      }
      const card = e.target.closest('.step-card');
      if (!card) return;
      _activeStep = card.dataset.stepId;
      _refreshStepList();
      _renderRight();
    });
  }

  function _updateTabs() {
    _el.querySelectorAll('.mode-tab').forEach(t =>
      t.classList.toggle('active', t.dataset.mode === _mode)
    );
  }

  function _computeCompat(steps, contracts) {
    const ctx = new Set();
    const result = {};
    for (const step of steps) {
      const c = contracts[step.type];
      if (c && c.input_schema && c.input_schema.length) {
        const req = c.input_schema.filter(f => f.required);
        const opt = c.input_schema.filter(f => !f.required);
        if (req.some(f => !ctx.has(f.name)))      result[step.step_id] = 'red';
        else if (opt.some(f => !ctx.has(f.name))) result[step.step_id] = 'yellow';
        else                                        result[step.step_id] = 'green';
      } else {
        result[step.step_id] = 'none';
      }
      if (c && c.output_schema) c.output_schema.forEach(f => ctx.add(f.name));
    }
    return result;
  }

  async function _refreshStepList() {
    const steps = _flow.steps || [];
    const el    = _el.querySelector('#ws-steps');
    if (!el) return;
    let compatMap = {};
    if (_mode === 'editor') {
      const contracts = await _getContracts();
      compatMap = _computeCompat(steps, contracts);
    }
    el.innerHTML = '<div class="step-list-label">Steps</div>'
      + steps.map((s, i) => {
          const compat     = compatMap[s.step_id] || 'none';
          const connector  = i > 0 ? StepCard.renderConnector(compat) : '';
          const collapsed  = _branchCollapsed[s.step_id] !== false;
          return connector
            + StepCard.render(s, _stepStats[s.step_id] || 'idle', s.step_id === _activeStep, collapsed)
            + StepCard.renderBranches(s, collapsed);
        }).join('');
    _bindStepClicks();
  }

  function _applyEvents(events) {
    for (const ev of events) {
      if (!ev.step_id) continue;
      if (ev.event === 'step.started')   _stepStats[ev.step_id] = 'running';
      if (ev.event === 'step.completed') _stepStats[ev.step_id] = 'completed';
      if (ev.event === 'step.failed')    _stepStats[ev.step_id] = 'failed';
      if (ev.event === 'step.skipped')   _stepStats[ev.step_id] = 'skipped';
      if (ev.event === 'step.warning')   _stepStats[ev.step_id] = 'warning';
    }
  }

  // ── Right panel dispatcher ─────────────────────────────────────────────────

  function _renderRight() {
    const el = _el.querySelector('#ws-right');
    if (!el) return;

    if (_mode === 'run' && _runId) {
      LiveRunView.render(el, {
        runId: _runId,
        onStatusChange: async () => {
          const evs = await api.getRunEvents(_runId).catch(() => []);
          _applyEvents(evs);
          _refreshStepList();
        },
      });
      return;
    }

    if (_mode === 'history') {
      if (_activeStep && _runId) {
        const step = (_flow.steps || []).find(s => s.step_id === _activeStep);
        if (step) {
          RightPanel.render(el, {
            step,
            runId:  _runId,
            status: _stepStats[step.step_id] || 'idle',
            onBack: () => { _activeStep = null; _renderHistory(el); },
          });
          return;
        }
      }
      _renderHistory(el);
      return;
    }

    // Editor mode
    if (_activeStep) {
      const step = (_flow.steps || []).find(s => s.step_id === _activeStep);
      if (step) { _renderStepDetail(el, step); return; }  // async, intentionally not awaited
    }
    el.innerHTML = `<p style="color:var(--muted)">Click a step to see its configuration.</p>`;
  }

  // ── Editor: step detail ────────────────────────────────────────────────────

  // Cache contracts for the session so we don't re-fetch on every step click
  let _contractsCache = null;

  async function _getContracts() {
    if (_contractsCache) return _contractsCache;
    try { _contractsCache = await api.getActionContracts(); } catch (_) { _contractsCache = {}; }
    return _contractsCache;
  }

  async function _renderStepDetail(el, step) {
    const hasParams = step.params && Object.keys(step.params).length > 0;
    const hasBranch = step.on_choice && Object.keys(step.on_choice).length > 0;
    const contracts = await _getContracts();
    const contract  = contracts[step.type] || null;
    const steps     = _flow.steps || [];

    // Build available template references from prior steps' output contracts
    const refs = [];
    for (const s of steps) {
      if (s.step_id === step.step_id) break;
      const c = contracts[s.type];
      if (c && c.output_schema) {
        for (const f of c.output_schema) {
          refs.push(`{{ steps.${s.step_id}.result.${f.name} }}`);
        }
      }
    }

    function _schemaTable(fields, label) {
      if (!fields || !fields.length) return '';
      return `<div class="detail-section">
        <div class="detail-label">${label}</div>
        <table style="width:100%;font-size:11px;border-collapse:collapse">
          <thead><tr style="opacity:0.5">
            <th style="text-align:left;padding:2px 6px 2px 0">field</th>
            <th style="text-align:left;padding:2px 6px 2px 0">type</th>
            <th style="text-align:left;padding:2px 0">req</th>
          </tr></thead>
          <tbody>${fields.map(f => `
            <tr>
              <td style="font-family:monospace;padding:2px 6px 2px 0">${_esc(f.name)}</td>
              <td style="color:var(--muted);padding:2px 6px 2px 0">${_esc(f.type)}</td>
              <td style="padding:2px 0">${f.required ? '●' : '<span style="opacity:0.35">○</span>'}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    }

    function _paramRows(params) {
      if (!params || !Object.keys(params).length) return '';
      const rows = Object.entries(params).map(([k, v]) => {
        const val = String(v ?? '');
        const isTemplate = val.includes('{{') || val === '';
        const suggestBtn = isTemplate && refs.length
          ? `<div class="ps-wrap">
               <button class="ps-btn" data-key="${_esc(k)}" title="Available references">{ }</button>
               <div class="ps-list hidden">
                 ${refs.map(r => `<div class="ps-item" data-ref="${_esc(r)}">${_esc(r)}</div>`).join('')}
               </div>
             </div>`
          : '';
        return `<tr>
          <td class="prow-key">${_esc(k)}</td>
          <td class="prow-val">${_esc(val) || '<span style="opacity:0.35">—</span>'}</td>
          <td style="vertical-align:top;padding-top:2px">${suggestBtn}</td>
        </tr>`;
      }).join('');
      return `<div class="detail-section">
        <div class="detail-label">Params</div>
        <table style="width:100%;font-size:12px;border-collapse:collapse" class="param-table">
          ${rows}
        </table>
      </div>`;
    }

    el.innerHTML = `
      <div class="detail-section">
        <div class="detail-label">Step</div>
        <div class="detail-value" style="font-weight:600">${_esc(step.step_id)}</div>
      </div>
      <div class="detail-section">
        <div class="detail-label">Type</div>
        <div class="detail-value" style="font-family:monospace">${_esc(step.type)}</div>
      </div>
      ${contract ? _schemaTable(contract.output_schema, 'Produces (output contract)') : ''}
      ${contract ? _schemaTable(contract.input_schema,  'Requires (input contract)')  : ''}
      ${_paramRows(step.params)}
      ${hasBranch ? `<div class="detail-section">
        <div class="detail-label">Branches (on_choice)</div>
        <pre class="detail-pre">${_esc(JSON.stringify(step.on_choice, null, 2))}</pre>
      </div>` : ''}
      ${step.on_timeout ? `<div class="detail-section">
        <div class="detail-label">On Timeout</div>
        <div class="detail-value" style="font-family:monospace">${_esc(step.on_timeout)}</div>
      </div>` : ''}
      ${step.on_error ? `<div class="detail-section">
        <div class="detail-label">On Error</div>
        <div class="detail-value" style="font-family:monospace">${_esc(step.on_error)}</div>
      </div>` : ''}`;

    // Wire suggestion dropdowns
    el.querySelectorAll('.ps-btn').forEach(btn => {
      const list = btn.nextElementSibling;
      btn.addEventListener('click', e => {
        e.stopPropagation();
        el.querySelectorAll('.ps-list').forEach(l => { if (l !== list) l.classList.add('hidden'); });
        list.classList.toggle('hidden');
      });
    });
    el.querySelectorAll('.ps-item').forEach(item => {
      item.addEventListener('click', () => {
        navigator.clipboard.writeText(item.dataset.ref).catch(() => {});
        item.textContent = '✓ copied';
        setTimeout(() => { item.textContent = item.dataset.ref; }, 1200);
        item.closest('.ps-list').classList.add('hidden');
      });
    });
    // Close dropdowns on outside click
    document.addEventListener('click', function _close() {
      el.querySelectorAll('.ps-list').forEach(l => l.classList.add('hidden'));
      document.removeEventListener('click', _close);
    });
  }

  // ── History: run details ───────────────────────────────────────────────────

  async function _renderHistory(el) {
    if (!_runId) {
      el.innerHTML = `<p style="color:var(--muted)">No run selected — use <em>Run Now</em> from the Flows list.</p>`;
      return;
    }
    el.innerHTML = `<p style="color:var(--muted)">Loading…</p>`;
    try {
      const [run, decisions, failures] = await Promise.all([
        api.getRun(_runId),
        api.getRunDecisions(_runId),
        api.getRunFailures(_runId),
      ]);

      el.innerHTML = `
        <div class="detail-section" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div>
            <div class="detail-label">Status</div>
            <span class="rs-badge rs-${_esc(run.status || '')}">${_esc(run.status || '—')}</span>
          </div>
          <div>
            <div class="detail-label">Steps</div>
            <div class="detail-value">${run.steps_completed || 0} done · ${run.steps_failed || 0} failed</div>
          </div>
        </div>
        <div class="detail-section">
          <div class="detail-label">Started</div>
          <div class="detail-value">${_esc((run.started_at || '—').replace('T', ' ').slice(0, 19))}</div>
        </div>
        <div class="detail-section">
          <div class="detail-label">Run ID</div>
          <div class="detail-value" style="font-family:monospace;font-size:11px;word-break:break-all">${_esc(_runId)}</div>
        </div>

        ${decisions.length > 0 ? `
          <div class="detail-section">
            <div class="detail-label">Decisions</div>
            <table style="width:100%;font-size:12px">
              <thead><tr><th>Step</th><th>Choice</th><th>Reasoning</th></tr></thead>
              <tbody>${decisions.map(d => `
                <tr>
                  <td style="font-family:monospace">${_esc(d.step_id)}</td>
                  <td><strong>${_esc(d.choice)}</strong></td>
                  <td style="color:var(--muted)">${_esc((d.reasoning || '').slice(0, 80))}</td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>` : ''}

        ${failures.length > 0 ? `
          <div class="detail-section">
            <div class="detail-label">Failures</div>
            <table style="width:100%;font-size:12px">
              <thead><tr><th>Step</th><th>Reason</th></tr></thead>
              <tbody>${failures.map(f => `
                <tr>
                  <td style="font-family:monospace">${_esc(f.step_id || '—')}</td>
                  <td style="color:var(--danger)">${_esc((f.failure_reason || f.message || '—').slice(0, 140))}</td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>` : ''}

        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
          <button class="btn btn-sm btn-secondary" id="ws-btn-tree">Decision Tree</button>
          <button class="btn btn-sm btn-secondary" id="ws-btn-log">Full Log</button>
        </div>`;

      el.querySelector('#ws-btn-tree').addEventListener('click', () =>
        TreeView.render(el, { flowId: _flow.id, runId: _runId })
      );
      el.querySelector('#ws-btn-log').addEventListener('click', async () => {
        const evs = await api.getRunEvents(_runId).catch(() => []);
        _renderFullLog(el, evs);
      });
    } catch (e) {
      el.innerHTML = `<p style="color:var(--danger)">Failed to load run details: ${_esc(e.message)}</p>`;
    }
  }

  function _renderFullLog(el, events) {
    const lines = events.map(ev => {
      const ts  = (ev.ts || '').slice(11, 19);
      const lvl = ev.level || 'INFO';
      return `<div class="ll-line">`
        + `<span class="ll-ts">${ts}</span> `
        + `<span class="ll-lvl-${lvl}">[${lvl}]</span> `
        + `<span class="ll-msg">${_esc(ev.message || '')}</span></div>`;
    }).join('');
    el.innerHTML = `
      <button class="btn btn-sm btn-secondary" id="ws-log-back" style="margin-bottom:12px">← Back</button>
      <div class="live-log" style="max-height:520px">${lines}</div>`;
    el.querySelector('#ws-log-back').addEventListener('click', () => _renderHistory(el));
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { render };
})();
