/**
 * App shell — router, modal manager, shared utilities.
 */
const App = (() => {
  const views = {
    dashboard: DashboardView,
    flows:     FlowsView,
    blocks:    BlockLibraryView,
    profiles:  ProfilesView,
    bookings:  BookingsView,
    schedules: SchedulesView,
    trial:     TrialView,
    settings:  SettingsView,
    planner:   PlannerView,
  };

  let _currentView = null;

  function navigate(viewName) {
    _currentView = viewName;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.view === viewName);
    });

    const content = document.getElementById('main-content');
    content.innerHTML = '<div class="loading">Loading...</div>';

    const view = views[viewName];
    if (view) {
      view.render(content).catch(err => {
        content.innerHTML = `<div class="view"><div class="alert alert-danger">
          Failed to load view: ${err.message}</div></div>`;
      });
    }
  }

  function showModal(html) {
    document.getElementById('modal-body').innerHTML = html;
    document.getElementById('modal-overlay').classList.remove('hidden');
  }

  function closeModal() {
    document.getElementById('modal-overlay').classList.add('hidden');
    document.getElementById('modal-body').innerHTML = '';
    window._siteSchemas = {};
  }

  async function showBookingLogs(bookingId) {
    const [booking, logs] = await Promise.all([
      api.getBooking(bookingId),
      api.getBookingLogs(bookingId),
    ]);
    const logLines = logs.map(l =>
      `<div class="log-line log-${l.level}"><span style="opacity:0.5">${l.ts.slice(11,19)}</span> ${l.msg}</div>`
    ).join('') || '<div class="log-line">No log entries.</div>';

    showModal(`
      <div class="modal-title">Booking Logs</div>
      <div style="font-size:13px;margin-bottom:8px">
        <strong>${booking?.target_date || bookingId}</strong>
        &nbsp;·&nbsp;
        <span class="text-muted">${booking?.site_id?.replace(/_/g,' ') || ''}</span>
      </div>
      <div class="log-viewer">${logLines}</div>
      <div class="modal-actions"><button class="btn btn-secondary" onclick="App.closeModal()">Close</button></div>
    `);
  }

  function init() {
    // Nav click handler
    document.getElementById('main-nav').addEventListener('click', e => {
      const item = e.target.closest('.nav-item');
      if (item?.dataset.view) navigate(item.dataset.view);
    });

    // Command palette
    CommandPalette.init();

    // Modal close
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-overlay').addEventListener('click', e => {
      if (e.target === document.getElementById('modal-overlay')) closeModal();
    });

    navigate('dashboard');
  }

  return { navigate, showModal, closeModal, showBookingLogs, init };
})();

window.addEventListener('pywebviewready', App.init);
// Fallback for dev environments without pywebview
if (document.readyState === 'complete') {
  setTimeout(App.init, 200);
} else {
  document.addEventListener('DOMContentLoaded', () => setTimeout(App.init, 200));
}
