# Gmail Setup Guide

The agent uses your Gmail account to send the initial permit form submission email, monitor the inbox for Beverly Hills' rejection response, and send the fallback reply — all as messages on your own account. Nothing is routed through a third-party service.

---

## Prerequisites

- A Google account (the one you want the agent to send/receive from)
- Access to [Google Cloud Console](https://console.cloud.google.com)

---

## Step 1 — Create a Google Cloud project

1. Go to **console.cloud.google.com**
2. Click the project dropdown at the top → **New Project**
3. Name it anything (e.g. `Jig`) and click **Create**

---

## Step 2 — Enable the Gmail API

1. In your project, go to **APIs & Services → Library**
2. Search for **Gmail API**
3. Click the result and hit **Enable**

---

## Step 3 — Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Choose **External** and click **Create**
3. Fill in:
   - **App name**: anything (e.g. `Jig`)
   - **User support email**: your Gmail address
   - **Developer contact email**: your Gmail address
4. Click through the Scopes and Test Users screens — no changes needed there except:
   - Under **Test users**, click **Add users** and add your own Gmail address
5. Save and continue through to the summary

> The app stays in "Testing" mode, which is fine for personal use. Only accounts listed as test users can authorize it.

---

## Step 4 — Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Set **Application type** to **Desktop app**
4. Name it anything and click **Create**
5. A dialog appears — click **Download JSON**

---

## Step 5 — Place credentials.json

Rename the downloaded file to `credentials.json` and move it to:

```
~/.jig/credentials.json
```

Create the directory if it doesn't exist:

```bash
mkdir -p ~/.jig
mv ~/Downloads/client_secret_*.json ~/.jig/credentials.json
```

Keeping credentials in your home directory means they stay outside the project folder and can never be accidentally committed to git.

---

## Step 6 — Connect in the app

1. Launch the app (`Jig.command`)
2. Go to **Settings** in the sidebar
3. Click **Connect Gmail**
4. A browser window opens — sign in with the same Google account
5. Accept the permissions (Gmail read/send access)
6. The Settings page refreshes and shows **Connected as your@gmail.com**

---

## Revoking access

To disconnect, go to **Settings → Disconnect Gmail**. This deletes the local token file (`data/credentials/token.json`). You can also revoke access from your Google account at **myaccount.google.com/permissions**.

---

## What the agent does with Gmail

| Action | When |
|---|---|
| Reads inbox | After form submission, polling for a response from `GreystoneEvents@beverlyhills.org` |
| Sends fallback reply | When a rejection is received and a viable same-day 2-hour slot is found |
| Sends intervention email to yourself | When CAPTCHA appears, no slot is available, or a second rejection arrives |

The agent never reads emails outside of messages from `GreystoneEvents@beverlyhills.org` and never sends email to anyone other than that address and yourself.
