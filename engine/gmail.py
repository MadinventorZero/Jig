"""Gmail API client — OAuth2 authentication, read inbox, send/reply."""
import base64
from pathlib import Path
from typing import Optional

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Credentials live outside the repo so they can never be accidentally committed.
CREDS_DIR        = Path.home() / ".jig"
CREDENTIALS_FILE = CREDS_DIR / "credentials.json"
TOKEN_FILE       = CREDS_DIR / "token.json"


def is_configured() -> bool:
    return CREDENTIALS_FILE.exists()


def is_authenticated() -> bool:
    if not TOKEN_FILE.exists():
        return False
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        return bool(creds and (creds.valid or creds.refresh_token))
    except Exception:
        return False


def get_service():
    """Return an authenticated Gmail API service, refreshing or prompting OAuth as needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDENTIALS_FILE}. "
                    "Download it from Google Cloud Console and place it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        CREDS_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build('gmail', 'v1', credentials=creds)


def get_authenticated_email(service) -> Optional[str]:
    profile = service.users().getProfile(userId='me').execute()
    return profile.get('emailAddress')


def revoke_token() -> None:
    TOKEN_FILE.unlink(missing_ok=True)


def list_messages(service, sender: str = None, subject_contains: str = None,
                  after_epoch: int = None, max_results: int = 20) -> list[dict]:
    parts = []
    if sender:
        parts.append(f"from:{sender}")
    if subject_contains:
        parts.append(f"subject:\"{subject_contains}\"")
    if after_epoch:
        parts.append(f"after:{after_epoch}")
    query = " ".join(parts)
    result = service.users().messages().list(
        userId='me', q=query, maxResults=max_results
    ).execute()
    return result.get('messages', [])


def get_message(service, message_id: str) -> tuple[str, str, str, str]:
    """Returns (subject, body_text, thread_id, message_id_header)."""
    msg = service.users().messages().get(
        userId='me', id=message_id, format='full'
    ).execute()
    headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
    subject    = headers.get('Subject', '')
    thread_id  = msg.get('threadId', '')
    msg_id_hdr = headers.get('Message-ID', '')
    body = _extract_body(msg['payload'])
    return subject, body, thread_id, msg_id_hdr


def _extract_body(payload: dict) -> str:
    if payload.get('mimeType') == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace') if data else ''
    for part in payload.get('parts', []):
        if part.get('mimeType') == 'text/plain':
            data = part.get('body', {}).get('data', '')
            return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace') if data else ''
        result = _extract_body(part)
        if result:
            return result
    return ''


def send_message(service, to: str, subject: str, body: str,
                 in_reply_to: str = None, thread_id: str = None) -> dict:
    from email.mime.text import MIMEText
    msg = MIMEText(body)
    msg['to'] = to
    msg['subject'] = subject
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References'] = in_reply_to
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body_dict: dict = {'raw': raw}
    if thread_id:
        body_dict['threadId'] = thread_id
    return service.users().messages().send(userId='me', body=body_dict).execute()


def mark_read(service, message_id: str) -> None:
    service.users().messages().modify(
        userId='me', id=message_id,
        body={'removeLabelIds': ['UNREAD']},
    ).execute()
