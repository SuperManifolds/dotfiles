# browser.sh — shared helper for the reddit-thread skill. Source it, then call
# `reddit_open <url>` to get a headless, challenge-passing Reddit session on that
# URL. Prints nothing on success.
#
# Reddit's Fastly edge fingerprints the browser, so we run fully headless (no
# window — it never steals focus) but present a consistent Google Chrome
# identity. Launch blank with the stealth init-script, set the matching request
# headers, then navigate. The wait lets Reddit's js_challenge run and set
# session cookies, after which same-origin fetch('<path>.json') works.
#
# Overriding User-Agent alone is NOT enough, and was why this used to fail on a
# distro Chromium: the Sec-CH-UA client-hint header still advertised "Chromium"
# while the UA string claimed "Chrome". Sec-CH-UA has to claim Google Chrome
# too, and the arch hints have to agree with the UA string. stealth.js patches
# the JS-visible half (navigator.userAgentData, platform); keep the constants
# below in sync with it.

_REDDIT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Isolate the browser per Claude Code instance so concurrent instances don't
# drive or close each other's session. Respects an inherited AGENT_BROWSER_SESSION
# (set in fish config), else derives one from the instance id, else a shared
# default. The session stays warm across calls within an instance.
export AGENT_BROWSER_SESSION="${AGENT_BROWSER_SESSION:-claude-${CLAUDE_CODE_SESSION_ID:-default}}"

# Keep in sync with stealth.js.
_REDDIT_UA_VERSION="148"
_REDDIT_UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${_REDDIT_UA_VERSION}.0.0.0 Safari/537.36"

reddit_open() {
  local url="$1" headers
  command -v agent-browser >/dev/null || { echo "error: agent-browser not installed" >&2; return 1; }

  agent-browser open --init-script "$_REDDIT_LIB_DIR/stealth.js" >/dev/null 2>&1 || true

  # Build the header JSON with python: Sec-CH-UA values contain double quotes,
  # which need escaping inside JSON, which needs escaping inside the shell.
  headers=$(UA="$_REDDIT_UA" V="$_REDDIT_UA_VERSION" python3 <<'PY'
import json, os
v = os.environ["V"]
brands = '"Not/A)Brand";v="99", "Google Chrome";v="%s", "Chromium";v="%s"' % (v, v)
print(json.dumps({
    "User-Agent": os.environ["UA"],
    "sec-ch-ua": brands,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-ch-ua-arch": '"x86"',
    "sec-ch-ua-bitness": '"64"',
}))
PY
) || return 1
  agent-browser set headers "$headers" >/dev/null 2>&1 || true

  agent-browser open "$url" >/dev/null 2>&1 || true
  agent-browser wait --load networkidle >/dev/null 2>&1 || true
}
