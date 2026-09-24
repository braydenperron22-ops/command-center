"""LG webOS TV control for the kiosk's own display, synced to the
dashboard's night_mode_active state — the real replacement for the
HDMI-CEC idea (this box's onboard HDMI has no CEC hardware wired
through, confirmed live by cec-client finding zero adapters) and for
the plain display-signal-drop approach (removed per session request:
"I should just see the night mode with the clock overnight" — dropping
the signal put the TV into its own no-signal/standby cycle, hiding the
clock instead of showing it).

Talks to the TV over the local network instead (aiowebostv, the same
webOS control protocol Home Assistant's own LG integration uses) —
genuinely more capable than CEC would have been: real power on/off,
input switching, AND the ability to ask the TV what it's currently
showing before acting, which is what makes the "don't interrupt me if
I'm watching something else" requirement possible at all.

Pairing is a one-time thing (see lg_tv_pair.py) — the TV shows an
on-screen "allow this device?" prompt exactly once, and the resulting
client-key is saved to KEY_FILE, outside the git repo (machine-
specific, credential-like, same reasoning secrets.toml is never
committed either).

Session requirement, both directions: never interrupt something
already playing. get_current_app() is checked before acting either
way — the TV is only powered off at night if it's currently showing
OUR OWN input, and only woken + switched back to our input in the
morning if the TV is either already off or already sitting on ours.
Anything else (the Xbox on HDMI_2, a smart-TV app) is left alone.

Session follow-up: "check the state every 15 minutes until it's back
to HDMI 1 or the TV is off itself, and then rest there." Both action
functions below return "settled" (goal achieved, or confirmed not
applicable — nothing left to do until the NEXT real night_mode_active
transition) or "deferred" (something else is genuinely in use right
now — see run_lg_tv_sync.py's own caller for how it turns "deferred"
into a 15-minute recheck rather than silently giving up for the night)
rather than returning None, so the caller can tell those two outcomes
apart."""

import asyncio
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Literal

from aiowebostv import WebOsClient, WebOsTvPairError

import ntfy_client
import persisted_state
import sleep_tracker

