"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ARIES — Advanced Gmail Email Tools (LiveKit function_tool compatible)       ║
║                                                                              ║
║  Replaces the old SMTP-based send_email.py with Gmail API OAuth2.            ║
║                                                                              ║
║  Tools exposed to Aries agent:                                              ║
║    • send_email_smart       — intent-aware send (voice/text NL input)        ║
║    • reply_to_last_email    — contextual reply to most recent thread         ║
║    • read_recent_emails     — fetch recent inbox messages                    ║
║    • draft_email            — save as Gmail draft (no send)                  ║
║    • send_email_direct      — low-level send (explicit args)                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

Quick wiring in agent.py:

    from Tools.send_email import (
        send_email_smart,
        reply_to_last_email,
        read_recent_emails,
        draft_email,
        send_email_direct,
    )

Then add them to the tools=[ ... ] list in Assistant.__init__().
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional, Any

from dotenv import load_dotenv
from livekit.agents import function_tool

load_dotenv()

log = logging.getLogger("aries.email.tools")

# ── Email status broadcaster (real-time frontend updates) ─────────────────────
try:
    from Tools.email_status_broadcaster import (
        notify_sending,
        notify_success,
        notify_failed,
    )
    _BROADCASTER_AVAILABLE = True
except ImportError:
    _BROADCASTER_AVAILABLE = False
    log.debug("[email_tools] Broadcaster not available – status updates disabled")

    # Provide no-op stubs so the rest of the code works unchanged
    async def notify_sending(*a, **kw) -> str: return ""
    async def notify_success(*a, **kw) -> None: pass
    async def notify_failed(*a, **kw) -> None: pass

# ── Lazy service accessors (avoids circular imports + speeds startup) ─────────

async def _gmail():
    from Tools.gmail_service import get_gmail_service
    return await get_gmail_service()

async def _contacts(gmail_svc: Optional[Any] = None):
    from Tools.email_contact_service import get_contact_service
    return await get_contact_service(gmail_service=gmail_svc)

async def _processor():
    from Tools.email_intent_processor import get_intent_processor
    return await get_intent_processor()


# ── Email validation helper ───────────────────────────────────────────────────
def _is_email(text: str) -> bool:
    return bool(re.match(r"^[\w.+-]+@[\w-]+\.[a-z]{2,}$", text, re.IGNORECASE))


