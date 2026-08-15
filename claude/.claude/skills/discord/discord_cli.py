"""
discord_cli.py — read-only CLI over a Discord *user* account.

Lets Claude (or you) search servers, browse channels, read history and forum
posts, look up profiles/mentions/DMs, and download attachments — all over the
authenticated REST endpoints, no gateway connection and NO write capability
(there is deliberately no message-writing command — no send/edit/delete or
add-reaction — so it can never post on your behalf; `reactions` only reads who
reacted).

    !!  Driving a user account is against Discord's ToS and can get it banned.  !!
    !!  Read-only + on-demand keeps the footprint low, but the risk isn't zero. !!

Auth: token from the macOS Keychain (service `discord-cli`) if present, else the
DISCORD_TOKEN env var. Store it once with:  discord auth store

Everything prints JSON to stdout (logs go to stderr), so pipe through jq/grep.
Run `discord <command> -h` for per-command flags.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import discord

KEYCHAIN_SERVICE = "discord-cli"
KEYCHAIN_ACCOUNT = "token"
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "discord"

logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
for noisy in ("discord", "discord.client", "discord.gateway", "discord.http"):
    logging.getLogger(noisy).setLevel(logging.ERROR)


# --- auth -------------------------------------------------------------------

def _keyring_backend() -> str | None:
    """Which OS secret store to use: macOS Keychain or libsecret."""
    if sys.platform == "darwin":
        return "security" if shutil.which("security") else None
    return "secret-tool" if shutil.which("secret-tool") else None


def get_token() -> str:
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        return token.strip()

    backend = _keyring_backend()
    if backend == "security":
        cmd = ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
               "-a", KEYCHAIN_ACCOUNT, "-w"]
    elif backend == "secret-tool":
        cmd = ["secret-tool", "lookup", "service", KEYCHAIN_SERVICE,
               "account", KEYCHAIN_ACCOUNT]
    else:
        cmd = None

    if cmd:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, check=True)
            if out.stdout.strip():
                return out.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    hint = "" if backend else (
        "\nNo OS secret store found. On Linux install libsecret "
        "(provides secret-tool), or export DISCORD_TOKEN."
    )
    sys.exit(f"No token found. Set DISCORD_TOKEN or run: discord auth store{hint}")


def store_token(token: str) -> None:
    backend = _keyring_backend()
    if backend == "security":
        # -w takes the secret as an argument; fine here since macOS `security`
        # offers no stdin form.
        subprocess.run(
            ["security", "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE,
             "-a", KEYCHAIN_ACCOUNT, "-w", token],
            check=True,
        )
    elif backend == "secret-tool":
        # secret-tool reads the secret from stdin, so it never reaches argv or
        # the process list.
        subprocess.run(
            ["secret-tool", "store", "--label", KEYCHAIN_SERVICE,
             "service", KEYCHAIN_SERVICE, "account", KEYCHAIN_ACCOUNT],
            input=token, text=True, check=True,
        )
    else:
        sys.exit(
            "No OS secret store available.\n"
            "  macOS: `security` should already be present.\n"
            "  Linux: install libsecret (provides secret-tool), or export "
            "DISCORD_TOKEN in your shell profile."
        )


# --- helpers ----------------------------------------------------------------

def out(obj) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


def parse_when(value: str | None):
    """Accept an ISO date/datetime or a raw snowflake id for before/after."""
    if not value:
        return None
    if value.isdigit():
        return discord.Object(id=int(value))
    return datetime.fromisoformat(value)


JUMP_RE = re.compile(r"channels/(?:@me|\d+)/(\d+)/(\d+)")


def parse_locator(args_list: list[str]) -> tuple[int, int]:
    """Return (channel_id, message_id) from a jump URL or two ids."""
    joined = " ".join(args_list)
    m = JUMP_RE.search(joined)
    if m:
        return int(m.group(1)), int(m.group(2))
    ids = [a for a in args_list if a.isdigit()]
    if len(ids) == 2:
        return int(ids[0]), int(ids[1])
    sys.exit("Give a jump URL (https://discord.com/channels/…/…/…) or: <channel_id> <message_id>")


URL_RE = re.compile(r"https?://[^\s<>|]+")


def extract_links(text: str | None) -> list[str]:
    return URL_RE.findall(text or "")


def fmt_embed(e) -> dict:
    d = {"type": e.type, "title": e.title, "url": e.url}
    if e.description:
        d["description"] = e.description[:600]
    if e.fields:
        d["fields"] = [{"name": f.name, "value": f.value} for f in e.fields]
    if e.author and e.author.name:
        d["author"] = e.author.name
    return {k: v for k, v in d.items() if v}


def fmt_channel(ch) -> dict:
    return {
        "id": str(ch.id),
        "name": getattr(ch, "name", None),
        "type": ch.type.name if getattr(ch, "type", None) else None,
        "topic": getattr(ch, "topic", None),
        "category": getattr(getattr(ch, "category", None), "name", None),
        "nsfw": getattr(ch, "nsfw", None),
    }


def fmt_message(msg, guild_id=None) -> dict:
    gid = msg.guild.id if msg.guild else guild_id
    jump = (f"https://discord.com/channels/{gid}/{msg.channel.id}/{msg.id}"
            if gid else msg.jump_url)
    return {
        "id": str(msg.id),
        "guild_id": str(gid) if gid else None,
        "channel_id": str(msg.channel.id),
        "channel": getattr(msg.channel, "name", None),
        "author": getattr(msg.author, "display_name", None) or msg.author.name,
        "author_handle": msg.author.name,
        "author_id": str(msg.author.id),
        "ts": msg.created_at.isoformat(),
        "content": msg.content,
        "attachments": [
            {"id": str(a.id), "filename": a.filename, "size": a.size,
             "content_type": a.content_type}
            for a in msg.attachments
        ],
        "embeds": [fmt_embed(e) for e in msg.embeds],
        "links": extract_links(msg.content),
        "reactions": [{"emoji": str(r.emoji), "count": r.count} for r in msg.reactions],
        "pinned": msg.pinned,
        "jump_url": jump,
    }


def fmt_raw_message(d: dict) -> dict:
    """Format a raw message dict (e.g. from the recent-mentions endpoint)."""
    author = d.get("author") or {}
    gid = d.get("guild_id")
    content = d.get("content") or ""
    return {
        "id": d.get("id"),
        "guild_id": gid,
        "channel_id": d.get("channel_id"),
        "author": author.get("global_name") or author.get("username"),
        "author_id": author.get("id"),
        "ts": d.get("timestamp"),
        "content": content,
        "attachments": [{"filename": a.get("filename"), "size": a.get("size")}
                        for a in d.get("attachments", [])],
        "links": extract_links(content),
        "jump_url": f"https://discord.com/channels/{gid or '@me'}/"
                    f"{d.get('channel_id')}/{d.get('id')}",
    }


def fmt_thread(t) -> dict:
    return {
        "id": str(t.id),
        "title": t.name,
        "owner_id": str(t.owner_id) if t.owner_id else None,
        "message_count": t.message_count,
        "archived": t.archived,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "jump_url": f"https://discord.com/channels/{t.guild.id}/{t.id}",
    }


def fmt_forum_post(t: dict, first_msg: dict | None, tag_names: dict, guild_id) -> dict:
    meta = t.get("thread_metadata", {})
    return {
        "id": t["id"],
        "title": t.get("name"),
        "owner_id": t.get("owner_id"),
        "message_count": t.get("message_count"),
        "created_at": meta.get("create_timestamp"),
        "archived": meta.get("archived", False),
        "tags": [tag_names.get(str(tid), str(tid)) for tid in t.get("applied_tags", [])],
        "jump_url": f"https://discord.com/channels/{guild_id}/{t['id']}",
        "op_excerpt": (first_msg.get("content") or "")[:400] if first_msg else None,
        "op_attachments": [a["filename"] for a in (first_msg or {}).get("attachments", [])],
    }


async def forum_posts(client, forum, limit: int, active: bool, archived: bool) -> list[dict]:
    """Page the user-client forum browse endpoint (/threads/search)."""
    tag_names = {str(t.id): t.name for t in getattr(forum, "available_tags", [])}
    results: list[dict] = []

    async def page(is_archived: bool):
        offset = 0
        while len(results) < limit:
            route = discord.http.Route("GET", "/channels/{channel_id}/threads/search",
                                       channel_id=forum.id)
            data = await client.http.request(route, params={
                "sort_by": "last_message_time", "sort_order": "desc",
                "limit": 25, "offset": offset, "archived": str(is_archived).lower()})
            threads = data.get("threads", [])
            firsts = {str(m["channel_id"]): m for m in data.get("first_messages", [])}
            for t in threads:
                results.append(fmt_forum_post(t, firsts.get(str(t["id"])), tag_names,
                                              forum.guild.id))
                if len(results) >= limit:
                    return
            if not data.get("has_more") or not threads:
                return
            offset += len(threads)

    if active:
        await page(False)
    if archived and len(results) < limit:
        await page(True)
    return results


async def resolve_guild_id(client, ref: str) -> int:
    if ref.isdigit():
        return int(ref)
    ref_l = ref.lower()
    guilds = await client.fetch_guilds(with_counts=False)
    matches = [g for g in guilds if ref_l in g.name.lower()]
    if not matches:
        sys.exit(f"No server matching {ref!r}.")
    if len(matches) > 1:
        exact = [g for g in matches if g.name.lower() == ref_l]
        if len(exact) == 1:
            return exact[0].id
        names = ", ".join(f"{g.name} ({g.id})" for g in matches[:8])
        sys.exit(f"Ambiguous server {ref!r}: {names}. Use the id.")
    return matches[0].id


async def resolve_channel(client, ref: str, server: str | None):
    if ref.isdigit():
        return await client.fetch_channel(int(ref))
    if not server:
        sys.exit("Channel by name needs --server; or pass a numeric channel id.")
    gid = await resolve_guild_id(client, server)
    guild = await client.fetch_guild(gid)
    ref_l = ref.lstrip("#").lower()
    for ch in await guild.fetch_channels():
        if getattr(ch, "name", "").lower() == ref_l:
            return ch
    sys.exit(f"No channel {ref!r} in that server.")


# --- commands ---------------------------------------------------------------

async def cmd_whoami(client, args):
    u = client.user
    out({"id": str(u.id), "handle": u.name, "display": u.global_name or u.name})


async def cmd_servers(client, args):
    guilds = await client.fetch_guilds(with_counts=True)
    rows = [{"id": str(g.id), "name": g.name,
             "member_count": getattr(g, "approximate_member_count", None),
             "owner": g.owner}
            for g in guilds]
    rows.sort(key=lambda r: (r["member_count"] or 0), reverse=True)
    out(rows)


async def cmd_channels(client, args):
    gid = await resolve_guild_id(client, args.server)
    guild = await client.fetch_guild(gid)
    channels = await guild.fetch_channels()
    if args.type:
        channels = [c for c in channels if c.type.name == args.type]
    out([fmt_channel(c) for c in channels])


def build_search_kwargs(args) -> dict:
    kwargs = {"limit": args.limit, "most_relevant": args.relevant}
    if args.has:
        kwargs["has"] = args.has
    if args.pinned:
        kwargs["pinned"] = True
    if args.author:
        kwargs["authors"] = [discord.Object(id=int(a)) for a in args.author]
    if args.mentions:
        kwargs["mentions"] = [discord.Object(id=int(a)) for a in args.mentions]
    if args.filename:
        kwargs["attachment_filenames"] = args.filename
    if args.ext:
        kwargs["attachment_extensions"] = args.ext
    before, after = parse_when(args.before), parse_when(args.after)
    if before:
        kwargs["before"] = before
    if after:
        kwargs["after"] = after
    return kwargs


async def cmd_search(client, args):
    kwargs = build_search_kwargs(args)
    content = args.query if args.query else discord.utils.MISSING

    if args.dm:
        # Search a single DM / group DM (opt-in; your most private data).
        ch = await client.fetch_channel(int(args.dm))
        out([fmt_message(m) async for m in ch.search(content, **kwargs)])
        return

    if args.all_servers:
        # Sweep every guild. Heavier + rate-limited, so be gentle and label rows.
        results = []
        for g in await client.fetch_guilds(with_counts=False):
            try:
                guild = await client.fetch_guild(g.id)
                async for msg in guild.search(content, **kwargs):
                    row = fmt_message(msg, guild_id=g.id)
                    row["server"] = g.name
                    results.append(row)
            except Exception:  # noqa: BLE001 - skip guilds we can't search
                continue
            await asyncio.sleep(0.4)
        out(results)
        return

    if not args.server:
        sys.exit("search needs --server (or --all-servers, or --dm <channel_id>).")
    gid = await resolve_guild_id(client, args.server)
    guild = await client.fetch_guild(gid)
    if args.channel:
        # Pass real channel objects (not bare Object ids): the library uses them
        # to build result Message objects and needs their guild_id, which a bare
        # Object lacks under our gateway-free (uncached) login.
        kwargs["channels"] = [await resolve_channel(client, c, args.server)
                              for c in args.channel]
    name_map = {str(c.id): c.name for c in await guild.fetch_channels()}
    results = []
    async for msg in guild.search(content, **kwargs):
        row = fmt_message(msg, guild_id=gid)
        row["channel"] = name_map.get(row["channel_id"], row["channel"])
        results.append(row)
    out(results)


async def cmd_read(client, args):
    ch = await resolve_channel(client, args.channel, args.server)
    if args.pinned:
        pins = await ch.pins()
        out([fmt_message(m) for m in pins])
        return
    hist_kwargs = {"limit": args.limit}
    if args.before:
        hist_kwargs["before"] = parse_when(args.before)
    if args.after:
        hist_kwargs["after"] = parse_when(args.after)
    if args.around:
        hist_kwargs["around"] = discord.Object(id=int(args.around))
    msgs = [m async for m in ch.history(**hist_kwargs)]
    msgs.reverse()  # oldest-first for readability
    out([fmt_message(m) for m in msgs])


async def cmd_threads(client, args):
    ch = await resolve_channel(client, args.forum, args.server)
    if isinstance(ch, discord.ForumChannel):
        out(await forum_posts(client, ch, limit=args.limit,
                              active=not args.archived_only,
                              archived=not args.active_only))
        return
    # Text/news channel: list its (public) archived threads over REST. Active
    # threads need the gateway, so they may be incomplete here.
    posts = []
    async for t in ch.archived_threads(limit=args.limit):
        posts.append(fmt_thread(t))
    out(posts)


async def cmd_thread(client, args):
    th = await client.fetch_channel(int(args.thread_id))
    msgs = [m async for m in th.history(limit=args.limit, oldest_first=True)]
    out({"id": str(th.id), "title": getattr(th, "name", None),
         "messages": [fmt_message(m) for m in msgs]})


async def cmd_message(client, args):
    ch = await client.fetch_channel(int(args.channel))
    if args.context:
        around = [m async for m in ch.history(limit=args.context * 2 + 1,
                                              around=discord.Object(id=int(args.message)))]
        around.reverse()
        out([fmt_message(m) for m in around])
    else:
        msg = await ch.fetch_message(int(args.message))
        out(fmt_message(msg))


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("_") or "file"


async def cmd_download(client, args):
    channel_id, message_id = parse_locator(args.target)
    ch = await client.fetch_channel(channel_id)
    msg = await ch.fetch_message(message_id)  # fresh, signed attachment URLs
    atts = msg.attachments
    if not atts:
        # Surface links/embeds so an externally-hosted file (Mega/GDrive/GitHub)
        # is still actionable even though there's no Discord attachment.
        out({"downloaded": [], "note": "No Discord attachments; see links/embeds.",
             "content": msg.content, "links": extract_links(msg.content),
             "embeds": [fmt_embed(e) for e in msg.embeds]})
        return
    if args.index is not None:
        atts = [atts[args.index]]
    elif args.name:
        pat = args.name.lower()
        atts = [a for a in atts if pat in a.filename.lower()]
    out_dir = Path(args.out).expanduser() if args.out else DEFAULT_DOWNLOAD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for a in atts:
        dest = out_dir / _safe_name(a.filename)
        n = await a.save(dest)
        saved.append({"filename": a.filename, "path": str(dest), "bytes": n,
                      "content_type": a.content_type})
    out({"downloaded": saved, "dir": str(out_dir)})


async def cmd_export(client, args):
    ch = await resolve_channel(client, args.channel, args.server)
    lines = [f"# Export: {getattr(ch, 'name', ch.id)} ({ch.id})\n"]

    async def dump(channel, header=None):
        if header:
            lines.append(f"\n## {header}\n")
        msgs = [m async for m in channel.history(limit=args.limit, oldest_first=True)]
        for m in msgs:
            who = getattr(m.author, "display_name", None) or m.author.name
            lines.append(f"**{who}** · {m.created_at.isoformat()} · {m.jump_url}")
            if m.content:
                lines.append(m.content)
            for a in m.attachments:
                lines.append(f"[attachment: {a.filename} ({a.size} bytes)]")
            lines.append("")

    if isinstance(ch, discord.ForumChannel):
        for post in await forum_posts(client, ch, limit=args.threads,
                                      active=True, archived=True):
            th = await client.fetch_channel(int(post["id"]))
            tags = f" [{', '.join(post['tags'])}]" if post["tags"] else ""
            await dump(th, header=f"{th.name}{tags} (post {th.id})")
    else:
        await dump(ch)

    dest = Path(args.out).expanduser() if args.out else \
        Path.cwd() / f"discord-export-{ch.id}.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    out({"exported": str(dest), "messages_channel": str(ch.id)})


async def cmd_mentions(client, args):
    kwargs = {"limit": args.limit, "roles": not args.no_roles,
              "everyone": not args.no_everyone}
    if args.server:
        kwargs["guild_id"] = discord.Object(id=await resolve_guild_id(client, args.server))
    data = await client.http.get_recent_mentions(**kwargs)
    out([fmt_raw_message(d) for d in data])


async def cmd_dms(client, args):
    rows = []
    for c in await client.fetch_private_channels():
        if isinstance(c, discord.GroupChannel):
            rows.append({"id": str(c.id), "type": "group", "name": c.name,
                         "recipients": [r.name for r in c.recipients]})
        else:
            r = c.recipient
            rows.append({"id": str(c.id), "type": "dm",
                         "name": r.name if r else None,
                         "recipient_id": str(r.id) if r else None})
    out(rows)


async def cmd_user(client, args):
    p = await client.fetch_user_profile(int(args.user_id))
    name_map = {g.id: g.name for g in await client.fetch_guilds(with_counts=False)}
    mutual = [{"id": str(mg.id),
               "name": name_map.get(mg.id) or getattr(mg.guild, "name", None),
               "nick": mg.nick}
              for mg in (p.mutual_guilds or [])]
    out({
        "id": str(p.id),
        "handle": p.name,
        "display": p.global_name or p.name,
        "bio": getattr(p, "bio", None) or None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "is_friend": getattr(p, "is_friend", None),
        "mutual_guilds": mutual,
        "mutual_friends_count": getattr(p, "mutual_friends_count", None),
        "connections": [{"type": getattr(x, "type", None), "name": getattr(x, "name", None),
                         "verified": getattr(x, "verified", None)}
                        for x in (getattr(p, "connections", None) or [])],
    })


async def cmd_reactions(client, args):
    ch = await client.fetch_channel(int(args.channel))
    msg = await ch.fetch_message(int(args.message))
    rows = []
    for r in msg.reactions:
        entry = {"emoji": str(r.emoji), "count": r.count}
        if args.users:
            entry["users"] = [u.name async for u in r.users(limit=args.user_limit)]
        rows.append(entry)
    out({"message": str(msg.id), "jump_url": msg.jump_url, "reactions": rows})


async def cmd_events(client, args):
    gid = await resolve_guild_id(client, args.server)
    guild = await client.fetch_guild(gid)
    events = await guild.fetch_scheduled_events(with_counts=True)
    out([{
        "id": str(e.id), "name": e.name, "description": e.description,
        "start": e.start_time.isoformat() if e.start_time else None,
        "end": e.end_time.isoformat() if e.end_time else None,
        "location": e.location or getattr(e.channel, "name", None),
        "user_count": getattr(e, "user_count", None),
        "status": str(e.status), "url": e.url,
    } for e in events])


# --- dispatch ---------------------------------------------------------------

PROPS_CACHE = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "discord-skill" / "client-props.json"
PROPS_TTL = 24 * 60 * 60


def _install_props_cache() -> None:
    """Cache the client fingerprint so each command stops re-fetching it.

    discord.py-self rebuilds its super-properties on every login, which costs a
    request to Discord's app page plus one to Chrome's version API. Since each
    CLI invocation is its own login, a handful of commands turns into a burst of
    identical fetches from one IP — exactly the pattern that reads as
    automation. The build number changes maybe daily, so caching it for a day is
    both safe and a big reduction in traffic.
    """
    from discord.utils import Headers

    original = Headers.default.__func__

    async def cached_default(cls, *a, **kw):
        try:
            blob = json.loads(PROPS_CACHE.read_text())
            if time.time() - blob["stamp"] < PROPS_TTL:
                props = blob["props"]
                encoded = base64.b64encode(
                    json.dumps(props, separators=(',', ':')).encode()
                ).decode()
                return Headers(
                    platform='Windows',
                    major_version=int(props['browser_version'].split('.')[0]),
                    super_properties=props,
                    encoded_super_properties=encoded,
                    extra_gateway_properties=blob.get("extra", {}),
                )
        except Exception:
            pass

        headers = await original(cls, *a, **kw)
        bn = headers.super_properties.get("client_build_number")
        if bn == Headers.FALLBACK_BUILD_NUMBER:
            # 9999 is the library's give-up value; sending it advertises a
            # client build that cannot exist. Better to stop than to look fake.
            sys.exit(
                "Refusing to connect: could not fetch Discord's real client build "
                "number, so requests would carry the bogus fallback (9999). Check "
                "your network and retry."
            )
        try:
            PROPS_CACHE.parent.mkdir(parents=True, exist_ok=True)
            PROPS_CACHE.write_text(json.dumps({
                "stamp": time.time(),
                "props": headers.super_properties,
                "extra": getattr(headers, "extra_gateway_properties", {}),
            }))
        except Exception:
            pass
        return headers

    Headers.default = classmethod(cached_default)


RATE_LOG = PROPS_CACHE.parent / "reqlog.json"
# Deliberately well under anything Discord would push back on. Each CLI run is
# its own process, so the budget has to live on disk or consecutive commands
# each start with a clean allowance and burst.
MAX_PER_MINUTE = int(os.environ.get("DISCORD_MAX_PER_MINUTE", "15"))
MIN_GAP_SECONDS = float(os.environ.get("DISCORD_MIN_GAP", "1.0"))
WINDOW = 60.0


def _reserve_slot() -> float:
    """Claim the next allowed request time; returns seconds to wait.

    Held under an exclusive lock so parallel invocations share one budget
    rather than each believing it has the full allowance.
    """
    import fcntl

    RATE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RATE_LOG, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            try:
                stamps = [float(x) for x in json.loads(fh.read() or "[]")]
            except Exception:
                stamps = []

            now = time.time()
            stamps = [t for t in stamps if now - t < WINDOW]

            earliest = now
            if stamps:
                earliest = max(earliest, stamps[-1] + MIN_GAP_SECONDS)
            if len(stamps) >= MAX_PER_MINUTE:
                # Wait for the oldest request in the window to age out.
                earliest = max(earliest, stamps[-MAX_PER_MINUTE] + WINDOW)

            stamps.append(earliest)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(stamps[-(MAX_PER_MINUTE * 2):]))
            return max(0.0, earliest - now)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _install_rate_limit() -> None:
    """Pace every outbound request.

    Two transports are in play: discord.py-self sends API calls through
    curl_cffi (which impersonates Chrome's TLS fingerprint), while the
    pre-login client-properties fetch goes over plain aiohttp. Both need
    throttling, so patch both.
    """
    import aiohttp
    from curl_cffi import requests as curl_requests

    def wrap(cls, attr, status_of):
        if getattr(cls, "_discord_skill_throttled", False):
            return
        original = getattr(cls, attr)

        async def throttled(self, method, url, *a, **kw):
            delay = _reserve_slot()
            if delay > 0:
                _log_throttle(delay)
                await asyncio.sleep(delay)
            resp = await original(self, method, url, *a, **kw)
            if status_of(resp) == 429:
                # Never argue with a 429 — say so and let the caller stop,
                # rather than retrying into a harder block.
                print("Rate limited by Discord. Backing off.", file=sys.stderr)
            return resp

        setattr(cls, attr, throttled)
        cls._discord_skill_throttled = True

    wrap(curl_requests.AsyncSession, "request", lambda r: getattr(r, "status_code", None))
    wrap(aiohttp.ClientSession, "_request", lambda r: getattr(r, "status", None))


def _log_throttle(delay: float) -> None:
    if delay >= 0.5:
        print(f"[rate limit] waiting {delay:.1f}s", file=sys.stderr)


async def run(fn, args):
    _install_props_cache()
    _install_rate_limit()
    client = discord.Client()
    try:
        await client.login(get_token())
        await fn(client, args)
    finally:
        await client.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="discord", description="Read-only Discord account CLI.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help):
        sp = sub.add_parser(name, help=help)
        sp.set_defaults(fn=fn)
        return sp

    ap = add("auth", None, "store or test the account token")
    ap.add_argument("action", choices=["store", "test"])
    ap.add_argument("--token", help="token to store (else read from stdin)")

    add("whoami", cmd_whoami, "show the logged-in account")
    add("servers", cmd_servers, "list your servers")

    sp = add("channels", cmd_channels, "list channels in a server")
    sp.add_argument("server")
    sp.add_argument("--type", help="filter by channel type (e.g. text, forum, news)")

    sp = add("search", cmd_search, "search messages in a server")
    sp.add_argument("query", nargs="?", help="text to search (optional if using filters)")
    sp.add_argument("--server", help="server name/id (required unless --all-servers/--dm)")
    sp.add_argument("--all-servers", action="store_true", help="search every server (slower)")
    sp.add_argument("--dm", help="search a DM/group channel id instead of a server")
    sp.add_argument("--channel", action="append", help="restrict to channel(s); repeatable")
    sp.add_argument("--author", action="append", help="author user id; repeatable")
    sp.add_argument("--mentions", action="append", help="mentioned user id; repeatable")
    sp.add_argument("--has", action="append",
                    help="link|embed|file|video|image|sound|sticker; repeatable")
    sp.add_argument("--filename", action="append", help="attachment filename contains; repeatable")
    sp.add_argument("--ext", action="append", help="attachment extension e.g. zip; repeatable")
    sp.add_argument("--pinned", action="store_true")
    sp.add_argument("--before"); sp.add_argument("--after")
    sp.add_argument("--relevant", action="store_true", help="sort by relevance, not recency")
    sp.add_argument("--limit", type=int, default=25)

    sp = add("read", cmd_read, "read a channel or thread's history")
    sp.add_argument("channel")
    sp.add_argument("--server")
    sp.add_argument("--limit", type=int, default=50)
    sp.add_argument("--before"); sp.add_argument("--after"); sp.add_argument("--around")
    sp.add_argument("--pinned", action="store_true", help="list pinned messages instead")

    sp = add("threads", cmd_threads, "list posts/threads in a forum or text channel")
    sp.add_argument("forum", help="forum or text channel (name or id)")
    sp.add_argument("--server")
    sp.add_argument("--limit", type=int, default=50, help="max posts to return")
    sp.add_argument("--active-only", action="store_true", help="forum: skip archived posts")
    sp.add_argument("--archived-only", action="store_true", help="forum: only archived posts")

    sp = add("thread", cmd_thread, "read one thread / forum post")
    sp.add_argument("thread_id")
    sp.add_argument("--limit", type=int, default=200)

    sp = add("message", cmd_message, "fetch a single message (optionally with context)")
    sp.add_argument("channel"); sp.add_argument("message")
    sp.add_argument("--context", type=int, help="also fetch N messages either side")

    sp = add("download", cmd_download, "download attachment(s) from a message")
    sp.add_argument("target", nargs="+", help="jump URL, or: <channel_id> <message_id>")
    sp.add_argument("--index", type=int, help="pick the Nth attachment (0-based)")
    sp.add_argument("--name", help="only attachments whose filename contains this")
    sp.add_argument("--out", help="destination directory (default ~/Downloads/discord)")

    sp = add("export", cmd_export, "dump a channel/forum/thread to a markdown file")
    sp.add_argument("channel"); sp.add_argument("--server")
    sp.add_argument("--limit", type=int, default=1000, help="messages per channel/thread")
    sp.add_argument("--threads", type=int, default=50, help="archived forum posts to include")
    sp.add_argument("--out")

    sp = add("mentions", cmd_mentions, "recent messages that mention you (inbox)")
    sp.add_argument("--server", help="only mentions from this server")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--no-roles", action="store_true", help="exclude role mentions")
    sp.add_argument("--no-everyone", action="store_true", help="exclude @everyone/@here")

    add("dms", cmd_dms, "list your DM and group-DM channels")

    sp = add("user", cmd_user, "look up a user's profile + mutual servers")
    sp.add_argument("user_id")

    sp = add("reactions", cmd_reactions, "read reactions on a message (who reacted)")
    sp.add_argument("channel"); sp.add_argument("message")
    sp.add_argument("--users", action="store_true", help="also list who reacted")
    sp.add_argument("--user-limit", type=int, default=50)

    sp = add("events", cmd_events, "list a server's scheduled events")
    sp.add_argument("server")

    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.cmd == "auth":
        if args.action == "store":
            if args.token:
                token = args.token.strip()
            elif sys.stdin.isatty():
                # Interactively, read one line. A bare sys.stdin.read() here
                # waits for EOF rather than Enter and prints no prompt, so the
                # terminal just looks frozen.
                try:
                    token = getpass.getpass("Discord token (input hidden): ").strip()
                except (EOFError, KeyboardInterrupt):
                    sys.exit("\nAborted.")
            else:
                token = sys.stdin.read().strip()
            if not token:
                sys.exit("Provide a token via --token, stdin, or the prompt.")
            if token.upper() in {"YOUR_TOKEN", "PASTE_THE_REAL_ONE_HERE", "TOKEN"}:
                sys.exit(f"That's the placeholder text, not a token ({token!r}).")
            store_token(token)
            where = "Keychain" if sys.platform == "darwin" else "libsecret keyring"
            print(f"Stored token in {where} (service 'discord-cli').", file=sys.stderr)
            return
        # auth test
        asyncio.run(run(cmd_whoami, args))
        return
    asyncio.run(run(args.fn, args))


if __name__ == "__main__":
    main()
