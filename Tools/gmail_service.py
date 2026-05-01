"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        JARVIS — Gmail API Service (OAuth2, Async-Safe, Production)          ║
║  Handles: Auth · Send · Draft · Reply · Read · Attachments · Rate Limiting  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage:
    svc = GmailService()
    await svc.initialize()
    result = await svc.send_email(to="x@y.com", subject="Hi", body="Hello")
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import time
from dataclasses import dataclass, field
from email.mime.application import MIMEApplication
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
log = logging.getLogger("jarvis.email")

# ── OAuth2 Scopes (read + send + compose) ────────────────────────────────────
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

# ── Paths (PyInstaller-safe) ──────────────────────────────────────────────────
#
# Problem: PyInstaller one-file mode extracts everything to a temp _MEI* folder.
#          __file__ points THERE, not to the real exe directory.
#          gmail_credentials.json / gmail_token.json live NEXT TO agent.exe,
#          so we must use sys.executable's parent when frozen.
#
# Resolution priority (highest → lowest):
#   1. GMAIL_CREDENTIALS_PATH / GMAIL_TOKEN_PATH env vars  (Electron sets these)
#   2. Next to sys.executable  (frozen EXE – the correct location)
#   3. Next to __file__/../..  (normal Python dev mode)

import sys as _sys

def _resolve_base_dir() -> Path:
    """Return the directory that contains agent.exe (frozen) or the project root (dev)."""
    if getattr(_sys, "frozen", False):
        # Running as PyInstaller one-file EXE
        # sys.executable = C:\...\backend\agent.exe
        return Path(_sys.executable).parent
    # Running as plain Python
    return Path(__file__).resolve().parent.parent

_BASE_DIR = _resolve_base_dir()

_CREDENTIALS_PATH = Path(os.getenv(
    "GMAIL_CREDENTIALS_PATH",
    str(_BASE_DIR / "gmail_credentials.json")
))
_TOKEN_PATH = Path(os.getenv(
    "GMAIL_TOKEN_PATH",
    str(_BASE_DIR / "gmail_token.json")
))

# ── Rate-limit config ─────────────────────────────────────────────────────────
_RATE_LIMIT_MAX    = int(os.getenv("EMAIL_RATE_LIMIT_MAX",    "20"))
_RATE_LIMIT_WINDOW = float(os.getenv("EMAIL_RATE_LIMIT_WINDOW", "60.0"))  # seconds

# ── Retry config ──────────────────────────────────────────────────────────────
_MAX_RETRIES     = int(os.getenv("EMAIL_MAX_RETRIES", "3"))
_RETRY_BASE_WAIT = float(os.getenv("EMAIL_RETRY_BASE_WAIT", "2.0"))  # seconds

# ── Whitelisted email actions ─────────────────────────────────────────────────
ALLOWED_EMAIL_ACTIONS: frozenset = frozenset({
    "send", "draft", "reply", "read", "search", "thread",
})


# ══════════════════════════════════════════════════════════════════════════════
# Data Models
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EmailMessage:
    """Structured email message model."""
    to: str
    subject: str
    body: str
    cc: Optional[str]         = None
    bcc: Optional[str]        = None
    reply_to_thread_id: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    attachments: List[str]    = field(default_factory=list)   # local file paths
    html_body: Optional[str]  = None
    tone: str                 = "formal"              # formal | casual | executive


@dataclass
class EmailSummary:
    """Compact email summary for memory storage."""
    message_id: str
    thread_id: str
    to: str
    subject: str
    snippet: str
    timestamp: str
    action: str                # sent | drafted | replied
    tone: str


@dataclass
class RawEmail:
    """Parsed incoming email."""
    message_id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    snippet: str
    date: str
    labels: List[str]


# ══════════════════════════════════════════════════════════════════════════════
# Rate-Limiter
# ══════════════════════════════════════════════════════════════════════════════

