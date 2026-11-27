"""Canonical Myanmar Unicode normalizer, syllable orderer, and loose lookup key builder."""

from __future__ import annotations

import re
import unicodedata

from pali_myanmar_dicts.zawgyi import assert_zero_zawgyi

ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200D\uFEFF\u00AD]")
MULTISPACE_RE = re.compile(r"[ \t\f\v]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")

# Combining-mark canonical rank within a single Myanmar base/subscript cluster (NFC + UTN #11).
# Note: kinzi `\u1004\u103A\u1039` is matched separately before the consonant it rides over so its
# `\u103A\u1039` pair is preserved intact.
_MARK_RANK: dict[str, int] = {
    "\u103b": 1,  # ျ medial ya
    "\u103c": 2,  # ြ medial ra
    "\u103d": 3,  # ွ medial wa
    "\u103e": 4,  # ှ medial ha
    "\u1031": 5,  # ေ vowel e
    "\u102d": 6,  # ိ vowel i
    "\u102e": 6,  # ီ vowel ii
    "\u102f": 7,  # ု vowel u
    "\u1030": 7,  # ူ vowel uu
    "\u1032": 8,  # ဲ vowel ai
    "\u102b": 9,  # ါ tall aa
    "\u102c": 9,  # ာ standard aa
    "\u1036": 10,  # ံ anusvara / niggahita
    "\u1037": 11,  # ့ dot below (ccc=7, precedes asat ccc=9 in NFC)
    "\u103a": 12,  # ် asat (ccc=9)
    "\u1038": 13,  # း visarga
}

# Move stacked subscripts (`\u1039` + consonant) placed erroneously after medials/vowels (e.g.
# `ဣနြ္ဒိယ` -> `ဣန္ဒြိယ`). Excludes `\u103A` from the preceding mark class so kinzi `\u1004\u103A\u1039`
# is never moved.
_SUBSCRIPT_AFTER_MARKS_RE = re.compile(
    r"([\u102B-\u1038\u103B-\u103E]+)((?:\u1039[\u1000-\u1021\u1050-\u1055])+)"
)

# Matches either a kinzi prefix (`င်္`), or a base Myanmar letter + subscripts + combining marks.
_CLUSTER_OR_KINZI_RE = re.compile(
    r"\u1004\u103A\u1039"
    r"|([\u1000-\u102A\u103F\u104E\u1050-\u1055](?:\u1039[\u1000-\u1021\u1050-\u1055])*)"
    r"([\u102B-\u1032\u1036-\u1038\u103A-\u103E]{2,})"
)
# Independent `ဥ` (`U+1025`) before `ါ`/`ာ`, `ေ`, virama `္`, asat `်`, or medial `ှ` is a glyph
# confusion for `ဉ` (`U+1009`), e.g. `ပဥှ` -> `ပဉှ`, `ဥာဏ်` -> `ဉာဏ်`, `သံယောဇဥ်` -> `သံယောဇဉ်`.
_MISUSED_INDEP_U_RE = re.compile(r"\u1025(?=[\u102B\u102C\u1031\u1039\u103A\u103E]|\u1037\u103A)")

# Loose headword normalization patterns:
_NORM_STRIP_RE = re.compile(r"[\s\-–—_.,;:!?\"'“”‘’()\[\]{}၊။…/\\+=0-9၀-၉]+")
_KINZI_VELAR_RE = re.compile(r"\u1004\u103A\u1039(?=[\u1000-\u1004])")
# Syllable-initial `ဉ` (`U+1009`) confused for `ဥ`/`ဦ` (`ဉပေက္ခာ` -> `ဥပေက္ခာ`, `လက်ဉီး` -> `လက်ဦး`):
_INITIAL_NYA_AS_U_RE = re.compile(
    r"(?:(?<![\u1000-\u103F])\u1009(?![\u102B-\u102D\u102F-\u103E])|(?<!\u1039)\u1009(?=\u102E))"
)


def _reorder_cluster_marks(match: re.Match[str]) -> str:
    full = match.group(0)
    if full == "\u1004\u103a\u1039":
        return full
    base = match.group(1)
    marks = match.group(2)
    deduped: list[str] = []
    for ch in marks:
        if ch not in deduped or ch == "\u103a":
            deduped.append(ch)
    ordered = "".join(sorted(deduped, key=lambda c: _MARK_RANK.get(c, 99)))
    return base + ordered


def canonicalize_myanmar_syllables(text: str) -> str:
    """Reorder Myanmar subscripts and combining marks into canonical UTN #11 + NFC storage order."""
    cur = _MISUSED_INDEP_U_RE.sub("\u1009", unicodedata.normalize("NFC", text))
    while True:
        swapped = _SUBSCRIPT_AFTER_MARKS_RE.sub(r"\2\1", cur)
        if swapped == cur:
            break
        cur = swapped
    reordered = _CLUSTER_OR_KINZI_RE.sub(_reorder_cluster_marks, cur)
    return unicodedata.normalize("NFC", reordered)


def normalize_myanmar_text(
    text: str,
    *,
    single_line: bool = False,
    check_zawgyi: bool = True,
) -> str:
    """Strip zero-width noise, normalize whitespace and syllable order, and verify Unicode."""
    if not text:
        return ""
    cleaned = ZERO_WIDTH_RE.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    if single_line:
        cleaned = MULTISPACE_RE.sub(" ", cleaned.replace("\n", " ")).strip()
    else:
        lines = [MULTISPACE_RE.sub(" ", ln).strip() for ln in cleaned.split("\n")]
        cleaned = BLANK_LINES_RE.sub("\n\n", "\n".join(lines)).strip()
    normalized = canonicalize_myanmar_syllables(cleaned)
    if check_zawgyi:
        assert_zero_zawgyi(normalized)
    return normalized


def to_headword_norm(text: str) -> str:
    """Build a loose Myanmar lookup key folding tall `ါ`, kinzi/`ံ`, stacked consonants, and spaces.

    Transformations applied so learner inputs match canonical Pāḷi/Burmese headwords:
    - Canonicalize to NFC Unicode and fold `ဉီး`/`ဉပ...` -> `ဦး`/`ဥပ...` before stripping spaces.
    - Strip spaces, hyphens, numerals, and punctuation.
    - Fold `ါ` (`U+102B`) -> `ာ` (`U+102C`) and kinzi `င်္` before velars `က–င` to `ံ` (`U+1036`).
    - Expand `ဿ` (`U+103F`) -> `သသ`, fold medial `ှ` (`U+103E`) -> `ဟ` (`U+101F`), and remove
      stacking virama `္` (`U+1039`) so stacked (`ဓမ္မ`, `ပဉှ`, `သဿတ`) and unstacked (`ဓမမ`, `ပဉဟ`,
      `သသသတ`) Pāḷi inputs collide cleanly.
    """
    norm = normalize_myanmar_text(text, single_line=True, check_zawgyi=False)
    norm = _INITIAL_NYA_AS_U_RE.sub("\u1025", norm)
    norm = unicodedata.normalize("NFC", norm)
    norm = _NORM_STRIP_RE.sub("", norm)
    norm = _KINZI_VELAR_RE.sub("\u1036", norm)
    norm = norm.replace("\u102b", "\u102c")
    norm = norm.replace("\u103f", "\u101e\u101e")
    norm = norm.replace("\u103e", "\u101f")
    norm = norm.replace("\u1039", "")
    return unicodedata.normalize("NFC", norm)
