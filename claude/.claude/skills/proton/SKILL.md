---
name: proton
description: Work out how to best run a Steam game on this Linux machine via Proton, gathering local Proton/NVIDIA/gamescope/GNOME versions, querying ProtonDB (summary API plus a headless-Chromium scrape of community reports), and producing a recommended Proton version and gamescope/HDR launch command tailored to this hardware and the user's HDR/scaling preferences. Can also research the best in-game graphics, display and gameplay settings for the RTX 5070 Ti at 4K (Step 7). Use when asked which Proton version to use for a game, how to launch a specific Steam or Windows game on Linux, or why one runs badly.
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

- **HDR:** wants it on for HDR-capable games on the OLED, but both blown-out/over-exposed (KCD2-style) *and* grey/washed-out results are unacceptable. **Default to the native-Wayland Proton HDR path** (`PROTON_ENABLE_WAYLAND=1 PROTON_ENABLE_HDR=1`) — on mutter 50.1 it gives crisp HDR and is more reliable than gamescope, whose `--hdr-debug-force-output` produced a grey-washed picture here (Jun 2026 session). Use gamescope only when the native path can't be made crisp or you need its tone-mapping/frame-limiting. Tune weak/blown HDR with the game's own calibration toward the panel's ~400 nits.
- **Fractional scaling (125% on DP-2):** GNOME runs fractional scaling; `xwayland-native-scaling` is enabled but **only fixes Xwayland (X11) apps** — it does nothing for native-Wayland games (the HDR path). Native-Wayland games blur at fractional scale because the DXGI swapchain is created at the *logical* size (e.g. 3072×1728) then upscaled; **fix = pin the in-game resolution to native panel res (3840×2160)**, which makes winewayland present 1:1 via viewporter (crisp) while keeping HDR. The user recoils from blurry output and is a recent macOS→Linux switcher; explain Linux-specific steps, don't assume deep familiarity.
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

### HDR launch recipe (this machine, current GNOME/gamescope state)

**`PROTON_ENABLE_HDR=1` is mandatory** for either path. Proton forces `DXVK_HDR=0` inside the pressure-vessel container unless this is set; bare `DXVK_HDR=1` on the host does NOT survive into the container (`PROTON_*` vars cross the boundary, `DXVK_HDR` does not — verified via `/proc/<pid>/environ`).

#### Preferred: native-Wayland HDR (no gamescope)

On mutter 50.1 the native-Wayland Proton path delivers crisp 4K **and** HDR while keeping the desktop at 125% scaling — GE-Proton10-32's `winewayland.so` carries `fractional_scale` + `viewporter` + `color_management` simultaneously (verified via `strings`). This is the default; it avoids gamescope's HDR fragility (below).

```
PROTON_ENABLE_WAYLAND=1 PROTON_ENABLE_HDR=1 PROTON_USE_SDL=1 %command% /HID/UseISteamInput:False /WineDetectionEnabled:False
```
- **Pin the in-game resolution to 3840×2160 (not auto/borderless-follows-desktop).** Otherwise the swapchain renders at the 1.25-logical size (~3072×1728) and gets upscaled → blur. Diagnose by prepending `DXVK_HUD=resolution`: the HUD must read `3840×2160`, not a sub-4K value.
- `PROTON_USE_SDL=1` + `/HID/UseISteamInput:False` — native-Wayland mode breaks SteamInput; these keep controllers working. Drop them if the game has no controller trouble.
- `/WineDetectionEnabled:False` — required by some games (e.g. MH Wilds) to enable ray tracing; harmless otherwise.
- Verify HDR took effect: `for p in $(pgrep -f '<exe>.exe'); do tr '\0' '\n' </proc/$p/environ | grep DXVK_HDR; done` — must show `DXVK_HDR=1`.

#### Alternative: nested gamescope HDR

Use only when the native path can't be made crisp, or you need gamescope's tone-mapping / frame-limiting. **Caveat: on this stack (gamescope 3.16.23) the gamescope HDR path produced a grey/washed-out picture** — `--hdr-debug-force-output` forces a PQ swapchain while bypassing the panel's real HDR metadata, so the image can look flat even though the chain is nominally "HDR." Prefer the native path.

- **`--hdr-debug-force-output`** is gamescope's workaround for issue #2018 (3.16.17–3.16.24, **still open**): on the wayland backend gamescope fails to detect the host output as HDR and silently builds an SDR swapchain; the flag forces HDR10 PQ. mutter's color-management fix (issue #4438, merged GNOME 50) is present and correct on the wire. **Re-test *without* this flag after any gamescope update** — if mutter already shows DP-2 at `color-mode 1` while gamescope runs, gamescope may now negotiate HDR on its own (and dropping the flag avoids the grey-wash).
- Nested gamescope ignores `--prefer-output` for window *placement*; ensure the window lands on **DP-2** (set it primary in GNOME Settings → Displays if needed).

```
ENABLE_GAMESCOPE_WSI=1 PROTON_ENABLE_HDR=1 gamescope -W 3840 -H 2160 -r 240 -f --hdr-enabled --hdr-debug-force-output --prefer-vk-device 10de:2c05 --backend wayland --force-grab-cursor -- %command%
```
- `-r 240` = panel native; lower if a game struggles.
- If highlights clip, add `--hdr-sdr-content-nits 203` and/or lower the game's in-game peak-brightness toward ~400 (panel's sustained nits).
- Verify `DXVK_HDR=1` as above.

