const SchedulesView = (() => {

  function fmtDateTime(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
    });
  }

  function fmtRelative(iso) {
    if (!iso) return null;
    const ms   = new Date(iso) - Date.now();
    const abs  = Math.abs(ms);
    const mins = Math.floor(abs / 60000);
    const hrs  = Math.floor(abs / 3600000);
    const days = Math.floor(abs / 86400000);
    const past = ms < 0;

    let label;
    if (mins < 2)       label = 'now';
    else if (mins < 60) label = `${mins}m`;
    else if (hrs < 24)  label = `${hrs}h`;
    else                label = `${days}d`;

    return past ? `${label} ago` : `in ${label}`;
  }

  function fmtTrigger(sched) {
    const t = sched.trigger_params || {};
    if (t.type === 'one-shot') {
      const dt = t.fire_at ? new Date(t.fire_at) : null;
      return dt ? `Once — ${dt.toLocaleString('en-US', { month:'short', day:'numeric',
        year:'numeric', hour:'numeric', minute:'2-digit' })}` : 'Once';
    }
    if (t.type === 'cron') {
      const h   = String(t.hour   ?? 9).padStart(2, '0');
      const m   = String(t.minute ?? 0).padStart(2, '0');
      const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
      const day  = t.weekday != null ? `Every ${days[t.weekday % 7]}` : 'Daily';
      return `${day} at ${h}:${m}`;
    }
    return sched.trigger_type || '—';
  }

  async function render(container) {
    const [schedules, profiles, sources, schedulesV3, flows] = await Promise.all([
      api.listSchedules(),
      api.listProfiles(),
      api.listSources(),
      api.listSchedulesV3(),
      api.listFlows(),
    ]);

    // Build flow and profile lookup maps for display
    const flowMap    = Object.fromEntries(flows.map(f => [f.id, f.name || f.id]));
    const profileMap = Object.fromEntries(profiles.map(p => [p.profile_id, p.label || p.profile_id]));

    container.innerHTML = `
      <div class="view">
        <div class="view-header">
          <div>
            <div class="view-title">Schedules</div>
            <div class="view-subtitle">Automate when flows run — new schedules are disabled by default</div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-secondary" id="btn-new-schedule">+ Booking Schedule</button>
            <button class="btn btn-primary"   id="btn-new-flow-schedule">+ Flow Schedule</button>
          </div>
        </div>

        <!-- V3 Flow Schedules -->
        <div style="margin-bottom:28px">
          <div class="detail-label" style="padding:0 0 8px 0">Flow Schedules</div>
          ${schedulesV3.length === 0
            ? '<div class="card"><div class="table-empty">No flow schedules yet. Click <strong>+ Flow Schedule</strong> to automate a flow.</div></div>'
            : `<div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Flow</th>
                      <th>Profile</th>
                      <th>Trigger</th>
                      <th>Last Run</th>
                      <th style="text-align:center">Enabled</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    ${schedulesV3.map(s => {
                      const rowDim = s.enabled ? '' : 'opacity:0.55';
                      return `
                      <tr style="${rowDim}">
                        <td>
                          <strong>${_esc(flowMap[s.flow_id] || s.flow_id)}</strong>
                          ${s.enabled
                            ? '<span class="badge badge-info" style="font-size:10px;margin-left:6px">enabled</span>'
                            : '<span class="badge badge-muted" style="font-size:10px;margin-left:6px">disabled</span>'}
                        </td>
                        <td class="text-muted">${_esc(profileMap[s.profile_id] || s.profile_id)}</td>
                        <td style="font-size:12px">${_esc(fmtTrigger(s))}</td>
                        <td class="text-muted" style="font-size:12px">${s.last_run_at ? fmtDateTime(s.last_run_at) : '—'}</td>
                        <td style="text-align:center">
                          <label class="toggle">
                            <input type="checkbox" class="toggle-v3"
                                   data-id="${s.schedule_id}" ${s.enabled ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                          </label>
                        </td>
                        <td style="text-align:right">
                          <button class="btn btn-sm btn-danger btn-delete-v3"
                                  data-id="${s.schedule_id}">Delete</button>
                        </td>
                      </tr>`;
                    }).join('')}
                  </tbody>
                </table>
              </div>`}
        </div>

        <!-- V2 Booking Schedules -->
        <div>
          <div class="detail-label" style="padding:0 0 8px 0">Booking Schedules</div>
          ${schedules.length === 0
            ? '<div class="card"><div class="table-empty">No booking schedules yet.</div></div>'
            : `<div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Label</th>
                      <th>Target Date</th>
                      <th>Next Run</th>
                      <th>Site</th>
                      <th>Last Run</th>
                      <th style="text-align:center">Enabled</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    ${schedules.map(s => {
                      const rel     = fmtRelative(s.fire_at);
                      const isPast  = s.fire_at && new Date(s.fire_at) < new Date();
                      const rowDim  = s.enabled ? '' : 'opacity:0.55';
                      return `
                      <tr style="${rowDim}">
                        <td>
                          <strong>${s.label}</strong>
                          ${s.enabled
                            ? '<span class="badge badge-info" style="font-size:10px;margin-left:6px">enabled</span>'
                            : '<span class="badge badge-muted" style="font-size:10px;margin-left:6px">disabled</span>'}
                        </td>
                        <td>${s.target_date}</td>
                        <td>
                          <div style="font-size:12px">${fmtDateTime(s.fire_at)}</div>
                          ${rel ? `<div style="font-size:11px;color:${isPast ? 'var(--danger)' : 'var(--navy)'};font-weight:600;margin-top:2px">${rel}</div>` : ''}
                        </td>
                        <td class="text-muted">${s.site_id.replace(/_/g, ' ')}</td>
                        <td class="text-muted" style="font-size:12px">${s.last_run_at ? fmtDateTime(s.last_run_at) : '—'}</td>
                        <td style="text-align:center">
                          <label class="toggle">
                            <input type="checkbox" class="toggle-enabled"
                                   data-id="${s.schedule_id}" ${s.enabled ? 'checked' : ''}>
                            <span class="toggle-slider"></span>
                          </label>
                        </td>
                        <td style="text-align:right">
                          <button class="btn btn-sm btn-secondary btn-edit-schedule"
                                  data-id="${s.schedule_id}" style="margin-right:6px">Edit</button>
                          <button class="btn btn-sm btn-danger btn-delete-schedule"
                                  data-id="${s.schedule_id}">Delete</button>
                        </td>
                      </tr>`;
                    }).join('')}
                  </tbody>
                </table>
              </div>`}
        </div>
      </div>`;

    document.getElementById('btn-new-schedule')
      .addEventListener('click', () => openScheduleModal(null, profiles, sources));

    document.getElementById('btn-new-flow-schedule')
      .addEventListener('click', () => openFlowScheduleModal(flows, profiles));

    container.querySelectorAll('.btn-edit-schedule').forEach(btn =>
      btn.addEventListener('click', async () => {
        const s = await api.getSchedule(btn.dataset.id);
        openScheduleModal(s, profiles, sources);
      }));

    container.querySelectorAll('.btn-delete-schedule').forEach(btn =>
      btn.addEventListener('click', async () => {
        if (!confirm('Delete this schedule? The launchd job will also be removed.')) return;
        await api.deleteSchedule(btn.dataset.id);
        App.navigate('schedules');
      }));

    container.querySelectorAll('.toggle-enabled').forEach(toggle =>
      toggle.addEventListener('change', async () => {
        const result = await api.toggleSchedule(toggle.dataset.id, toggle.checked);
        if (!result.ok) {
          alert('Failed to toggle schedule. Check that the fire time is in the future.');
          toggle.checked = !toggle.checked;
        } else {
          App.navigate('schedules');
        }
      }));

    container.querySelectorAll('.btn-delete-v3').forEach(btn =>
      btn.addEventListener('click', async () => {
        if (!confirm('Delete this flow schedule? The system job will also be removed.')) return;
        await api.deleteScheduleV3(btn.dataset.id);
        App.navigate('schedules');
      }));

    container.querySelectorAll('.toggle-v3').forEach(toggle =>
      toggle.addEventListener('change', async () => {
        const result = await api.toggleScheduleV3(toggle.dataset.id, toggle.checked);
        if (!result.ok) {
          alert(`Failed to toggle schedule: ${result.error || 'unknown error'}`);
          toggle.checked = !toggle.checked;
        } else {
          App.navigate('schedules');
        }
      }));
  }

  function openScheduleModal(schedule, profiles, sources) {
    const isNew = !schedule;

    App.showModal(`
      <div class="modal-title">${isNew ? 'New Schedule' : 'Edit Schedule'}</div>

      ${isNew ? `
        <div class="alert alert-info" style="font-size:12px;margin-bottom:16px">
          New schedules are <strong>disabled by default</strong>. Enable the toggle on the
          Schedules page after saving to activate the launchd job.
        </div>` : ''}

      <div class="form-group">
        <label>Label</label>
        <input type="text" id="s-label" value="${schedule?.label || ''}"
               placeholder="e.g. May 29 Greystone Attempt">
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Profile</label>
          <select id="s-profile">
            ${profiles.map(p => `
              <option value="${p.profile_id}" ${schedule?.profile_id === p.profile_id ? 'selected' : ''}>
                ${p.label}
              </option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>Booking Site</label>
          <select id="s-site">
            ${sources.map(s => `
              <option value="${s.site_id}" ${schedule?.site_id === s.site_id ? 'selected' : ''}>
                ${s.label}
              </option>`).join('')}
          </select>
        </div>
      </div>

      <div class="form-group">
        <label>Target Date <span class="text-muted" style="text-transform:none;font-weight:400">(the date you want the permit for)</span></label>
        <input type="date" id="s-target-date" value="${schedule?.target_date || ''}">
        <div class="form-hint" id="fire-time-preview">
          ${schedule?.fire_at ? `Agent fires at: ${new Date(schedule.fire_at).toLocaleString()}` : 'Select a date to see fire time'}
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Retry Attempts</label>
          <input type="number" id="s-retry-count" value="${schedule?.retry_count ?? 3}" min="1" max="10">
          <div class="form-hint">How many times to attempt if the form fails</div>
        </div>
        <div class="form-group">
          <label>Retry Interval (seconds)</label>
          <input type="number" id="s-retry-interval" value="${schedule?.retry_interval_seconds ?? 60}" min="10">
        </div>
      </div>

      <div class="modal-actions">
        <button class="btn btn-secondary" id="btn-cancel-schedule">Cancel</button>
        <button class="btn btn-primary" id="btn-save-schedule">Save Schedule</button>
      </div>
    `);

    document.getElementById('s-target-date').addEventListener('change', async (e) => {
      const val = e.target.value;
      if (!val) return;
      const result = await api.previewFireTime(val);
      const preview = document.getElementById('fire-time-preview');
      if (result.ok) {
        preview.textContent = `Agent fires at: ${result.display}`;
        preview.style.color = 'var(--navy)';
      } else {
        preview.textContent = result.error;
        preview.style.color = 'var(--danger)';
      }
    });

    document.getElementById('btn-cancel-schedule').addEventListener('click', App.closeModal);

    document.getElementById('btn-save-schedule').addEventListener('click', async () => {
      const data = {
        schedule_id:             schedule?.schedule_id,
        label:                   document.getElementById('s-label').value.trim(),
        profile_id:              document.getElementById('s-profile').value,
        site_id:                 document.getElementById('s-site').value,
        target_date:             document.getElementById('s-target-date').value,
        retry_count:             parseInt(document.getElementById('s-retry-count').value, 10),
        retry_interval_seconds:  parseInt(document.getElementById('s-retry-interval').value, 10),
        enabled:                 schedule?.enabled ?? false,
      };
      if (!data.label || !data.target_date) {
        alert('Label and Target Date are required.');
        return;
      }
      await api.saveSchedule(data);
      App.closeModal();
      App.navigate('schedules');
    });
  }

  // ── Flow Schedule Modal ────────────────────────────────────────────────────

  function openFlowScheduleModal(flows, profiles) {
    App.showModal(`
      <div class="modal-title">New Flow Schedule</div>

      <div class="alert alert-info" style="font-size:12px;margin-bottom:16px">
        The schedule starts <strong>enabled</strong>. The system job is registered immediately on save.
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Flow</label>
          <select id="fs-flow">
            <option value="">— select a flow —</option>
            ${flows.map(f => `<option value="${_esc(f.id)}">${_esc(f.name || f.id)}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>Profile</label>
          <select id="fs-profile">
            <option value="">— select a profile —</option>
            ${profiles.map(p => `<option value="${_esc(p.profile_id)}">${_esc(p.label || p.profile_id)}</option>`).join('')}
          </select>
        </div>
      </div>

      <div class="form-group">
        <label>Trigger type</label>
        <div style="display:flex;gap:16px;padding:4px 0">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-weight:400">
            <input type="radio" name="fs-trigger-type" value="one-shot" checked> One-time
          </label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-weight:400">
            <input type="radio" name="fs-trigger-type" value="cron"> Recurring (cron)
          </label>
        </div>
      </div>

      <!-- One-shot config -->
      <div id="fs-oneshot-section" class="form-group">
        <label>Fire at</label>
        <input type="datetime-local" id="fs-fire-at">
        <div class="form-hint" id="fs-oneshot-preview" style="color:var(--navy)"></div>
      </div>

      <!-- Cron config (hidden initially) -->
      <div id="fs-cron-section" style="display:none">
        <div class="form-row">
          <div class="form-group">
            <label>Hour (0–23)</label>
            <input type="number" id="fs-cron-hour" value="9" min="0" max="23">
          </div>
          <div class="form-group">
            <label>Minute (0–59)</label>
            <input type="number" id="fs-cron-minute" value="0" min="0" max="59">
          </div>
        </div>
        <div class="form-group">
          <label>Repeat</label>
          <select id="fs-cron-repeat">
            <option value="daily">Every day</option>
            <option value="mon">Every Monday</option>
            <option value="tue">Every Tuesday</option>
            <option value="wed">Every Wednesday</option>
            <option value="thu">Every Thursday</option>
            <option value="fri">Every Friday</option>
            <option value="sat">Every Saturday</option>
            <option value="sun">Every Sunday</option>
          </select>
        </div>
        <div class="form-hint" id="fs-cron-preview" style="color:var(--navy)"></div>
      </div>

      <div class="modal-actions">
        <button class="btn btn-secondary" id="btn-cancel-fs">Cancel</button>
        <button class="btn btn-primary" id="btn-save-fs">Save &amp; Enable</button>
      </div>
    `);

    // Toggle sections on trigger type change
    function _refreshTriggerUI() {
      const type = document.querySelector('input[name="fs-trigger-type"]:checked')?.value;
      document.getElementById('fs-oneshot-section').style.display = type === 'one-shot' ? '' : 'none';
      document.getElementById('fs-cron-section').style.display    = type === 'cron'     ? '' : 'none';
      _updatePreview();
    }

    function _updatePreview() {
      const type = document.querySelector('input[name="fs-trigger-type"]:checked')?.value;
      if (type === 'one-shot') {
        const val = document.getElementById('fs-fire-at').value;
        const prev = document.getElementById('fs-oneshot-preview');
        if (val) {
          const dt = new Date(val);
          prev.textContent = `Fires at: ${dt.toLocaleString('en-US', { month:'short',
            day:'numeric', year:'numeric', hour:'numeric', minute:'2-digit', timeZoneName:'short' })}`;
        } else {
          prev.textContent = '';
        }
      } else if (type === 'cron') {
        const h    = String(document.getElementById('fs-cron-hour').value   || 9).padStart(2, '0');
        const m    = String(document.getElementById('fs-cron-minute').value || 0).padStart(2, '0');
        const rep  = document.getElementById('fs-cron-repeat').value;
        const dayLabels = { daily:'Every day', mon:'Every Monday', tue:'Every Tuesday',
          wed:'Every Wednesday', thu:'Every Thursday', fri:'Every Friday',
          sat:'Every Saturday', sun:'Every Sunday' };
        document.getElementById('fs-cron-preview').textContent =
          `Fires: ${dayLabels[rep] || 'daily'} at ${h}:${m}`;
      }
    }

    document.querySelectorAll('input[name="fs-trigger-type"]').forEach(r =>
      r.addEventListener('change', _refreshTriggerUI));
    document.getElementById('fs-fire-at').addEventListener('input', _updatePreview);
    document.getElementById('fs-cron-hour').addEventListener('input', _updatePreview);
    document.getElementById('fs-cron-minute').addEventListener('input', _updatePreview);
    document.getElementById('fs-cron-repeat').addEventListener('change', _updatePreview);

    document.getElementById('btn-cancel-fs').addEventListener('click', App.closeModal);

    document.getElementById('btn-save-fs').addEventListener('click', async () => {
      const flowId    = document.getElementById('fs-flow').value.trim();
      const profileId = document.getElementById('fs-profile').value.trim();
      if (!flowId || !profileId) {
        alert('Please select a flow and a profile.');
        return;
      }

      const triggerType = document.querySelector('input[name="fs-trigger-type"]:checked')?.value;
      let trigger;

      if (triggerType === 'one-shot') {
        const fireAt = document.getElementById('fs-fire-at').value;
        if (!fireAt) { alert('Please set a fire date and time.'); return; }
        trigger = { type: 'one-shot', fire_at: new Date(fireAt).toISOString() };
      } else {
        const hour   = parseInt(document.getElementById('fs-cron-hour').value,   10);
        const minute = parseInt(document.getElementById('fs-cron-minute').value, 10);
        const repeat = document.getElementById('fs-cron-repeat').value;
        const weekdayMap = { mon:0, tue:1, wed:2, thu:3, fri:4, sat:5, sun:6 };
        trigger = { type: 'cron', hour, minute };
        if (repeat !== 'daily') trigger.weekday = weekdayMap[repeat];
      }

      const btn = document.getElementById('btn-save-fs');
      btn.disabled = true;
      btn.textContent = 'Saving…';

      const result = await api.scheduleFlow(flowId, profileId, trigger);
      if (!result.ok) {
        alert(`Failed to save schedule: ${result.error || 'unknown error'}`);
        btn.disabled = false;
        btn.textContent = 'Save & Enable';
        return;
      }
      App.closeModal();
      App.navigate('schedules');
    });
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  return { render };
})();
