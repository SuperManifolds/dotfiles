---
name: discord
description: Read-only access to the user's Discord account — search servers, browse channels, read message history and forum posts, and download attachments (e.g. mods/files). Use whenever the user wants Claude to look something up in their Discord servers, find instructions/answers buried in a server, search for a file or mod and download it, read a channel or forum, or otherwise pull information out of Discord. Triggers on "look through <server> for…", "search my Discord for…", "find the mod/file… and download it", "what did people say about… in <server>", "read the <channel> channel". Does NOT post, reply, react, or edit — read-only.
allowed-tools: Bash(/Users/alex/.claude/skills/discord/bin/discord:*), Read
---

# Discord (read-only)

Drives the user's Discord **user account** over authenticated REST endpoints via
this skill's launcher:

```
/Users/alex/.claude/skills/discord/bin/discord <command> …
```

On first use it bootstraps a private venv (in `~/.cache/discord-skill/`) and
installs `discord.py-self` — so it's self-contained and portable via dotfiles.
Token is in the macOS Keychain (service `discord-cli`), read automatically —
never pass it on the command line.

**Read-only by construction.** There is no send/edit/delete/react command. Never
try to post on the user's behalf.

**ToS / rate limits.** Automating a user account breaks Discord's ToS (small ban
risk). Keep it on-demand and gentle: prefer `search` over dumping whole channels,
cap `--limit`, don't loop over every server unless asked. Output is JSON on stdout
(logs on stderr) — pipe through `jq`/`python` to slice it.

## Commands

```
discord servers                         # list servers (id, name, member_count)
discord channels <server>               # all channels; --type forum|text|news|media
discord search <query> --server <s>     # message search (the primary tool)
    [--channel <c> …] [--author <id>] [--mentions <id>] [--pinned]
    [--has link|embed|file|image|video|sound] [--filename <s>] [--ext zip]
    [--before <iso|id>] [--after <iso|id>] [--relevant] [--limit 25]
discord read <channel|thread> [--server <s>]    # history, oldest-first
    [--limit 50] [--around <msgid>] [--before …] [--after …] [--pinned]
discord threads <forum> [--server <s>]  # forum posts: title, tags, msg count, OP files
    [--limit 50] [--active-only] [--archived-only]
discord thread <thread_id> [--limit 200]        # read one forum post / thread
discord message <channel> <msgid> [--context N] # one message (+/- N around it)
discord download <jumpUrl | channel_id msgid>   # save attachment(s)
    [--index N] [--name <substr>] [--out <dir>]  # default ~/Downloads/discord
discord export <channel|forum> [--server <s>]   # dump to markdown file, then Read it
    [--limit 1000] [--threads 50] [--out file.md]
discord auth store   # (once) read token from stdin into Keychain
discord whoami       # verify login
```

`<server>` and named `<channel>` accept a case-insensitive name substring or a
numeric id. A numeric id always works and avoids ambiguity — resolve names to ids
with `servers` / `channels` when unsure.

## How to answer "look through <server> for how to do X"

1. **Map it.** `discord channels <server>` — note likely spots: #faq, #rules,
   #guides, #how-to, pinned-heavy channels, and any `forum`-type channels.
2. **Search broad, then narrow.** `discord search "X" --server <server> --relevant`.
   Re-query with synonyms/keywords you learn from the first hits. Each hit has a
   `jump_url` and `channel_id`.
3. **Read around the hits.** `discord read <channel_id> --around <msgid>` for
   context, or `discord thread <id>` if the hit is in a forum post.
4. **Check pins** in relevant channels (`discord read <channel> --pinned`) — "how
   to" answers often live there.
5. **Forums:** `discord threads <forum>` to see posts (title/tags/OP file names),
   then `discord thread <id>` to read one.
6. **Answer with citations** — quote the finding and include `jump_url`s so the
   user can verify.

For reading a lot (a whole channel/forum), prefer `discord export … --out f.md`
then `Read` the file — far cheaper than many `read` calls.

## "Find the mod/file X and download it"

1. `discord search "X" --server <s> --has file` (or `--filename X` / `--ext rar`).
   In mod-sharing **forums**, `discord threads <forum>` shows each post's
   `op_attachments` (filenames) directly.
2. Pick the hit; its `jump_url` encodes channel+message.
3. `discord download <jump_url>` (add `--name <substr>` or `--index N` if the
   message has several files). Files are **saved, never executed** — report the
   path and size; leave running/installing to the user.

## Notes
- Search is server-scoped by Discord's design (`--server` required). It *does*
  index messages inside threads/forum posts.
- Search hits inside forum posts show `channel: null` (the "channel" is a thread);
  the `jump_url` and `channel_id` still work with `read`/`thread`/`download`.
- Full member lists need the gateway — use `collect.py` in this skill's directory
  (writes `graph-data.js` for `viz.html`, the mutual-server graph), not the REST
  commands above.