TV_HOST = "192.168.0.152"
TV_MAC = "d8:e3:5e:bb:2c:7a"
# Session audit: "is there a gap we haven't bridged yet" -- TV_HOST is
# a hardcoded IP with no confirmed DHCP reservation on the router (no
# admin access available from here to check). Rather than depend on
# that assumption, verify_tv_ip (called once a day, see run_lg_tv_
# sync.py) re-discovers the TV over SSDP -- the exact same real
# discovery that found it in the first place -- and caches whatever it
# finds here, so a router-assigned IP change self-heals instead of
# silently breaking every function in this module.
_DISCOVERED_IP_FILE = Path.home() / ".config" / "kiosk-lg-tv-ip"
# webOS's own app ids for each labeled HDMI port — confirmed live via
# get_inputs()/get_current_app() while each device was actually the
# active input. Session request: "HDMI 1 is my kiosk, and HDMI 2 is my
# Xbox... mark these so you know which one they are."
KIOSK_APP_ID = "com.webos.app.hdmi1"
KIOSK_INPUT_ID = "HDMI_1"
XBOX_APP_ID = "com.webos.app.hdmi2"
KEY_FILE = Path.home() / ".config" / "kiosk-lg-tv-key"
CONNECT_TIMEOUT_SECONDS = 5
# Session audit: "is there a gap we haven't bridged yet" surfaced a
# real one -- the persistent state watcher's connection was dropping
# and reconnecting every 2-15 minutes on no fixed schedule (confirmed
# live in lg-tv-sync.log). aiowebostv's own default heartbeat (5s,
# passed straight through to aiohttp's ws_connect) pings the TV every
# 5 seconds and kills the connection on a missed pong -- aggressive
# for a WiFi-connected TV that can have brief, completely normal radio
# power-save hiccups. Loosened well past that; a genuinely dead
# connection still gets caught, just not mistaken for one as easily.
# Harmless for every OTHER (short-lived, connect-act-disconnect)
# caller of _connect() too -- they're gone long before this would ever
# matter.
HEARTBEAT_SECONDS = 30
# Rough real-world boot time for webOS to come back up enough to accept
# a fresh websocket connection after a Wake-on-LAN packet — tuned loose
# rather than tight, a few extra seconds of "TV still says off" costs
# nothing here, a too-short wait would just mean a failed connect and a
# wasted cycle (the poller tries again next minute regardless).
WOL_BOOT_WAIT_SECONDS = 10
# Session request: "set a floor for the volume every single day...
# probably like 7 to 10." Picked the middle of that range as one
# concrete number rather than leaving it a fuzzy range — easy to
# change here if 8 turns out too loud/quiet in practice.
VOLUME_FLOOR = 8
# Session follow-up: "the base kiosk volume is 20, always... when I
# move to the Xbox, it can be moved as need be, but as soon as it
# comes back to the kiosk, make it 20 flat." Unlike VOLUME_FLOOR (a
# floor, applies regardless of input, only ever raises), this is a
# fixed value enforced specifically while on the kiosk's own input —
# see wake_and_switch_if_safe below for where it's applied.
KIOSK_VOLUME = 20
# Session follow-up: "set the volume to like five when we're going to
# the Xbox... so it's not blasting at 20 volume... when I'm
# transferring to the Xbox." A one-time landing value applied only on
# the EDGE into Xbox (see _watch_state_once's own edge-tracking) — not
# re-enforced afterward, unlike KIOSK_VOLUME, since "it can be moved as
# need be" once there was already the explicit rule for this input.
XBOX_LANDING_VOLUME = 5
# Must match ntfy_client.py's own _TV_QUEUE_KEY on the Cloud side —
# that's the one place every real phone push already funnels through
# (see that module's own docstring), queuing a copy here for this box
# to pick up. Session request: "anything that I get a notification for
# on my phone I should get a notification for on the TV as well [while
# I'm on my Xbox, not looking at the kiosk]."
NOTIFICATION_QUEUE_KEY = "tv_notification_queue"
NOTIFICATION_MAX_CHARS = 200
# Must match ntfy_client.py's own _TV_QUEUE_MAX_AGE_SECONDS -- see
# send_pending_notifications' own docstring for why staleness is
# checked here too, not just relied on at write time.
NOTIFICATION_MAX_AGE_SECONDS = 10 * 60

Result = Literal["settled", "deferred"]


def _label_for(app_id: str | None) -> str:
    if app_id == KIOSK_APP_ID:
        return "kiosk"
    if app_id == XBOX_APP_ID:
        return "Xbox"
    return repr(app_id)


def _client_key() -> str | None:
    if KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
        return key or None
    return None


def _current_tv_host() -> str:
    if _DISCOVERED_IP_FILE.exists():
        cached = _DISCOVERED_IP_FILE.read_text().strip()
        if cached:
            return cached
    return TV_HOST


_SSDP_MSEARCH = (
    'M-SEARCH * HTTP/1.1\r\n'
    'HOST: 239.255.255.250:1900\r\n'
    'MAN: "ssdp:discover"\r\n'
    'MX: 3\r\n'
    'ST: ssdp:all\r\n'
    '\r\n'
).encode()