# ══════════════════════════════════════════════════════════════════════════════
# Tool 1 — Smart Email (intent-based, voice-friendly)
# ══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def send_email_smart(
    user_command: str,
    confirmed: bool = False,
    attachment_path: Optional[str] = None,
) -> str:
    """
    Send an email using natural language understanding.

    Interprets the user's voice or text command in any language (Hindi/English),
    resolves the recipient from contacts, generates a professional email via LLM,
    shows a confirmation preview, and sends only when confirmed=True.

    Args:
        user_command:    Natural language command, e.g.
                         "Rahul ko meeting ke baare mein mail bhejo"
                         "Send a follow-up email to Priya about the project deadline"
        confirmed:       Set True ONLY after user has seen the preview and approved.
                         First call (confirmed=False) returns a preview for approval.
        attachment_path: Optional absolute path to a file to attach.

    Returns:
        str: Preview text (if confirmed=False) or send confirmation (if confirmed=True)

    Examples:
        # First call — get preview
        preview = await send_email_smart("Rahul ko meeting reminder bhejo")

        # Second call — user said yes, send it
        result = await send_email_smart("Rahul ko meeting reminder bhejo", confirmed=True)
    """
    try:
        # ── 1. Extract intent from user command ──────────────────────────
        proc   = await _processor()
        intent = await proc.extract_intent(user_command)

        if intent.action not in ("send", "draft"):
            return (
                f"⚠️ Intent detected as '{intent.action}', not 'send'. "
                "Please use a specific email command."
            )

        # ── 2. Resolve recipient email ───────────────────────────────────
        gmail_svc     = await _gmail()
        contact_svc   = await _contacts(gmail_svc)

        recipient_email = intent.recipient_email
        recipient_name  = intent.recipient_name

        # Direct email given in command (e.g. "email to boss@co.com")
        if not recipient_email and recipient_name:
            if _is_email(recipient_name):
                recipient_email = recipient_name
                recipient_name  = recipient_email.split("@")[0]
            else:
                recipient_email = await contact_svc.resolve(recipient_name)

        # ── Final safety-net: scan raw command + try default "me" ─────────────
        if not recipient_email:
            # 1. Regex scan for direct address in command
            raw_email_match = re.search(
                r'[\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+',
                user_command, re.IGNORECASE
            )
            if raw_email_match:
                recipient_email = raw_email_match.group(0)
                if not recipient_name:
                    recipient_name = recipient_email.split("@")[0]
                log.info(f"[send_email_smart] Recovered from raw command: {recipient_email}")
            
            # 2. Default to Boss (me) if still empty
            if not recipient_email:
                recipient_email = await contact_svc.resolve("me")
                if recipient_email:
                    recipient_name = "Boss (Me)"
                    log.info(f"[send_email_smart] Defaulted to 'me' -> {recipient_email}")

        if not recipient_email:
            return (
                f"❓ I couldn't find an email address for '{recipient_name or 'the recipient'}'. "
                "Please provide the full email address or add them to contacts by Name or ID.\n"
                "Example: 'Email ID 1 about the meeting' or 'Send mail to Jayesh'"
            )

        # ── 3. Safeguard: Check if sending to self ───────────────────────────
        if recipient_email == gmail_svc.authenticated_email and not confirmed:
            log.info(f"[send_email_smart] Recipient is the same as sender: {recipient_email}")
            # We don't block it, but we make sure the user knows in the preview.
            recipient_name = f"Self ({recipient_name})" if recipient_name != "Boss (Me)" else recipient_name

        # ── 4. Retrieve memory context (Local ChromaDB) ───────────────────
        memory_context = ""
        try:
            from memory.memory_manager import MemoryManager
            # Use local memory search for context
            mem_mgr = MemoryManager(user_id="aries_email")
            await mem_mgr.initialize()
            # We wait a brief moment for the vector layer if needed, 
            # though it usually loads in background.
            results = await mem_mgr.search_memory(
                query=f"{recipient_name} {intent.topic}",
                top_k=3
            )
            if results:
                memory_context = " | ".join([r.text for r in results])
                log.info(f"[send_email_smart] Found {len(results)} relevant memories.")
        except Exception as exc:
            log.debug(f"[send_email_smart] Local memory fetch skipped: {exc}")

        # ── 5. Generate email via LLM ────────────────────────────────────
        generated = await proc.generate_email(
            intent          = intent,
            recipient_email = recipient_email,
            memory_context  = memory_context,
        )

        # ── 6. Handle attachment ─────────────────────────────────────────
        attachments = []
        if attachment_path:
            from pathlib import Path
            if Path(attachment_path).exists():
                attachments.append(attachment_path)
            else:
                log.warning(f"[send_email_smart] Attachment not found: {attachment_path}")

        # ── 7. Show preview if not yet confirmed ─────────────────────────
        if not confirmed:
            preview = proc.build_confirmation_preview(
                generated      = generated,
                recipient_email = recipient_email,
                recipient_name  = recipient_name,
                attachments     = attachments,
                is_draft        = (intent.action == "draft"),
            )
            # Store the generated content in a temp cache so second call reuses it
            _intent_cache[_cache_key(user_command)] = {
                "intent":           intent,
                "generated":        generated,
                "recipient_email":  recipient_email,
                "recipient_name":   recipient_name,
                "attachments":      attachments,
                "ts":               asyncio.get_event_loop().time(),
            }
            return preview

        # ── 8. User confirmed — retrieve cached email if available ────────
        cached = _intent_cache.get(_cache_key(user_command))
        if cached and (asyncio.get_event_loop().time() - cached["ts"] < 300):
            intent          = cached["intent"]
            generated       = cached["generated"]
            recipient_email = cached["recipient_email"]
            recipient_name  = cached["recipient_name"]
            attachments     = cached["attachments"]

        # ── 9. Build and send / draft ─────────────────────────────────────
        from Tools.gmail_service import EmailMessage
        msg = EmailMessage(
            to          = recipient_email,
            subject     = generated.subject,
            body        = generated.body,
            html_body   = generated.html_body,
            attachments = attachments,
            tone        = generated.tone,
        )

        if intent.action == "draft":
            ok, draft_info, detail = await gmail_svc.create_draft(msg)
            if ok:
                return f"📝 Draft saved!\n{detail}\nDraft ID: {draft_info.get('draft_id', '')}"
            return f"❌ Draft failed: {detail}"

        # ── Notify frontend: sending in progress ──────────────────────────
        record_id = await notify_sending(
            recipient     = recipient_email,
            subject       = generated.subject,
            action        = "sent",
            tone          = generated.tone,
            has_attachment= bool(attachments),
        )

        ok, summary, detail = await gmail_svc.send_email(msg)
        if not ok:
            await notify_failed(record_id, detail, recipient_email, generated.subject)
            return f"❌ Send failed: {detail}"

        # ── 10. Notify frontend: success ───────────────────────────────────
        await notify_success(
            record_id  = record_id,
            message_id = summary.message_id if summary else "",
            recipient  = recipient_email,
            subject    = generated.subject,
            action     = "sent",
        )

        # ── 11. Store in memory ───────────────────────────────────────────
        try:
            from memory import MemoryManager, MemoryType
            log.info(f"[send_email_smart] Email sent: {summary.to} | {summary.subject}")
        except Exception:
            pass

        return (
            f"✅ Email sent successfully!\n"
            f"To      : {recipient_name} <{recipient_email}>\n"
            f"Subject : {generated.subject}\n"
            f"Tone    : {generated.tone.capitalize()}\n"
            f"ID      : {summary.message_id if summary else 'N/A'}"
        )

    except ValueError as exc:
        return f"⚠️ {exc}"
    except Exception as exc:
        log.error(f"[send_email_smart] Unexpected error: {exc}", exc_info=True)
        return f"❌ Email error: {exc}"


