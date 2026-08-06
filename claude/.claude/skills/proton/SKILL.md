---
name: proton
description: Work out how to best run a Steam game on this Linux machine via Proton: gathers local Proton/NVIDIA/gamescope/GNOME versions, queries ProtonDB (summary API plus a headless-Chromium scrape of community reports), and produces a recommended Proton version and gamescope/HDR launch command tailored to this hardware and the user's HDR/scaling preferences. Use when asked which Proton version to use for a game, how to launch a specific Steam or Windows game on Linux, or why one runs badly.
argument-hint: "<game name or Steam AppID>"
allowed-tools: Bash, Read, WebFetch, WebSearch
---

Recommend the best way to run a Steam game through Proton on **this machine**. The game is `$ARGUMENTS` (a name or a Steam AppID). If empty, ask which game.

This skill was built from a long debugging session on this exact machine. The hardware facts, the user's preferences, and the gamescope/HDR gotchas below are **known-true for this system** — use them directly, don't re-derive them.

## This machine (baseline — verify versions live, treat hardware as fixed)

- **GPU:** NVIDIA GeForce RTX 5070 Ti (Blackwell), PCI id `10de:2c05`, open kernel module (required for Blackwell). Secondary AMD Granite Ridge iGPU (`1002:13c0`) exists but **displays are on the NVIDIA card** — always pin the NVIDIA GPU with `--prefer-vk-device 10de:2c05`.
- **OS:** CachyOS (Arch-based). Update with `paru`.
- **Desktop:** GNOME Shell / mutter on **Wayland**.
- **Primary HDR display:** Samsung Odyssey G81SF on **DP-2** — 4K, 240 Hz, QD-OLED. Genuine HDR (ST2084/PQ + BT.2020 + HDR10+), sustained ~400 nits. Other connected monitors (DP-1, DP-3) are SDR.
- **Proton:** stock Proton 10 + Proton Experimental, **plus GE-Proton** in `~/.steam/root/compatibilitytools.d/`.

## User preferences (apply these by default)

- **HDR:** wants it on for HDR-capable games on the OLED, but KCD2-style "blown out / over-exposed" results are unacceptable — prefer the gamescope tone-mapped path over the raw native-Wayland path when a game's own HDR is weak.
- **Fractional scaling:** GNOME runs fractional scaling; `xwayland-native-scaling` is enabled. Recoil from blurry Xwayland output — prefer borderless/native or gamescope at native panel res. The user is a recent macOS→Linux switcher; explain Linux-specific steps, don't assume deep familiarity.
- **Don't launch everything in gamescope reflexively** — only when it buys HDR tone-mapping, scaling correctness, or frame-limiting.

## Step 1 — Gather live system state

Run in parallel and report concisely:

```bash
# GPU + driver
lspci -nn | grep -iE "vga|3d"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null
# Versions
pacman -Q gamescope mutter gnome-shell 2>/dev/null
gamescope --version 2>&1 | head -1
# Installed Proton flavours
ls ~/.local/share/Steam/steamapps/common/ 2>/dev/null | grep -i proton
ls ~/.steam/root/compatibilitytools.d/ 2>/dev/null
# Monitor / HDR state: which output is in HDR (color-mode 1) right now
gdbus call --session --dest org.gnome.Mutter.DisplayConfig \
  --object-path /org/gnome/Mutter/DisplayConfig \
  --method org.gnome.Mutter.DisplayConfig.GetCurrentState 2>/dev/null \
  | grep -oE "'color-mode': <uint32 [0-9]>" | head
```

Note any version drift from the baseline (esp. gamescope, mutter, NVIDIA driver) — it affects whether the HDR workaround below is still needed.

## Step 2 — Resolve the AppID

If `$ARGUMENTS` is a number, it's the AppID. Otherwise find it:

```bash
# Search installed games first
ls ~/.local/share/Steam/steamapps/common/ 2>/dev/null
grep -il "<name>" ~/.local/share/Steam/steamapps/appmanifest_*.acf 2>/dev/null
```
If not installed locally, use WebSearch for `steamdb <game name> appid` or `store.steampowered.com <game name>` to get the numeric AppID. Confirm with the user if ambiguous.

## Step 3 — ProtonDB: official summary API

