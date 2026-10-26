#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Search stock-music libraries for candidates by title, artist and duration.

Usage:
  libsearch.py storyblocks [QUERY] [--artist PORTAL_ID] [--set SET_ID] [--dur S] [--tol T] [--pages N]
  libsearch.py stockmusic  [QUERY] [--artist NAME] [--dur S] [--tol T] [--pages N]
  libsearch.py itunes      QUERY [--dur S] [--tol T]
  libsearch.py deezer      QUERY [--dur S] [--tol T]
  libsearch.py preview     SPOTIFY_OR_DEEZER_TRACK_URL [...]
  libsearch.py stockmusic-dump OUT.jsonl
  libsearch.py catalog DUMP.jsonl --dur S [--tol T]

Each result prints `duration | artist | title | preview URL | page | extra`,
with `<==` on rows within --tol seconds of --dur. --previews prints only the
preview URLs of the flagged rows (all rows without --dur), ready to pass to
compare.py. Durations are listed lengths, not proof: compare.py decides.

storyblocks: plain HTML with a browser User-Agent (the browser gets 403).
--dur also filters server-side (listed durations are rounded down, so
--tol 0 asks for the one second the file falls in), and --dur alone sweeps
the whole catalogue at that length. --artist takes the portal_artist_ids value
from an artist link on a track page; --set takes a result's collapsedSetId
and lists the hidden alternate versions (vocal, instrumental, stems, loops).
stockmusic: stockmusic.net's open JSON API. --artist filters on the
contributor name. stockmusic-dump saves the whole catalogue (about 12,100
tracks, about 7 minutes) for `catalog` sweeps by duration and artist.
itunes, deezer: the iTunes Search API and Deezer's open API; previews are
30 s, which compare.py handles.
preview: the 30 s preview URL and exact length of a Spotify or Deezer track
(the links AudD returns), to prove an AudD hit with compare.py. Spotify's
embed page carries both; a region-restricted track has no preview.
"""

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
STORYBLOCKS = "https://www.storyblocks.com"
STOCKMUSIC_API = "https://stockmusic.net/api"
ITUNES_SEARCH = "https://itunes.apple.com/search"
ITUNES_LIMIT = 200
DEEZER_API = "https://api.deezer.com"
DEEZER_LIMIT = 100
SPOTIFY_EMBED = "https://open.spotify.com/embed/track/"
SPOTIFY_ID = re.compile(r"(?:spotify\.com/(?:intl-[a-z-]+/)?track/|spotify:track:)([A-Za-z0-9]{22})")
DEEZER_ID = re.compile(r"deezer\.com/(?:[a-z]{2}/)?track/(\d+)")
DEFAULT_TOL_SECONDS = 2.0
DEFAULT_PAGES = 3
HTTP_TIMEOUT_SECONDS = 60
HTTP_RETRIES = 3
HTTP_NOT_FOUND = 404
RETRY_BACKOFF_SECONDS = 5
DUMP_WORKERS = 8
# The search API serves at most 416 pages of 24 (9,984 of about 12,100
# tracks) and answers 400 beyond that. Reading the newest-first default order
# and the oldest-first order covers the catalogue from both ends.
STOCKMUSIC_MAX_PAGES = 416
STOCKMUSIC_ORDERS = ("", "oldest")
HTTP_BAD_REQUEST = 400


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
    for attempt in range(HTTP_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            # Client errors are answers, not transient failures.
            if error.code < 500 or attempt == HTTP_RETRIES - 1:
                raise
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == HTTP_RETRIES - 1:
                raise RuntimeError(f"GET {url} failed after {HTTP_RETRIES} attempts: {error}") from error
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise AssertionError("unreachable")


def storyblocks_items(html: str) -> list[dict]:
    """The search page embeds each result as a JSON "stockItem" object."""
    decoder = json.JSONDecoder()
    items = []
    for match in re.finditer(r'"stockItem":\{', html):
        item, _ = decoder.raw_decode(html, match.end() - 1)
        if item.get("contentClass") == "audio":
            items.append(item)
    return items


def storyblocks(args) -> list[dict]:
    params = {"media-type": "music"}
    if args.artist:
        params["portal_artist_ids"] = args.artist
    if args.set:
        params["collapsed-set-id"] = args.set
    if args.dur is not None:
        # Storyblocks lists durations rounded down to whole seconds.
        params["duration_min"] = math.floor(args.dur - args.tol)
        params["duration_max"] = math.floor(args.dur + args.tol)
    slug = re.sub(r"[^a-z0-9]+", "-", (args.query or "").lower()).strip("-")
    base = f"{STORYBLOCKS}/audio/search" + (f"/{slug}" if slug else "")
    rows, seen = [], set()
    for page in range(1, args.pages + 1):
        try:
            html = get(f"{base}?{urllib.parse.urlencode({**params, 'page': page})}")
        except urllib.error.HTTPError as error:
            # Storyblocks answers 404 for a search without results and for a
            # page past the last one.
            if error.code == HTTP_NOT_FOUND:
                break
            raise
        items = storyblocks_items(html)
        fresh = [i for i in items if i["id"] not in seen]
        if not fresh:
            break
        for item in fresh:
            seen.add(item["id"])
            rows.append({
                "dur": item.get("duration"), "artist": item.get("composer"), "title": item.get("title"),
                "preview": item.get("previewUrl"), "page": STORYBLOCKS + item.get("detailsUrl", ""),
                "extra": f"set={item.get('collapsedSetId')} versions={item.get('numCollapses')}",
            })
    return rows


def stockmusic_row(product: dict) -> dict:
    demo = dur = None
    for media in product.get("media", []):
        if media.get("type") == "demomp3":
            demo = media.get("url_slug")
            if wave := media.get("waveform"):
                dur = round(wave["length"] * wave["samples_per_pixel"] / wave["sample_rate"], 1)
    return {
        "dur": dur, "artist": (product.get("contributor") or {}).get("display_name"), "title": product.get("name"),
        "preview": demo, "page": f"https://stockmusic.net{product.get('url_slug', '')}", "extra": product.get("upc"),
    }


def stockmusic_page(query: str, page: int, order: str = "") -> tuple[list[dict], int]:
    params = {"productable": "track", "page": page} | ({"text": query} if query else {}) | ({"sortType": order} if order else {})
    data = json.loads(get(f"{STOCKMUSIC_API}/music/search?{urllib.parse.urlencode(params)}"))
    return [stockmusic_row(p) for p in data.get("productables", [])], data.get("last_page", page)


def stockmusic(args) -> list[dict]:
    rows, seen = [], set()
    for page in range(1, args.pages + 1):
        found, last = stockmusic_page(args.query or "", page)
        for row in found:
            if row["extra"] in seen or (args.artist and args.artist.lower() not in (row["artist"] or "").lower()):
                continue
            seen.add(row["extra"])
            rows.append(row)
        if page >= last:
            break
    return rows


def itunes(args) -> list[dict]:
    data = json.loads(get(f"{ITUNES_SEARCH}?{urllib.parse.urlencode({'term': args.query, 'entity': 'song', 'limit': ITUNES_LIMIT})}"))
    return [
        {"dur": round(r["trackTimeMillis"] / 1000, 1), "artist": r.get("artistName"), "title": r.get("trackName"),
         "preview": r.get("previewUrl"), "page": r.get("trackViewUrl"), "extra": r.get("collectionName")}
        for r in data.get("results", []) if r.get("trackTimeMillis")
    ]


def deezer(args) -> list[dict]:
    data = json.loads(get(f"{DEEZER_API}/search?{urllib.parse.urlencode({'q': args.query, 'limit': DEEZER_LIMIT})}"))
    return [
        {"dur": r.get("duration"), "artist": (r.get("artist") or {}).get("name"), "title": r.get("title"),
         "preview": r.get("preview") or None, "page": r.get("link"), "extra": (r.get("album") or {}).get("title")}
        for r in data.get("data", [])
    ]


def preview(args) -> None:
    for link in args.links:
        if m := SPOTIFY_ID.search(link):
            page = get(SPOTIFY_EMBED + m.group(1))
            data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
            entity = json.loads(data.group(1))["props"]["pageProps"]["state"]["data"]["entity"] if data else {}
            url = (entity.get("audioPreview") or {}).get("url")
            dur = entity.get("duration", 0) / 1000
            note = "" if url else f"no preview ({entity.get('playabilityReason', 'unknown')})"
        elif m := DEEZER_ID.search(link):
            entity = json.loads(get(f"{DEEZER_API}/track/{m.group(1)}"))
            url, dur = entity.get("preview") or None, entity.get("duration", 0)
            note = "" if url else "no preview"
        else:
            print(f"not a Spotify or Deezer track link: {link}", file=sys.stderr)
            continue
        print(f"{dur} | {url or ''} | {link}{' | ' + note if note else ''}")


def stockmusic_dump(args) -> None:
    _, last = stockmusic_page("", 1)
    failed: list[tuple[str, int]] = []

    def fetch(job: tuple[str, int]) -> list[dict]:
        order, page = job
        try:
            return stockmusic_page("", page, order)[0]
        except urllib.error.HTTPError as error:
            if error.code != HTTP_BAD_REQUEST:
                failed.append(job)
            return []
        except RuntimeError:
            failed.append(job)
            return []

    jobs = [(order, page) for order in STOCKMUSIC_ORDERS for page in range(1, min(last, STOCKMUSIC_MAX_PAGES) + 1)]
    with ThreadPoolExecutor(DUMP_WORKERS) as pool:
        pages = list(pool.map(fetch, jobs))
    unique = {row["extra"]: row for rows in pages for row in rows}
    with Path(args.out).open("w") as out:
        for row in unique.values():
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(unique)} tracks from {len(jobs)} pages ({len(failed)} failed: {failed[:10]}) -> {args.out}", file=sys.stderr)


def catalog(args) -> list[dict]:
    rows = [json.loads(line) for line in Path(args.dump).read_text().splitlines() if line.strip()]
    return [r for r in rows if not args.artist or args.artist.lower() in (r["artist"] or "").lower()]


def near(row: dict, dur: float | None, tol: float, floored: bool = False) -> bool:
    if dur is None or row["dur"] is None:
        return False
    if floored:
        return math.floor(dur - tol) <= row["dur"] <= math.floor(dur + tol)
    return abs(row["dur"] - dur) <= tol


def report(rows: list[dict], args) -> None:
    if args.dur is not None and args.command == "catalog":
        rows = [r for r in rows if near(r, args.dur, args.tol)]
    for row in rows:
        flagged = near(row, args.dur, args.tol, floored=args.command == "storyblocks")
        if args.previews:
            if (flagged or args.dur is None) and row["preview"]:
                print(row["preview"])
            continue
        print(f"{row['dur']} | {row['artist']} | {row['title']} | {row['preview']} | {row['page']} | {row['extra']}{'  <==' if flagged else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search stock-music libraries by title, artist and duration.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("storyblocks", "stockmusic", "itunes", "deezer", "catalog"):
        p = sub.add_parser(name)
        if name == "catalog":
            p.add_argument("dump")
        else:
            p.add_argument("query", nargs="?" if name in ("storyblocks", "stockmusic") else None)
        if name not in ("itunes", "deezer"):
            p.add_argument("--artist")
        if name in ("storyblocks", "stockmusic"):
            p.add_argument("--pages", type=int, default=DEFAULT_PAGES)
        if name == "storyblocks":
            p.add_argument("--set")
        p.add_argument("--dur", type=float, required=name == "catalog")
        p.add_argument("--tol", type=float, default=DEFAULT_TOL_SECONDS)
        p.add_argument("--previews", action="store_true")
    dump = sub.add_parser("stockmusic-dump")
    dump.add_argument("out")
    prev = sub.add_parser("preview")
    prev.add_argument("links", nargs="+")
    args = parser.parse_args()
    if args.command in ("stockmusic-dump", "preview"):
        try:
            {"stockmusic-dump": stockmusic_dump, "preview": preview}[args.command](args)
        except (RuntimeError, urllib.error.URLError, KeyError, json.JSONDecodeError) as error:
            sys.exit(f"{args.command}: {error}")
        return
    if args.command == "storyblocks" and not (args.query or args.artist or args.set or args.dur is not None):
        parser.error("storyblocks needs a QUERY, --artist, --set or --dur")
    search = {"storyblocks": storyblocks, "stockmusic": stockmusic, "itunes": itunes, "deezer": deezer, "catalog": catalog}[args.command]
    try:
        rows = search(args)
    except (RuntimeError, urllib.error.URLError) as error:
        sys.exit(f"{args.command}: {error}")
    report(rows, args)


main()