# ── Intent cache (in-memory, short TTL) ──────────────────────────────────────
_intent_cache: dict = {}

def _cache_key(utterance: str) -> str:
    import hashlib
    return hashlib.md5(utterance.strip().lower().encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# Tool 2 — Reply to Last Email
# ══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def reply_to_last_email(
    reply_instructions: str,
    confirmed: bool        = False,
    tone: str              = "formal",
    search_query: str      = "in:inbox",
) -> str:
    """
    Fetch the most recent email thread and generate a contextual reply using LLM.

    Args:
        reply_instructions: What to say in the reply, in natural language.
                            E.g. "politely decline the meeting" or
                            "confirm attendance and ask for agenda"
        confirmed:          Set True after user approves the preview.
        tone:               "formal" | "casual" | "executive"
        search_query:       Gmail search query to find the thread.
                            Default: "in:inbox" (most recent inbox message)

    Returns:
        str: Preview (first call) or send confirmation (second call with confirmed=True)
    """
    try:
        gmail_svc = await _gmail()
        proc      = await _processor()

        # ── 1. Fetch last thread ─────────────────────────────────────────
        ok, thread_info, msg = await gmail_svc.get_last_thread(query=search_query)
        if not ok or not thread_info:
            return f"📭 No email thread found. {msg}"

        # ── 2. Generate reply ────────────────────────────────────────────
        generated = await proc.generate_reply(
            thread_info       = thread_info,
            user_instructions = reply_instructions,
            tone              = tone,
        )

        sender_email = ""
        sender_raw   = thread_info.get("sender", "")
        match = re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", sender_raw, re.IGNORECASE)
        if match:
            sender_email = match.group(0)

        if not confirmed:
            preview = proc.build_confirmation_preview(
                generated       = generated,
                recipient_email = sender_email,
                recipient_name  = sender_raw.split("<")[0].strip(),
                is_reply        = True,
            )
            # Cache for second call
            _intent_cache[f"reply_{thread_info['thread_id']}"] = {
                "thread_info":   thread_info,
                "generated":     generated,
                "sender_email":  sender_email,
                "ts":            asyncio.get_event_loop().time(),
            }
            return (
                f"📬 Latest thread: '{thread_info['subject']}'\n"
                f"From: {thread_info['sender']}\n"
                f"───\n{preview}"
            )

        # ── 3. Send reply ────────────────────────────────────────────────
        cached = _intent_cache.get(f"reply_{thread_info['thread_id']}")
        if cached and (asyncio.get_event_loop().time() - cached["ts"] < 300):
            generated    = cached["generated"]
            sender_email = cached["sender_email"]
            thread_info  = cached["thread_info"]

        if not sender_email:
            return "❌ Could not determine reply-to email address from thread."

        from Tools.gmail_service import EmailMessage
        reply_msg = EmailMessage(
            to                   = sender_email,
            subject              = generated.subject,
            body                 = generated.body,
            html_body            = generated.html_body,
            reply_to_thread_id   = thread_info.get("thread_id"),
            reply_to_message_id  = thread_info.get("last_message_id_header"),
            tone                 = tone,
        )

        # Notify frontend: reply sending in progress
        record_id = await notify_sending(
            recipient = sender_email,
            subject   = generated.subject,
            action    = "replied",
            tone      = tone,
        )

        ok, summary, detail = await gmail_svc.send_email(reply_msg)
        if not ok:
            await notify_failed(record_id, detail, sender_email, generated.subject)
            return f"❌ Reply failed: {detail}"

        # Notify frontend: reply success
        await notify_success(
            record_id  = record_id,
            message_id = summary.message_id if summary else "",
            recipient  = sender_email,
            subject    = generated.subject,
            action     = "replied",
        )

        return (
            f"✅ Reply sent!\n"
            f"To      : {sender_email}\n"
            f"Subject : {generated.subject}\n"
            f"Thread  : {thread_info.get('thread_id', 'N/A')}"
        )

    except Exception as exc:
        log.error(f"[reply_to_last_email] Error: {exc}", exc_info=True)
        return f"❌ Reply error: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Tool 3 — Read Recent Emails
