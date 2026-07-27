---
name: reddit-thread
description: Reliably read or search Reddit. Read the full content of a discussion thread (post + entire nested comment tree), or search Reddit for threads matching a query (optionally scoped to a subreddit), as clean markdown or JSON. Use whenever the user gives a reddit.com / old.reddit.com thread URL, asks to read/summarize/extract a thread's comments, or wants to search Reddit / find Reddit discussions on a topic. Works where fetch/scrape fail (Reddit 403s plain requests and Firecrawl can't scrape it); drives a headless Chrome that passes Reddit's bot challenge. No API key required.
allowed-tools:
  - Bash(agent-browser:*)
  - Bash(*/reddit-read.sh:*)
  - Bash(reddit-read.sh:*)
  - Bash(*/reddit-search.sh:*)
  - Bash(reddit-search.sh:*)
---

# reddit-thread

Read or search Reddit reliably — no API key, no Firecrawl credits. Both scripts
live in this skill dir; invoke by path (e.g. `"$CLAUDE_SKILL_DIR/reddit-read.sh"`).

## Read a thread

```
reddit-read.sh <thread-url> [--json] [--limit N]
```

- Prints the post plus the nested comment tree as markdown.
- `--json` — raw structured result (`roots` + `byId` comment map) instead.
- `--limit N` — cap the initial comment fetch (default 500).
- Accepts `www.`/`old.`/`np.` URLs; a wrong slug or subreddit still resolves (the
  thread is fetched by id).

## Search

```
reddit-search.sh <query...> [--sub S] [--sort SORT] [--time T] [--limit N] [--json]
```

- Lists matches as `title · subreddit · score · comments · URL`; feed any URL to
  `reddit-read.sh` to read it in full.
- `--sub S` — restrict to a subreddit (with or without `r/`).
- `--sort` — `relevance` (default) | `hot` | `top` | `new` | `comments`. Prefer
  `relevance` for topical matches; `top` ranks by score alone.
- `--time` — `hour` | `day` | `week` | `month` | `year` | `all` (default `all`).
- `--limit N` — max results (default 25).

## Notes

- First call on a cold browser is slower (it passes a one-time bot challenge);
  later calls in the same session reuse it.
- On error, just rerun — the challenge is occasionally flaky.
- Cite the threads you used.
