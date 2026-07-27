#!/usr/bin/env python3
"""Render Reddit search results (from search.js) as markdown or raw JSON.

Usage: render-search.py '<agent-browser --json envelope>'
  MODE=json in the environment emits the raw structured result instead.
Invoked by reddit-search.sh; not meant to be run directly.
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
            "error: search failed — challenge may not have passed. "
            "Retry, or inspect `agent-browser get text body`.",
            file=sys.stderr,
        )
        sys.exit(1)
    d = env["data"]["result"]

    if os.environ.get("MODE") == "json":
        print(json.dumps(d, indent=2))
        return

    q = d.get("query", "")
    results = d.get("results", [])
    if not results:
        print(f"No Reddit results for {q!r}." if q else "No Reddit results.")
        return

    print(f"# Reddit search: {q}" if q else "# Reddit search")
    print(f"\n*{len(results)} results*\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. **{r['title']}** — {r['subreddit']} · score {r['score']} · {r['num_comments']} comments")
        print(f"   {r['url']}")


if __name__ == "__main__":
    main()
