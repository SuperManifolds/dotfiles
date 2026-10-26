#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy"]
# ///
"""Check whether candidate recordings are the same recording as a local file.

Usage: compare.py [--jobs N] <local audio file> <candidate> [more candidates ...]

A candidate is a local file, a direct audio URL (a library's preview MP3) or a
YouTube id or URL. Builds a Haitsma-Kalker style binary fingerprint (sign of
band-energy differences across frequency and time) for both, takes three
blocks from the shorter of the two and slides each over the longer one, and
reports the bit error rate (BER) at the best offset. Taking the blocks from
the shorter side lets a 30 s store preview or a trimmed game file match.

Prints one line per candidate:
  MATCH     median BER under 0.30 (true matches score 0.04-0.15)
  PARTIAL   one block under 0.30: another mix, a stem, an edit or a loop
  no match  unrelated audio scores about 0.47
For a true match the three blocks also share one offset (the `shift`).
"""

import argparse
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

RATE = 5512
FRAME = 2048
HOP = 64
BANDS = 33
FMIN, FMAX = 300.0, 2000.0
BLOCK_SECONDS = 12
BLOCK_POSITIONS = (0.2, 0.5, 0.8)
MAX_CANDIDATE_SECONDS = 420
MATCH_BER = 0.30
FETCH_TIMEOUT_SECONDS = 180
DEFAULT_JOBS = 4


def decode(source: str, seconds: int | None = None) -> np.ndarray:
    cmd = ["ffmpeg", "-loglevel", "error", "-i", source]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=FETCH_TIMEOUT_SECONDS).stdout
    return np.frombuffer(raw, dtype=np.float32)


def fetch(candidate: str, workdir: Path) -> str:
    if Path(candidate).is_file() or (candidate.startswith("http") and "youtu" not in candidate):
        return candidate
    out = workdir / "cand.%(ext)s"
    subprocess.run(
        ["yt-dlp", "-q", "--no-playlist", "-f", "bestaudio", "--download-sections", f"*0-{MAX_CANDIDATE_SECONDS}",
         "-o", str(out), "--", candidate],
        check=True, capture_output=True, timeout=FETCH_TIMEOUT_SECONDS,
    )
    return str(next(workdir.glob("cand.*")))


def fingerprint(signal: np.ndarray) -> np.ndarray:
    frames = 1 + (len(signal) - FRAME) // HOP
    if frames < 3:
        raise ValueError("audio too short")
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(signal[idx] * np.hanning(FRAME), axis=1)) ** 2
    freqs = np.fft.rfftfreq(FRAME, 1 / RATE)
    edges = np.geomspace(FMIN, FMAX, BANDS + 1)
    energy = np.stack([spec[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) for lo, hi in zip(edges[:-1], edges[1:])], axis=1)
    diff = energy[:, :-1] - energy[:, 1:]
    bits = (diff[1:] - diff[:-1]) > 0
    return np.where(bits, 1.0, -1.0).astype(np.float32)


def best_ber(query: np.ndarray, target: np.ndarray) -> tuple[float, int]:
    """BER of query at its best position inside target, and that position in frames."""
    n, m = len(query), len(target)
    if m < n:
        query, target = query[:m], target
        n = m
    size = 1 << int(np.ceil(np.log2(n + m)))
    corr = np.zeros(m - n + 1, dtype=np.float64)
    for b in range(query.shape[1]):
        q = np.fft.rfft(query[::-1, b], size)
        t = np.fft.rfft(target[:, b], size)
        corr += np.fft.irfft(q * t, size)[n - 1 : m]
    best = int(np.argmax(corr))
    agreement = corr[best] / (n * query.shape[1])
    return (1 - agreement) / 2, best


def compare(local_sig: np.ndarray, candidate: str) -> str:
    with tempfile.TemporaryDirectory(prefix="cmp-") as tmp:
        cand_sig = decode(fetch(candidate, Path(tmp)), MAX_CANDIDATE_SECONDS)
    # Blocks come from the shorter recording so previews and trims still line up.
    blocks_from_local = len(local_sig) <= len(cand_sig)
    short, long_ = (local_sig, cand_sig) if blocks_from_local else (cand_sig, local_sig)
    long_fp = fingerprint(long_)
    block = min(int(BLOCK_SECONDS * RATE), len(short))
    seconds_per_frame = HOP / RATE
    results = []
    for pos in BLOCK_POSITIONS:
        start = int(max(0, min(len(short) - block, pos * len(short) - block / 2)))
        ber, off = best_ber(fingerprint(short[start : start + block]), long_fp)
        short_at, long_at = start / RATE, off * seconds_per_frame
        local_at, cand_at = (short_at, long_at) if blocks_from_local else (long_at, short_at)
        results.append((ber, local_at, cand_at))
    bers = [r[0] for r in results]
    median = float(np.median(bers))
    verdict = "MATCH" if median < MATCH_BER else ("PARTIAL" if min(bers) < MATCH_BER else "no match")
    detail = ", ".join(f"local@{l:.0f}s->cand@{c:.0f}s ber={b:.3f}" for b, l, c in results)
    shifts = sorted({round(c - l) for _, l, c in results})
    return f"{verdict} | median_ber={median:.3f} | {detail} | shift={shifts}s | {candidate}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fingerprint-compare candidate recordings against a local file.")
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="candidates fetched and compared in parallel")
    parser.add_argument("local", type=Path, metavar="local-file")
    parser.add_argument("candidates", nargs="+", metavar="candidate")
    args = parser.parse_args()
    if not args.local.is_file():
        parser.error(f"not a file: {args.local}")
    local_sig = decode(str(args.local))

    def run(candidate: str) -> str:
        try:
            return compare(local_sig, candidate)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, StopIteration) as error:
            detail = (getattr(error, "stderr", None) or b"").decode(errors="replace").strip().splitlines()
            return f"error | {type(error).__name__}: {detail[-1] if detail else error} | {candidate}"

    with ThreadPoolExecutor(max(1, args.jobs)) as pool:
        for line in pool.map(run, args.candidates):
            print(line, flush=True)


main()
