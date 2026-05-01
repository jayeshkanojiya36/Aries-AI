"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        JARVIS — Email Contact Service                                        ║
║  Resolves names → email addresses from:                                      ║
║    1. Hard-coded contacts dict (fast, no DB needed)                          ║
║    2. PostgreSQL contacts table (production)                                 ║
║    3. Gmail "Sent" folder (fallback auto-discovery)                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional, Tuple, Any

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("jarvis.contacts")

# ── Static contacts — add your own here or load from DB ──────────────────────
# Maps normalized name strings → email addresses.
# You can also load these from environment variables or a YAML/JSON config.
_STATIC_CONTACTS: Dict[str, str] = {
    # Format: "normalized_name": "email@example.com"
    "jayesh": "Kanojiya755Jayesh@gmail.com",
    "dost": "Kanojiya755Jayesh@gmail.com",
    "friend": "Kanojiya755Jayesh@gmail.com",
    "romeo": "romeorajbhar05@gmail.com",
    "boss": "romeorajbhar05@gmail.com",
    "me": "romeorajbhar05@gmail.com",
    
    # ID based contacts as requested by user
    "1": "Kanojiya755Jayesh@gmail.com",
    "2": "romeorajbhar05@gmail.com",
    "3": "romeorajbhar033@gmail.com",
}

# ── Load extra contacts from env (comma-separated "Name:email" pairs) ─────────
_extra = os.getenv("JARVIS_CONTACTS", "")
for _pair in _extra.split(","):
    _pair = _pair.strip()
    if ":" in _pair:
        _name, _email = _pair.split(":", 1)
        _STATIC_CONTACTS[_name.strip().lower()] = _email.strip()


# ══════════════════════════════════════════════════════════════════════════════
# ContactService
# ══════════════════════════════════════════════════════════════════════════════

