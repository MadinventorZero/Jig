const ProfilesView = (() => {

  async function render(container) {
    const [profiles, sources] = await Promise.all([
      api.listProfiles(),
      api.listSources(),
    ]);

    container.innerHTML = `
      <div class="view">
        <div class="view-header">
          <div>
            <div class="view-title">Profiles</div>
            <div class="view-subtitle">Manage booking profiles and site-specific settings</div>
          </div>
          <button class="btn btn-primary" id="btn-new-profile">+ New Profile</button>
        </div>

        <div class="table-wrap">
          ${profiles.length === 0
            ? '<div class="table-empty">No profiles yet. Create one to get started.</div>'
            : `<table>
                <thead>
                  <tr><th>Label</th><th>Name</th><th>Email</th><th>Sites</th><th></th></tr>
                </thead>
                <tbody>
                  ${profiles.map(p => `
                    <tr>
                      <td><strong>${p.label}</strong></td>
                      <td>${p.name}</td>
                      <td class="text-muted">${p.email}</td>
                      <td class="text-muted">${Object.keys(p.sites || {}).join(', ') || '—'}</td>
                      <td style="text-align:right">
                        <button class="btn btn-sm btn-secondary btn-edit-profile" data-id="${p.profile_id}">Edit</button>
                        <button class="btn btn-sm btn-danger btn-delete-profile" data-id="${p.profile_id}" style="margin-left:6px">Delete</button>
                      </td>
                    </tr>`).join('')}
                </tbody>
              </table>`}
        </div>
      </div>`;

    container.querySelector('#btn-new-profile')
      .addEventListener('click', () => openProfileModal(null, sources));

    container.querySelectorAll('.btn-edit-profile').forEach(btn =>
      btn.addEventListener('click', async () => {
        const profile = await api.getProfile(btn.dataset.id);
        openProfileModal(profile, sources);
      }));

    container.querySelectorAll('.btn-delete-profile').forEach(btn =>
      btn.addEventListener('click', async () => {
        if (!confirm('Delete this profile?')) return;
        await api.deleteProfile(btn.dataset.id);
        App.navigate('profiles');
      }));
  }

  async function openProfileModal(profile, sources) {
    const isNew = !profile;
    const profileId = profile?.profile_id || await api.newProfileId();
    const sites = profile?.sites || {};

    // Build site tab HTML
    const siteTabs = sources.map(s => `
      <div class="site-tab" id="site-tab-${s.site_id}" style="display:none">
        <div id="site-fields-${s.site_id}"></div>
      </div>`).join('');

    const siteNavItems = sources.map((s, i) => `
      <button class="btn btn-sm ${i === 0 ? 'btn-primary' : 'btn-secondary'} btn-site-tab"
              data-site="${s.site_id}" style="margin-right:6px">${s.label}</button>`).join('');

    App.showModal(`
      <div class="modal-title">${isNew ? 'New Profile' : 'Edit Profile'}</div>

      <div class="section-title" style="margin-top:0">Personal Info</div>
      <div class="form-group">
        <label>Profile Label</label>
        <input type="text" id="p-label" value="${profile?.label || ''}" placeholder="e.g. My Engagement Booking">
      </div>
      <div class="form-row">
        <div class="form-group"><label>Full Name</label>
          <input type="text" id="p-name" value="${profile?.name || ''}"></div>
        <div class="form-group"><label>Phone</label>
          <input type="tel" id="p-phone" value="${profile?.phone || ''}"></div>
      </div>
      <div class="form-group"><label>Address</label>
        <input type="text" id="p-address" value="${profile?.address || ''}"></div>
      <div class="form-row-3">
        <div class="form-group"><label>City</label>
          <input type="text" id="p-city" value="${profile?.city || ''}"></div>
        <div class="form-group"><label>State</label>
          <input type="text" id="p-state" value="${profile?.state || ''}" maxlength="2"></div>
        <div class="form-group"><label>Zip Code</label>
          <input type="text" id="p-zip" value="${profile?.zip_code || ''}"></div>
      </div>
      <div class="form-group"><label>Email Address</label>
        <input type="email" id="p-email" value="${profile?.email || ''}"></div>

      <div class="section-title">Site-Specific Settings</div>
      <div style="margin-bottom:14px">${siteNavItems}</div>
      ${siteTabs}

      <div class="modal-actions">
        <button class="btn btn-secondary" id="btn-cancel-profile">Cancel</button>
        <button class="btn btn-primary" id="btn-save-profile">Save Profile</button>
      </div>
    `);

    // Render site fields
    for (const source of sources) {
      const schema = await api.getSourceSchema(source.site_id);
      const siteData = sites[source.site_id] || {};
      renderSiteFields(source.site_id, schema, siteData);
    }

    // Show first site tab
    if (sources.length) showSiteTab(sources[0].site_id, sources);

    document.querySelectorAll('.btn-site-tab').forEach(btn =>
      btn.addEventListener('click', () => showSiteTab(btn.dataset.site, sources)));

    document.getElementById('btn-cancel-profile')
      .addEventListener('click', App.closeModal);

    document.getElementById('btn-save-profile')
      .addEventListener('click', async () => {
        const sitesData = {};
        sources.forEach(s => {
          const schema = window._siteSchemas?.[s.site_id] || [];
          const data = {};
          schema.forEach(field => {
            const el = document.getElementById(`sf-${s.site_id}-${field.key}`);
            if (el) data[field.key] = el.value;
          });
          sitesData[s.site_id] = data;
        });

        const profileData = {
          profile_id: profileId,
          label:    document.getElementById('p-label').value.trim(),
          name:     document.getElementById('p-name').value.trim(),
          phone:    document.getElementById('p-phone').value.trim(),
          address:  document.getElementById('p-address').value.trim(),
          city:     document.getElementById('p-city').value.trim(),
          state:    document.getElementById('p-state').value.trim(),
          zip_code: document.getElementById('p-zip').value.trim(),
          email:    document.getElementById('p-email').value.trim(),
          sites:    sitesData,
        };

        await api.saveProfile(profileData);
        App.closeModal();
        App.navigate('profiles');
      });
  }

  function renderSiteFields(siteId, schema, currentData) {
    window._siteSchemas = window._siteSchemas || {};
    window._siteSchemas[siteId] = schema;

    const container = document.getElementById(`site-fields-${siteId}`);
    if (!container) return;
    container.innerHTML = schema.map(field => {
      const val = currentData[field.key] || '';
      if (field.type === 'select') {
        return `<div class="form-group">
          <label>${field.label}</label>
          <select id="sf-${siteId}-${field.key}">
            ${field.options.map(o => `<option value="${o}" ${String(o) === String(val) ? 'selected' : ''}>${o}</option>`).join('')}
          </select>
          ${field.hint ? `<div class="form-hint">${field.hint}</div>` : ''}
        </div>`;
      }
      return `<div class="form-group">
        <label>${field.label}</label>
        <input type="${field.type === 'date' ? 'date' : field.type === 'time' ? 'time' : 'text'}"
               id="sf-${siteId}-${field.key}" value="${val}">
        ${field.hint ? `<div class="form-hint">${field.hint}</div>` : ''}
      </div>`;
    }).join('');
  }

  function showSiteTab(siteId, sources) {
    sources.forEach(s => {
      const tab = document.getElementById(`site-tab-${s.site_id}`);
      if (tab) tab.style.display = s.site_id === siteId ? 'block' : 'none';
    });
    document.querySelectorAll('.btn-site-tab').forEach(btn => {
      btn.className = `btn btn-sm ${btn.dataset.site === siteId ? 'btn-primary' : 'btn-secondary'} btn-site-tab`;
    });
  }

  return { render };
})();
