"""Extract the retrieval Q&A pairs from the study guide and build an Anki deck.

Each <details class="unit-block"> in the source has a <div class="qa-list">
with multiple <details class="qa"><summary>Q: …</summary><div class="answer">A: …</div>.
We turn each Q/A pair into one Anki note. Tags = unit-id + cluster letter.

Anki 2.1+ supports MathJax natively for \\(...\\) and \\[...\\] delimiters, so the
KaTeX-style math survives the round trip without conversion.

Output: iliad-anki.apkg in this directory.

Reads the *source* HTML (pre-SSR copy) so the math stays in LaTeX form, not
baked KaTeX HTML — Anki/MathJax can render LaTeX but choke on KaTeX spans.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
import genanki

HERE = Path(__file__).parent
# Prefer the live source HTML; falls back to the mobile copy if needed.
SOURCE_CANDIDATES = [
    HERE.parent / "iliad-intensive-study-guide.html",
    HERE / "index.pre-ssr.html",
    HERE / "index.html",
]
OUTPUT = HERE / "iliad-anki.apkg"


def deterministic_id(seed: str) -> int:
    """Stable 31-bit id derived from a seed string — Anki ids must be unique
    and fit in signed 32-bit."""
    h = hashlib.sha1(seed.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") & 0x7FFFFFFF


def find_source() -> Path:
    for p in SOURCE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(f"No source HTML found; tried: {SOURCE_CANDIDATES}")


def inner_html(node: Tag) -> str:
    """Serialize children of a tag (not the tag itself)."""
    return "".join(str(c) for c in node.children).strip()


def text_of(node: Tag | NavigableString) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def strip_qa_prefix(s: str) -> str:
    # Q: / A: prefixes are signage in the source; redundant in Anki.
    return re.sub(r"^\s*[QA]\s*:\s*", "", s, count=1)


def cluster_letter(unit_id: str) -> str:
    m = re.match(r"([A-Za-z])", unit_id)
    if m:
        return m.group(1).upper()
    return "P"  # prerequisites


def build():
    src = find_source()
    print(f"Source: {src}")
    html = src.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    units = soup.select("details.unit-block")
    print(f"  found {len(units)} unit blocks")

    # ---- Anki model ----
    # Single field pair: Front (label + Q), Back (label + Q + A) — Anki convention is
    # to show Q on the front; we put unit context on both sides so reviewers know
    # where the card came from.
    model = genanki.Model(
        deterministic_id("iliad-model-v1"),
        "Iliad Study QA",
        fields=[
            {"name": "UnitLabel"},
            {"name": "UnitTitle"},
            {"name": "Question"},
            {"name": "Answer"},
        ],
        templates=[
            {
                "name": "Q -> A",
                "qfmt": (
                    '<div class="unit-tag">{{UnitLabel}} &middot; {{UnitTitle}}</div>'
                    '<div class="q">{{Question}}</div>'
                ),
                "afmt": (
                    '{{FrontSide}}'
                    '<hr id="answer">'
                    '<div class="a">{{Answer}}</div>'
                ),
            }
        ],
        css=(
            ".card { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', "
            "Roboto, Arial, sans-serif; font-size: 18px; line-height: 1.5; "
            "color: #15171c; background: #fafbfd; padding: 18px; text-align: left; }\n"
            ".unit-tag { font-size: 12px; color: #5f6775; text-transform: uppercase; "
            "letter-spacing: 0.05em; margin-bottom: 10px; }\n"
            ".q { font-weight: 600; font-size: 19px; }\n"
            ".a { color: #2a3142; }\n"
            "hr#answer { border: 0; border-top: 1px solid #dfe3ea; margin: 14px 0; }\n"
            "code { background: #f2f4f8; border-radius: 4px; padding: 1px 5px; "
            "font-family: SFMono-Regular, Consolas, monospace; font-size: 0.92em; }\n"
            "pre { background: #f2f4f8; border-radius: 6px; padding: 10px 12px; "
            "overflow-x: auto; }\n"
            "@media (prefers-color-scheme: dark) {\n"
            "  .card { color: #e6edf3; background: #1c2128; }\n"
            "  .unit-tag { color: #8d96a0; }\n"
            "  .a { color: #c7cdd5; }\n"
            "  hr#answer { border-top-color: #3a4350; }\n"
            "  code, pre { background: #2f3640; color: #e6edf3; }\n"
            "}\n"
        ),
    )

    deck = genanki.Deck(
        deterministic_id("iliad-deck-v1"),
        "Iliad Alignment Study",
        description=(
            "Retrieval-practice Q&A from the Iliad Intensive AI alignment "
            "self-study guide. Auto-extracted from the HTML <details class='qa'> "
            "blocks. Tags reflect unit id (e.g. b3) and cluster letter (e.g. B)."
        ),
    )

    n_cards = 0
    per_unit = []

    for unit in units:
        unit_id = unit.get("id") or "unknown"
        label_el = unit.select_one(".unit-label")
        title_el = unit.select_one(".unit-title")
        label = text_of(label_el) if label_el else unit_id
        title = text_of(title_el) if title_el else unit_id

        qa_pairs = []
        for qa in unit.select("div.qa-list > details.qa"):
            q_el = qa.find("summary")
            a_el = qa.select_one(".answer")
            if not q_el or not a_el:
                continue
            # Use inner_html so math markup (\\(...\\), \\[...\\]) and inline HTML survive
            q_html = strip_qa_prefix(inner_html(q_el))
            a_html = strip_qa_prefix(inner_html(a_el))
            qa_pairs.append((q_html, a_html))

        per_unit.append((label, title, len(qa_pairs)))

        cluster = cluster_letter(unit_id)
        for i, (q, a) in enumerate(qa_pairs, 1):
            note = genanki.Note(
                model=model,
                fields=[label, title, q, a],
                tags=[
                    f"iliad",
                    f"unit::{unit_id}",
                    f"cluster::{cluster}",
                ],
                guid=genanki.guid_for(f"iliad::{unit_id}::{i}"),
            )
            deck.add_note(note)
            n_cards += 1

    pkg = genanki.Package(deck)
    pkg.write_to_file(str(OUTPUT))

    print(f"\nPer-unit card counts:")
    for label, title, n in per_unit:
        print(f"  {label:>4}  n={n:>2}  {title}")
    print(f"\nTotal: {n_cards} cards across {len(units)} units")
    print(f"Output: {OUTPUT}  ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    sys.exit(build())