# ══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def read_recent_emails(
    count: int         = 5,
    search_query: str  = "",
    unread_only: bool  = False,
) -> str:
    """
    Read and summarize recent emails from Gmail inbox.

    Args:
        count:        Number of emails to fetch (1–20)
        search_query: Gmail search query, e.g. "from:boss@company.com"
                      or "subject:invoice" or "has:attachment"
        unread_only:  If True, only show unread emails

    Returns:
        str: Formatted summary of recent emails

    Examples:
        await read_recent_emails(5)
        await read_recent_emails(3, search_query="from:hr@company.com")
        await read_recent_emails(10, unread_only=True)
    """
    try:
        gmail_svc   = await _gmail()
        count       = max(1, min(count, 20))
        query       = search_query
        label_ids   = ["UNREAD"] if unread_only else None

        if unread_only and not query:
            query = "is:unread"
        elif unread_only:
            query += " is:unread"

        ok, emails, msg = await gmail_svc.read_recent_emails(
            max_results = count,
            query       = query,
            label_ids   = label_ids,
        )

        if not ok:
            return f"❌ Failed to read emails: {msg}"

        if not emails:
            return "📭 No emails found matching your criteria."

        lines = [f"📬 {len(emails)} Email(s) Found\n{'─' * 45}"]
        for i, email in enumerate(emails, 1):
            lines.append(
                f"\n[{i}] From    : {email.sender}\n"
                f"     Subject : {email.subject}\n"
                f"     Date    : {email.date}\n"
                f"     Preview : {email.snippet[:120]}..."
            )
        lines.append(f"\n{'─' * 45}")
        return "\n".join(lines)

    except Exception as exc:
        log.error(f"[read_recent_emails] Error: {exc}", exc_info=True)
        return f"❌ Error reading emails: {exc}"


