/**
 * LiveRunView — streams live run events via 2-second polling.
 *
 * Usage:
 *   await LiveRunView.render(container, { runId, onStatusChange })
 *   LiveRunView.stop()   ← call when navigating away
 */
const LiveRunView = (() => {
  let _timer    = null;
  let _lastId   = 0;
  let _runId    = null;
  let _logEl    = null;
  let _statEl   = null;
  let _overlayEl = null;
  let _done     = false;
  let _paused   = false;

  const TERMINAL = new Set(['run.completed', 'run.failed', 'run.cancelled', 'run.aborted']);

  function stop() {
    if (_timer) { clearInterval(_timer); _timer = null; }
    _done = true;
    _hideDebugOverlay();
  }

  async function render(container, { runId, onStatusChange }) {
    stop();
    _runId    = runId;
    _lastId   = 0;
    _done     = false;
    _paused   = false;

    container.innerHTML = `
      <div class="lrv-wrap">
        <div class="lrv-header">
          <span id="lrv-stat" class="run-indicator running">⟳ RUNNING</span>
          <button class="btn btn-sm btn-danger" id="lrv-cancel">Cancel</button>
        </div>
        <div id="lrv-log" class="live-log"></div>
        <div id="lrv-debug-overlay" class="lrv-debug-overlay hidden"></div>
      </div>
    `;
    _logEl    = container.querySelector('#lrv-log');
    _statEl   = container.querySelector('#lrv-stat');
    _overlayEl = container.querySelector('#lrv-debug-overlay');

    container.querySelector('#lrv-cancel').addEventListener('click', async () => {
      await api.cancelRun(runId);
    });

    // First poll immediately, then every 2s
    await _poll(onStatusChange);
    if (!_done) {
      _timer = setInterval(() => _poll(onStatusChange), 2000);
    }
  }

  async function _poll(onStatusChange) {
    if (_done) return;
    try {
      const events = await api.getRunEventsSince(_runId, _lastId);
      for (const ev of events) {
        if (ev.id > _lastId) _lastId = ev.id;
        if (ev.event === 'step.debug_pause') {
          _showDebugOverlay(ev);
        } else {
          if (_paused && ev.event === 'step.started') _hideDebugOverlay();
          _appendLine(ev);
        }
        if (TERMINAL.has(ev.event)) {
          const status = ev.event.replace('run.', '');
          _statEl.className = `run-indicator ${status}`;
          _statEl.textContent = status.toUpperCase();
          stop();
          if (onStatusChange) onStatusChange(status);
          return;
        }
      }
    } catch (_) {
      /* transient poll errors — ignore, retry next interval */
    }
  }

  function _showDebugOverlay(ev) {
    _paused = true;
    const data        = ev.data || {};
    const stepId      = ev.step_id || '';
    const stepType    = data.step_type || '';
    const screenshotPath = data.screenshot_path || '';

    _overlayEl.innerHTML = `
      <div class="lrv-debug-box">
        <div class="lrv-debug-title">Debug Pause — <code>${_esc(stepId)}</code></div>
        <div class="lrv-debug-type">${_esc(stepType)}</div>
        ${screenshotPath
          ? `<img class="lrv-debug-screenshot" src="data:image/png;base64,__screenshot__" data-path="${_esc(screenshotPath)}" alt="Step screenshot" />`
          : '<div class="lrv-debug-no-screenshot">No browser screenshot available</div>'}
        <div class="lrv-debug-actions">
          <button class="btn btn-primary btn-sm" id="lrv-dbg-continue">Continue</button>
          <button class="btn btn-secondary btn-sm" id="lrv-dbg-skip">Skip Step</button>
          <button class="btn btn-danger btn-sm" id="lrv-dbg-abort">Abort</button>
        </div>
      </div>`;
    _overlayEl.classList.remove('hidden');

    // Load screenshot via API if path available
    if (screenshotPath) {
      api.getScreenshot(screenshotPath).then(b64 => {
        const img = _overlayEl.querySelector('.lrv-debug-screenshot');
        if (img && b64) img.src = `data:image/png;base64,${b64}`;
      }).catch(() => {});
    }

    _overlayEl.querySelector('#lrv-dbg-continue').addEventListener('click', async () => {
      await api.debugContinue(_runId);
      _hideDebugOverlay();
    });
    _overlayEl.querySelector('#lrv-dbg-skip').addEventListener('click', async () => {
      await api.debugSkip(_runId);
      _hideDebugOverlay();
    });
    _overlayEl.querySelector('#lrv-dbg-abort').addEventListener('click', async () => {
      await api.cancelRun(_runId);
      _hideDebugOverlay();
    });
  }

  function _hideDebugOverlay() {
    _paused = false;
    if (_overlayEl) _overlayEl.classList.add('hidden');
  }

  function _appendLine(ev) {
    const ts  = (ev.ts  || '').slice(11, 19);
    const lvl = ev.level || 'INFO';
    const msg = ev.message || '';
    const el  = document.createElement('div');
    el.className = 'll-line';
    el.innerHTML =
      `<span class="ll-ts">${ts}</span> ` +
      `<span class="ll-lvl-${lvl}">[${lvl}]</span> ` +
      `<span class="ll-msg">${_esc(msg)}</span>`;
    _logEl.appendChild(el);
    _logEl.scrollTop = _logEl.scrollHeight;
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { render, stop };
})();
