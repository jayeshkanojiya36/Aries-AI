"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        JARVIS — Email Intent Processor (LLM-Powered + Regex Fallback)       ║
║  Parses voice/text intent → generates subject, body, tone + confirmation    ║
║                                                                              ║
║  EXE-Safe: Works even when google-generativeai is missing in PyInstaller    ║
║  by falling back to robust regex-based extraction.                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

Responsibilities:
    1. Extract email intent from natural language (Hindi/English/mixed)
    2. Resolve recipient name → email via ContactService
    3. Generate smart subject + body via Gemini LLM (with regex fallback)
    4. Detect tone (formal / casual / executive)
    5. Build human-readable confirmation preview
    6. Store email summary in vector memory after sending
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("jarvis.email.intent")

# ── Unified API key resolution ────────────────────────────────────────────────
# Electron injects GEMINI_API_KEY; plain Python uses GOOGLE_API_KEY.
# Accept EITHER so the intent processor works in both modes.
def _get_api_key() -> str:
    return (
        os.getenv("GEMINI_API_KEY", "")
        or os.getenv("GOOGLE_API_KEY", "")
        or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY", "")
    )


# ══════════════════════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EmailIntent:
    """Structured result of intent extraction from a user utterance."""
    action: str                   # "send" | "draft" | "reply" | "read" | "search"
    recipient_name: str           = ""
    recipient_email: str          = ""
    topic: str                    = ""
    extra_context: str            = ""
    tone: str                     = "formal"   # formal | casual | executive
    attachments: list             = None
    raw_utterance: str            = ""

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []


@dataclass
class GeneratedEmail:
    """LLM-generated email content."""
    subject: str
    body: str
    tone: str
    html_body: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# Prompts
# ══════════════════════════════════════════════════════════════════════════════

_INTENT_EXTRACTION_PROMPT = """
You are Jarvis, an AI assistant. The user gave a voice or text command to send/manage an email.

Analyze the following user message and extract email intent as JSON.

User message: "{utterance}"

Return ONLY valid JSON with this exact schema:
{{
  "action": "<send|draft|reply|read|search>",
  "recipient_name": "<person's name if mentioned, else empty string>",
  "recipient_email": "<direct email if mentioned, else empty string>",
  "topic": "<brief topic/purpose of email in English>",
  "extra_context": "<any extra instructions: urgency, attachment mention, etc.>",
  "tone": "<formal|casual|executive>"
}}

Rules:
- action "send" = user wants to send a new email
- action "draft" = user wants to save a draft (not send yet)
- action "reply" = user wants to reply to the last email
- action "read" = user wants to read recent emails
- action "search" = user wants to search for a specific email
- Tone "executive" = high-level, very brief and direct
- Tone "formal" = professional and polite
- Tone "casual" = friendly and conversational
- If tone is ambiguous, default to "formal"

Output ONLY the JSON object. No explanation, no markdown.
"""

_EMAIL_GENERATION_PROMPT = """
You are Jarvis, an AI email assistant.

Generate a professional email based on:
- Subject (optional hint): {subject_hint}
- Recipient: {recipient}
- Topic / Purpose: {topic}
- Tone: {tone}
- Context from memory: {memory_context}
- Extra instructions: {extra_context}

Requirements:
- The email must feel natural and human-written, not robotic
- Tone guide:
    * formal → professional, respectful, grammatically correct
    * casual → friendly, warm, relaxed language
    * executive → very brief, bullet-pointed if needed, no filler words
- Language: match the language/mix from the topic field (Hindi/English mix is fine)
- Do NOT include a greeting like "Dear [Name]," unless tone is formal
- Do NOT sign with a placeholder — use just: "Regards,\nJarvis"

Return ONLY valid JSON:
{{
  "subject": "<generated email subject>",
  "body": "<plain-text email body>",
  "html_body": "<same body in clean HTML, no inline CSS>"
}}
"""