### SDR launch recipe

If the game has no HDR, or HDR isn't wanted, skip the HDR pipeline. Prefer **borderless/fullscreen + GNOME's `xwayland-native-scaling`** (no gamescope) for correct fractional scaling. Only wrap in gamescope for frame-limiting or scaling problems:
```
gamescope -W 3840 -H 2160 -r 240 -f --prefer-output DP-2 -- %command%
```

### Fallback if nested gamescope HDR misbehaves

A **standalone gamescope session** (from a TTY, `--backend drm -O DP-2`) bypasses GNOME entirely and reads the monitor EDID directly. More reliable for HDR but heavier; gamescope's DRM backend on Blackwell + driver 595 is less mature than on AMD. Offer this only if the nested path fails.

## Step 7 — In-game settings research (when the user wants graphics/display/gameplay settings)

Separate from the launch recommendation. Games get patched and settings advice goes stale, so **web-research current guides** and tailor to the RTX 5070 Ti / 4K 240 OLED rather than answering from memory.

**7a. Search the web.** Fan out a few searches (in parallel) covering the angles that matter for this rig — phrase the queries however gets the best hits, and follow up on whatever the first results surface:
- **graphics/perf, hardware-matched** — settings for the RTX 5070 Ti (or RTX 50-series) at 4K, including DLSS / Frame Gen guidance;
- **per-setting heaviness + VRAM** — which individual settings cost the most, and texture/VRAM requirements;
- **display + clarity** — screen mode (fullscreen vs borderless), V-Sync, anti-aliasing, and any known blurry/TAA complaints;
- **gameplay QoL** (only if the user wants it) — the settings players change first (camera, controls, HUD).

`WebFetch` the most data-dense guide for exact per-setting values, but many sites return 403/405 — fall back to the search-result summaries (usually enough). Prefer recent, post-latest-patch sources; cite them; don't fabricate values.

**7b. Hardware facts to apply (RTX 5070 Ti, this machine):**
- **16 GB VRAM.** 4K Ultra / Hi-Res texture packs often want the full 16 GB → check live headroom first: `nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv`. Desktop apps (gnome-shell, Steam webhelper, Discord, streaming daemons like sunshine / gnome-remote-desktop) routinely eat 3–4 GB; recommend **High textures unless that VRAM is freed**, and offer to stop the streaming daemons.
- **DLSS 4 / Transformer + Multi-Frame Gen** are 50-series features and **work under Proton/GE** — the Windows-only NVIDIA Profile Inspector "DLSS 4 override" is unnecessary if the game exposes the DLSS 4 preset in-menu. DLSS DLL version **310.x = DLSS 4 / Transformer**, 3.x = old CNN. Check on disk: `strings -el <game>/nvngx_dlss.dll | grep -oE '3[0-9][0-9],[0-9]+,[0-9]+,[0-9]+' | head -1` (also `nvngx_dlssg.dll` = Frame Gen, `nvngx_dlssd.dll` = Ray Reconstruction).
- **4K is upscaling territory** even on a 5070 Ti — recommend DLSS **Quality** (sharper than native+TAA via the Transformer model), not Balanced/Performance (where the blur complaints come from). Frame Gen on only if base ≥45–60 fps.

**7c. Synthesize — give the user:**
1. **Graphics** — upscaling (DLSS Quality / Transformer), Frame Gen, Ray Tracing (Medium or Off; RT needs `/WineDetectionEnabled:False` on the Proton launch line), and the **heaviest settings to lower** (commonly volumetric fog/clouds, shadows, SSR). Gate texture quality on the VRAM check.
2. **Display** — borderless (most DX12 games lack true exclusive fullscreen), **pin resolution to native 3840×2160** (ties into the fractional-scale fix in Step 6 — this is what keeps it crisp), V-Sync off (VRR handles tearing; cap a few fps under 240 to stay in the VRR window and avoid OLED gamma-flicker), disable motion blur / chromatic aberration / film grain for clarity, AF ×16.
3. **HDR** — pull the in-game peak-brightness slider toward the panel's ~400 nits sustained; note many games (e.g. MH Wilds) ship mediocre HDR regardless of pipeline.
4. **Gameplay QoL** (if asked) — camera distance/speed, lock-on / focus-camera, auto-sheathe, radial-menu type, HUD/minimap rotation, tutorial volume — from the guides.

Flag when advice rests on a single source; prefer hardware-matched (RTX 50-series, 4K) reports.

## Notes

- Don't blindly trust stale advice ("supports 4.3", "use X version") — verify against the live system state from Step 1 and current ProtonDB reports.
- If the ProtonDB scrape returns only a ~3KB shell, Chromium didn't render — bump `--virtual-time-budget` or retry; do not fall back to the summary API alone and claim it had report detail.
- Cite ProtonDB reports you relied on, and flag when a recommendation rests on a single report.
