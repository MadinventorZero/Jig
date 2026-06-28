const DashboardView = (() => {
  const STATUS_ORDER = ['running', 'intervention_required', 'submitted',
                        'fallback_submitted', 'confirmed', 'permit_granted',
                        'rejected', 'failed', 'cancelled', 'idle'];

  function badgeClass(status) {
    const map = {
      running: 'badge-running', submitted: 'badge-info',
      fallback_submitted: 'badge-info', confirmed: 'badge-success',
      permit_granted: 'badge-success', rejected: 'badge-danger',
      failed: 'badge-danger', cancelled: 'badge-muted',
      idle: 'badge-muted', intervention_required: 'badge-warning',
    };
    return map[status] || 'badge-muted';
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function fmtDateTime(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  }

  async function render(container) {
    container.innerHTML = '<div class="loading">Loading dashboard...</div>';

    const [bookings, schedules] = await Promise.all([
      api.listBookings(),
      api.listSchedules(),
    ]);

    const active   = bookings.filter(b => ['running', 'submitted', 'fallback_submitted', 'intervention_required'].includes(b.status));
    const upcoming = schedules.filter(s => s.enabled).sort((a, b) => a.fire_at.localeCompare(b.fire_at));
    const recent   = bookings.slice(0, 8);

    container.innerHTML = `
      <div class="view">
        <div class="view-header">
          <div>
            <div class="view-title">Dashboard</div>
            <div class="view-subtitle">Booking activity overview</div>
          </div>
        </div>

        <div class="card-grid">
          <div class="stat-card">
            <div class="stat-label">Total Bookings</div>
            <div class="stat-value">${bookings.length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Active / In Progress</div>
            <div class="stat-value">${active.length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Confirmed / Granted</div>
            <div class="stat-value">${bookings.filter(b => ['confirmed','permit_granted'].includes(b.status)).length}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Scheduled Runs</div>
            <div class="stat-value">${upcoming.length}</div>
          </div>
        </div>

        ${upcoming.length ? `
        <div class="card mb-16" style="margin-bottom:20px">
          <div class="section-title" style="margin-top:0">Next Scheduled Run</div>
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
            <div>
              <strong>${upcoming[0].label}</strong>
              <span class="text-muted" style="margin-left:12px">Target: ${upcoming[0].target_date}</span>
            </div>
            <div class="text-muted" style="font-size:13px">Fires at ${fmtDateTime(upcoming[0].fire_at)}</div>
          </div>
        </div>` : ''}

        <div class="section-title">Recent Bookings</div>
        <div class="table-wrap">
          ${recent.length === 0
            ? '<div class="table-empty">No bookings yet. Create a profile and schedule a run.</div>'
            : `<table>
                <thead>
                  <tr>
                    <th>Target Date</th>
                    <th>Site</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  ${recent.map(b => `
                    <tr class="clickable" data-booking-id="${b.booking_id}">
                      <td>${b.target_date}</td>
                      <td>${b.site_id.replace(/_/g, ' ')}</td>
                      <td><span class="badge ${badgeClass(b.status)}">${b.status.replace(/_/g, ' ')}</span></td>
                      <td class="text-muted">${fmtDate(b.created_at)}</td>
                      <td><button class="btn btn-sm btn-secondary" data-booking-id="${b.booking_id}">Logs</button></td>
                    </tr>`).join('')}
                </tbody>
              </table>`}
        </div>
      </div>`;

    container.querySelectorAll('[data-booking-id]').forEach(el => {
      el.addEventListener('click', () => App.showBookingLogs(el.dataset.bookingId));
    });
  }

  return { render };
})();
