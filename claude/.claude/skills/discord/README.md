# Discord toolkit

Read-only tools over your Discord **user account**, via
[`discord.py-self`](https://github.com/dolfies/discord.py-self):

1. **`discord` CLI** (`bin/discord`) — search servers, browse channels, read
   history and forum posts, and download attachments. No write commands exist, so
   it can't post. Paired with the `discord` Claude Code skill so Claude can drive
   it ("look through this server for how to do X", "find this mod and download it").
2. **Mutual-server graph** (`collect.py` + `viz.html`) — visualise everyone who
   shares more than one of your servers with you (see bottom of this file).

## ⚠️ Read first: this is a self-bot

Discord's official bot API only sees servers your *bot* is in, not the servers
*you* are in — so these tools drive the **user client endpoints**. **Automating a
user account violates Discord's ToS and can get it terminated.** It must be your
own account, so the account at risk is your real one. Everything here is
read-only and on-demand, which lowers but does not remove the risk.

## The `discord` CLI

```bash
printf '%s' 'your-user-token' | bin/discord auth store   # once → OS secret store
bin/discord whoami                                        # verify

bin/discord servers
bin/discord channels "Illusion Soft" --type forum
bin/discord search "how to install" --server "Illusion Soft" --relevant
bin/discord threads <forum_id>                            # forum posts + OP filenames
bin/discord thread <thread_id>                            # read one post
bin/discord read <channel_id> --pinned
bin/discord download <jump_url> --name mymod.rar          # → ~/Downloads/discord
bin/discord export <channel_or_forum_id> --out out.md     # bulk read → markdown
```

Token resolves from the OS secret store (service `discord-cli`) — macOS
Keychain via `security`, Linux via `secret-tool` (libsecret) — or `DISCORD_TOKEN`. All
output is JSON on stdout (logs on stderr); pipe through `jq`. Run any command with
`-h` for flags. Full command reference lives in the skill:
`~/.claude/skills/discord/SKILL.md`.

Downloaded files are **saved, never executed** — treat mods/binaries as untrusted.

---

# Mutual-server graph

Visualise everyone who shares **more than one** of your Discord servers with you,
as a bipartite people ↔ servers graph rendered with Cytoscape.js. Same self-bot
caveat as above applies.

## Setup

```bash
pip install -r requirements.txt
export DISCORD_TOKEN='your-user-token'
python collect.py            # writes graph.json + graph-data.js
open viz.html                # any modern browser
```

### Getting your user token

In the Discord **web** client: DevTools → Network tab → trigger any request →
copy the `Authorization` request header. Treat it like a password. Don't paste it
anywhere but your own shell, and never commit it (`.gitignore` covers the outputs).

### Tuning (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `MIN_SHARED` | `2` | Keep a person only if they share ≥ this many of your servers |
| `PER_GUILD_DELAY` | `5.0` | Seconds to wait between servers (be gentle on the API) |

## Coverage caveat (important)

For each server the collector tries a full member **chunk** first. That works when:

- you have `manage_roles` / `kick_members` / `ban_members` there, **or**
- the server has < 1,000 members with a channel everyone can view.

Otherwise it falls back to scraping the member sidebar, which for servers over
1,000 members **only returns currently-online members** — so big servers where
you're a regular user will be *partial*. The viewer flags how many servers came
back partial, and each server node shows its `coverage` on click. Re-running at a
busy hour catches more online members.

## The viewer

- **Gold squares** = your servers (hubs). **Round nodes** = people, sized and
  coloured (blue → red) by how many of your servers they share.
- **Layout** dropdown:
  - **Hub map** (default) — servers pinned on a ring; each person sits at the
    centroid of the servers they belong to, grouped by their exact server-set.
    Deterministic, instant even at thousands of nodes, and it actually shows
    structure: a blob's position tells you *which* servers it spans, its size how
    many people share that exact set. This is the readable default.
  - **Force-directed** (fcose) — organic spring layout. Honest but hairballs when
    everyone shares many servers; best after filtering to ≥3–4 with the slider.
    Runs only on the visible subset and never animates (animating thousands of
    nodes is what froze earlier builds).
- **Min shared servers** slider (2–10) filters people live. Lowering it adds nodes
  at the origin — hit **Re-run layout** to place them (force mode) or just switch
  layout (hub mode repositions instantly).
- **Find a person** highlights by username / display name and zooms to them.
- Click any node for a details panel (a person's shared servers; a server's stats).
- Drag to pan, scroll to zoom.

## Files

- `collect.py` — gateway collector + graph builder.
- `viz.html` — self-contained Cytoscape.js viewer (loads `graph-data.js`).
- `graph-data.SAMPLE.js` — fake data; copy to `graph-data.js` to preview the viewer
  without touching Discord.

## Preview without Discord

```bash
cp graph-data.SAMPLE.js graph-data.js && open viz.html
```
