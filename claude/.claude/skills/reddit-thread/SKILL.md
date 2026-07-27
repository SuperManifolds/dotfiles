---
name: reddit-thread
description: Reliably read the full content of a Reddit discussion thread (post + entire nested comment tree) as clean markdown or JSON. Use whenever the user gives a reddit.com / old.reddit.com thread URL, or asks to read, summarize, or extract a Reddit thread's comments. Works where fetch/scrape fail — Reddit returns 403 to plain requests; this drives Chrome (via agent-browser) headless with a spoofed User-Agent that passes Reddit's Fastly JS challenge, then reads the thread's .json from inside the session. Runs windowless — never steals focus. No API key required.
allowed-tools:
  - Bash(agent-browser:*)
  - Bash(*/reddit-read.sh:*)
  - Bash(reddit-read.sh:*)
---

# reddit-thread

Read a Reddit thread reliably, without the (defunct) legacy API and without
Firecrawl credits.

## Usage

```bash
# Markdown (post + threaded comments):
"$CLAUDE_SKILL_DIR/reddit-read.sh" "https://www.reddit.com/r/programming/comments/<id>/<slug>/"

# Raw structured JSON (roots + byId comment map):
reddit-read.sh "<thread-url>" --json

# Cap the initial comment fetch (default 500):
reddit-read.sh "<thread-url>" --limit 200
```

Accepts `www.`, `old.`, or `np.` reddit URLs (normalized to `www.`).

## Why the obvious approaches fail (verified April 2026)

| Approach | Result |
| --- | --- |
| `curl <url>.json` (browser UA) | **403** — Fastly blocks the IP/UA |
| `old.reddit.com` in a plain automated browser | **403** "blocked by network security" |
| Firecrawl hosted scrape | works, but costs credits (and here: 0 left) |
| CDP browser, no stealth | **blocked** — `navigator.webdriver === true` fails Reddit's `js_challenge` |
| Headless Chrome, default UA | **403** — Fastly blocks the `HeadlessChrome` UA token at the edge |
| **Headless Chrome + real-Chrome UA header + stealth, in-session `.json` fetch** | ✅ **200**, full thread, no window |

The legacy Reddit API key is not an option (no longer issued). The current
free OAuth "script app" API still exists but requires registering an app;
this skill deliberately avoids that and needs no credentials.

## How it works

1. `agent-browser` launches **Chrome for Testing** *headless* — no window, so
   it never steals focus — and overrides the `User-Agent` request header to
   strip the `HeadlessChrome` token that Fastly blocks at the edge. `stealth.js`
   runs as an `--init-script`, hiding the remaining automation tells
   (`navigator.webdriver`, and keeping the page's `navigator.userAgent` in sync)
   *before* page JS runs, so Reddit's Fastly `js_challenge` passes and sets
   normal session cookies.
2. From inside that authenticated, same-origin page, it `fetch()`es
   `<permalink>.json?limit=500&raw_json=1` — returning the full comment tree
   as clean structured data (no fragile DOM/lazy-load scraping).
3. `kind:"more"` stubs (deep/collapsed threads) are resolved in batches via
   `/api/morechildren.json`, which also works with the session cookies.
4. Output is rendered as nested markdown (or `--json`).

Typical coverage is ~96–100% of `num_comments`; the small remainder is
deleted/removed nodes or very deep stubs.

## Troubleshooting

- **"extraction failed / challenge may not have passed"** — rerun (challenges
  are occasionally flaky). Inspect with `agent-browser get text body`; if it
  says *"blocked by network security"*, the challenge didn't pass — the IP may
  be rate-limited; wait and retry.
- Keep the browser warm: the first call passes the challenge; subsequent calls
  in the same session reuse cookies and are faster.
- Files: `reddit-read.sh` (orchestrator), `stealth.js` (fingerprint patch,
  init-script), `extract.js` (in-page thread fetch + comment-tree walk),
  `render.py` (result → markdown / raw JSON).
