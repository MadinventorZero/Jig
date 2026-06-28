const SettingsView = (() => {

  async function render(container) {
    container.innerHTML = '<div class="view"><div class="loading">Checking Gmail status...</div></div>';

    const status = await api.getGmailStatus();

    container.innerHTML = `
      <div class="view">
        <div class="view-header">
          <div>
            <div class="view-title">Settings</div>
            <div class="view-subtitle">Gmail connection and app configuration</div>
          </div>
        </div>

        <div style="max-width:620px">

          <div class="card">
            <div class="section-title" style="margin-top:0">Gmail Connection</div>

            ${!status.configured ? `
              <div class="alert alert-warning" style="margin-bottom:20px">
                <strong>credentials.json not found.</strong><br>
                Complete the steps below, then place the file at:<br>
                <code style="font-size:11px;word-break:break-all;display:block;margin-top:6px">${status.credentials_path}</code>
              </div>

              <div class="section-title" style="font-size:12px;margin-top:0;margin-bottom:14px">Gmail API Setup Guide</div>

              <ol style="font-size:13px;line-height:1;margin-left:4px;padding-left:0;list-style:none">

                <li style="display:flex;gap:12px;margin-bottom:18px">
                  <span style="background:var(--navy);color:#fff;border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:700;flex-shrink:0;display:flex;align-items:center;justify-content:center">1</span>
                  <div>
                    <div style="font-weight:600;margin-bottom:3px">Create a Google Cloud project</div>
                    <div class="text-muted">Go to <strong>console.cloud.google.com</strong> → click the project dropdown at the top → <strong>New Project</strong>. Name it anything (e.g. "Jig").</div>
                  </div>
                </li>

                <li style="display:flex;gap:12px;margin-bottom:18px">
                  <span style="background:var(--navy);color:#fff;border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:700;flex-shrink:0;display:flex;align-items:center;justify-content:center">2</span>
                  <div>
                    <div style="font-weight:600;margin-bottom:3px">Enable the Gmail API</div>
                    <div class="text-muted">In your project, go to <strong>APIs &amp; Services → Library</strong>. Search for <strong>"Gmail API"</strong> and click <strong>Enable</strong>.</div>
                  </div>
                </li>

                <li style="display:flex;gap:12px;margin-bottom:18px">
                  <span style="background:var(--navy);color:#fff;border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:700;flex-shrink:0;display:flex;align-items:center;justify-content:center">3</span>
                  <div>
                    <div style="font-weight:600;margin-bottom:3px">Configure the OAuth consent screen</div>
                    <div class="text-muted">Go to <strong>APIs &amp; Services → OAuth consent screen</strong>. Choose <strong>External</strong>, fill in an app name, add your Gmail address as both the support email and a test user. You can leave most fields blank.</div>
                  </div>
                </li>

                <li style="display:flex;gap:12px;margin-bottom:18px">
                  <span style="background:var(--navy);color:#fff;border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:700;flex-shrink:0;display:flex;align-items:center;justify-content:center">4</span>
                  <div>
                    <div style="font-weight:600;margin-bottom:3px">Create OAuth credentials</div>
                    <div class="text-muted">Go to <strong>APIs &amp; Services → Credentials → Create Credentials → OAuth client ID</strong>. Choose <strong>Desktop app</strong> as the application type. Click <strong>Create</strong>.</div>
                  </div>
                </li>

                <li style="display:flex;gap:12px;margin-bottom:18px">
                  <span style="background:var(--navy);color:#fff;border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:700;flex-shrink:0;display:flex;align-items:center;justify-content:center">5</span>
                  <div>
                    <div style="font-weight:600;margin-bottom:3px">Download and place credentials.json</div>
                    <div class="text-muted">Click <strong>Download JSON</strong> on the credential you just created. Rename the file to <strong>credentials.json</strong> and move it to:<br>
                    <code style="font-size:11px;word-break:break-all;display:block;margin-top:4px">${status.credentials_path}</code></div>
                  </div>
                </li>

                <li style="display:flex;gap:12px">
                  <span style="background:var(--gold);color:var(--navy);border-radius:50%;width:22px;height:22px;font-size:11px;font-weight:700;flex-shrink:0;display:flex;align-items:center;justify-content:center">6</span>
                  <div>
                    <div style="font-weight:600;margin-bottom:3px">Return here and connect</div>
                    <div class="text-muted">Reload this page — a <strong>Connect Gmail</strong> button will appear. Clicking it opens the Google OAuth consent screen in your browser. Sign in with the same account you used above.</div>
                  </div>
                </li>

              </ol>

              <div class="alert alert-info" style="margin-top:20px;font-size:12px">
                <strong>Why Gmail?</strong> The agent sends the permit form, monitors the inbox for a rejection email from Beverly Hills, and sends a fallback reply — all as self-to-self messages on your own account. No data leaves your machine except the emails themselves.
              </div>

            ` : status.authenticated ? `
              <div class="alert alert-success">
                Connected as <strong>${status.email}</strong>
              </div>
              <p style="font-size:13px;color:var(--muted);margin-bottom:16px">
                The agent will read and send email as this account. Outbound emails go to yourself
                (self-to-self) so you can monitor and respond to intervention prompts.
              </p>
              <button class="btn btn-secondary" id="btn-revoke-gmail">Disconnect Gmail</button>
            ` : `
              <div class="alert alert-info">
                credentials.json found — not yet authenticated.
              </div>
              <p style="font-size:13px;color:var(--muted);margin-bottom:16px">
                Click Connect to open the Google OAuth consent screen in your browser.
                Sign in with the Gmail account you want the agent to use.
              </p>
              <button class="btn btn-primary" id="btn-connect-gmail">Connect Gmail</button>
            `}
          </div>

        </div>
      </div>`;

    const connectBtn = container.querySelector('#btn-connect-gmail');
    if (connectBtn) {
      connectBtn.addEventListener('click', async () => {
        connectBtn.disabled = true;
        connectBtn.textContent = 'Opening browser...';
        const result = await api.startGmailOAuth();
        if (result.ok) {
          App.navigate('settings');
        } else {
          alert(`OAuth failed: ${result.error}`);
          connectBtn.disabled = false;
          connectBtn.textContent = 'Connect Gmail';
        }
      });
    }

    const revokeBtn = container.querySelector('#btn-revoke-gmail');
    if (revokeBtn) {
      revokeBtn.addEventListener('click', async () => {
        if (!confirm('Disconnect Gmail? The agent will not be able to send or read emails until reconnected.')) return;
        await api.revokeGmail();
        App.navigate('settings');
      });
    }
  }

  return { render };
})();
