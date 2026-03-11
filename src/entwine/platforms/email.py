"""Email (Gmail) platform adapter using Google API client."""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import structlog

from entwine.platforms.base import PlatformAdapter
from entwine.platforms.settings import EmailSettings

log = structlog.get_logger(__name__)


def _build_gmail_service(settings: EmailSettings) -> Any:
    """Construct an authenticated Gmail API service resource."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
    creds: Credentials | None = None

    token_path = Path(settings.token_json)
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(settings.credentials_json, scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


class EmailLiveAdapter(PlatformAdapter):
    """Real Gmail adapter using the Google API Python client."""

    def __init__(self, settings: EmailSettings) -> None:
        self._settings = settings
        self._service = _build_gmail_service(settings)
        self._user_email = settings.user_email or "me"

    @property
    def platform_name(self) -> str:
        return "email"

    async def send(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        log.info("email.send", action=action)
        if action == "send_email":
            msg = MIMEText(payload.get("body", ""))
            msg["to"] = payload["to"]
            msg["subject"] = payload.get("subject", "(no subject)")
            if self._user_email != "me":
                msg["from"] = self._user_email
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

            # Google API client is synchronous; wrap in executor.
            import asyncio

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: (
                    self._service.users().messages().send(userId="me", body={"raw": raw}).execute()
                ),
            )
            return {
                "status": "ok",
                "platform": "email",
                "action": action,
                "simulated": False,
                "message_id": result.get("id", ""),
            }

        return {"status": "error", "platform": "email", "message": f"Unknown action: {action}"}

    async def read(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        log.info("email.read", query=query, limit=limit)
        import asyncio

        loop = asyncio.get_running_loop()

        results = await loop.run_in_executor(
            None,
            lambda: (
                self._service.users()
                .messages()
                .list(userId="me", q=query, maxResults=limit)
                .execute()
            ),
        )

        messages: list[dict[str, Any]] = []
        for msg_ref in results.get("messages", []):
            msg_data = await loop.run_in_executor(
                None,
                lambda mid=msg_ref["id"]: (
                    self._service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=mid,
                        format="metadata",
                        metadataHeaders=["Subject", "From"],
                    )
                    .execute()
                ),
            )
            headers = {
                h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])
            }
            messages.append(
                {
                    "id": msg_ref["id"],
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                }
            )
        return messages

    def available_actions(self) -> list[str]:
        return ["send_email", "read_inbox"]
