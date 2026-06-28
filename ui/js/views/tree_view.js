/**
 * TreeView — renders a Mermaid decision tree for a flow.
 * Optionally overlays run-outcome node classes on a completed run.
 *
 * Usage: await TreeView.render(container, { flowId, runId? })
 */
const TreeView = (() => {
  let _initialized = false;

  function _ensureInit() {
    if (_initialized || !window.mermaid) return;
    mermaid.initialize({ startOnLoad: false, theme: 'neutral' });
    _initialized = true;
  }

  async function render(container, { flowId, runId }) {
    container.innerHTML = `<div style="padding:16px;color:var(--muted)">Loading decision tree…</div>`;

    try {
      const [graphStr, events] = await Promise.all([
        api.getFlowGraph(flowId),
        runId ? api.getRunEvents(runId) : Promise.resolve([]),
      ]);

      if (!graphStr) {
        container.innerHTML = `<div style="padding:16px;color:var(--muted)">No decision graph available for this flow.</div>`;
        return;
      }

      // Build step_id → outcome from run events
      const nodeStatus = {};
      for (const ev of events) {
        if (!ev.step_id) continue;
        if (ev.event === 'step.completed') nodeStatus[ev.step_id] = 'completed';
        if (ev.event === 'step.failed')    nodeStatus[ev.step_id] = 'failed';
        if (ev.event === 'step.skipped')   nodeStatus[ev.step_id] = 'skipped';
      }

      // Append outcome class definitions + per-node class assignments
      let mmd = graphStr;
      if (Object.keys(nodeStatus).length > 0) {
        mmd +=
          '\nclassDef completed fill:#5A8A57,color:#fff,stroke-width:0' +
          '\nclassDef failed fill:#B8513A,color:#fff,stroke-width:0' +
          '\nclassDef skipped fill:#8A8A8A,color:#fff,stroke-width:0\n' +
          Object.entries(nodeStatus).map(([id, cls]) => `class ${id} ${cls}`).join('\n');
      }

      _ensureInit();

      if (!window.mermaid) {
        // Mermaid CDN not loaded (offline) — show raw Mermaid text
        container.innerHTML = `<div class="mermaid-wrap"><pre class="detail-pre">${_esc(mmd)}</pre></div>`;
        return;
      }

      const uid = 'mmd-' + Date.now();
      container.innerHTML = `<div class="mermaid-wrap"><div id="${uid}"></div></div>`;
      try {
        const { svg } = await mermaid.render(uid, mmd);
        container.querySelector(`#${uid}`).innerHTML = svg;
      } catch (e) {
        // Mermaid parse error — show raw text as fallback
        container.querySelector(`#${uid}`).innerHTML =
          `<pre class="detail-pre">${_esc(mmd)}</pre>`;
      }
    } catch (e) {
      container.innerHTML =
        `<div style="padding:16px;color:var(--danger)">Failed to load tree: ${_esc(e.message)}</div>`;
    }
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { render };
})();