def _discover_tv_ip() -> str | None:
    """Real SSDP scan for the TV's current IP -- same M-SEARCH this TV
    was originally found with, matched the same way (LG's own webOS
    devices identify themselves in their SSDP response). None if
    nothing answers within the timeout (the TV being off is the normal
    case here, not conclusive proof the IP is wrong)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(4)
    try:
        sock.sendto(_SSDP_MSEARCH, ("239.255.255.250", 1900))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                return None
            if "lge" in data.decode(errors="replace").lower():
                return addr[0]
    finally:
        sock.close()


async def verify_tv_ip(log=lambda msg: None) -> None:
    """Call once a day (see run_lg_tv_sync.py's own daily-check shape,
    same as enforce_volume_floor) -- re-discovers the TV over SSDP and
    updates the cached IP if it's genuinely different from what's
    currently in use. See _DISCOVERED_IP_FILE's own comment for why
    this exists at all."""
    discovered = _discover_tv_ip()
    if discovered is None:
        return
    current = _current_tv_host()
    if discovered != current:
        _DISCOVERED_IP_FILE.write_text(discovered)
        log(f"TV IP changed from {current} to {discovered} -- updated")


def send_wol(mac: str = TV_MAC) -> None:
    """Broadcasts a standard Wake-on-LAN magic packet — the only way to
    reach a webOS TV that's gone into full standby (its websocket
    server, and therefore every other command in this module, is
    unreachable at that point; only a low-power WoL listener stays up,
    and only if Wake on LAN is enabled in the TV's own network
    settings — confirmed live already on)."""
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(packet, ("255.255.255.255", 9))
    finally:
        sock.close()


# Session audit: "is there a gap we haven't bridged yet" -- a revoked
# pairing (a webOS firmware update, a factory reset, or the TV's own
# "connected devices" settings) would otherwise fail silently forever,
# indistinguishable from "the TV is just off" to every caller here.
# aiowebostv raises WebOsTvPairError specifically for a rejected/
# expired client-key (confirmed by reading its own _check_registration
# — a genuine registration rejection, not a connection-level timeout),
# which IS distinguishable — so this is the one failure mode worth a
# real phone alert instead of the usual silent "try again later."
# Deduped to once per real day (persisted, survives a service
# restart) so a TV that stays unpaired doesn't re-alert every poll
# tick forever.
_PAIRING_ALERT_DATE_KEY = "lg_tv_pairing_broken_alert_date"


def _alert_pairing_broken() -> None:
    from datetime import date

    today = date.today().isoformat()
    if persisted_state.load(_PAIRING_ALERT_DATE_KEY, None) == today:
        return
    persisted_state.save(_PAIRING_ALERT_DATE_KEY, today)
    ntfy_client.send(
        title="TV pairing broken",
        message="The kiosk's LG TV pairing was rejected -- re-run lg_tv_pair.py on the kiosk box.",
        priority="high",
        tags="warning",
    )


async def _connect() -> WebOsClient | None:
    """A connected, already-paired client, or None if there's no saved
    pairing yet or the TV genuinely isn't reachable right now (off, or
    off the network) — never raises, every caller treats None the same
    way a CEC "no adapter" result already had to be treated: skip this
    cycle, try again later. The one exception that DOES get a real
    phone alert first is a genuinely revoked pairing — see
    _alert_pairing_broken's own comment."""
    key = _client_key()
    if key is None:
        return None
    client = WebOsClient(
        _current_tv_host(), client_key=key, connect_timeout=CONNECT_TIMEOUT_SECONDS, heartbeat=HEARTBEAT_SECONDS
    )
    try:
        await client.connect()
    except WebOsTvPairError:
        _alert_pairing_broken()
        return None
    except Exception:
        return None
    return client


# Real bug, confirmed live: wake_and_switch_if_safe's "is the TV
# already on Xbox?" check used a single _connect() attempt -- one
# transient failure (a slow/flaky websocket accept on a TV that was
# genuinely ON and on Xbox at the time) got misread as "TV is off,"
# which fell through to Wake-on-LAN + switching the input away from a
# real, active Xbox session. A single failed attempt is fine for
# power_off_if_ours (the safe default there is "do nothing"), but not
# for this one, where "presumed off" triggers a real, hard-to-undo
# action. A couple of quick retries costs at most a few seconds and
# closes that gap.
_STATE_CHECK_ATTEMPTS = 3
_STATE_CHECK_RETRY_DELAY_SECONDS = 2.0


async def _connect_for_state_check() -> WebOsClient | None:
    for attempt in range(_STATE_CHECK_ATTEMPTS):
        client = await _connect()
        if client is not None:
            return client
        if attempt < _STATE_CHECK_ATTEMPTS - 1:
            await asyncio.sleep(_STATE_CHECK_RETRY_DELAY_SECONDS)
    return None