# ══════════════════════════════════════════════════════════════════════════════
# Tool 4 — Draft Email
# ══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def draft_email(
    user_command: str,
    attachment_path: Optional[str] = None,
) -> str:
    """
    Create a Gmail draft (not sent) using natural language.

    Same as send_email_smart but always saves as draft without sending.
    No confirmation needed since no email is actually sent.

    Args:
        user_command:    Natural language command describing the email.
        attachment_path: Optional path to a file to attach to the draft.

    Returns:
        str: Draft creation confirmation with draft ID.
    """
    # Modify command to hint "draft" action for intent extraction
    return await send_email_smart(
        user_command    = user_command + " (save as draft, do not send)",
        confirmed       = True,
        attachment_path = attachment_path,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tool 5 — Direct Email Send (explicit args, no NL processing)
# ══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def send_email_direct(
    to_email: str,
    subject: str,
    body: str,
    cc_email: Optional[str]        = None,
    bcc_email: Optional[str]       = None,
    attachment_path: Optional[str] = None,
    tone: str                      = "formal",
) -> str:
    """
    Send an email with explicit parameters (bypasses NL intent processing).

    Use this when all email fields are already known. For natural language
    commands, use send_email_smart instead.

    Args:
        to_email:        Recipient email address (required)
        subject:         Email subject line (required)
        body:            Plain-text email body (required)
        cc_email:        CC recipient email (optional)
        bcc_email:       BCC recipient email (optional)
        attachment_path: Absolute path to attachment file (optional)
        tone:            "formal" | "casual" | "executive"

    Returns:
        str: Success confirmation or error message

    Example:
        await send_email_direct(
            to_email = "boss@company.com",
            subject  = "Project Update",
            body     = "Hi,\n\nPlease find the update below...",
        )
    """
    try:
        # Validate email addresses
        if not _is_email(to_email):
            return f"❌ Invalid recipient email: {to_email}"
        if cc_email and not _is_email(cc_email):
            return f"❌ Invalid CC email: {cc_email}"
        if bcc_email and not _is_email(bcc_email):
            return f"❌ Invalid BCC email: {bcc_email}"

        # Build attachment list
        attachments = []
        if attachment_path:
            from pathlib import Path
            p = Path(attachment_path)
            if not p.exists():
                return f"❌ Attachment file not found: {attachment_path}"
            attachments.append(attachment_path)

        gmail_svc = await _gmail()

        from Tools.gmail_service import EmailMessage
        msg = EmailMessage(
            to          = to_email,
            subject     = subject,
            body        = body,
            cc          = cc_email,
            bcc         = bcc_email,
            attachments = attachments,
            tone        = tone,
        )

        # Notify frontend: sending in progress
        record_id = await notify_sending(
            recipient     = to_email,
            subject       = subject,
            action        = "sent",
            tone          = tone,
            cc            = cc_email or "",
            has_attachment= bool(attachment_path),
        )

        ok, summary, detail = await gmail_svc.send_email(msg)
        if not ok:
            await notify_failed(record_id, detail, to_email, subject)
            return f"❌ {detail}"

        # Notify frontend: success
        await notify_success(
            record_id  = record_id,
            message_id = summary.message_id if summary else "",
            recipient  = to_email,
            subject    = subject,
            action     = "sent",
        )

        log.info(f"[send_email_direct] Sent → {to_email} | {subject}")
        return (
            f"✅ Email sent!\n"
            f"To      : {to_email}\n"
            f"Subject : {subject}\n"
            f"ID      : {summary.message_id if summary else 'N/A'}"
        )

    except Exception as exc:
        log.error(f"[send_email_direct] Error: {exc}", exc_info=True)
        return f"❌ Email error: {exc}"
