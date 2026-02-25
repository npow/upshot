"""Gmail API client — OAuth flow and message fetching."""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta
from pathlib import Path
from email.utils import parseaddr

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from upshot.config import get_settings
from upshot.models import EmailData
from upshot.utils.hashing import content_hash

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_PATH = Path("token.json")


def authenticate(interactive: bool = False) -> Credentials:
    """Authenticate with Gmail API, returning credentials.

    Args:
        interactive: If True, run the OAuth consent flow if no token exists.
    """
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    elif not creds or not creds.valid:
        if not interactive:
            raise RuntimeError(
                "No valid Gmail credentials. Run 'upshot auth --setup' first."
            )
        settings = get_settings()
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.gmail_credentials_path, SCOPES
        )
        creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def get_service():
    """Build and return a Gmail API service object."""
    creds = authenticate()
    return build("gmail", "v1", credentials=creds)


def _get_label_ids(service, label_names: list[str]) -> list[str]:
    """Resolve label names to IDs."""
    results = service.users().labels().list(userId="me").execute()
    labels = results.get("labels", [])
    name_to_id = {label["name"]: label["id"] for label in labels}

    label_ids = []
    for name in label_names:
        if name in name_to_id:
            label_ids.append(name_to_id[name])
        else:
            logger.warning("Label '%s' not found in Gmail. Available: %s", name, list(name_to_id))
    return label_ids


def _parse_email(msg: dict, label: str | None = None) -> EmailData:
    """Parse a Gmail API message into an EmailData model."""
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

    sender_full = headers.get("from", "")
    sender_name, sender_email = parseaddr(sender_full)

    # Extract body
    raw_html = ""
    raw_text = ""
    payload = msg.get("payload", {})

    def _extract_parts(part: dict) -> None:
        nonlocal raw_html, raw_text
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            if mime == "text/html":
                raw_html = decoded
            elif mime == "text/plain":
                raw_text = decoded

        for sub_part in part.get("parts", []):
            _extract_parts(sub_part)

    _extract_parts(payload)

    # Parse date
    internal_date_ms = int(msg.get("internalDate", "0"))
    received_at = datetime.fromtimestamp(internal_date_ms / 1000)

    body_for_hash = raw_html or raw_text or ""
    return EmailData(
        gmail_id=msg["id"],
        thread_id=msg.get("threadId"),
        subject=headers.get("subject"),
        sender=sender_name or sender_email,
        sender_email=sender_email,
        received_at=received_at,
        content_hash=content_hash(headers.get("subject", ""), body_for_hash),
        raw_html=raw_html,
        raw_text=raw_text,
        label=label,
    )


def fetch_emails(
    since: datetime | None = None,
    label_names: list[str] | None = None,
    max_results: int = 50,
) -> list[EmailData]:
    """Fetch newsletter emails from Gmail.

    Args:
        since: Only fetch emails after this datetime.
        label_names: Gmail labels to search in.
        max_results: Maximum number of emails to fetch.
    """
    settings = get_settings()
    service = get_service()

    if label_names is None:
        label_names = settings.gmail.labels
    if since is None:
        since = datetime.now() - timedelta(days=settings.gmail.initial_lookback_days)

    label_ids = _get_label_ids(service, label_names)
    if not label_ids:
        logger.warning("No matching labels found. Fetching from INBOX.")
        label_ids = ["INBOX"]

    # Build query
    after_str = since.strftime("%Y/%m/%d")
    query = f"after:{after_str}"

    emails: list[EmailData] = []
    page_token = None

    while len(emails) < max_results:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=label_ids,
                q=query,
                maxResults=min(max_results - len(emails), 50),
                pageToken=page_token,
            )
            .execute()
        )

        messages = results.get("messages", [])
        if not messages:
            break

        for msg_ref in messages:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )
            label = label_names[0] if label_names else None
            emails.append(_parse_email(msg, label))

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    logger.info("Fetched %d emails from Gmail", len(emails))
    return emails