async def _current_app_id(client: WebOsClient) -> str | None:
    """aiowebostv's own type hint on get_current_app() claims a dict,
    but confirmed live it actually returns the plain app-id string
    directly (or None) -- get_current_app() -> res.get("appId") inside
    the library itself, already unwrapped.

    Also confirmed live: a TV that was JUST powered off can still
    briefly answer this over the websocket (a transitional/quick-start
    grace period, not fully asleep yet) with an EMPTY string rather
    than None -- treated the same as "no real app info" below (falsy),
    not as "a genuinely different app," or wake_and_switch_if_safe
    would wrongly read a TV we ourselves just turned off as someone
    else's in-use input and refuse to wake it back up."""
    try:
        app_id = await client.get_current_app()
    except Exception:
        return None
    return app_id or None


async def power_off_if_ours(log=lambda msg: None) -> Result:
    """Night mode engaging: power the TV off, but only if it's
    currently showing OUR OWN input. "settled" whenever there's
    genuinely nothing left to do this cycle -- already off/unreachable
    (that's the goal state already), or a successful power-off just
    now. "deferred" only when something else (the Xbox, a smart-TV
    app) is actually in use right now -- see this module's own
    docstring for how the caller turns that into a 15-minute recheck."""
    client = await _connect()
    if client is None:
        log("TV unreachable (presumed already off) -- nothing to do")
        return "settled"
    try:
        current = await _current_app_id(client)
        if current != KIOSK_APP_ID:
            log(f"TV is on {_label_for(current)} -- leaving it alone, will recheck later")
            return "deferred"
        await client.power_off()
        log("TV was on our input -- powered off")
        return "settled"
    except Exception as e:
        log(f"power-off attempt failed: {e}")
        return "settled"  # a transient error isn't "someone's using it" -- don't wait 15 min on it
    finally:
        await client.disconnect()


async def _enforce_kiosk_volume(client: WebOsClient, log) -> None:
    """Session follow-up: "the base kiosk volume is 20, always... when
    I move to the Xbox, it can be moved as need be, but as soon as it
    comes back to the kiosk, make it 20 flat." Called only from places
    that have already confirmed the TV is genuinely on the kiosk's own
    input -- reuses the caller's already-open connection rather than a
    fresh one. Unlike VOLUME_FLOOR (a floor, only ever raises, applies
    regardless of input), this sets an exact value and can lower the
    volume too."""
    try:
        volume = await client.get_volume()
        if volume is not None and volume != KIOSK_VOLUME:
            await client.set_volume(KIOSK_VOLUME)
            log(f"kiosk volume was {volume} -- set to {KIOSK_VOLUME}")
    except Exception as e:
        log(f"kiosk volume enforcement failed: {e}")


async def _set_xbox_landing_volume(client: WebOsClient, log) -> None:
    """Session follow-up: "set the volume to like five when we're going
    to the Xbox... so it's not blasting at 20." Called once, only on
    the EDGE into Xbox (see _watch_state_once) -- unlike
    _enforce_kiosk_volume this is a one-shot landing value, not
    something re-applied on every push while already there, since the
    whole point of the Xbox input is that volume is free to move
    afterward."""
    try:
        volume = await client.get_volume()
        if volume is not None and volume != XBOX_LANDING_VOLUME:
            await client.set_volume(XBOX_LANDING_VOLUME)
            log(f"landed on Xbox at volume {volume} -- set to {XBOX_LANDING_VOLUME}")
    except Exception as e:
        log(f"Xbox landing volume failed: {e}")


