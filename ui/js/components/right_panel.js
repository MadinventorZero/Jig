/**
 * RightPanel — step inspection panel for History mode.
 *
 * RightPanel.render(el, { step, runId, status, onBack })
 *   Shows the latest step result: header, error (if any), screenshot tab,
 *   output-values tab.
 */
const RightPanel = (() => {

  async function render(el, { step, runId, status, onBack }) {
    el.innerHTML = '<p style="color:var(--muted);padding:12px">Loading result…</p>';

    try {
      const rows   = await api.getStepResult(runId, step.step_id);
      const latest = rows && rows.length ? rows[rows.length - 1] : null;

      if (!latest) {
        el.innerHTML = `
          ${_backBtn(onBack)}
          <p style="color:var(--muted)">No result recorded for this step.</p>`;
        _wireBack(el, onBack);
        return;
      }

      const result = latest.result || {};
      const error  = latest.error  || null;
      const dur    = _dur(latest.started_at, latest.completed_at);
      const ss     = (result.screenshot_path) ||
                     (error && error.screenshot_path) || null;

      el.innerHTML = `
        ${_backBtn(onBack)}

        <div class="detail-section" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <strong style="font-size:13px">${_esc(step.step_id)}</strong>
          <span class="rs-badge rs-${_esc(latest.status)}">${_esc(latest.status)}</span>
          <span style="color:var(--muted);font-size:11px">${_esc(dur)}</span>
          <span style="color:var(--muted);font-size:11px;font-family:monospace">${_esc(step.type)}</span>
        </div>

        ${error ? _errorBlock(error) : ''}

        <div class="rp-tabs">
          ${ss ? '<button class="rp-tab active" data-tab="screenshot">Screenshot</button>' : ''}
          <button class="rp-tab${ss ? '' : ' active'}" data-tab="output">Output</button>
          ${rows.length > 1 ? `<button class="rp-tab" data-tab="retries">Retries (${rows.length})</button>` : ''}
        </div>
        <div id="rp-body" class="rp-body"></div>`;

      _wireBack(el, onBack);

      const tabsEl = el.querySelector('.rp-tabs');
      const bodyEl = el.querySelector('#rp-body');

      function showTab(name) {
        tabsEl.querySelectorAll('.rp-tab')
              .forEach(t => t.classList.toggle('active', t.dataset.tab === name));
        if (name === 'screenshot') _renderScreenshot(bodyEl, ss);
        else if (name === 'retries') _renderRetries(bodyEl, rows);
        else _renderOutput(bodyEl, result, error);
      }

      tabsEl.addEventListener('click', e => {
        const tab = e.target.closest('.rp-tab');
        if (tab) showTab(tab.dataset.tab);
      });

      showTab(ss ? 'screenshot' : 'output');

    } catch (e) {
      el.innerHTML = `
        ${_backBtn(onBack)}
        <p style="color:var(--danger)">Failed to load result: ${_esc(e.message)}</p>`;
      _wireBack(el, onBack);
    }
  }

  // ── Tab renderers ──────────────────────────────────────────────────────────

  async function _renderScreenshot(el, ssPath) {
    el.innerHTML = '<p style="color:var(--muted);padding:8px">Loading screenshot…</p>';
    try {
      const data = await api.getScreenshot(ssPath);
      if (data && data.b64) {
        el.innerHTML = `
          <div class="rp-screenshot-wrap">
            <img class="rp-screenshot" src="data:image/png;base64,${data.b64}"
                 alt="Step screenshot" title="Click to expand">
          </div>`;
        el.querySelector('.rp-screenshot').addEventListener('click', function () {
          this.classList.toggle('rp-screenshot-expanded');
        });
      } else {
        el.innerHTML = `<p style="color:var(--muted);padding:8px">Screenshot not available${data.error ? ': ' + _esc(data.error) : '.'}</p>`;
      }
    } catch (_) {
      el.innerHTML = `<p style="color:var(--muted);padding:8px">Screenshot not available.</p>`;
    }
  }

  function _renderOutput(el, result, error) {
    const entries = Object.entries(result || {})
      .filter(([k]) => k !== 'screenshot_path');  // shown in screenshot tab

    if (!entries.length && !error) {
      el.innerHTML = '<p style="color:var(--muted);padding:8px">No output values recorded.</p>';
      return;
    }
    el.innerHTML = `
      <table style="width:100%;font-size:12px;border-collapse:collapse;padding:4px 0">
        ${entries.map(([k, v]) => `
          <tr>
            <td style="font-family:monospace;color:var(--muted);padding:3px 10px 3px 0;
                       vertical-align:top;white-space:nowrap">${_esc(k)}</td>
            <td style="word-break:break-all;vertical-align:top">${_esc(
              typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? '')
            )}</td>
          </tr>`).join('')}
      </table>`;
  }

  function _renderRetries(el, rows) {
    el.innerHTML = `
      <table style="width:100%;font-size:11px;border-collapse:collapse">
        <thead><tr style="opacity:0.5">
          <th style="text-align:left;padding:2px 8px 2px 0">attempt</th>
          <th style="text-align:left;padding:2px 8px 2px 0">status</th>
          <th style="text-align:left;padding:2px 0">duration</th>
        </tr></thead>
        <tbody>${rows.map((r, i) => `
          <tr>
            <td style="padding:2px 8px 2px 0">${i + 1}</td>
            <td style="padding:2px 8px 2px 0">
              <span class="rs-badge rs-${_esc(r.status)}">${_esc(r.status)}</span>
            </td>
            <td style="padding:2px 0;color:var(--muted)">${_esc(_dur(r.started_at, r.completed_at))}</td>
          </tr>`).join('')}
        </tbody>
      </table>`;
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  function _errorBlock(error) {
    const msg = error.humanized || error.error || 'Unknown error';
    return `
      <div class="detail-section">
        <div class="detail-label">Error</div>
        <div style="color:var(--danger);font-size:12px;line-height:1.5">${_esc(msg)}</div>
        ${error.traceback ? `
          <details style="margin-top:8px">
            <summary style="font-size:11px;cursor:pointer;color:var(--muted);user-select:none">
              Raw traceback
            </summary>
            <pre class="detail-pre" style="font-size:10px;max-height:160px;overflow:auto;margin-top:6px">${_esc(error.traceback)}</pre>
          </details>` : ''}
      </div>`;
  }

  function _backBtn(onBack) {
    if (!onBack) return '';
    return `<button class="btn btn-sm btn-secondary rp-back"
              style="margin-bottom:12px">← Run summary</button>`;
  }

  function _wireBack(el, onBack) {
    if (!onBack) return;
    const btn = el.querySelector('.rp-back');
    if (btn) btn.addEventListener('click', onBack);
  }

  function _dur(start, end) {
    if (!start) return '—';
    const sec = ((end ? new Date(end) : new Date()) - new Date(start)) / 1000;
    if (sec < 60) return `${sec.toFixed(2)}s`;
    return `${Math.floor(sec / 60)}m ${(sec % 60).toFixed(0)}s`;
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { render };
})();
