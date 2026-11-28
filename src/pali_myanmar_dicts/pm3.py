"""Conservative hyphenated headword enrichment from the PM3 source dump."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from pali_myanmar_dicts.normalize import normalize_myanmar_text, to_headword_norm
from pali_myanmar_dicts.translit import myanmar_to_iast
from pali_myanmar_dicts.zawgyi import has_zawgyi_codepoint_marker, zawgyi_to_unicode_batch

PM3_LINE = re.compile(r"^'((?:\\.|[^'])*)':'((?:\\.|[^'])*)'[,}]?;?\s*$")
PM3_HEADWORD = re.compile(r"^([\u1000-\u109f-]+)")
PM3_URL = "https://github.com/bksubhuti/Tipitaka-Pali-Projector"


def read_pm3_candidates(path: Path) -> list[tuple[str, str]]:
    """Parse the simple PM3 object without executing JavaScript."""
    candidates = []
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            if number == 1 and line.strip() == "var pm3 = {":
                continue
            match = PM3_LINE.fullmatch(line.rstrip("\n\r"))
            if match is None:
                raise ValueError(f"Unsupported PM3 syntax on line {number}")
            roman, meaning = match.groups()
            if "\\" in roman or "\\" in meaning:
                raise ValueError(f"Unsupported PM3 escape on line {number}")
            headword = PM3_HEADWORD.match(meaning)
            if headword and "-" in headword[1]:
                candidates.append((roman, headword[1]))
    return candidates


def build_pm3_index(path: Path) -> dict[tuple[str, str], set[str]]:
    """Convert known-Zawgyi PM3 headwords once and index unambiguous matching keys."""
    candidates = read_pm3_candidates(path)
    converted = zawgyi_to_unicode_batch([headword for _, headword in candidates])
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for (roman, _), text in zip(candidates, converted, strict=True):
        if has_zawgyi_codepoint_marker(text):
            continue
        text = normalize_myanmar_text(text, single_line=True)
        index[(roman, to_headword_norm(text))].add(text)
    return dict(index)


def matching_compound(word: str, index: dict[tuple[str, str], set[str]]) -> str | None:
    """Return only a unique match on both Roman and Myanmar loose keys."""
    matches = index.get((myanmar_to_iast(word), to_headword_norm(word)), set())
    return next(iter(matches)) if len(matches) == 1 else None