async def wake_and_switch_if_safe(log=lambda msg: None) -> Result:
    """Night mode ending: bring the TV back to our input, defaulting to
    HDMI_1 -- but same "don't interrupt" rule, checked BEFORE waking
    anything. "deferred" only if the TV is already reachable and
    genuinely on something else (the Xbox); "settled" for every other
    outcome (already on ours, or a real wake + switch attempt, success
    or failure -- a failed WoL/reconnect isn't "someone's using it"
    either, see power_off_if_ours' own reasoning for the same call).

    Uses _connect_for_state_check (a few retries) rather than a single
    _connect() attempt for this specific check -- confirmed live, a
    single failed attempt here once misread a TV that was genuinely ON
    and on Xbox as "off," and proceeded to wake + switch it away from a
    real, active session. See that helper's own comment for the full
    story.

    Also enforces KIOSK_VOLUME (see _enforce_kiosk_volume) every time
    the TV is confirmed on our input -- both the already-there case and
    right after a fresh switch -- so it stays at a known level any time
    the kiosk is genuinely what's showing."""
    client = await _connect_for_state_check()
    if client is not None:
        current = await _current_app_id(client)
        if current is not None and current != KIOSK_APP_ID:
            await client.disconnect()
            log(f"TV is already on {_label_for(current)} -- leaving it alone, will recheck later")
            return "deferred"
        if current == KIOSK_APP_ID:
            await _enforce_kiosk_volume(client, log)
            await client.disconnect()
            log("TV already on our input -- nothing to do")
            return "settled"
        # current is None despite being reachable (e.g. a screensaver
        # app with no clean appId) -- fall through and just make sure
        # our input is selected, same as the unreachable/off path below.
        await client.disconnect()

    log("waking TV via Wake-on-LAN")
    send_wol()
    await asyncio.sleep(WOL_BOOT_WAIT_SECONDS)

    client = await _connect()
    if client is None:
        log("could not reach TV after Wake-on-LAN -- will retry next cycle")
        return "settled"
    try:
        await client.set_input(KIOSK_INPUT_ID)
        log("switched TV to our input")
        await _enforce_kiosk_volume(client, log)
    except Exception as e:
        log(f"input-switch attempt failed: {e}")
    finally:
        await client.disconnect()
    return "settled"


async def enforce_volume_floor(log=lambda msg: None) -> bool:
    """Bumps the TV's volume up to VOLUME_FLOOR if it's currently
    below that -- session request: "set a floor for the volume every
    single day." Never lowers it (someone deliberately turning it up
    is untouched); only raises a volume that's dropped below the
    floor (a kid/guest turning it down, or it just defaulting low).
    Returns whether it actually got to run (True) or the TV was
    unreachable (False, run_lg_tv_sync.py's own caller just tries
    again later the same day) -- deliberately NOT gated on which input
    is active, unlike the two functions above: a volume floor is about
    the TV as a whole, not specifically the kiosk's own input, and
    raising (never lowering) the volume doesn't interrupt whatever's
    playing the way a power-off or input-switch would."""
    client = await _connect()
    if client is None:
        return False
    try:
        volume = await client.get_volume()
        if volume is None:
            log("could not read current volume -- skipping floor check")
            return False
        if volume < VOLUME_FLOOR:
            await client.set_volume(VOLUME_FLOOR)
            log(f"volume was {volume}, below the floor of {VOLUME_FLOOR} -- raised")
        else:
            log(f"volume is {volume}, already at or above the floor of {VOLUME_FLOOR} -- left alone")
        return True
    except Exception as e:
        log(f"volume floor check failed: {e}")
        return False
    finally:
        await client.disconnect()