class _RateLimiter:
    """Sliding-window token-bucket rate limiter (asyncio-safe)."""

    def __init__(self, max_calls: int = _RATE_LIMIT_MAX,
                 window: float = _RATE_LIMIT_WINDOW) -> None:
        self._max    = max_calls
        self._window = window
        self._calls: List[float] = []
        self._lock   = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until a slot is available within the rate window."""
        async with self._lock:
            now = time.monotonic()
            # Purge expired timestamps
            self._calls = [t for t in self._calls if t > now - self._window]
            if len(self._calls) >= self._max:
                oldest  = self._calls[0]
                wait_s  = self._window - (now - oldest)
                log.warning(f"[RateLimit] Email rate limit hit — waiting {wait_s:.1f}s")
                await asyncio.sleep(wait_s + 0.05)
                self._calls = [t for t in self._calls if t > time.monotonic() - self._window]
            self._calls.append(time.monotonic())


# ══════════════════════════════════════════════════════════════════════════════
# GmailService — Core Service Class
# ══════════════════════════════════════════════════════════════════════════════

class GmailService:
    """
    Production-grade async Gmail API service.

    All blocking Google API calls are dispatched to a thread-pool via
    ``asyncio.get_event_loop().run_in_executor(None, ...)`` so they
    never block the LiveKit event loop.

    Thread-safety: ``_creds`` is refreshed inside the executor while
    a per-instance asyncio.Lock serializes concurrent refresh attempts.
    """

    def __init__(self) -> None:
        self._creds: Optional[Credentials] = None
        self._service: Any                 = None
        self._user_email: Optional[str]    = None
        self._rate_limiter                 = _RateLimiter()
        self._refresh_lock                 = asyncio.Lock()
        self._ready                        = False

    # ── Initialization ─────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Load / refresh OAuth2 credentials and build the Gmail service."""
        # Log resolved paths so issues are visible in the backend log
        log.info(
            f"[GmailService] Credentials: {_CREDENTIALS_PATH} (exists={_CREDENTIALS_PATH.exists()})"
        )
        log.info(
            f"[GmailService] Token      : {_TOKEN_PATH} (exists={_TOKEN_PATH.exists()})"
        )
        if getattr(_sys, "frozen", False):
            log.info(f"[GmailService] Running frozen EXE — base dir: {_BASE_DIR}")
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._load_credentials_sync)
            self._service = await loop.run_in_executor(None, self._build_service_sync)
            # ── Mark ready BEFORE profile call so _ensure_ready() won't fire ──
            self._ready = True
            self._user_email = await self._get_authenticated_email()
            log.info(f"[GmailService] Authenticated as: {self._user_email}")
        except FileNotFoundError as exc:
            self._ready = False
            log.error(f"[GmailService] credentials JSON not found: {exc}")
            raise
        except RefreshError as exc:
            self._ready = False
            log.error(f"[GmailService] Token refresh failed — delete gmail_token.json and re-run oauth setup: {exc}")
            raise
        except Exception as exc:
            self._ready = False
            log.error(f"[GmailService] Initialization failed: {exc}")
            raise

    def _load_credentials_sync(self) -> None:
        """Synchronous credential loading+refresh (run in executor)."""
        creds = None

        # 1. Load existing token
        if _TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), GMAIL_SCOPES)
            log.debug("[Auth] Loaded token from disk")

        # 2. Refresh or re-authorize
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                log.info("[Auth] Access token refreshed successfully")
                self._save_token_sync(creds)
            except RefreshError:
                log.warning("[Auth] Refresh failed — need full re-auth")
                creds = None

        if not creds or not creds.valid:
            if not _CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail OAuth credentials not found at: {_CREDENTIALS_PATH}\n"
                    "Run `python gmail_oauth_setup.py` to complete OAuth2 flow."
                )
            flow  = InstalledAppFlow.from_client_secrets_file(
                str(_CREDENTIALS_PATH), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)
            log.info("[Auth] New OAuth2 token obtained via browser flow")
            self._save_token_sync(creds)

        self._creds = creds

    def _save_token_sync(self, creds: Credentials) -> None:
        """Persist token to disk (run in executor)."""
        _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        log.debug(f"[Auth] Token saved → {_TOKEN_PATH}")

    def _build_service_sync(self) -> Any:
        """Build authenticated Gmail API client (run in executor)."""
        return build("gmail", "v1", credentials=self._creds, cache_discovery=False)

    async def _ensure_ready(self) -> None:
        """Guard: raise if service is not initialized."""
        if not self._ready or not self._service:
            raise RuntimeError(
                "GmailService is not initialized. Call `await svc.initialize()` first."
            )

    async def _refresh_if_needed(self) -> None:
        """Auto-refresh expired token before an API call."""
        if not self._creds or not self._creds.expired:
            return
        async with self._refresh_lock:
            if not self._creds.expired:
                return  # another task already refreshed
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, lambda: self._creds.refresh(Request()))
                self._service = await loop.run_in_executor(None, self._build_service_sync)
                await loop.run_in_executor(None, lambda: self._save_token_sync(self._creds))
                log.info("[Auth] Auto-refreshed expiring token")
            except RefreshError as exc:
                log.error(f"[Auth] Auto-refresh failed: {exc}")
                raise

    # ── Internal API executor ──────────────────────────────────────────────

    async def _execute(self, request_fn, *args) -> Any:
        """
        Execute a Gmail API call in a thread pool with:
        - Rate limiting
        - Auto token refresh
        - Exponential backoff retry
        """
        await self._ensure_ready()
        await self._rate_limiter.acquire()
        await self._refresh_if_needed()

        loop = asyncio.get_event_loop()
        last_exc: Optional[Exception] = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = await loop.run_in_executor(None, request_fn, *args)
                return result
            except HttpError as exc:
                status = exc.resp.status if exc.resp else 0
                if status in (429, 500, 502, 503):
                    wait = _RETRY_BASE_WAIT ** attempt
                    log.warning(
                        f"[API] HTTP {status} on attempt {attempt}/{_MAX_RETRIES} "
                        f"— retrying in {wait:.1f}s"
                    )
                    await asyncio.sleep(wait)
                    last_exc = exc
                elif status == 401:
                    # Token might have just expired; try one refresh
                    log.warning("[API] 401 Unauthorized — attempting token refresh")
                    await self._refresh_if_needed()
                    last_exc = exc
                else:
                    log.error(f"[API] Unrecoverable HTTP {status}: {exc}")
                    raise
            except asyncio.TimeoutError:
                log.warning(f"[API] Timeout on attempt {attempt}/{_MAX_RETRIES}")
                last_exc = asyncio.TimeoutError()
            except Exception as exc:
                log.error(f"[API] Unexpected error: {exc}", exc_info=True)
                raise

        raise RuntimeError(
            f"Gmail API call failed after {_MAX_RETRIES} retries. Last error: {last_exc}"
        )

    # ── Authenticated user ─────────────────────────────────────────────────

    async def _get_authenticated_email(self) -> str:
        """
        Return the authenticated Gmail address (me profile).

        NOTE: Calls the API directly via run_in_executor — does NOT go through
        _execute() — because this is called during initialize() and _execute()
        internally calls _ensure_ready() which would raise before _ready is set.
        """
        loop = asyncio.get_event_loop()
        def _call():
            return self._service.users().getProfile(userId="me").execute()
        try:
            profile = await loop.run_in_executor(None, _call)
            return profile.get("emailAddress", "unknown@gmail.com")
        except Exception as exc:
            log.warning(f"[Auth] Could not fetch profile email: {exc}")
            return "unknown@gmail.com"

    # ══════════════════════════════════════════════════════════════════════
    # Email Construction Helpers
    # ══════════════════════════════════════════════════════════════════════

    def _build_mime_message(self, msg: EmailMessage) -> MIMEMultipart:
        """Construct a MIME message from an EmailMessage dataclass."""
        mime = MIMEMultipart("mixed")
        mime["From"]    = self._user_email
        mime["To"]      = msg.to
        mime["Subject"] = msg.subject
        if msg.cc:
            mime["Cc"]  = msg.cc
        if msg.bcc:
            mime["Bcc"] = msg.bcc

        # Thread reply headers
        if msg.reply_to_message_id:
            mime["In-Reply-To"] = msg.reply_to_message_id
            mime["References"]  = msg.reply_to_message_id

        # Body
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(msg.body, "plain", "utf-8"))
        if msg.html_body:
            alt.attach(MIMEText(msg.html_body, "html", "utf-8"))
        mime.attach(alt)

        # Attachments
        for file_path_str in msg.attachments:
            file_path = Path(file_path_str)
            if not file_path.exists():
                log.warning(f"[Attachment] File not found, skipping: {file_path}")
                continue
            mime.attach(self._build_attachment(file_path))

        return mime

    @staticmethod
    def _build_attachment(file_path: Path) -> MIMEBase:
        """Detect MIME type and return appropriate MIME part for an attachment."""
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type is None:
            mime_type = "application/octet-stream"

        main_type, sub_type = mime_type.split("/", 1)
        data = file_path.read_bytes()

        if main_type == "text":
            part = MIMEText(data.decode("utf-8", errors="replace"), _subtype=sub_type)
        elif main_type == "image":
            part = MIMEImage(data, _subtype=sub_type)
        elif main_type == "audio":
            part = MIMEAudio(data, _subtype=sub_type)
        elif main_type == "application":
            part = MIMEApplication(data, _subtype=sub_type)
        else:
            part = MIMEBase(main_type, sub_type)
            part.set_payload(data)

        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=file_path.name,
        )
        return part

    @staticmethod
    def _encode_message(mime: MIMEMultipart) -> str:
        """Base64url-encode a MIME message for Gmail API."""
        return base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")

    # ══════════════════════════════════════════════════════════════════════
    # Public API — Send
    # ══════════════════════════════════════════════════════════════════════

    async def send_email(self, msg: EmailMessage) -> Tuple[bool, EmailSummary, str]:
        """
        Send an email via Gmail API.

        Returns:
            (success: bool, summary: EmailSummary, detail_msg: str)
        """
        mime     = self._build_mime_message(msg)
        raw      = self._encode_message(mime)
        body     = {"raw": raw}
        if msg.reply_to_thread_id:
            body["threadId"] = msg.reply_to_thread_id

        def _call():
            return (
                self._service.users()
                .messages()
                .send(userId="me", body=body)
                .execute()
            )

        try:
            result = await self._execute(_call)
            summary = EmailSummary(
                message_id = result.get("id", ""),
                thread_id  = result.get("threadId", ""),
                to         = msg.to,
                subject    = msg.subject,
                snippet    = msg.body[:120].replace("\n", " "),
                timestamp  = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                action     = "replied" if msg.reply_to_thread_id else "sent",
                tone       = msg.tone,
            )
            log.info(
                f"[Send] Email sent → {msg.to} | subject={msg.subject!r} "
                f"| id={summary.message_id}"
            )
            return True, summary, f"✅ Email successfully sent to {msg.to}"
        except Exception as exc:
            log.error(f"[Send] Failed: {exc}", exc_info=True)
            return False, None, f"❌ Failed to send email: {exc}"

    # ══════════════════════════════════════════════════════════════════════
    # Public API — Draft
    # ══════════════════════════════════════════════════════════════════════

    async def create_draft(self, msg: EmailMessage) -> Tuple[bool, Dict, str]:
        """
        Create an email draft (not sent).

        Returns:
            (success: bool, draft_info: dict, detail_msg: str)
        """
        mime = self._build_mime_message(msg)
        raw  = self._encode_message(mime)
        body = {"message": {"raw": raw}}
        if msg.reply_to_thread_id:
            body["message"]["threadId"] = msg.reply_to_thread_id

        def _call():
            return (
                self._service.users()
                .drafts()
                .create(userId="me", body=body)
                .execute()
            )

        try:
            result = await self._execute(_call)
            draft_id = result.get("id", "")
            info     = {
                "draft_id":  draft_id,
                "to":        msg.to,
                "subject":   msg.subject,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            log.info(f"[Draft] Created draft_id={draft_id} → {msg.to}")
            return True, info, f"📝 Draft saved (id: {draft_id})"
        except Exception as exc:
            log.error(f"[Draft] Failed: {exc}", exc_info=True)
            return False, {}, f"❌ Failed to create draft: {exc}"

    # ══════════════════════════════════════════════════════════════════════
    # Public API — Read
    # ══════════════════════════════════════════════════════════════════════

    async def read_recent_emails(
        self,
        max_results: int = 5,
        query: str = "",
        label_ids: Optional[List[str]] = None,
    ) -> Tuple[bool, List[RawEmail], str]:
        """
        Fetch recent emails from Gmail inbox.

        Args:
            max_results: Number of messages to return (max 50)
            query:       Gmail search query string, e.g. 'from:boss@co.com'
            label_ids:   List of Gmail label IDs to filter

        Returns:
            (success, list_of_RawEmail, detail_msg)
        """
        max_results = min(max_results, 50)

        list_params: Dict[str, Any] = {
            "userId":     "me",
            "maxResults": max_results,
        }
        if query:
            list_params["q"] = query
        if label_ids:
            list_params["labelIds"] = label_ids

        def _list_call():
            return self._service.users().messages().list(**list_params).execute()

        try:
            list_result = await self._execute(_list_call)
        except Exception as exc:
            log.error(f"[Read] list failed: {exc}")
            return False, [], f"❌ Failed to list emails: {exc}"

        messages_meta = list_result.get("messages", [])
        if not messages_meta:
            return True, [], "📭 No emails found"

        emails: List[RawEmail] = []
        for meta in messages_meta[:max_results]:
            msg_id = meta["id"]
            try:
                raw_email = await self._fetch_single_message(msg_id)
                if raw_email:
                    emails.append(raw_email)
            except Exception as exc:
                log.warning(f"[Read] Could not fetch message {msg_id}: {exc}")

        log.info(f"[Read] Retrieved {len(emails)} emails")
        return True, emails, f"📧 Retrieved {len(emails)} recent emails"

    async def _fetch_single_message(self, message_id: str) -> Optional[RawEmail]:
        """Fetch and parse a single Gmail message."""
        def _call():
            return (
                self._service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

        data = await self._execute(_call)
        if not data:
            return None

        headers  = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        body_text = self._extract_body(data.get("payload", {}))

        return RawEmail(
            message_id = data.get("id", ""),
            thread_id  = data.get("threadId", ""),
            sender     = headers.get("From", "Unknown"),
            subject    = headers.get("Subject", "(no subject)"),
            body       = body_text,
            snippet    = data.get("snippet", ""),
            date       = headers.get("Date", ""),
            labels     = data.get("labelIds", []),
        )

    @staticmethod
    def _extract_body(payload: Dict) -> str:
        """Recursively extract plain-text body from a Gmail message payload."""
        mime_type = payload.get("mimeType", "")

        if mime_type == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

        if mime_type.startswith("multipart/"):
            for part in payload.get("parts", []):
                body = GmailService._extract_body(part)
                if body:
                    return body

        return ""

    # ══════════════════════════════════════════════════════════════════════
    # Public API — Thread (Reply context)
    # ══════════════════════════════════════════════════════════════════════

    async def get_last_thread(
        self,
        query: str = "in:inbox",
    ) -> Tuple[bool, Optional[Dict], str]:
        """
        Fetch the most recent email thread matching `query`.

        Returns a dict with:
            thread_id, last_message_id, last_message_id_header,
            subject, sender, snippet, messages_count, last_body
        """
        def _list_call():
            return (
                self._service.users()
                .messages()
                .list(userId="me", q=query, maxResults=1)
                .execute()
            )

        try:
            list_res = await self._execute(_list_call)
        except Exception as exc:
            log.error(f"[Thread] list failed: {exc}")
            return False, None, f"❌ Failed to fetch thread: {exc}"

        messages = list_res.get("messages", [])
        if not messages:
            return True, None, "📭 No thread found"

        # Get the full thread
        thread_id = messages[0].get("threadId", "")

        def _thread_call():
            return (
                self._service.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            )

        try:
            thread_data = await self._execute(_thread_call)
        except Exception as exc:
            log.error(f"[Thread] get failed: {exc}")
            return False, None, f"❌ Failed to load thread detail: {exc}"

        thread_messages = thread_data.get("messages", [])
        if not thread_messages:
            return True, None, "📭 Thread is empty"

        last_msg   = thread_messages[-1]
        headers    = {h["name"]: h["value"]
                      for h in last_msg.get("payload", {}).get("headers", [])}
        body_text  = self._extract_body(last_msg.get("payload", {}))

        thread_info = {
            "thread_id":             thread_id,
            "last_message_id":       last_msg.get("id", ""),
            "last_message_id_header": headers.get("Message-ID", ""),
            "subject":               headers.get("Subject", "(no subject)"),
            "sender":                headers.get("From", "Unknown"),
            "snippet":               last_msg.get("snippet", ""),
            "messages_count":        len(thread_messages),
            "last_body":             body_text[:2000],
        }
        log.info(
            f"[Thread] Fetched thread_id={thread_id} | "
            f"{len(thread_messages)} messages | subject={thread_info['subject']!r}"
        )
        return True, thread_info, f"📧 Thread found: {thread_info['subject']!r}"

    # ══════════════════════════════════════════════════════════════════════
    # Public API — Search
    # ══════════════════════════════════════════════════════════════════════

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
    ) -> Tuple[bool, List[RawEmail], str]:
        """
        Search Gmail using the same query syntax as the Gmail search box.
        e.g. 'from:hr@company.com subject:offer'
        """
        return await self.read_recent_emails(
            max_results=max_results,
            query=query,
        )

    # ══════════════════════════════════════════════════════════════════════
    # Utility
    # ══════════════════════════════════════════════════════════════════════

    @property
    def authenticated_email(self) -> Optional[str]:
        return self._user_email

    def is_ready(self) -> bool:
        return self._ready


# ══════════════════════════════════════════════════════════════════════════════
# Module-level singleton (lazy-initialized on first use)
# ══════════════════════════════════════════════════════════════════════════════

_gmail_service: Optional[GmailService] = None
_init_lock: Optional[asyncio.Lock]     = None


async def get_gmail_service() -> GmailService:
    """
    Return the module-level GmailService singleton.
    Thread-safe across coroutines via asyncio.Lock.
    """
    global _gmail_service, _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()

    if _gmail_service and _gmail_service.is_ready():
        return _gmail_service

    async with _init_lock:
        if _gmail_service and _gmail_service.is_ready():
            return _gmail_service                  # double-check after lock
        svc = GmailService()
        await svc.initialize()
        _gmail_service = svc
        return _gmail_service
