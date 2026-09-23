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
OUR OWN input (webOS reports HDMI_1 as "com.webos.app.hdmi1"), and
only woken + switched back to our input in the morning if the TV is
either already off or already sitting on our own input. Anything else
(a different HDMI port, a smart-TV app like Netflix) is left alone.
"""

import asyncio
import socket
from pathlib import Path

from aiowebostv import WebOsClient

TV_HOST = "192.168.0.152"
TV_MAC = "d8:e3:5e:bb:2c:7a"
# webOS's own app id for whichever HDMI port the kiosk box is plugged
# into — confirmed live via get_current_app() while the kiosk was the
# active input (see this module's own pairing/verification session).
OUR_APP_ID = "com.webos.app.hdmi1"
OUR_INPUT_ID = "HDMI_1"
KEY_FILE = Path.home() / ".config" / "kiosk-lg-tv-key"
CONNECT_TIMEOUT_SECONDS = 5
# Rough real-world boot time for webOS to come back up enough to accept
# a fresh websocket connection after a Wake-on-LAN packet — tuned loose
# rather than tight, a few extra seconds of "TV still says off" costs
# nothing here, a too-short wait would just mean a failed connect and a
# wasted cycle (the poller tries again next minute regardless).
WOL_BOOT_WAIT_SECONDS = 10


def _client_key() -> str | None:
    if KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
        return key or None
    return None


def send_wol(mac: str = TV_MAC) -> None:
    """Broadcasts a standard Wake-on-LAN magic packet — the only way to
    reach a webOS TV that's gone into full standby (its websocket
    server, and therefore every other command in this module, is
    unreachable at that point; only a low-power WoL listener stays up,
    and only if Wake on LAN is enabled in the TV's own network
    settings)."""
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.sendto(packet, ("255.255.255.255", 9))
    finally:
        sock.close()


async def _connect() -> WebOsClient | None:
    """A connected, already-paired client, or None if there's no saved
    pairing yet or the TV genuinely isn't reachable right now (off, or
    off the network) — never raises, every caller treats None the same
    way a CEC "no adapter" result already had to be treated: skip this
    cycle, try again later."""
    key = _client_key()
    if key is None:
        return None
    client = WebOsClient(TV_HOST, client_key=key, connect_timeout=CONNECT_TIMEOUT_SECONDS)
    try:
        await client.connect()
    except Exception:
        return None
    return client


async def _current_app_id(client: WebOsClient) -> str | None:
    """aiowebostv's own type hint on get_current_app() claims a dict,
    but confirmed live it actually returns the plain app-id string
    directly (or None) -- get_current_app() -> res.get("appId") inside
    the library itself, already unwrapped."""
    try:
        return await client.get_current_app()
    except Exception:
        return None


async def power_off_if_ours(log=lambda msg: None) -> None:
    """Night mode engaging: power the TV off, but only if it's
    currently showing OUR OWN input — see this module's own docstring
    for why. Silently does nothing if the TV's already off/unreachable
    (nothing to turn off) or on something else entirely (not ours to
    touch)."""
    client = await _connect()
    if client is None:
        log("TV unreachable or not yet paired -- skipping power-off")
        return
    try:
        current = await _current_app_id(client)
        if current != OUR_APP_ID:
            log(f"TV is on a different input/app ({current!r}) -- leaving it alone")
            return
        await client.power_off()
        log("TV was on our input -- powered off")
    except Exception as e:
        log(f"power-off attempt failed: {e}")
    finally:
        await client.disconnect()


async def wake_and_switch_if_safe(log=lambda msg: None) -> None:
    """Night mode ending: bring the TV back to our input — but same
    "don't interrupt" rule, checked BEFORE waking anything. If the TV
    is already reachable and on something other than our own input, it
    means someone's actively using it (or already on it, no-op either
    way) -- left alone. Only reachable-and-idle-on-ours or genuinely
    unreachable (presumed off, since we're the only thing that turns it
    off) leads to a real wake + switch."""
    client = await _connect()
    if client is not None:
        try:
            current = await _current_app_id(client)
        finally:
            await client.disconnect()
        if current is not None and current != OUR_APP_ID:
            log(f"TV is already on a different input/app ({current!r}) -- leaving it alone")
            return
        if current == OUR_APP_ID:
            log("TV already on our input -- nothing to do")
            return
        # current is None despite being reachable (e.g. a screensaver
        # app with no clean appId) -- fall through and just make sure
        # our input is selected, same as the unreachable/off path below.

    log("waking TV via Wake-on-LAN")
    send_wol()
    await asyncio.sleep(WOL_BOOT_WAIT_SECONDS)

    client = await _connect()
    if client is None:
        log("could not reach TV after Wake-on-LAN -- will retry next cycle")
        return
    try:
        await client.set_input(OUR_INPUT_ID)
        log("switched TV to our input")
    except Exception as e:
        log(f"input-switch attempt failed: {e}")
    finally:
        await client.disconnect()
