"""One-time pairing helper for lg_tv_control.py — run manually
(`python3 lg_tv_pair.py`) if the TV is ever un-paired (a factory
reset, a new TV, a revoked "connected devices" entry in the TV's own
settings). The TV shows an on-screen "allow this device to connect?"
prompt during connect(); accept it there. Every normal run afterwards
(lg_tv_control.py's own poller) reuses the saved key silently, no
prompt."""

import asyncio

from aiowebostv import WebOsClient

from lg_tv_control import KEY_FILE, TV_HOST


async def main() -> None:
    client = WebOsClient(TV_HOST, client_key=None)
    print(f"Connecting to {TV_HOST} -- accept the prompt on the TV screen now...")
    await client.connect()
    if not client.client_key:
        print("No client key received -- pairing did not complete.")
        return
    KEY_FILE.write_text(client.client_key)
    print(f"Paired. Client key saved to {KEY_FILE}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
