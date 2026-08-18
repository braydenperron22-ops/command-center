"""Gmail integration — session request: "incorporate emails... I want
the morning brief to get emails... I also want important emails to be
sent to me via a toast alert, but you need to make sure that they're
important, and not crap... I want the morning brief to be able to see
my email so that it can kinda give me an update on what's going on in
the other aspects of my life as well."

IMAP + an app password (session answer, over Gmail API/OAuth2 —
"IMAP + app password (recommended)... matches this app's own pattern
of avoiding unnecessary API complexity"): no Google Cloud project, no
OAuth consent screen, no refresh-token setup script, just two secrets
(GMAIL_ADDRESS, GMAIL_APP_PASSWORD — generate the second at
myaccount.google.com/apppasswords, needs 2FA on) and Python's own
built-in imaplib/email modules, no new dependency. Read-only in every
sense that matters: connects via IMAP `EXAMINE` (see _fetch_recent_raw's
own `readonly=True`), which the protocol itself guarantees can't change
any flag (a message's read/unread state included) no matter what gets
fetched — this app looks at your inbox, never touches it.

Importance is a real AI judgment call (session answer — "AI judgment
call (recommended)... same pattern this app already uses for weather
severity tiers and picking the morning brief's featured facts"), not a
fixed rule list — see _build_batch_prompt's own criteria. Only ever
reads sender/subject/a short plain-text snippet, never a full HTML
render or attachments, and a toast only ever shows that same short
snippet — never the full body — the same "don't put more on screen
than the moment calls for" instinct this app already applies to
calendar descriptions (morning_briefing._DESCRIPTION_FACT_CHARS) and
weather bulletins.

NOT YET LIVE-VERIFIED against a real inbox — GMAIL_ADDRESS/
GMAIL_APP_PASSWORD aren't in secrets.toml yet. Built and verified
against synthetic IMAP responses (mocked at the imaplib level) the
same way precip_nowcast_client.py was before its own real key existed;
needs a real check once both secrets are actually set."""

import email
import html
import imaplib
import json
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header

import streamlit as st

import groq_client
import persisted_state

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# How far back a single IMAP fetch looks — generous enough that a
# kiosk asleep for a few hours (screen off overnight, a redeploy, a
# brief outage) doesn't miss a genuinely new email once it wakes back
# up, small enough that this is never scanning weeks of old mail on
# every cache refresh. Toast-worthiness is decided separately by the
# _seen dedup set below, not by this window alone — an old email
# inside this window that's already been seen never re-toasts.
FETCH_LOOKBACK_HOURS = 6

# Same cadence class as this app's other periodic-but-not-real-time
# fetches (scores_client.GAME_CACHE_TTL_SECONDS, commute_client's own
# route cache) — frequent enough that a new email shows up within a
# few minutes, far short of hammering Gmail every 5s kiosk rerun.
CACHE_TTL_SECONDS = 3 * 60

# Plain-text snippet length a toast/morning-brief fact ever carries —
# same "cap it, don't dump the whole thing" reasoning as
# morning_briefing._DESCRIPTION_FACT_CHARS for a calendar description.
SNIPPET_MAX_CHARS = 200

# Session request: "give as much data as possible" is morning_briefing's
# own established default for its OTHER facts, but email is a genuinely
# different case — real personal correspondence, and a much longer
# lookback than the toast fetch above (that one's about catching a NEW
# email quickly; this one's about "what's been going on," a slower
# question). Capped count, not capped time, for the same "don't let one
# unusually email-heavy day blow out the prompt" reasoning
# AGENDA_LIST_CAP already uses for a packed calendar.
MORNING_BRIEF_LOOKBACK_HOURS = 24
MORNING_BRIEF_MAX_EMAILS = 5

_last_good_raw: list[dict] = []


def _configured() -> bool:
    return bool(st.secrets.get("GMAIL_ADDRESS")) and bool(st.secrets.get("GMAIL_APP_PASSWORD"))


def configured() -> bool:
    """Public wrapper — pages_email.py's own "not set up yet" tile
    needs the same check every other caller in this module already
    makes internally."""
    return _configured()


