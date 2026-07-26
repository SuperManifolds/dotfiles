#!/usr/bin/env bash
# reddit-read.sh — reliably dump a Reddit discussion thread (post + full comment
# tree) as clean markdown, using a real Chrome via agent-browser to pass Reddit's
# Fastly "js_challenge" bot detection, then fetching the thread's .json from
# inside that authenticated browser session.
#
# Why this works (see SKILL.md): plain curl / .json / old.reddit all return 403,
# and a CDP-driven browser is blocked because navigator.webdriver === true. The
# stealth init-script hides that tell so the challenge passes; once cookies are
# set, same-origin fetch('<permalink>.json') returns the full structured thread.
#
# Usage:  reddit-read.sh <reddit-thread-url> [--json] [--limit N]
#   --json    emit raw structured JSON instead of markdown
#   --limit   max top-level fetch size (default 500)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STEALTH="$SCRIPT_DIR/stealth.js"

URL=""
MODE="markdown"
LIMIT=500
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)  MODE="json"; shift ;;
    --limit) LIMIT="$2"; shift 2 ;;
    *)       URL="$1"; shift ;;
  esac
done

if [[ -z "$URL" ]]; then
  echo "usage: reddit-read.sh <reddit-thread-url> [--json] [--limit N]" >&2
  exit 2
fi

# Normalize to a www.reddit.com comments permalink.
URL="${URL//old.reddit.com/www.reddit.com}"
URL="${URL//np.reddit.com/www.reddit.com}"
if [[ "$URL" != http*://www.reddit.com/* ]]; then
  echo "error: not a reddit thread URL: $URL" >&2
  exit 2
fi

command -v agent-browser >/dev/null || { echo "error: agent-browser not installed" >&2; exit 1; }

# Open the thread itself with the stealth patch — this both passes the challenge
# and lands us same-origin for the .json fetch. --headed is less detectable.
agent-browser open "$URL" --init-script "$STEALTH" --headed >/dev/null 2>&1 || true
agent-browser wait --load networkidle >/dev/null 2>&1 || true

# In-session extraction (script via --stdin, result via --json envelope).
# Fetch the thread .json, then recursively resolve kind:"more" stubs via
# /api/morechildren.json (works with the session's challenge cookies).
ENVELOPE=$(agent-browser eval --json --stdin <<EOF
(async () => {
  const permalink = location.pathname.replace(/\/\$/, '');
  const linkId = permalink.split('/')[4];
  const raw = '&raw_json=1';
  const base = await (await fetch(permalink + '.json?limit=${LIMIT}' + raw)).json();
  const post = base[0].data.children[0].data;

  const byId = {};
  const roots = [];
  let moreQueue = [];

  function add(d, parentId){
    if (byId[d.id]) return;
    byId[d.id] = { id:d.id, author:d.author, score:d.score, body:d.body||'', kids:[] };
    if (parentId && byId[parentId]) byId[parentId].kids.push(d.id);
    else if (!parentId) roots.push(d.id);
  }
  function ingest(children, parentId){
    for (const c of children){
      if (c.kind === 't1'){
        add(c.data, parentId);
        if (c.data.replies && c.data.replies.data) ingest(c.data.replies.data.children, c.data.id);
      } else if (c.kind === 'more'){
        moreQueue.push(...(c.data.children||[]));
      }
    }
  }
  ingest(base[1].data.children, null);

  let rounds = 0;
  while (moreQueue.length && rounds < 15){
    rounds++;
    const batch = moreQueue.splice(0, 100);
    const u = '/api/morechildren.json?api_type=json&link_id=t3_' + linkId + '&children=' + batch.join(',') + raw;
    let things = [];
    try { const m = await (await fetch(u,{headers:{'Accept':'application/json'}})).json(); things = m.json.data.things||[]; }
    catch(e){ break; }
    for (const t of things){
      if (t.kind === 't1'){
        const d = t.data;
        const parentId = (d.parent_id||'').replace(/^t\d_/, '');
        add(d, byId[parentId] ? parentId : null);
      } else if (t.kind === 'more'){
        moreQueue.push(...(t.data.children||[]));
      }
    }
  }

  return {
    url: location.origin + permalink,
    title: post.title,
    author: post.author,
    score: post.score,
    num_comments: post.num_comments,
    selftext: post.selftext || '',
    extracted: Object.keys(byId).length,
    unresolved_more_ids: moreQueue.length,
    roots, byId
  };
})()
EOF
)

MODE="$MODE" python3 - "$ENVELOPE" <<'PY'
import sys, json, os
try:
    env = json.loads(sys.argv[1])
except Exception:
    print("error: could not parse agent-browser output", file=sys.stderr); sys.exit(1)
if not env.get("success") or env.get("data", {}).get("result") is None:
    print("error: extraction failed — challenge may not have passed. "
          "Retry, or inspect `agent-browser get text body`.", file=sys.stderr)
    sys.exit(1)
d = env["data"]["result"]

if os.environ.get("MODE") == "json":
    print(json.dumps(d, indent=2)); sys.exit(0)

print(f"# {d['title']}")
print(f"\n**u/{d['author']}** · score {d['score']} · {d['num_comments']} comments · {d['url']}")
if d['selftext'].strip():
    print("\n" + d['selftext'].strip())
note = f" ({d['unresolved_more_ids']} deep stubs unresolved)" if d['unresolved_more_ids'] else ""
print(f"\n---\n\n*Extracted {d['extracted']} comments{note}*\n")
by = d['byId']
def walk(cid, depth):
    c = by.get(cid)
    if not c: return
    body = " ".join(c['body'].split())
    print(f"{'  '*depth}- **u/{c['author']}** ({c['score']}): {body}")
    for k in c['kids']:
        walk(k, depth + 1)
for r in d['roots']:
    walk(r, 0)
PY