```bash
curl -s --max-time 20 "https://www.protondb.com/api/v1/reports/summaries/<APPID>.json" | python3 -m json.tool
```
Gives `tier` (platinum/gold/…), `confidence`, `score`, `total` report count. This is the only structured data ProtonDB exposes — the per-report text is **not** in any public API (the `max-p.me` mirror is a stale 2018 dump; don't use it).

## Step 4 — ProtonDB: scrape ALL community reports → structured data → sub-agent

The report bodies (launch options, Proton versions, HDR/gamescope notes) are client-rendered JS. Render the page, then extract **every** report into structured JSON — do **not** keyword-filter at this stage; valuable reports often don't contain obvious keywords, and a naive grep silently drops them.

**4a. Render the page (headless Chromium):**
```bash
timeout 90 chromium --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --virtual-time-budget=20000 --dump-dom "https://www.protondb.com/app/<APPID>" \
  > /tmp/protondb_<APPID>.html 2>/dev/null
wc -c /tmp/protondb_<APPID>.html   # sanity: ~300KB+, not a 3KB JS shell
```
If `chromium` isn't found, try `google-chrome-stable`/`brave` with the same flags. If the file is only a few KB, the render didn't execute JS — bump `--virtual-time-budget` and retry. Do NOT fall back to keyword-grepping the shell and pretend it had report data.

**4b. Parse into structured records** with the companion script (lives next to this skill):
```bash
python3 ~/.claude/skills/proton/protondb_parse.py /tmp/protondb_<APPID>.html >| /tmp/protondb_<APPID>.json
python3 -c "import json;d=json.load(open('/tmp/protondb_<APPID>.json'));print(len(d),'reports')"
```
Each record has: `text` (full cleaned report — the source of truth), `proton`, `date`, `distro`, and boolean hints `has_launch_options` / `mentions_nvidia` / `mentions_hdr`. Sanity-check the count is in the tens, not 0–1.

**4c. Hand the WHOLE set to a sub-agent.** Spawn a sub-agent (Agent tool, general-purpose) and give it: the JSON file path, this machine's profile from Step 1, and the user preferences above. Instruct it to **read every report's `text`** (not just keyword matches) and return:
- the 3–6 most relevant reports for *this* hardware (NVIDIA RTX 50-series / Wayland / HDR), quoting their exact launch options and Proton version;
- any consensus on the best Proton version;
- recurring problems (crashes, anti-cheat, DLSS/FSR, stutter) even when phrased in unusual words;
- contradictions between reports and which to trust (prefer recent + hardware-matched).

The sub-agent reasons over the full corpus so nothing valuable is dropped by keyword bias. Use its summary as the ProtonDB evidence for Step 6. If the report count is tiny (≤5), skip the sub-agent and just read them inline.

## Step 5 — Detect the game's renderer (affects HDR path)

```bash
DIR=$(ls -d ~/.local/share/Steam/steamapps/common/*/ 2>/dev/null | grep -i "<name>")
# DX12 → VKD3D-Proton; DX11 → DXVK. Look for feature-level hints / d3d dlls.
grep -rils "feature level 12\|d3d12\|D3D_FEATURE_LEVEL_12" "$DIR" 2>/dev/null | head
```
DX12 games use VKD3D-Proton; DX11/10/9 use DXVK. Both honor `PROTON_ENABLE_HDR=1`. Native-Vulkan Linux games are rare and use `ENABLE_HDR_WSI=1` instead — don't apply the Proton HDR flag to those.

## Step 6 — Synthesize the recommendation

Give the user:

1. **Verdict** — ProtonDB tier + confidence, and whether it's known-good on NVIDIA Wayland.
2. **Proton version** — default to the latest **GE-Proton** if HDR is wanted (stock Proton resets `DXVK_HDR=0` and lacks some fixes); stock Proton 10 is fine for SDR/Platinum titles. If reports name a specific working GE version, prefer it.
3. **Launch command** — build from the rules below.
4. **Caveats** — crashes, anti-cheat, DLSS/FSR notes from the reports.

### HDR launch recipe (this machine, current gamescope/GNOME state)

**Critical gotchas discovered on this system — both still apply until the upstream bugs close:**

- **`PROTON_ENABLE_HDR=1` is mandatory.** Proton forces `DXVK_HDR=0` inside the pressure-vessel container unless this is set. Setting bare `DXVK_HDR=1` on the host does NOT survive into the container (verified via `/proc/<pid>/environ`). `PROTON_*` vars cross the boundary; `DXVK_HDR` does not.
- **`--hdr-debug-force-output` is required for nested gamescope HDR on GNOME.** mutter's color-management fix (issue #4438, merged GNOME 50) is present and correctly sends PQ/BT.2020/target_primaries/target_luminance — verified on the wire. But gamescope 3.16.17–3.16.24 has a regression (issue #2018, **still open**) where it fails to detect the host output as HDR and silently builds an SDR swapchain. `--hdr-debug-force-output` overrides that and forces real HDR10 PQ — which looks correct here because the panel genuinely is HDR. Drop this flag once gamescope #2018 is fixed (re-test without it after any gamescope update).
- Nested gamescope ignores `--prefer-output` for window *placement*; ensure the gamescope window lands on **DP-2** (set it primary in GNOME Settings → Displays if needed).

**HDR launch options (paste into Steam → game → Properties → Launch Options), force GE-Proton in Compatibility:**

```
ENABLE_GAMESCOPE_WSI=1 PROTON_ENABLE_HDR=1 gamescope -W 3840 -H 2160 -r 240 -f --hdr-enabled --hdr-debug-force-output --prefer-vk-device 10de:2c05 --backend wayland --force-grab-cursor -- %command%
```
- `-r 240` = panel native; lower if a game struggles.
- If highlights clip, add `--hdr-sdr-content-nits 203` and/or lower the game's in-game peak-brightness toward ~400 (panel's sustained nits).
- Verify it took effect after launch: `for p in $(pgrep -f '<exe>.exe'); do tr '\0' '\n' </proc/$p/environ | grep DXVK_HDR; done` — must show `DXVK_HDR=1`.

### SDR launch recipe

If the game has no HDR, or HDR isn't wanted, skip the HDR pipeline. Prefer **borderless/fullscreen + GNOME's `xwayland-native-scaling`** (no gamescope) for correct fractional scaling. Only wrap in gamescope for frame-limiting or scaling problems:
```
gamescope -W 3840 -H 2160 -r 240 -f --prefer-output DP-2 -- %command%
```

### Fallback if nested gamescope HDR misbehaves

A **standalone gamescope session** (from a TTY, `--backend drm -O DP-2`) bypasses GNOME entirely and reads the monitor EDID directly. More reliable for HDR but heavier; gamescope's DRM backend on Blackwell + driver 595 is less mature than on AMD. Offer this only if the nested path fails.

## Notes

- Don't blindly trust stale advice ("supports 4.3", "use X version") — verify against the live system state from Step 1 and current ProtonDB reports.
- If the ProtonDB scrape returns only a ~3KB shell, Chromium didn't render — bump `--virtual-time-budget` or retry; do not fall back to the summary API alone and claim it had report detail.
- Cite ProtonDB reports you relied on, and flag when a recommendation rests on a single report.
