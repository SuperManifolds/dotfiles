#!/usr/bin/env python3
"""Mechanical AI-tell scanner for short prose.

Counts the patterns that corpus studies show discriminate LLM prose from human
prose, and the human habits LLMs underuse. It does not judge: it reports counts
and snippets so the writer can decide. Eyeballing reliably misses the
paragraph-level patterns, which is the whole reason this exists.

Usage:  scan.py FILE [FILE...]
        cat draft.md | scan.py -
Blocks are separated by blank lines, so each paragraph or comment is scored on
its own. Inline code spans, fenced blocks and block quotes are stripped before
prose analysis, so identifiers do not pollute the word counts.
"""
import re
import sys
import statistics

# Tier A: high discrimination. See references/tells.md for sources and effect sizes.
AI_VOCAB = [
    "delve", "delves", "delving", "intricate", "pivotal", "underscore", "underscores",
    "underscoring", "showcase", "showcases", "showcasing", "crucial", "comprehensive",
    "robust", "seamless", "seamlessly", "leverage", "leverages", "leveraging",
    "meticulous", "meticulously", "realm", "landscape", "tapestry", "myriad",
    "nuanced", "holistic", "paradigm", "testament", "boasts", "elevate", "unlock",
    "harness", "foster", "fostering", "navigate", "navigating", "vital", "essential",
    "significant", "notably", "furthermore", "moreover", "additionally",
]
# Copula avoidance / nominalization markers.
NOMINAL = ["serves as", "stands as", "functions as", "acts as", "represents",
           "provides", "offers", "facilitates", "enables", "utilises", "utilizes",
           "performs", "conducts", "undertakes", "in order to", "is able to"]
OPENERS = [
    "great question", "good question", "excellent question", "you're absolutely right",
    "you are absolutely right", "you're right", "great catch", "good catch to you",
    "thanks for", "thank you for", "happy to help", "certainly", "absolutely",
    "i'd be happy to", "that's a great", "what a great", "i hope this helps",
    "let me know if", "feel free to",
]
SIGNPOST = ["firstly", "secondly", "thirdly", "in conclusion", "in summary",
            "in short", "overall", "to summarize", "to summarise", "ultimately",
            "it is worth noting", "it's worth noting", "importantly",
            "that said", "with that said", "here's the thing"]
COUNTER = {
    "because": r"\bbecause\b",
    "contraction": r"\b\w+(?:n't|'re|'ve|'ll|'d|'s)\b",
    "first person": r"\bI\b|\bI'm\b|\bI'd\b|\bmy\b",
    "second person": r"\byou\b|\byour\b|\byou're\b",
    "bare this/that": r"(?:^|\. )(?:This|That)\s+\w+",
    "informal hedge": r"\b(?:about|roughly|around|almost|nearly|a bit)\b",
    "amplifier": r"\b(?:really|very|way)\b",
    "clausal coord": r",\s+(?:but|and)\s+(?:I|you|it|they|we|he|she|this|that)\b",
}
DECORATIVE = re.compile(
    r"[←-⇿∀-⋿─-╿☀-➿⬀-⯿"
    r"\U0001F300-\U0001FAFF✓✔✗❌✅⚠]"
)
# ", <verb>ing" tail clause, excluding conjunctions and common non-participles.
PARTICIPLE_STOP = {"nothing", "something", "anything", "everything", "during",
                   "string", "thing", "being", "spring", "king", "ring"}


def strip_code(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " CODE ", text)
    text = re.sub(r"^\s*>.*$", " ", text, flags=re.M)
    return text


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p.strip()]


def find_participial_tails(text):
    hits = []
    for m in re.finditer(r",\s+(\w+ing)\b", text):
        w = m.group(1).lower()
        if w in PARTICIPLE_STOP:
            continue
        hits.append(m.group(0).strip() + " ...")
    return hits


def find_triads(text):
    """Lists of exactly three comma-separated items joined by and/or."""
    hits = []
    pat = re.compile(
        r"(?<![,\w])([^,;:.()]{2,40}),\s+([^,;:.()]{2,40}),?\s+(?:and|or)\s+([^,;:.()]{2,40}?)(?=[.,;:]|$)"
    )
    for m in pat.finditer(text):
        # reject when a fourth item precedes (it is a longer list, not a triad)
        before = text[max(0, m.start() - 60):m.start()]
        if before.rstrip().endswith(","):
            continue
        hits.append(", ".join(x.strip() for x in m.groups()))
    return hits


def report_block(i, raw):
    text = strip_code(raw)
    words = len(text.split())
    sents = sentences(text)
    lens = [len(s.split()) for s in sents]
    out = []

    def add(tier, label, items):
        if items:
            n = len(items) if isinstance(items, list) else items
            sample = ""
            if isinstance(items, list) and items:
                sample = "  e.g. " + " | ".join(items[:3])
            out.append(f"  [{tier}] {label}: {n}{sample}")

    add("A", "em dash", [m for m in re.findall(r"—", text)])
    add("A", "decorative unicode/emoji", DECORATIVE.findall(raw))
    add("A", "markdown bold/header", re.findall(r"\*\*[^*]+\*\*|^#{1,6} ", raw, flags=re.M))
    add("A", "participial tail clause", find_participial_tails(text))
    first = sents[0].lower() if sents else ""
    hit = [o for o in OPENERS if first.startswith(o) or first.startswith(o.capitalize().lower())]
    add("A", "sycophantic/filler opener", [sents[0][:60]] if hit else [])
    tail = " ".join(sents[-2:]).lower() if sents else ""
    if re.search(r"\b(in short|overall|in summary|in conclusion|ultimately|to sum up)\b", tail):
        add("A", "closing restatement", [sents[-1][:60]])
    add("A", "parallel ', so X' clauses", re.findall(r",\s+so\s+\w+", text))

    add("B", "AI vocabulary", [w for w in re.findall(r"[A-Za-z']+", text) if w.lower() in AI_VOCAB])
    add("B", "negative parallelism", re.findall(r"not just [^,.]+,? but|isn't [^,.]+,? it's|it's not [^,.]+, it's", text, flags=re.I))
    add("B", "triad", find_triads(text))
    add("B", "nominalization/copula avoidance", [p for p in NOMINAL if re.search(r"\b" + p + r"\b", text, flags=re.I)])
    add("B", "signposting", [p for p in SIGNPOST if re.search(r"\b" + re.escape(p) + r"\b", text, flags=re.I)])
    add("B", "rhetorical question", re.findall(r"\?\s+[A-Z][^.?]{0,60}\.", text))

    present = [k for k, pat in COUNTER.items() if re.search(pat, text)]
    missing = [k for k in COUNTER if k not in present]

    cv = (statistics.pstdev(lens) / statistics.mean(lens)) if len(lens) > 1 and statistics.mean(lens) else 0
    print(f"\nblock {i}: {words} words, {len(sents)} sentences, lengths {lens}")
    print(f"  sentence-length CV {cv:.2f}" + ("  <-- uniform, vary it" if cv < 0.35 and len(lens) > 2 else ""))
    if out:
        print("\n".join(out))
    else:
        print("  no tier A/B hits")
    print(f"  counter-signals present: {', '.join(present) if present else 'NONE'}")
    if missing:
        print(f"  counter-signals absent:  {', '.join(missing)}")


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    for path in argv:
        raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        print(f"=== {path} ===")
        blocks = [b for b in re.split(r"\n\s*\n", raw) if b.strip()]
        for i, b in enumerate(blocks, 1):
            report_block(i, b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
