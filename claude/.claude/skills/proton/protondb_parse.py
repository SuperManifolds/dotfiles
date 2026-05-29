#!/usr/bin/env python3
"""Segment a headless-rendered ProtonDB app page into per-report records.
Usage: protondb_parse.py <rendered.html>  ->  JSON array on stdout.

Captures EVERY report (no keyword filtering). `text` is the cleaned full
report block and is the source of truth; the other fields are best-effort
hints. Intended to be handed wholesale to a reasoning agent.
"""
import re, html, json, sys

raw = open(sys.argv[1], encoding='utf-8', errors='ignore').read()
segments = re.split(r'ReportListRenderer__CenterColumn', raw)[1:]  # one per report

def strip(s):
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)                 # whole tags
    s = re.sub(r'^[^>]*>', '', s)                  # leading partial tag from split
    s = re.sub(r'<[^>]*$', '', s)                  # trailing partial tag
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()

reports = []
for seg in segments:
    txt = strip(seg[:6000])
    if len(txt) < 10:
        continue
    rec = {}
    m = re.search(r'(GE-Proton[0-9.\-]+|Proton-GE[0-9.\-]*|Proton(?:[ \-](?:Experimental|Hotfix|[0-9][0-9.\-]*)))', txt)
    rec['proton'] = m.group(1) if m else None
    m = re.search(r'(\d+\s+(?:hour|day|week|month|year)s?\s+ago)', txt)
    rec['date'] = m.group(1) if m else None
    m = re.search(r'Distro:\s*([A-Za-z0-9/.,_+\-() ]{2,40}?)\s+(?:CPU|GPU|Kernel|RAM|Proton|$)', txt)
    rec['distro'] = m.group(1).strip() if m else None
    rec['has_launch_options'] = bool(re.search(r'%command%|gamescope |PROTON_|DXVK_|ENABLE_HDR_WSI|mangohud|gamemoderun|VKD3D_', txt))
    rec['mentions_nvidia'] = bool(re.search(r'NVIDIA|RTX|GeForce|nvidia', txt))
    rec['mentions_hdr'] = 'hdr' in txt.lower()
    rec['text'] = txt[:1500]
    reports.append(rec)

print(json.dumps(reports, indent=2, ensure_ascii=False))
