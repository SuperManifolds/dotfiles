#!/usr/bin/env python3
"""Render the extract.js result into markdown (or pass through raw JSON).

Usage: render.py '<agent-browser --json envelope>'
  MODE=json in the environment emits the raw structured result instead.
Invoked by reddit-read.sh; not meant to be run directly.
"""
import sys
import json
import os


def main():
    try:
        env = json.loads(sys.argv[1])
    except (IndexError, ValueError):
        print("error: could not parse agent-browser output", file=sys.stderr)
        sys.exit(1)

    if not env.get("success") or env.get("data", {}).get("result") is None:
        print(
            "error: extraction failed — challenge may not have passed. "
            "Retry, or inspect `agent-browser get text body`.",
            file=sys.stderr,
        )
        sys.exit(1)
    d = env["data"]["result"]

    if os.environ.get("MODE") == "json":
        print(json.dumps(d, indent=2))
        return

    print(f"# {d['title']}")
    print(f"\n**u/{d['author']}** · score {d['score']} · {d['num_comments']} comments · {d['url']}")
    if d["selftext"].strip():
        print("\n" + d["selftext"].strip())
    note = f" ({d['unresolved_more_ids']} deep stubs unresolved)" if d["unresolved_more_ids"] else ""
    print(f"\n---\n\n*Extracted {d['extracted']} comments{note}*\n")

    by = d["byId"]

    def walk(cid, depth):
        c = by.get(cid)
        if not c:
            return
        body = " ".join(c["body"].split())
        print(f"{'  ' * depth}- **u/{c['author']}** ({c['score']}): {body}")
        for k in c["kids"]:
            walk(k, depth + 1)

    for r in d["roots"]:
        walk(r, 0)


if __name__ == "__main__":
    main()