async def send_pending_notifications(last_shown_at: float, log=lambda msg: None) -> float:
    """Shows any queued phone-style notification (ntfy_client.py's own
    queue_for_tv — every real ntfy_client.send() call already queues
    one here too) that arrived after last_shown_at, as a real on-screen
    webOS toast (confirmed live: send_message overlays cleanly even
    while genuinely on the Xbox input, not just on webOS's own home
    screen).

    Session follow-up: "I only get the on-screen messages though when
    I'm on my Xbox, not on the kiosk" — an alert on the kiosk's own
    input is already visible as a toast on the dashboard itself right
    there, showing it again here would be pure noise. Gated on
    get_current_app() the same way the other two action functions in
    this module already are.

    Returns the new watermark to persist. Deliberately UNCHANGED
    (never advanced) when nothing was actually shown — TV off/
    unreachable, or genuinely on the kiosk's own input — so a real
    notification that arrives while away from any screen, or while
    currently looking at the kiosk, is still waiting once genuinely
    back on the Xbox, rather than silently marked "seen" and lost.

    Real gap, caught live: ntfy_client.py's own age cap only trims the
    queue as a side effect of a NEW write -- it's not a background
    timer. A kiosk-box outage (see run_lg_tv_sync.py's own systemd
    Restart=on-failure) that catches exactly one notification with
    nothing after it would leave that single entry sitting un-trimmed
    indefinitely, so it could still show up looking "fresh" long after
    it's genuinely stale once the box reconnects. Filtered by the same
    age here too, at READ time, so staleness is caught either way --
    whichever of the two checks (this one, or ntfy_client.py's own
    write-time trim) runs first."""
    queue = persisted_state.load(NOTIFICATION_QUEUE_KEY, [])
    now_ts = time.time()
    pending = [
        n for n in queue
        if n.get("at", 0) > last_shown_at and now_ts - n.get("at", 0) <= NOTIFICATION_MAX_AGE_SECONDS
    ]
    if not pending:
        return last_shown_at

    client = await _connect()
    if client is None:
        return last_shown_at  # TV off/unreachable -- leave watermark alone, try again later
    try:
        current = await _current_app_id(client)
        if current == KIOSK_APP_ID:
            log("TV is on the kiosk -- notifications already visible there, skipping TV toast")
            return last_shown_at
        newest = last_shown_at
        for note in sorted(pending, key=lambda n: n.get("at", 0)):
            title = (note.get("title") or "").strip()
            message = (note.get("message") or "").strip()
            text = f"{title}: {message}" if title and message else (title or message)
            try:
                await client.send_message(text[:NOTIFICATION_MAX_CHARS])
                log(f"showed TV notification: {text[:60]!r}")
            except Exception as e:
                log(f"send_message failed for {text[:60]!r}: {e}")
            newest = max(newest, note.get("at", 0))
            if len(pending) > 1:
                await asyncio.sleep(1)  # let toasts land one at a time rather than clobbering
        return newest
    finally:
        await client.disconnect()


# Session request: "do the push subscriptions... if it means everything
# will start reacting in real time, that's good." aiowebostv already
# subscribes to the TV's own state (power/current app/volume/etc.)
# automatically as part of connect() -- confirmed live by reading the
# library's own connect_handler (_get_states_and_subscribe_state_
# updates runs unprompted, no manual subscribe_x() calls needed) --
# register_state_update_callback below just taps into that already-
# running stream. This is the one real "instant, not polled" half of
# the sync: the TV pushes a change the moment it happens (someone
# nudges the kiosk volume, switches input by hand) instead of run_lg_tv
# _sync.py finding out up to CHECK_INTERVAL_SECONDS later.
#
# What's still genuinely polled: night_mode_active and the
# notification queue live in Upstash, a plain REST key/value store
# with no push/webhook mechanism on the free tier -- there's no way to
# make THAT half instant, only faster-polled (see run_lg_tv_sync.py's
# own reduced interval). This function is purely about the TV's own
# state, not the dashboard's.
STATE_WATCH_RECONNECT_DELAY_SECONDS = 15


# Session request: "have the TV turn on like an hour before I have to
# get up... check... if I wake up I know how much time I have and
# whether it's worth going back to bed." Deliberately independent of
# night_mode_active itself -- this fires WHILE still in night mode,
# waking the TV to the SAME night-mode-styled screen (which now
# includes sleep_tracker's own wake-countdown block) rather than
# ending night mode early into the full bright daytime dashboard.
# Shares sleep_tracker.WAKE_PREVIEW_MINUTES with that display so "the
# TV turns on" and "the countdown is visible" always agree on timing.
#
# Only ever wakes a TV that's currently UNREACHABLE (presumed off) --
# if it's already reachable (on the kiosk, on Xbox, whatever), this is
# a no-op; the whole point is waking a sleeping TV for an early check-
# in, never fighting something already active. This also means it
# naturally never re-fires once the TV's awake for the window: the
# very next call finds it reachable and does nothing, no separate dedup
# state needed. Deliberately does NOT auto-power the TV back off if
# left on and unused -- out of scope for what was actually asked; a
# known trade-off, not an oversight.
async def wake_preview_if_due(log=lambda msg: None) -> None:
    # Session bug, live: this used to gate on its own narrower window
    # (0 <= remaining <= WAKE_PREVIEW_MINUTES) -- only the run-up to
    # wake_time, never the WAKE_OVERDUE_GRACE_MINUTES after it that
    # sleep_tracker.in_wake_grace_window (and the dashboard's own "Get
    # up now" countdown) already covers. Caught live: the TV went
    # unreachable at 8:30 wake time and this stayed silent through the
    # whole overdue stretch instead of bringing it back -- if anything,
    # overdue is the moment you most want the TV actually on. Reuses
    # the exact same window the dashboard countdown uses so the two can
    # never disagree with each other.
    now = datetime.now()
    if not sleep_tracker.in_wake_grace_window(now):
        return
    wake_time = sleep_tracker.wake_time_for(now)
    if wake_time is None:
        return
    now_aware = now.replace(tzinfo=wake_time.tzinfo) if wake_time.tzinfo else now
    remaining_minutes = (wake_time - now_aware).total_seconds() / 60

    client = await _connect()
    if client is not None:
        await client.disconnect()
        return  # already reachable (on, whatever it's showing) -- nothing to do

    log(f"waking TV for wake-preview ({remaining_minutes:+.0f} min relative to wake time)")
    send_wol()
    await asyncio.sleep(WOL_BOOT_WAIT_SECONDS)
    client = await _connect()
    if client is None:
        log("could not reach TV after wake-preview WoL -- will retry next cycle")
        return
    try:
        await client.set_input(KIOSK_INPUT_ID)
        log("switched TV to kiosk for wake-preview")
    except Exception as e:
        log(f"wake-preview input-switch failed: {e}")
    finally:
        await client.disconnect()