_REPLY_GENERATION_PROMPT = """
You are Jarvis, an AI email assistant.

Generate a reply to the following email thread:

Original email:
Subject: {original_subject}
From: {original_sender}
Body:
{original_body}

Reply instructions from user: {user_instructions}
Tone: {tone}
Memory context: {memory_context}

Requirements:
- The reply should reference the original email naturally
- Match the specified tone
- Keep it concise

Return ONLY valid JSON:
{{
  "subject": "Re: {original_subject}",
  "body": "<plain-text reply body>",
  "html_body": "<same reply in HTML>"
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# EmailIntentProcessor
# ══════════════════════════════════════════════════════════════════════════════

class EmailIntentProcessor:
    """
    LLM-powered email intent processor with regex fallback.

    Tries two Gemini client libraries in order:
      1. google-generativeai  (legacy genai package)
      2. google-genai         (new google.genai package, already in requirements)

    If both fail (EXE mode, missing package, no API key), falls back to
    robust regex-based intent extraction so emails still work.
    """

    def __init__(self) -> None:
        self._llm_client = None          # google.generativeai GenerativeModel
        self._genai_client = None        # google.genai Client  (fallback)
        self._model_name = os.getenv("GEMINI_EMAIL_MODEL", "gemini-2.0-flash")
        self._llm_ready = False

    async def initialize(self) -> None:
        """Initialize Gemini client — tries both library variants."""
        api_key = _get_api_key()
        if not api_key:
            log.warning("[IntentProcessor] No Gemini API key found — regex-only fallback mode")
            return

        # ── Attempt 1: google-generativeai (legacy) ───────────────────────────
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=api_key)
            self._llm_client = genai.GenerativeModel(self._model_name)
            self._llm_ready = True
            log.info(f"[IntentProcessor] google-generativeai ready — model={self._model_name}")
            return
        except ImportError:
            log.info("[IntentProcessor] google-generativeai not installed, trying google-genai")
        except Exception as exc:
            log.warning(f"[IntentProcessor] google-generativeai init error: {exc}")

        # ── Attempt 2: google-genai (new SDK, always bundled) ─────────────────
        try:
            from google import genai as new_genai  # type: ignore
            self._genai_client = new_genai.Client(api_key=api_key)
            self._llm_ready = True
            log.info(f"[IntentProcessor] google-genai client ready — model={self._model_name}")
        except Exception as exc:
            log.warning(f"[IntentProcessor] google-genai init error: {exc} — regex-only fallback")

    async def _call_llm(self, prompt: str, timeout: float = 20.0) -> str:
        """Call Gemini API in a thread pool. Tries legacy then new SDK."""
        import asyncio

        if not self._llm_ready:
            return "{}"

        loop = asyncio.get_event_loop()

        # ── Try google-generativeai ───────────────────────────────────────────
        if self._llm_client:
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self._llm_client.generate_content(prompt),
                    ),
                    timeout=timeout,
                )
                return response.text.strip()
            except asyncio.TimeoutError:
                log.warning("[IntentProcessor] LLM call timed out (genai legacy)")
                return "{}"
            except Exception as exc:
                if "429" in str(exc) or "quota" in str(exc).lower():
                    log.warning(f"[IntentProcessor] Gemini Quota Exceeded (429) — falling back to regex/hardcoded logic.")
                else:
                    log.warning(f"[IntentProcessor] LLM error (genai legacy): {exc}")
                return "{}"

        # ── Try google-genai (new SDK) ────────────────────────────────────────
        if self._genai_client:
            try:
                from google.genai import types as _gt  # type: ignore
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self._genai_client.models.generate_content(
                            model=self._model_name,
                            contents=prompt,
                        ),
                    ),
                    timeout=timeout,
                )
                return response.text.strip()
            except asyncio.TimeoutError:
                log.warning("[IntentProcessor] LLM call timed out (google-genai)")
                return "{}"
            except Exception as exc:
                if "429" in str(exc) or "quota" in str(exc).lower():
                    log.warning(f"[IntentProcessor] Gemini Quota Exceeded (429) — falling back to regex/hardcoded logic.")
                else:
                    log.warning(f"[IntentProcessor] LLM error (google-genai): {exc}")
                return "{}"

        return "{}"

    @staticmethod
    def _parse_json_safely(raw: str) -> Dict[str, Any]:
        """Strip markdown fences and parse JSON safely."""
        raw = raw.strip()
        # Strip ```json ... ``` or ``` ... ``` fences
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE)
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            # Last resort: try to find a {...} block somewhere in the string
            match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            log.warning(f"[IntentProcessor] JSON parse error: {exc} | raw={raw[:200]}")
            return {}

    # ── Regex-based fallback intent extraction ─────────────────────────────

    @staticmethod
    def _extract_intent_regex(utterance: str) -> Dict[str, Any]:
        """
        Pure regex extraction — no LLM needed.

        Handles patterns like:
          "send email to boss@co.com about meeting"
          "Rahul ko mail bhejo"
          "email john at john@gmail.com"
          "draft message for priya about project"
          "reply to last email"
        """
        u = utterance.lower().strip()
        result: Dict[str, Any] = {
            "action": "send",
            "recipient_name": "",
            "recipient_email": "",
            "topic": utterance,
            "extra_context": "",
            "tone": "formal",
        }

        # ── Action detection ──────────────────────────────────────────────
        if re.search(r'\b(draft|save|save as draft)\b', u):
            result["action"] = "draft"
        elif re.search(r'\b(reply|respond|jawab)\b', u):
            result["action"] = "reply"
        elif re.search(r'\b(read|check|dekho|dekhao|show)\b.*\b(email|mail|inbox)\b', u):
            result["action"] = "read"
        else:
            result["action"] = "send"

        # ── Email address extraction (highest priority) ────────────────────
        email_match = re.search(
            r'[\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+', utterance, re.IGNORECASE
        )
        if email_match:
            result["recipient_email"] = email_match.group(0)
            # Derive name from local part if no name found later
            result["recipient_name"] = email_match.group(0).split("@")[0]

        # ── Recipient name extraction ─────────────────────────────────────
        # Patterns: "to <Name>", "for <Name>", "<Name> ko", "at <Name>"
        # Updated to support Unicode (Hindi) characters
        name_patterns = [
            r'(?:send|email|mail|bhejo|message|msg)\s+(?:to|for|ko)?\s*([\w\u0900-\u097F]+(?:\s+[\w\u0900-\u097F]+)?)\s+(?:about|regarding|ke baare|ki taraf|ki baat)',
            r'(?:to|for|ko)\s+([\w\u0900-\u097F]+(?:\s+[\w\u0900-\u097F]+)?)\s+(?:about|regarding|ke|mail|email)',
            r'(?:email|mail|message|bhejo)\s+([\w\u0900-\u097F]+(?:\s+[\w\u0900-\u097F]+)?)\s+(?:about|ke|ko)',
            r'([\w\u0900-\u097F]+(?:\s+[\w\u0900-\u097F]+)?)\s+ko\s+(?:mail|email|message|bhejo)',
            r'(?:to|for)\s+([\w\u0900-\u097F]+(?:\s+[\w\u0900-\u097F]+)?)',
        ]
        for pattern in name_patterns:
            m = re.search(pattern, utterance, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                name_lower = name.lower()
                # Skip common articles and third-person pronouns that aren't specific names.
                if name_lower not in ('the', 'a', 'an', 'him', 'her', 'them', 'it', 'us', 'you', 'your', 'kise', 'kisne'):
                    result["recipient_name"] = name
                    break

        # ── Topic extraction ──────────────────────────────────────────────
        topic_match = re.search(
            r'(?:about|regarding|ke baare mein|ke baare|ki baat)\s+(.+)',
            utterance, re.IGNORECASE
        )
        if topic_match:
            result["topic"] = topic_match.group(1).strip()
        else:
            # Strip common lead-in words to get the core topic
            cleaned = re.sub(
                r'^(?:send|email|mail|write|draft|bhejo|likh|message|msg)\s+'
                r'(?:an?\s+)?(?:email|mail|message)?\s*'
                r'(?:to|for|ko)?\s*(?:[\w.+@-]+@[\w-]+\.[a-z]+)?\s*',
                '', utterance, flags=re.IGNORECASE
            ).strip()
            result["topic"] = cleaned or utterance

        # ── Tone detection ────────────────────────────────────────────────
        if re.search(r'\b(casual|friendly|informal|chill)\b', u):
            result["tone"] = "casual"
        elif re.search(r'\b(executive|brief|concise|short|quick)\b', u):
            result["tone"] = "executive"
        else:
            result["tone"] = "formal"

        # ── Urgency ───────────────────────────────────────────────────────
        if re.search(r'\b(urgent|asap|immediately|jaldi|abhi)\b', u):
            result["extra_context"] = "This is urgent"

        log.info(
            f"[Intent/Regex] action={result['action']!r} | "
            f"name={result['recipient_name']!r} | "
            f"email={result['recipient_email']!r} | "
            f"topic={result['topic']!r}"
        )
        return result

    # ── Intent Extraction ─────────────────────────────────────────────────

    async def extract_intent(self, utterance: str) -> EmailIntent:
        """
        Parse natural language utterance → EmailIntent.

        Strategy:
          1. Try LLM (google-generativeai or google-genai)
          2. If LLM returns empty/useless result, fall back to regex
          3. Merge: prefer LLM fields when non-empty, fill gaps with regex

        Args:
            utterance: User's voice/text command

        Returns:
            EmailIntent dataclass (always valid, never all-empty)
        """
        # ── Step 1: LLM attempt ───────────────────────────────────────────
        prompt   = _INTENT_EXTRACTION_PROMPT.format(utterance=utterance)
        raw      = await self._call_llm(prompt)
        llm_data = self._parse_json_safely(raw)

        # ── Step 2: Regex fallback ────────────────────────────────────────
        # Run regex always; use it to fill any gaps left by LLM
        regex_data = self._extract_intent_regex(utterance)

        # ── Step 3: Merge (LLM wins for non-empty values) ─────────────────
        def _pick(key: str, default: str = "") -> str:
            llm_val   = str(llm_data.get(key, "")).strip()
            regex_val = str(regex_data.get(key, "")).strip()
            return llm_val if llm_val else regex_val if regex_val else default

        intent = EmailIntent(
            action          = _pick("action", "send"),
            recipient_name  = _pick("recipient_name"),
            recipient_email = _pick("recipient_email"),
            topic           = _pick("topic", utterance),
            extra_context   = _pick("extra_context"),
            tone            = _pick("tone", "formal"),
            raw_utterance   = utterance,
        )

        log.info(
            f"[Intent] action={intent.action!r} | "
            f"recipient_name={intent.recipient_name!r} | "
            f"recipient_email={intent.recipient_email!r} | "
            f"topic={intent.topic!r} | tone={intent.tone!r} | "
            f"llm_used={bool(llm_data)} | llm_ready={self._llm_ready}"
        )
        return intent

    # ── Email Generation ──────────────────────────────────────────────────

    async def generate_email(
        self,
        intent: EmailIntent,
        recipient_email: str,
        memory_context: str = "",
        subject_hint: str   = "",
    ) -> GeneratedEmail:
        """
        Generate email subject + body using LLM.

        Args:
            intent:          Extracted EmailIntent
            recipient_email: Resolved recipient email address
            memory_context:  Relevant past context from vector memory
            subject_hint:    Optional subject hint to guide generation

        Returns:
            GeneratedEmail dataclass
        """
        prompt = _EMAIL_GENERATION_PROMPT.format(
            subject_hint   = subject_hint or "(auto-generate)",
            recipient      = f"{intent.recipient_name} <{recipient_email}>",
            topic          = intent.topic,
            tone           = intent.tone,
            memory_context = memory_context or "No relevant context available.",
            extra_context  = intent.extra_context or "None",
        )
        raw  = await self._call_llm(prompt, timeout=30.0)
        data = self._parse_json_safely(raw)

        # ── Fallback body when LLM returns nothing ──────────────────────────
        # This runs when Gemini quota is hit or LLM is unavailable.
        # Fixed: Fallback to better templates, especially for Hindi inputs.
        
        fallback_subject = f"Regarding: {intent.topic}" if intent.topic else "Hello"
        name_greeting    = intent.recipient_name.title() if intent.recipient_name else "there"
        
        # If topic is in Hindi, use a more generic greeting if we can't be sure
        if re.search(r'[\u0900-\u097F]', intent.topic):
            fallback_subject = f"Message regarding: {intent.topic}"
            
        ctx_note         = f"\n\nContext: {intent.extra_context}" if intent.extra_context else ""
        fallback_body    = (
            f"Hi {name_greeting},\n\n"
            f"Jarvis here. I'm writing to you regarding: {intent.topic}."
            f"{ctx_note}\n\n"
            f"Regards,\nJarvis"
        )
        fallback_html = (
            f"<p>Hi {name_greeting},</p>"
            f"<p>Jarvis here. I'm writing to you regarding: <strong>{intent.topic}</strong>.</p>"
            f"{'<p><i>' + intent.extra_context + '</i></p>' if intent.extra_context else ''}"
            f"<br><p>Regards,<br>Jarvis</p>"
        )

        generated = GeneratedEmail(
            subject   = data.get("subject") or fallback_subject,
            body      = data.get("body") or fallback_body,
            tone      = intent.tone,
            html_body = data.get("html_body") or fallback_html,
        )
        log.info(
            f"[Generate] subject={generated.subject!r} | tone={generated.tone!r} | "
            f"llm_generated={bool(data.get('body'))} | llm_ready={self._llm_ready}"
        )
        return generated

    # ── Reply Generation ──────────────────────────────────────────────────

    async def generate_reply(
        self,
        thread_info: Dict[str, Any],
        user_instructions: str,
        tone: str = "formal",
        memory_context: str = "",
    ) -> GeneratedEmail:
        """
        Generate a reply to an existing email thread.

        Args:
            thread_info:       Dict from GmailService.get_last_thread()
            user_instructions: What the user said (e.g. "politely decline")
            tone:              Email tone
            memory_context:    Vector memory context

        Returns:
            GeneratedEmail dataclass
        """
        original_subject = thread_info.get("subject", "(no subject)")
        prompt = _REPLY_GENERATION_PROMPT.format(
            original_subject = original_subject,
            original_sender  = thread_info.get("sender", "Unknown"),
            original_body    = thread_info.get("last_body", "")[:800],
            user_instructions = user_instructions,
            tone             = tone,
            memory_context   = memory_context or "None",
        )
        # Fix literal {original_subject} in the reply subject field
        prompt = prompt.replace(
            '"subject": "Re: {original_subject}"',
            f'"subject": "Re: {original_subject}"'
        )

        raw  = await self._call_llm(prompt, timeout=30.0)
        data = self._parse_json_safely(raw)

        generated = GeneratedEmail(
            subject   = data.get("subject", f"Re: {original_subject}"),
            body      = data.get("body", ""),
            tone      = tone,
            html_body = data.get("html_body"),
        )
        log.info(f"[Reply] Generated reply for thread: {original_subject!r}")
        return generated

    # ── Confirmation Preview ──────────────────────────────────────────────

    def build_confirmation_preview(
        self,
        generated: GeneratedEmail,
        recipient_email: str,
        recipient_name: str  = "",
        attachments: list    = None,
        is_draft: bool       = False,
        is_reply: bool       = False,
    ) -> str:
        """
        Build a human-readable confirmation message for the user.

        Returns a formatted string that Jarvis reads aloud or displays
        before requesting user approval.
        """
        lines = []
        action_label = "Draft" if is_draft else ("Reply" if is_reply else "Email")
        recipient_label = f"{recipient_name} <{recipient_email}>" if recipient_name else recipient_email

        lines.append(f"📧 {action_label} Preview")
        lines.append(f"{'─' * 40}")
        lines.append(f"To      : {recipient_label}")
        lines.append(f"Subject : {generated.subject}")
        lines.append(f"Tone    : {generated.tone.capitalize()}")
        if attachments:
            lines.append(f"Files   : {', '.join(attachments)}")
        lines.append(f"{'─' * 40}")
        lines.append("Body:")
        lines.append(generated.body[:600] + ("..." if len(generated.body) > 600 else ""))
        lines.append(f"{'─' * 40}")

        action_word = "save this draft" if is_draft else "send this email"
        lines.append(f"✅ Shall I {action_word}? (yes / no / edit)")

        return "\n".join(lines)

    # ── Memory Integration ─────────────────────────────────────────────────

    async def store_email_in_memory(
        self,
        mem_manager,
        summary,
        generated: GeneratedEmail,
        recipient_name: str,
    ) -> None:
        """
        Store a compact email action summary in the vector memory DB.

        Args:
            mem_manager:    MemoryManager instance from memory/__init__.py
            summary:        EmailSummary dataclass from GmailService
            generated:      GeneratedEmail that was sent
            recipient_name: Human-readable recipient name
        """
        if not mem_manager:
            return
        try:
            memory_text = (
                f"[EMAIL ACTION] {summary.action.upper()} | "
                f"To: {recipient_name} <{summary.to}> | "
                f"Subject: {summary.subject} | "
                f"Tone: {summary.tone} | "
                f"Time: {summary.timestamp} | "
                f"Preview: {summary.snippet}"
            )
            from memory import MemoryType
            await mem_manager.store_message(
                memory_text,
                role        = "assistant",
                memory_type = MemoryType.ASSISTANT,
            )
            log.info(f"[Memory] Email summary stored: {summary.subject!r}")
        except Exception as exc:
            log.warning(f"[Memory] Failed to store email summary: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# Module singleton
# ══════════════════════════════════════════════════════════════════════════════

_processor: Optional[EmailIntentProcessor] = None


async def get_intent_processor() -> EmailIntentProcessor:
    """Return the module-level EmailIntentProcessor singleton."""
    global _processor
    if _processor is None:
        _processor = EmailIntentProcessor()
        await _processor.initialize()
    return _processor
