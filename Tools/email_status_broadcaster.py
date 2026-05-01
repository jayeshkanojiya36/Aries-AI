"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   JARVIS — Email Status Broadcaster                                         ║
║                                                                              ║
║   Sends real-time email events to the Electron/React frontend via the       ║
║   LiveKit data channel.  Uses the SAME mechanism as PLAY_SONG / SCAN_RESULT ║
║   so no extra sockets or IPC ports are needed.                               ║
║                                                                              ║
║   Message types emitted:                                                     ║
║     EMAIL_SENDING  — email is about to be sent (show spinner)               ║
║     EMAIL_SUCCESS  — email sent OK  (show green toast + add to history)     ║
║     EMAIL_FAILED   — send failed    (show red alert  + add to history)      ║
║     EMAIL_HISTORY  — full history dump on request                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional

log = logging.getLogger("jarvis.email.broadcaster")

# ---------------------------------------------------------------------------
# Module-level reference to the LiveKit room (set by agent.py at startup)
# ---------------------------------------------------------------------------
_livekit_room = None   # type: ignore[assignment]


def set_livekit_room(room) -> None:
    """
    Call this from agent.py after the LiveKit room is ready so the broadcaster
    can publish data messages to the frontend.

    Example in agent.py:
        from Tools.email_status_broadcaster import set_livekit_room
        set_livekit_room(ctx.room)
    """
    global _livekit_room
    _livekit_room = room
    log.info("[EmailBroadcaster] LiveKit room registered")


# ---------------------------------------------------------------------------
# In-memory email history (last 50 emails, survives until process restart)
# ---------------------------------------------------------------------------
_MAX_HISTORY = 50

@dataclass
class EmailRecord:
    id: str                         # unique record id  (timestamp-based)
    timestamp: str                  # ISO-8601 UTC
    recipient: str
    subject: str
    status: str                     # "sending" | "success" | "failed"
    action: str                     # "sent" | "replied" | "drafted"
    message_id: str = ""            # Gmail message id (populated on success)
    error: str = ""                 # error text (populated on failure)
    tone: str = "formal"
    cc: str = ""
    has_attachment: bool = False

_email_history: List[EmailRecord] = []
_history_lock = asyncio.Lock()


async def _add_to_history(record: EmailRecord) -> None:
    async with _history_lock:
        _email_history.append(record)
        # Keep only the last N records
        if len(_email_history) > _MAX_HISTORY:
            _email_history[:] = _email_history[-_MAX_HISTORY:]


def get_email_history() -> List[dict]:
    """Return a copy of the email history as plain dicts (safe to serialize)."""
    return [asdict(r) for r in list(_email_history)]


# ---------------------------------------------------------------------------
# LiveKit publish helper
# ---------------------------------------------------------------------------

async def _publish(payload: dict) -> None:
    """Serialize and publish a dict to the LiveKit data channel (best-effort)."""
    if _livekit_room is None:
        log.debug("[EmailBroadcaster] No LiveKit room – skipping publish: %s", payload.get("type"))
        return
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        await _livekit_room.local_participant.publish_data(data, reliable=True)
        log.debug("[EmailBroadcaster] Published %s", payload.get("type"))
    except Exception as exc:
        log.warning("[EmailBroadcaster] Publish failed: %s", exc)


# ---------------------------------------------------------------------------
# Public API  — call these from send_email.py / gmail_service.py
# ---------------------------------------------------------------------------

async def notify_sending(
    recipient: str,
    subject: str,
    action: str = "sent",
    cc: str = "",
    tone: str = "formal",
    has_attachment: bool = False,
) -> str:
    """
    Notify the frontend that an email is being sent right now.
    Returns a unique record_id that you must pass to notify_success / notify_failed.

    Usage:
        record_id = await notify_sending(recipient="a@b.com", subject="Hi")
        ok, summary, detail = await gmail_svc.send_email(msg)
        if ok:
            await notify_success(record_id, summary.message_id, summary.to, summary.subject)
        else:
            await notify_failed(record_id, detail, recipient, subject)
    """
    record_id = f"email_{int(time.time() * 1000)}"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    record = EmailRecord(
        id=record_id,
        timestamp=ts,
        recipient=recipient,
        subject=subject,
        status="sending",
        action=action,
        tone=tone,
        cc=cc,
        has_attachment=has_attachment,
    )
    await _add_to_history(record)

    await _publish({
        "type": "EMAIL_SENDING",
        "record_id": record_id,
        "timestamp": ts,
        "recipient": recipient,
        "subject": subject,
        "action": action,
        "cc": cc,
        "tone": tone,
        "has_attachment": has_attachment,
    })
    log.info("[EmailBroadcaster] SENDING → %s | %s", recipient, subject)
    return record_id


async def notify_success(
    record_id: str,
    message_id: str,
    recipient: str,
    subject: str,
    action: str = "sent",
) -> None:
    """
    Notify the frontend that the email was sent successfully.
    Updates the existing history record in-place.
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Update in-place
    async with _history_lock:
        for r in _email_history:
            if r.id == record_id:
                r.status = "success"
                r.message_id = message_id
                r.timestamp = ts
                break

    await _publish({
        "type": "EMAIL_SUCCESS",
        "record_id": record_id,
        "timestamp": ts,
        "recipient": recipient,
        "subject": subject,
        "message_id": message_id,
        "action": action,
    })
    log.info("[EmailBroadcaster] SUCCESS → %s | id=%s", recipient, message_id)


async def notify_failed(
    record_id: str,
    error: str,
    recipient: str,
    subject: str,
) -> None:
    """
    Notify the frontend that the email send failed.
    Updates the existing history record in-place.
    """
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Update in-place
    async with _history_lock:
        for r in _email_history:
            if r.id == record_id:
                r.status = "failed"
                r.error = error
                r.timestamp = ts
                break

    await _publish({
        "type": "EMAIL_FAILED",
        "record_id": record_id,
        "timestamp": ts,
        "recipient": recipient,
        "subject": subject,
        "error": error,
    })
    log.warning("[EmailBroadcaster] FAILED → %s | %s", recipient, error)


async def broadcast_history() -> None:
    """
    Push the full email history to the frontend (e.g. on reconnect or on demand).
    The frontend merges this into its local state.
    """
    history = get_email_history()
    await _publish({
        "type": "EMAIL_HISTORY",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "records": history,
    })
    log.info("[EmailBroadcaster] Broadcasted %d history records", len(history))