async def watch_state(log=lambda msg: None) -> None:
    """Runs forever (until cancelled) — maintains one persistent
    connection to the TV and reacts instantly to its own state pushes.
    Right now that means: the moment the TV reports it's on our own
    input, enforce KIOSK_VOLUME immediately, rather than waiting for
    the next poll tick to notice a manual volume nudge. When the TV
    goes offline (sleeps, loses network), this simply waits
    STATE_WATCH_RECONNECT_DELAY_SECONDS and tries again — it does NOT
    attempt to wake the TV itself (that's run_lg_tv_sync.py's own
    Upstash-driven job, via wake_and_switch_if_safe); this function
    only ever reacts to a TV that's already reachable on its own."""
    while True:
        try:
            await _watch_state_once(log)
        except Exception as e:
            # Same "one bad cycle must never kill the loop" rule every
            # other long-running poller in this app already follows
            # (run_spoken_morning_brief.py's own main(), etc.) -- a
            # single unexpected error here (e.g. client.disconnect()
            # itself raising on an already-broken socket) would
            # otherwise propagate out of watch_state entirely, taking
            # down the asyncio.gather() it runs under in
            # run_lg_tv_sync.py and killing the OTHER coroutine
            # (_poll_loop) right along with it.
            log(f"state watcher error: {e}")
            await asyncio.sleep(STATE_WATCH_RECONNECT_DELAY_SECONDS)


async def _watch_state_once(log) -> None:
    client = await _connect()
    if client is None:
        await asyncio.sleep(STATE_WATCH_RECONNECT_DELAY_SECONDS)
        return

    log("state watcher connected -- live TV pushes active")
    last_app_id: str | None = None

    async def on_state_update(state) -> None:
        nonlocal last_app_id
        current = state.current_app_id
        # Kiosk: reacts to EVERY push while on our own input, not just
        # the edge into it -- a manual volume nudge while already
        # watching the kiosk is itself one of these pushes, and should
        # snap back immediately too, not just on the next input switch.
        # _enforce_kiosk_volume is a safe no-op once volume is already
        # correct (including the follow-up push ITS OWN set_volume
        # call triggers), so no feedback loop.
        if current == KIOSK_APP_ID:
            await _enforce_kiosk_volume(client, log)
        # Xbox: the OPPOSITE shape on purpose -- only on the edge INTO
        # Xbox from something else, a one-time landing volume, never
        # re-applied while already there (volume is free to move
        # afterward, per the session's own explicit "as need be").
        elif current == XBOX_APP_ID and last_app_id != XBOX_APP_ID:
            await _set_xbox_landing_volume(client, log)
        last_app_id = current

    client.register_state_update_callback(on_state_update)
    try:
        while client.is_connected():
            await asyncio.sleep(2)
    finally:
        log("state watcher lost connection to TV -- will retry")
        await client.disconnect()