def _decode_mime_words(raw: str | None) -> str:
    """A MIME-encoded header (subject, display name) as plain text —
    email headers are technically ASCII-only, so anything outside that
    (a real name with an accent, an emoji in a subject line) arrives
    RFC 2047-encoded ("=?UTF-8?B?...?=") rather than as the literal
    characters. decode_header does the real decoding; this just joins
    the (text, charset) pairs it returns back into one string."""
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            try:
                out.append(text.decode(charset or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_WS_RE = re.compile(r"[ \t\r\f\v]+")


def _html_to_snippet(html: str) -> str:
    """A crude, good-enough plain-text snippet from an HTML-only email
    body — this never needs to be a real HTML renderer, just enough to
    pull a readable opening line or two for a toast/fact string. Tags
    stripped outright (no attempt to preserve links, formatting,
    images); collapsed whitespace since stripped-tag HTML is usually
    full of newlines/indentation that read as garbled run-together
    text otherwise."""
    text = _HTML_TAG_RE.sub(" ", html)
    text = _HTML_WS_RE.sub(" ", text)
    return text.strip()


def _extract_snippet(msg: email.message.Message) -> str:
    """A short plain-text preview of the message body — prefers a real
    text/plain part (most real email has one even when it's not the
    primary rendered version); falls back to stripping tags out of
    text/html only when that's genuinely all there is. "" on anything
    unexpected (an encrypted/signed message with no readable part,
    decode failure) rather than raising — a missing snippet just means
    a shorter fact/toast, not a broken one."""
    try:
        plain, html_fallback = None, None
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    continue
                content_type = part.get_content_type()
                if content_type == "text/plain" and plain is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        plain = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                elif content_type == "text/html" and html_fallback is None:
                    payload = part.get_payload(decode=True)
                    if payload:
                        html_fallback = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                if msg.get_content_type() == "text/html":
                    html_fallback = text
                else:
                    plain = text
        text = plain if plain is not None else (_html_to_snippet(html_fallback) if html_fallback else "")
        text = " ".join(text.split())  # collapse all whitespace/newlines to single spaces
        return text[:SNIPPET_MAX_CHARS].strip()
    except Exception:
        return ""


def _parse_message(raw_bytes: bytes) -> dict | None:
    """{"message_id", "from", "subject", "snippet"} from one raw RFC 822
    message, or None if it's missing the one field (Message-ID)
    everything else here keys dedup off of. "from" is the display name
    when the header has one ("Jane Doe <jane@x.com>" -> "Jane Doe"), the
    bare address otherwise — a display name reads better in a toast/fact
    and is what's actually available for most real senders.

    Deliberately no "unread" key here — that comes from the FETCH
    response's own FLAGS, not the message bytes this function parses,
    so _fetch_recent_raw attaches it separately."""
    try:
        msg = email.message_from_bytes(raw_bytes)
    except Exception:
        return None
    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:
        return None
    from_header = _decode_mime_words(msg.get("From"))
    display_name = from_header.split("<")[0].strip().strip('"') if "<" in from_header else from_header
    subject = _decode_mime_words(msg.get("Subject")) or "(no subject)"
    return {
        "message_id": message_id,
        "from": display_name or from_header,
        "subject": subject,
        "snippet": _extract_snippet(msg),
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_recent_raw(lookback_hours: int) -> list[dict]:
    """Every INBOX message since `lookback_hours` ago, newest first,
    each carrying its own live "unread" bool — [] if not configured,
    and the last good copy on any fetch failure (a transient IMAP
    hiccup), same graceful-degradation rule every other live fetch in
    this app already follows.

    `readonly=True` on select() puts the connection in IMAP's own
    EXAMINE mode — the protocol-level guarantee (not just a client-side
    convention) that nothing fetched through this connection can change
    a flag server-side, a real message's read/unread state included.
    This app only ever looks, including for the \\Seen flag itself:
    FLAGS is read alongside BODY.PEEK[] purely to report the *existing*
    state, same as opening the inbox in EXAMINE mode from any other
    read-only mail client would show."""
    global _last_good_raw
    if not _configured():
        return []
    since = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime("%d-%b-%Y")
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(st.secrets["GMAIL_ADDRESS"], st.secrets["GMAIL_APP_PASSWORD"])
            imap.select("INBOX", readonly=True)
            status, data = imap.search(None, f'(SINCE "{since}")')
            if status != "OK" or not data or not data[0]:
                return []
            uids = data[0].split()
            out = []
            for uid in uids:
                # BODY.PEEK[] (not BODY[]) — the explicit, standard way
                # to ask IMAP for content without a \Seen side effect,
                # kept even though readonly=True above already
                # guarantees it at the connection level; two
                # independent reasons this can never mark something
                # read is better than relying on just one. FLAGS
                # alongside it is a pure read of the flag, not a
                # request to set one — session request: "flag if I
                # haven't read it," for the new email feed page
                # (pages_email.py).
                status, msg_data = imap.fetch(uid, "(FLAGS BODY.PEEK[])")
                if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                meta, raw = msg_data[0]
                parsed = _parse_message(raw)
                if parsed:
                    # meta looks like b'1 (FLAGS (\\Seen \\Answered) BODY[] {1234}'
                    # — a substring check is all a real \Seen flag needs,
                    # no need to fully parse the parenthesized flag list.
                    parsed["unread"] = b"\\Seen" not in meta
                    out.append(parsed)
    except Exception:
        return _last_good_raw
    out.reverse()  # IMAP SEARCH returns ascending UID order; newest first for everything downstream
    _last_good_raw = out
    return out


def fetch_recent(lookback_hours: int) -> list[dict]:
    """Public wrapper around _fetch_recent_raw — pages_email.py's own
    feed page needs the full raw list (unread flag included), not just
    the toast-worthy subset get_new_alerts filters down to, so it calls
    this directly rather than reaching past the module's private
    fetch/dedup internals."""
    return _fetch_recent_raw(lookback_hours)


# Session request's own criteria, verbatim: "make sure that they're
# important, and not crap." Same batched-JSON-verdict shape news.py's
# own headline classifier uses (_build_batch_prompt/_classify_batch),
# reused here rather than re-invented — a real, already-proven pattern
# in this exact codebase for "AI reads a numbered list, returns a JSON
# array of judgments in the same order."
_CLASSIFICATION_CRITERIA = (
    "IMPORTANT: real personal correspondence — someone writing to him directly (not a company, "
    "not a list), something that genuinely needs a reply or an action, a real appointment/"
    "interview/deadline, a genuine account security alert (a real sign-in/password notice), a "
    "bill or payment that's actually due. NOT important: marketing, promotions, newsletters, "
    "social media notifications, automated receipts or shipping updates with nothing left to do, "
    "mailing lists, anything that reads like bulk or automated sending regardless of how the "
    "subject line is phrased."
)


def _build_batch_prompt(emails: list[dict]) -> str:
    lines = []
    for i, e in enumerate(emails):
        entry = f'{i + 1}. FROM: {e["from"]}\n   SUBJECT: {e["subject"]}'
        if e.get("snippet"):
            entry += f'\n   SNIPPET: {e["snippet"]}'
        lines.append(entry)
    email_block = "\n".join(lines)
    return (
        f"You are filtering email for someone's home dashboard, deciding which of the following "
        f"{len(emails)} emails are worth interrupting him with a toast notification for. Judge "
        f"EACH independently.\n\n{_CLASSIFICATION_CRITERIA}\n\n{email_block}\n\n"
        'Respond with ONLY a JSON array, no markdown code fence, no other text, exactly one '
        'object per email above IN THE SAME ORDER: [{"important": true}, {"important": false}, ...]'
    )


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


# Classification cache — {message_id: bool}, persisted the same shape/
# reasoning as news.py's own _decided: a real Groq call is real cost
# and real latency, so a message already judged once never gets
# reclassified just because it's still inside the fetch window on a
# later rerun. Bounded the same way news.MAX_SEEN_HEADLINES is.
MAX_DECIDED = 1000
_decided: dict[str, bool] = dict(persisted_state.load("email_decided", {}))


def _classify_pending(emails: list[dict]) -> None:
    """Classifies every email in `emails` not already in _decided, one
    real batched Groq call for all of them — mutates _decided in
    place. A failed or unparseable response leaves the whole batch
    pending or drops it (see get_new_alerts_for_toast — an email
    that's still unclassified this rerun is retried next time, not
    lost)."""
    global _decided
    pending = [e for e in emails if e["message_id"] not in _decided]
    if not pending:
        return
    prompt = _build_batch_prompt(pending)
    # account="primary"/reasoning_effort="low" — same real-cost reasoning
    # as news.py's own _classify_batch: a keep-or-reject judgment call,
    # not creative prose, needs low effort, not a specific account
    # tied to a shared model-keyed default (see groq_client.generate's
    # own docstring on why an explicit account matters now).
    result = groq_client.generate(prompt, temperature=0.1, max_output_tokens=400, account="primary", reasoning_effort="low")
    if result is None:
        return
    try:
        verdicts = json.loads(_strip_code_fence(result))
    except Exception:
        return
    if not isinstance(verdicts, list):
        return
    for e, verdict in zip(pending, verdicts):
        if isinstance(verdict, dict) and isinstance(verdict.get("important"), bool):
            _decided[e["message_id"]] = verdict["important"]
    if len(_decided) > MAX_DECIDED:
        for _ in range(len(_decided) - MAX_DECIDED):
            _decided.pop(next(iter(_decided)))
    persisted_state.save("email_decided", _decided)


def classify(emails: list[dict]) -> None:
    """Public wrapper around _classify_pending — pages_email.py triggers
    classification for its own full 24h list independently of
    get_new_alerts's toast-only dedup path, sharing the same _decided
    cache either way (a message classified for one is never
    re-classified for the other)."""
    _classify_pending(emails)


def is_important(message_id: str) -> bool:
    """Whatever _decided already knows about this message — False (not
    "unknown yet") for anything not yet classified, since the feed page
    just needs a badge to show or not, not a three-state answer."""
    return bool(_decided.get(message_id))


# Toast dedup — same "mark everything seen on first sight, only alert
# for what arrives AFTER that" baseline rule news.py/sports_alerts.py
# both already use, so shipping this doesn't dump every recent inbox
# email in FETCH_LOOKBACK_HOURS as a fresh toast the moment it goes
# live. Per-instance (session request precedent elsewhere in this app:
# "every single toast we get... make sure every terminal gets its own
# alert") — a real new email should toast on every kiosk, not just
# whichever one's process happened to see it first.
_seen: dict = dict(persisted_state.load_per_instance("email_seen", {}))
_baseline_done = persisted_state.load_per_instance("email_baseline_done", False)


def get_new_alerts(now: datetime) -> list[dict]:
    """{"kind": "email", "from", "subject", "snippet"} for every
    genuinely new, AI-judged-important email since the last check —
    [] if unconfigured, on any fetch failure, or if nothing new and
    important showed up. Call at most once per rerun — marking
    something "seen" is a side effect, same contract news.get_new_alerts
    already documents for itself."""
    global _seen, _baseline_done
    if not _configured():
        return []
    raw = _fetch_recent_raw(FETCH_LOOKBACK_HOURS)
    if not raw:
        return []

    if not _baseline_done:
        for e in raw:
            _seen[e["message_id"]] = True
        _baseline_done = True
        persisted_state.save_per_instance("email_seen", _seen)
        persisted_state.save_per_instance("email_baseline_done", True)
        return []

    new_emails = [e for e in raw if e["message_id"] not in _seen]
    if not new_emails:
        return []
    _classify_pending(new_emails)

    alerts = []
    for e in new_emails:
        _seen[e["message_id"]] = True
        if len(_seen) > MAX_DECIDED:
            _seen.pop(next(iter(_seen)))
        if not _decided.get(e["message_id"]):
            continue
        alerts.append({"kind": "email", "from": e["from"], "subject": e["subject"], "snippet": e["snippet"]})
    persisted_state.save_per_instance("email_seen", _seen)
    return alerts


def morning_brief_summary(now: datetime) -> str | None:
    """"email: N important — 'Subject' from Sender, ..." for
    morning_briefing's own fact list, capped to MORNING_BRIEF_MAX_EMAILS
    — None if unconfigured or nothing important showed up in
    MORNING_BRIEF_LOOKBACK_HOURS. Reuses the exact same _decided
    classification cache get_new_alerts already fills, so an email
    already judged for a toast is never re-classified again here — the
    two features share one real judgment per message, not two."""
    if not _configured():
        return None
    raw = _fetch_recent_raw(MORNING_BRIEF_LOOKBACK_HOURS)
    if not raw:
        return None
    _classify_pending(raw)
    important = [e for e in raw if _decided.get(e["message_id"])]
    if not important:
        return None
    shown = important[:MORNING_BRIEF_MAX_EMAILS]
    parts = [f'"{e["subject"]}" from {e["from"]}' for e in shown]
    remaining = len(important) - len(shown)
    joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + f", and {parts[-1]}"
    suffix = f", plus {remaining} more" if remaining > 0 else ""
    return f"{len(important)} important — {joined}{suffix}"


def render_alert_bar(alert: dict) -> None:
    """Bottom-strip toast — sender + subject, same plain immediately-
    visible bar shape as every other toast kind, its own color so it
    reads as its own category at a glance. The snippet is deliberately
    NOT shown here — a subject line is enough to know an email arrived
    and roughly what it's about; the full preview text is for the
    morning brief's own AI fact, not a screen anyone in the room can
    see at a glance."""
    from_text = html.escape(alert.get("from", ""))
    subject_text = html.escape(alert.get("subject", ""))
    st.markdown(
        f'<div class="email-alert-bar">'
        f'<span class="news-breaking-label">EMAIL</span>'
        f'<span class="email-alert-from">{from_text}</span>'
        f'<span class="news-alert-headline">{subject_text}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
