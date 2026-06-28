/**
 * FlowsView — top-level view: lists all v3 YAML flows.
 *
 * Each flow row shows name, version, step count, last run status badge,
 * and Run Now / Validate / History buttons.
 * Opening a flow (Run Now or View in history) navigates into WorkspaceView.
 */
const FlowsView = (() => {
  let _el    = null;
  let _flows = [];

  async function render(container) {
    _el = container;
    _el.innerHTML = '<div class="view"><div class="loading">Loading flows…</div></div>';
    try {
      _flows = await api.listFlows();
      _renderList();
    } catch (e) {
      _el.innerHTML = `<div class="view"><p style="color:var(--danger)">Failed to load flows: ${_esc(e.message)}</p></div>`;
    }
  }

  // ── List rendering ─────────────────────────────────────────────────────────

  function _renderList() {
    if (!_flows.length) {
      _el.innerHTML = `
        <div class="view">
          <div class="view-header"><div class="view-title">Flows</div></div>
          <div class="card">
            <p style="color:var(--muted)">No YAML flows found in <code>sources/flows/</code>.</p>
          </div>
        </div>`;
      return;
    }

    _el.innerHTML = `
      <div class="view" style="max-width:900px">
        <div class="view-header">
          <div>
            <div class="view-title">Flows</div>
            <div class="view-subtitle">${_flows.length} flow${_flows.length !== 1 ? 's' : ''} available</div>
          </div>
        </div>
        <div id="fl-list">
          ${_flows.map(_flowHTML).join('')}
        </div>
      </div>`;

    _el.querySelector('#fl-list').addEventListener('click', e => _onClick(e));
  }

  function _flowHTML(f) {
    const badge = f.last_run_status
      ? `<span class="rs-badge rs-${_esc(f.last_run_status)}">${_esc(f.last_run_status)}</span>`
      : `<span style="color:var(--muted);font-size:12px">never run</span>`;
    const ago = f.last_run_at ? ' · Last run ' + _relTime(f.last_run_at) : '';
    return `
      <div class="flow-item" data-fid="${_esc(f.id)}">
        <div class="flow-item-header">
          <div>
            <div class="flow-item-name">${_esc(f.name || f.id)}</div>
            <div class="flow-item-meta">v${f.version || 1} · ${f.step_count || 0} steps${ago}</div>
          </div>
          <div class="flow-item-right">
            ${badge}
            <div class="flow-item-actions">
              <button class="btn btn-primary btn-sm fl-run">Run Now</button>
              <button class="btn btn-secondary btn-sm fl-debug">Debug</button>
              <button class="btn btn-secondary btn-sm fl-validate">Validate</button>
              <button class="btn btn-secondary btn-sm fl-history">History</button>
            </div>
          </div>
        </div>
        <div class="validate-msg" id="vm-${_esc(f.id)}"></div>
        <div class="run-history-panel" id="rh-${_esc(f.id)}"></div>
      </div>`;
  }

  // ── Event routing ──────────────────────────────────────────────────────────

  async function _onClick(e) {
    const item = e.target.closest('.flow-item');
    if (!item) return;
    const fid = item.dataset.fid;

    if (e.target.classList.contains('fl-run'))           await _doRun(fid, item);
    else if (e.target.classList.contains('fl-debug'))    await _doDebugRun(fid, item);
    else if (e.target.classList.contains('fl-validate')) await _doValidate(fid, item);
    else if (e.target.classList.contains('fl-history'))  await _doHistory(fid, item);
    else if (e.target.classList.contains('fl-open-run')) _openWorkspace(fid, e.target.dataset.rid);
  }

  // ── Run Now ────────────────────────────────────────────────────────────────

  async function _doRun(flowId, item) {
    const btn = item.querySelector('.fl-run');
    btn.disabled = true; btn.textContent = 'Starting…';
    try {
      const profiles = await api.listProfiles();
      if (!profiles.length) {
        alert('Create a profile in the Profiles tab before running a flow.');
        return;
      }
      const result = await api.runFlow(flowId, profiles[0].id, false);
      if (result.ok) {
        _openWorkspace(flowId, result.run_id);
      } else {
        alert(`Failed to start: ${result.error || 'unknown error'}`);
      }
    } finally {
      btn.disabled = false; btn.textContent = 'Run Now';
    }
  }

  // ── Debug Run ──────────────────────────────────────────────────────────────

  async function _doDebugRun(flowId, item) {
    const btn = item.querySelector('.fl-debug');
    btn.disabled = true; btn.textContent = 'Starting…';
    try {
      const profiles = await api.listProfiles();
      if (!profiles.length) {
        alert('Create a profile in the Profiles tab before running a flow.');
        return;
      }
      const result = await api.startDebugRun(flowId, profiles[0].id);
      if (result.ok) {
        _openWorkspace(flowId, result.run_id);
      } else {
        alert(`Failed to start debug run: ${result.error || 'unknown error'}`);
      }
    } finally {
      btn.disabled = false; btn.textContent = 'Debug';
    }
  }

  // ── Validate ───────────────────────────────────────────────────────────────

  async function _doValidate(flowId, item) {
    const btn   = item.querySelector('.fl-validate');
    const msgEl = document.getElementById(`vm-${flowId}`);
    btn.disabled = true;
    msgEl.style.display = 'block';
    msgEl.innerHTML = '<em style="color:var(--muted)">Validating…</em>';
    try {
      const r = await api.getFlowViolations(flowId);
      if (r.error && !r.violations) {
        msgEl.innerHTML = `<span style="color:var(--danger)">✗ ${_esc(r.error)}</span>`;
        return;
      }
      const errors   = (r.violations || []).filter(v => v.severity === 'error');
      const warnings = (r.violations || []).filter(v => v.severity === 'warning');
      if (!errors.length && !warnings.length) {
        msgEl.innerHTML = `<span style="color:var(--success)">✓ All contracts satisfied</span>`;
      } else {
        const errHtml = errors.map(v =>
          `<div style="color:var(--danger);font-size:11px">✗ [${_esc(v.step_id)}] ${_esc(v.message)}</div>`
        ).join('');
        const warnHtml = warnings.map(v =>
          `<div style="color:var(--warning,#c8820a);font-size:11px">⚠ [${_esc(v.step_id)}] ${_esc(v.message)}</div>`
        ).join('');
        msgEl.innerHTML = errHtml + warnHtml;
      }
    } finally {
      btn.disabled = false;
    }
  }

  // ── History expand ─────────────────────────────────────────────────────────

  async function _doHistory(flowId, item) {
    const panel = document.getElementById(`rh-${flowId}`);
    if (panel.style.display === 'block') {
      panel.style.display = 'none';
      return;
    }
    panel.style.display = 'block';
    panel.innerHTML = '<div style="padding:12px;color:var(--muted)">Loading…</div>';
    try {
      const runs = await api.listRuns(flowId, 15);
      if (!runs.length) {
        panel.innerHTML = '<div style="padding:12px;color:var(--muted)">No runs yet.</div>';
        return;
      }
      const maxDurSec = Math.max(...runs.map(r => _durSec(r.started_at, r.completed_at)), 1);
      panel.innerHTML = `
        <table style="width:100%">
          <thead><tr>
            <th>Started</th><th>Duration</th><th>Status</th><th>Steps</th><th></th>
          </tr></thead>
          <tbody>${runs.map(r => _runRowHTML(r, maxDurSec)).join('')}</tbody>
        </table>`;
    } catch (e) {
      panel.innerHTML = `<div style="padding:12px;color:var(--danger)">Failed: ${_esc(e.message)}</div>`;
    }
  }

  function _runRowHTML(r, maxDurSec) {
    const started   = (r.started_at || '').replace('T', ' ').slice(0, 19);
    const durSec    = _durSec(r.started_at, r.completed_at);
    const durLabel  = _dur(r.started_at, r.completed_at);
    const steps     = `${r.steps_completed || 0} / ${(r.steps_completed || 0) + (r.steps_failed || 0)}`;
    const resumable = ['failed', 'cancelled', 'aborted'].includes(r.status);
    const barPct    = maxDurSec > 0 ? Math.round((durSec / maxDurSec) * 100) : 0;
    const barColor  = r.status === 'completed' ? 'var(--success)'
                    : r.status === 'failed'    ? 'var(--danger)'
                    : 'var(--muted)';
    return `
      <tr>
        <td>${_esc(started)}</td>
        <td>
          <div style="display:flex;align-items:center;gap:6px">
            <div style="flex:1;height:4px;background:var(--border);border-radius:2px;min-width:60px">
              <div style="width:${barPct}%;height:100%;background:${barColor};border-radius:2px"></div>
            </div>
            <span style="white-space:nowrap;font-size:11px;color:var(--muted)">${_esc(durLabel)}</span>
          </div>
        </td>
        <td><span class="rs-badge rs-${_esc(r.status)}">${_esc(r.status)}</span></td>
        <td>${_esc(steps)}</td>
        <td style="white-space:nowrap">
          <button class="btn btn-sm btn-secondary fl-open-run" data-rid="${_esc(r.run_id)}" style="margin-right:4px">View</button>
          ${resumable ? `<button class="btn btn-sm btn-secondary fl-open-run" data-rid="${_esc(r.run_id)}" title="Resume from last checkpoint">↩ Resume</button>` : ''}
        </td>
      </tr>`;
  }

  // ── Navigation ─────────────────────────────────────────────────────────────

  function _openWorkspace(flowId, runId) {
    WorkspaceView.render(_el, { flowId, runId, onBack: () => render(_el) });
  }

  // ── Utilities ──────────────────────────────────────────────────────────────

  function _relTime(iso) {
    const diff = (Date.now() - new Date(iso)) / 1000;
    if (diff < 60)    return 'just now';
    if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  function _durSec(start, end) {
    if (!start || !end) return 0;
    return Math.max(0, (new Date(end) - new Date(start)) / 1000);
  }

  function _dur(start, end) {
    if (!start) return '—';
    const sec = ((end ? new Date(end) : new Date()) - new Date(start)) / 1000;
    if (sec < 60) return `${sec.toFixed(1)}s`;
    return `${Math.floor(sec / 60)}m ${Math.floor(sec % 60)}s`;
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { render };
})();
