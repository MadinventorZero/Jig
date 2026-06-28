/**
 * StepCard — renders a single step card for the workspace step list.
 * Returns an HTML string (injected via innerHTML).
 *
 * status: 'idle' | 'running' | 'completed' | 'failed' | 'skipped'
 */
const StepCard = (() => {
  const TYPE_ABBR = {
    browser_navigate:   'nav',
    browser_click:      'click',
    browser_type:       'type',
    browser_fill:       'fill',
    browser_screenshot: 'shot',
    browser_extract:    'extr',
    gmail_watch:        'gmail',
    gmail_send:         'gmail',
    gmail_search:       'gmail',
    llm_decide:         'llm',
    claude_complete:    'llm',
    claude_extract:     'llm',
    human_pause:        'pause',
    captcha_detect:     'captcha',
    captcha_execute:    'captcha',
    block:              'block',
    condition:          'cond',
    wait:               'wait',
    http_request:       'http',
    run_script:         'script',
    python_run:         'script',
    set_variable:       'var',
    loop:               'loop',
    notify_system:      'notify',
  };

  function _statusSuffix(status) {
    if (status === 'completed') return ' <span style="color:var(--success)">✓</span>';
    if (status === 'failed')    return ' <span style="color:var(--danger)">✗</span>';
    if (status === 'warning')   return ' <span style="color:var(--warning,#c8820a)">⚠</span>';
    if (status === 'running')   return ' <span style="color:var(--info)">⟳</span>';
    if (status === 'skipped')   return ' <span style="color:var(--muted)">—</span>';
    return '';
  }

  const ROUTER_TYPES = new Set(['llm_decide', 'condition', 'gmail_watch']);

  function _isRouter(step) {
    return ROUTER_TYPES.has(step.type) ||
           (step.on_choice && Object.keys(step.on_choice).length > 0);
  }

  function render(step, status = 'idle', active = false, branchCollapsed = true) {
    const name     = (step.step_id || '').replace(/_/g, ' ');
    const abbr     = TYPE_ABBR[step.type] || step.type || '';
    const dotCls   = status || 'idle';
    const actCls   = active ? ' active' : '';
    const isRouter = _isRouter(step);
    const toggle   = isRouter
      ? `<button class="sc-toggle" data-step-id="${_esc(step.step_id)}" title="${branchCollapsed ? 'Expand branches' : 'Collapse branches'}">${branchCollapsed ? '▶' : '▼'}</button>`
      : '';
    return `
      <div class="step-card${actCls}" data-step-id="${_esc(step.step_id)}">
        <span class="step-dot ${dotCls}"></span>
        <span class="step-name">${_esc(name)}${_statusSuffix(status)}</span>
        <span class="step-type-tag">${_esc(abbr)}</span>
        ${toggle}
      </div>`;
  }

  function renderBranches(step, collapsed) {
    const choices = step.on_choice ? Object.entries(step.on_choice) : [];
    if (!choices.length || collapsed) return '';
    const items = choices.map(([choice, target]) => {
      const cleanTarget = String(target).replace('skip_to:', '').trim();
      return `<div class="branch-item">
        <span class="branch-choice">${_esc(choice)}</span>
        <span class="branch-arrow">→</span>
        <span class="branch-target">${_esc(cleanTarget)}</span>
      </div>`;
    }).join('');
    return `<div class="branch-columns">${items}</div>`;
  }

  function renderConnector(compat) {
    if (compat === 'none') return '';
    const colors = { green: 'var(--success)', yellow: 'var(--warning)', red: 'var(--danger)' };
    const color  = colors[compat] || 'var(--border)';
    return `<div class="step-connector-wrap">
      <div class="step-connector-dot" style="background:${color}" title="Contract: ${compat}"></div>
    </div>`;
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { render, renderBranches, renderConnector };
})();