class ContactService:
    """
    Multi-source contact resolution service.

    Resolution priority:
        1. Static dictionary (fastest)
        2. PostgreSQL ``contacts`` table (production)
        3. Gmail Sent-folder auto-discovery (slowest, fallback only)
    """

    def __init__(self) -> None:
        self._pg_pool   = None       # asyncpg connection pool (optional)
        self._gmail_svc = None       # GmailService instance (for sent-folder search)
        self._cache: Dict[str, Optional[str]] = {}   # in-memory LRU-ish cache

    # ── Setup ──────────────────────────────────────────────────────────────

    async def initialize(self, gmail_service=None) -> None:
        """
        Optional: pass a GmailService for Gmail-based contact discovery.
        Optional: configure PostgreSQL via CONTACTS_PG_DSN env var.
        """
        self._gmail_svc = gmail_service
        pg_dsn = os.getenv("CONTACTS_PG_DSN", "")
        if pg_dsn:
            try:
                import asyncpg
                self._pg_pool = await asyncpg.create_pool(pg_dsn, min_size=1, max_size=5)
                log.info("[Contacts] PostgreSQL pool connected")
            except ImportError:
                log.warning("[Contacts] asyncpg not installed — PostgreSQL disabled")
            except Exception as exc:
                log.warning(f"[Contacts] PostgreSQL connect failed: {exc}")

    # ── Public API ─────────────────────────────────────────────────────────

    async def resolve(self, name: str) -> Optional[str]:
        """
        Resolve a contact name to an email address.

        Args:
            name: Free-form name string (e.g. "Rahul", "rahul sharma", "boss")

        Returns:
            Email address string or None if not found.

        Example:
            email = await contacts.resolve("Rahul")
            # → "rahul@example.com"
        """
        key = self._normalize(name)

        # 1. Cache hit
        if key in self._cache:
            result = self._cache[key]
            log.debug(f"[Contacts] Cache hit: {name!r} → {result}")
            return result

        # 2. Direct ID/Exact Match in static dict
        email = self._from_static(key)
        if email:
            self._cache[key] = email
            log.info(f"[Contacts] Static/ID match: {name!r} → {email}")
            return email

        # 3. Self-resolution logic ("me", "myself", "my email", etc.)
        if key in ("me", "myself", "my", "my email", "my address", "mere", "apne"):
            # Try to resolve user's own email from environment or Gmail profile
            self_email = (
                os.getenv("USER_EMAIL") or
                os.getenv("MY_EMAIL") or
                os.getenv("GMAIL_OAUTH_EMAIL") or
                os.getenv("GMAIL_USER")
            )
            if not self_email and self._gmail_svc:
                self_email = self._gmail_svc.authenticated_email
            
            if self_email:
                log.info(f"[Contacts] Resolved 'me' to self: {self_email}")
                self._cache[key] = self_email
                return self_email

        # 3. PostgreSQL
        if self._pg_pool:
            email = await self._from_postgres(key)
            if email:
                self._cache[key] = email
                log.info(f"[Contacts] DB match: {name!r} → {email}")
                return email

        # 4. Gmail sent-folder
        if self._gmail_svc:
            email = await self._from_gmail_sent(key)
            if email:
                self._cache[key] = email
                log.info(f"[Contacts] Gmail auto-discover: {name!r} → {email}")
                return email

        log.warning(f"[Contacts] Could not resolve: {name!r}")
        self._cache[key] = None
        return None

    async def resolve_or_raise(self, name: str) -> str:
        """Like resolve(), but raises ValueError if not found."""
        email = await self.resolve(name)
        if not email:
            raise ValueError(
                f"No email found for contact: '{name}'. "
                "Please add them to your contacts or provide the full email address."
            )
        return email

    async def add_contact(self, name: str, email: str) -> None:
        """
        Add or update a contact in the static dict + cache.
        For production persistence, also writes to PostgreSQL.
        """
        key = self._normalize(name)
        _STATIC_CONTACTS[key] = email
        self._cache[key]      = email
        log.info(f"[Contacts] Added: {name!r} → {email}")

        if self._pg_pool:
            await self._upsert_postgres(name, email)

    async def list_contacts(self) -> List[Dict[str, str]]:
        """Return all known contacts as a list of {name, email} dicts."""
        contacts = [{"name": k, "email": v}
                    for k, v in _STATIC_CONTACTS.items()]
        if self._pg_pool:
            try:
                async with self._pg_pool.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT name, email FROM contacts ORDER BY name"
                    )
                    for row in rows:
                        contacts.append({
                            "name":  row["name"],
                            "email": row["email"],
                        })
            except Exception as exc:
                log.warning(f"[Contacts] list_contacts DB error: {exc}")
        return contacts

    # ── Resolution backends ────────────────────────────────────────────────

    def _from_static(self, key: str) -> Optional[str]:
        """Exact + partial match against static dict."""
        if key in _STATIC_CONTACTS:
            return _STATIC_CONTACTS[key]
        # Partial: key is contained in a static key (e.g. "rahul" in "rahul sharma")
        for static_key, email in _STATIC_CONTACTS.items():
            if key in static_key or static_key in key:
                return email
        return None

    async def _from_postgres(self, key: str) -> Optional[str]:
        """Query PostgreSQL for partial name match."""
        try:
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT email FROM contacts
                    WHERE LOWER(name) LIKE $1
                    LIMIT 1
                    """,
                    f"%{key}%",
                )
                return row["email"] if row else None
        except Exception as exc:
            log.warning(f"[Contacts] PostgreSQL query error: {exc}")
            return None

    async def _from_gmail_sent(self, key: str) -> Optional[str]:
        """Search Gmail Sent folder to auto-discover an email address."""
        if not self._gmail_svc or not self._gmail_svc.is_ready():
            return None
        try:
            success, emails, _ = await self._gmail_svc.read_recent_emails(
                max_results=20,
                query=f"in:sent {key}",
            )
            if success and emails:
                # Extract email from "To" header of results
                for email_obj in emails:
                    extracted = self._extract_email_from_string(email_obj.sender)
                    if extracted and key in email_obj.sender.lower():
                        return extracted
        except Exception as exc:
            log.debug(f"[Contacts] Gmail auto-discover error: {exc}")
        return None

    async def _upsert_postgres(self, name: str, email: str) -> None:
        """Upsert a contact into PostgreSQL."""
        try:
            async with self._pg_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO contacts (name, email)
                    VALUES ($1, $2)
                    ON CONFLICT (email)
                    DO UPDATE SET name = EXCLUDED.name
                    """,
                    name, email,
                )
        except Exception as exc:
            log.warning(f"[Contacts] upsert DB error: {exc}")

    # ── Utilities ──────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(name: str) -> str:
        """Lowercase, strip padding, and handle common Hindi aliases."""
        n = name.strip().lower()
        # Common Hindi → English aliases for relation/contact types
        aliases = {
            "दोस्त": "dost",
            "friend": "dost",
            "भाई": "brother",
            "pappa": "papa",
            "पिताजी": "papa",
            "मम्मी": "mom",
            "माताजी": "mom",
            "office": "work",
            "दफ्तर": "work",
        }
        # Remove "id" or "number" prefix if user says "id 1" or "number 1"
        n = re.sub(r'^(id|number|no|id no|id number)\s+', '', n)
        
        return aliases.get(n, n)

    @staticmethod
    def _extract_email_from_string(text: str) -> Optional[str]:
        """Extract the first valid email address from a string."""
        match = re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text, re.IGNORECASE)
        return match.group(0) if match else None

    async def close(self) -> None:
        if self._pg_pool:
            await self._pg_pool.close()
            log.info("[Contacts] PostgreSQL pool closed")


# ══════════════════════════════════════════════════════════════════════════════
# Module-level singleton
# ══════════════════════════════════════════════════════════════════════════════

_contact_service: Optional[ContactService] = None


async def get_contact_service(gmail_service: Optional[Any] = None) -> ContactService:
    """Return (or lazily create) the module-level ContactService singleton."""
    global _contact_service
    if _contact_service is None:
        _contact_service = ContactService()
        await _contact_service.initialize(gmail_service=gmail_service)
    return _contact_service
