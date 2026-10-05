#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown>=3.6"]
# ///
"""Turn a summary written in Markdown into a saved report.

Creates one folder per video holding `summary.md`, the images it references
(converted to JPEG, linked relatively) and a self-contained `summary.html`
with those images embedded, so the HTML file can be moved or shared alone.
Timestamp links stay ordinary YouTube links that open at that moment.

Usage: report.py <summary.md> [--out-root DIR]
  Looks for meta.json next to summary.md to name the folder.
Prints the paths of the Markdown and HTML files.
"""

import argparse
import base64
import html
import json
import re
import subprocess
import sys
from pathlib import Path

import markdown

DEFAULT_OUT_ROOT = Path.home() / "youtube-summaries"
IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
IMAGE_MAX_WIDTH = 1280
JPEG_QUALITY = 4            # ffmpeg -q:v scale: 2 (best) to 31
SLUG_MAX_LENGTH = 60

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --page: #fbfaf7; --ink: #1d1c1a; --muted: #6b6860; --rule: #e3dfd6;
  --accent: #9a3b1e; --chip: #f1ece2; --code: #f3f0e9;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --page: #171614; --ink: #e9e5dc; --muted: #9c978b; --rule: #33302b;
    --accent: #e8926f; --chip: #26231f; --code: #211f1b;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 3rem 1rem 5rem; background: var(--page); color: var(--ink);
  font: 17px/1.62 Charter, "Iowan Old Style", Georgia, serif;
}}
main {{ max-width: 44rem; margin: 0 auto; }}
h1, h2, h3 {{ font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; line-height: 1.25; }}
h1 {{ font-size: 1.9rem; margin: 0 0 .4rem; letter-spacing: -.01em; }}
h1 + p {{ color: var(--muted); font-size: .92rem; margin-top: 0;
          font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; }}
h2 {{ font-size: 1.15rem; margin: 2.6rem 0 .8rem; padding-top: 1.1rem; border-top: 1px solid var(--rule); }}
h3 {{ font-size: 1rem; margin: 1.8rem 0 .4rem; }}
p, li {{ overflow-wrap: break-word; }}
li {{ margin: .35rem 0; }}
a {{ color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }}
a[href*="youtu"] {{
  font: 600 .78rem/1 ui-monospace, "SF Mono", Menlo, monospace; text-decoration: none;
  background: var(--chip); padding: .22rem .42rem; border-radius: 4px; white-space: nowrap;
}}
a[href*="youtu"]:hover {{ background: var(--accent); color: var(--page); }}
h1 + p a[href*="youtu"] {{ font: inherit; background: none; padding: 0; text-decoration: underline; }}
img {{ display: block; max-width: 100%; height: auto; border: 1px solid var(--rule); border-radius: 6px; }}
figure {{ margin: 1.2rem 0 1.6rem; }}
figcaption {{ margin-top: .45rem; color: var(--muted); font-size: .85rem;
              font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; }}
code {{ font: .86em ui-monospace, "SF Mono", Menlo, monospace; background: var(--code);
        padding: .1em .3em; border-radius: 3px; }}
pre {{ background: var(--code); padding: .9rem 1rem; border-radius: 6px; overflow-x: auto; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ margin: 1rem 0; padding-left: 1rem; border-left: 3px solid var(--rule); color: var(--muted); }}
table {{ border-collapse: collapse; width: 100%; font-size: .93rem; }}
th, td {{ text-align: left; padding: .4rem .6rem; border-bottom: 1px solid var(--rule); vertical-align: top; }}
</style>
</head>
<body>
<main>
{body}
</main>
</body>
</html>
"""


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:SLUG_MAX_LENGTH].rstrip("-") or "video"


def convert_image(source: Path, target: Path) -> None:
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(source),
         "-vf", f"scale='min({IMAGE_MAX_WIDTH},iw)':-2", "-q:v", str(JPEG_QUALITY), str(target)],
        capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"could not convert {source}: {result.stderr.strip()}")


def collect_images(text: str, source_dir: Path, images_dir: Path) -> tuple[str, list[str]]:
    """Copy local images into the report and point the Markdown at the copies."""
    missing: list[str] = []

    def relocate(match: re.Match) -> str:
        alt, target = match.group(1), match.group(2)
        if re.match(r"^[a-z]+://|^data:", target):
            return match.group(0)
        source = Path(target).expanduser()
        if not source.is_absolute():
            source = source_dir / source
        if not source.is_file():
            missing.append(target)
            return match.group(0)
        images_dir.mkdir(parents=True, exist_ok=True)
        copy = images_dir / f"{source.stem}.jpg"
        convert_image(source, copy)
        return f"![{alt}]({images_dir.name}/{copy.name})"

    return IMAGE_PATTERN.sub(relocate, text), missing


def render_html(text: str, report_dir: Path, fallback_title: str) -> str:
    body = markdown.markdown(text, extensions=["extra", "sane_lists"])
    body = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', body)

    def embed(match: re.Match) -> str:
        image = report_dir / match.group(1)
        if not image.is_file():
            return match.group(0)
        data = base64.b64encode(image.read_bytes()).decode("ascii")
        return f'src="data:image/jpeg;base64,{data}" loading="lazy"'

    body = re.sub(r'src="([^":]+\.jpg)"', embed, body)
    # An image alone in a paragraph becomes a figure captioned with its alt text.
    body = re.sub(r'<p>(<img alt="([^"]*)"[^>]*>)</p>',
                  r'<figure>\1<figcaption>\2</figcaption></figure>', body)
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.DOTALL)
    title = re.sub(r"<[^>]+>", "", heading.group(1)) if heading else html.escape(fallback_title)
    return PAGE.format(title=title, body=body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("summary", type=Path, help="Markdown summary to save")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = parser.parse_args()

    if not args.summary.is_file():
        print(f"report: no such file: {args.summary}", file=sys.stderr)
        return 1
    text = args.summary.read_text()
    source_dir = args.summary.resolve().parent
    meta_path = source_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
    title = meta.get("title") or args.summary.stem
    video_id = meta.get("id")
    report_dir = args.out_root.expanduser() / "-".join(filter(None, [slugify(title), video_id]))
    report_dir.mkdir(parents=True, exist_ok=True)

    try:
        text, missing = collect_images(text, source_dir, report_dir / "images")
    except RuntimeError as error:
        print(f"report: {error}", file=sys.stderr)
        return 1
    for target in missing:
        print(f"report: image not found, left as written: {target}", file=sys.stderr)

    markdown_path = report_dir / "summary.md"
    html_path = report_dir / "summary.html"
    markdown_path.write_text(text)
    html_path.write_text(render_html(text, report_dir, title))
    print(markdown_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
