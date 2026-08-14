"""
Collect the member lists of every Discord server you're in, find the people who
share >= N of those servers with you, and export a bipartite graph
(people <-> servers) for the Cytoscape.js viewer.

    !!  This drives Discord's *user* client endpoints via a self-bot library.  !!
    !!  Automating a user account violates Discord's Terms of Service and can   !!
    !!  get the account terminated. It has to be YOUR account (an alt won't be  !!
    !!  in your servers), so the account at risk is your real one. Read-only     !!
    !!  and throttled, but not zero-risk. You accepted this tradeoff.            !!

Usage:
    pip install -r requirements.txt
    export DISCORD_TOKEN='your-user-token'      # never hard-code / commit this
    python collect.py                           # writes graph.json + graph-data.js

Then open viz.html in a browser.

Getting your token (web client): open DevTools -> Network, filter by "science" or
any API request, and copy the value of the `Authorization` request header. Treat
it like a password; anyone with it has full access to your account.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import defaultdict

import discord

# --- config -----------------------------------------------------------------

TOKEN = os.environ.get("DISCORD_TOKEN")

# Keep a person only if they share at least this many of *your* servers with you.
MIN_SHARED = int(os.environ.get("MIN_SHARED", "2"))

# Politeness delay (seconds) between processing guilds, to stay gentle on the API.
PER_GUILD_DELAY = float(os.environ.get("PER_GUILD_DELAY", "5.0"))

# Delay (seconds) between sidebar-scrape requests *within* a large guild.
SCRAPE_DELAY = float(os.environ.get("SCRAPE_DELAY", "1.0"))

OUT_JSON = "graph.json"
OUT_JS = "graph-data.js"  # same data, wrapped so viz.html can load it via file://


async def collect_guild_members(guild: discord.Guild) -> tuple[dict[int, discord.Member], str]:
    """Return {user_id: Member} for a guild plus a short note about completeness.

    ``Guild.fetch_members`` requests members normally (including offline) when the
    account has kick/ban/manage_roles here; otherwise it scrapes the member
    sidebar, which for >1000-member guilds may only return online members.
    """
    try:
        members_list = await guild.fetch_members(cache=True, delay=SCRAPE_DELAY)
    except Exception as exc:  # noqa: BLE001 - report and continue with the rest
        return {}, f"error: {exc}"

    members = {m.id: m for m in members_list}
    member_count = guild.member_count or 0
    if member_count and len(members) < member_count:
        note = f"partial ({len(members)}/{member_count}; likely online-only)"
    else:
        note = "full"
    return members, note


class Collector(discord.Client):
    async def on_ready(self) -> None:
        try:
            await self.run_collection()
        finally:
            await self.close()

    async def run_collection(self) -> None:
        me = self.user
        guilds = list(self.guilds)
        print(f"Logged in as {me} ({me.id}). In {len(guilds)} servers.\n", file=sys.stderr)

        # guild_id -> set of member ids ; and lookup tables for names.
        guild_members: dict[int, set[int]] = {}
        guild_info: dict[int, dict] = {}
        user_names: dict[int, dict] = {}

        for i, guild in enumerate(guilds, 1):
            members, note = await collect_guild_members(guild)
            guild_members[guild.id] = set(members)
            guild_info[guild.id] = {
                "id": str(guild.id),
                "name": guild.name,
                "member_count": guild.member_count,
                "collected": len(members),
                "coverage": note,
            }
            for uid, m in members.items():
                if uid not in user_names:
                    user_names[uid] = {
                        "id": str(uid),
                        "username": str(getattr(m, "name", "") or ""),
                        "display": m.display_name,
                    }
            print(
                f"[{i}/{len(guilds)}] {guild.name!r}: {len(members)} members ({note})",
                file=sys.stderr,
            )
            await asyncio.sleep(PER_GUILD_DELAY)

        # How many of MY guilds each user appears in.
        shared_by_user: dict[int, list[int]] = defaultdict(list)
        for gid, member_ids in guild_members.items():
            for uid in member_ids:
                shared_by_user[uid].append(gid)

        my_id = me.id
        people = []
        for uid, gids in shared_by_user.items():
            if uid == my_id:
                continue
            if len(gids) < MIN_SHARED:
                continue
            info = user_names.get(uid, {"id": str(uid), "username": "", "display": str(uid)})
            people.append(
                {
                    **info,
                    "shared": [str(g) for g in gids],
                    "shared_count": len(gids),
                }
            )

        people.sort(key=lambda p: p["shared_count"], reverse=True)

        data = {
            "me": {"id": str(my_id), "display": me.display_name, "username": str(me.name)},
            "min_shared": MIN_SHARED,
            "servers": list(guild_info.values()),
            "people": people,
        }

        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(OUT_JS, "w", encoding="utf-8") as f:
            f.write("window.GRAPH_DATA = ")
            json.dump(data, f, ensure_ascii=False)
            f.write(";\n")

        print(
            f"\nDone. {len(people)} people share >= {MIN_SHARED} servers with you.\n"
            f"Wrote {OUT_JSON} and {OUT_JS}. Open viz.html to explore.",
            file=sys.stderr,
        )


def main() -> None:
    if not TOKEN:
        sys.exit("Set DISCORD_TOKEN in your environment first (see the module docstring).")
    client = Collector()
    # discord.py-self logs in as a user account when given a user token.
    client.run(TOKEN)


if __name__ == "__main__":
    main()
