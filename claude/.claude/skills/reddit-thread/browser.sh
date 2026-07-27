# browser.sh — shared helper for the reddit-thread skill. Source it, then call
# `reddit_open <url>` to get a headless, challenge-passing Reddit session on that
# URL. Prints nothing on success.
#
# Reddit's Fastly edge blocks the "HeadlessChrome" User-Agent token, so we run
# fully headless (no window — it never steals focus) but present a normal Chrome
# UA. Launch blank with the stealth init-script, read the browser's real UA,
# strip the "Headless" token, set it as the request header, then navigate. The
# wait lets Reddit's js_challenge run and set session cookies, after which
# same-origin fetch('<path>.json') works.

_REDDIT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

reddit_open() {
  local url="$1" ua
  command -v agent-browser >/dev/null || { echo "error: agent-browser not installed" >&2; return 1; }

  agent-browser open --init-script "$_REDDIT_LIB_DIR/stealth.js" >/dev/null 2>&1 || true
  ua=$(agent-browser eval --json --stdin <<<'(async () => navigator.userAgent)()' 2>/dev/null \
       | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"]["result"])' 2>/dev/null || true)
  # Strip the "Headless" token that Fastly blocks (the init-script patches the
  # page's navigator.userAgent, but not this pre-navigation blank page).
  ua="${ua//HeadlessChrome/Chrome}"
  [[ -n "$ua" ]] && agent-browser set headers "{\"User-Agent\": \"$ua\"}" >/dev/null 2>&1 || true

  agent-browser open "$url" >/dev/null 2>&1 || true
  agent-browser wait --load networkidle >/dev/null 2>&1 || true
}
