"""Conservative repairs for mixed-encoding primary dictionary headers."""

import re

from pali_myanmar_dicts.zawgyi import has_zawgyi_codepoint_marker

from .normalize import normalize_myanmar_text

# U+1064 is the Zawgyi kinzi glyph, sometimes stored after its Myanmar base and vowels.
# Only accept the rearrangement when the source's separate Unicode lookup word agrees.
KINZI_AFTER_BASE = re.compile(r"([\u1000-\u1021])([\u102b-\u1038\u103b-\u103e]*)\u1064")


def repair_header_kinzi(header: str, lookup_word: str) -> tuple[str, bool]:
    """Move a misplaced kinzi only when the separate lookup word verifies the result."""
    if "\u1064" not in header:
        return header, False
    repaired = normalize_myanmar_text(
        KINZI_AFTER_BASE.sub(r"င်္\1\2", header), single_line=True, check_zawgyi=False
    )
    expected = normalize_myanmar_text(lookup_word, single_line=True, check_zawgyi=False)
    if not has_zawgyi_codepoint_marker(repaired) and repaired.replace("-", "") == expected:
        return repaired, True
    return header, False


# Exact malformed tokens and clean spellings cross-checked against headwords in
# tipitaka_pali.db books 1–4. Avoid broad conversion of mixed-script sentences.
VERIFIED_KINZI_TOKENS = {
    "သခုၤဘိတ": "သင်္ခုဘိတ",
    "သခုၤဘိတွာ": "သင်္ခုဘိတွာ",
    "ဟိဂုၤလ": "ဟိင်္ဂုလ",
    "ဟိဂုၤလိ": "ဟိင်္ဂုလိ",
    "အကုၤရ": "အင်္ကုရ",
    "အကုၤသ": "အင်္ကုသ",
    "အကုၤသက": "အင်္ကုသက",
    "အဂုၤဋ္ဌ": "အင်္ဂုဋ္ဌ",
    "အဂုၤလ": "အင်္ဂုလ",
    "အဂုၤလိ": "အင်္ဂုလိ",
    "အဂုၤလိမုဒ္ဒိကာ": "အင်္ဂုလိမုဒ္ဒိကာ",
    "အလကုၤရုမာန": "အလင်္ကုရုမာန",
}
# Clean spellings also occur in definitions in the same primary corpus.
VERIFIED_CONTEXT_TOKENS = {
    # Book 1 ဘာဝနီယ gives the same ဘူ+အနီယ analysis; book 2 ဘဝနီယ agrees.
    "အနီၤယ": "အနီယ",
    # Compare book 2 entries ဂေရုကပရိကမ္မကတ and အဓောဂင်္ဂါယ respectively.
    "ဂွေ့သဘောၤဖြင့်": "ဂွေ့သင်္ဘောဖြင့်",
    "ဂင်္ဂၤါအကြေသို့": "ဂင်္ဂါအကြေသို့",
    "စတုရဂုၤလံ": "စတုရင်္ဂုလံ",
    "သကုၤလမည်သော": "သင်္ကုလမည်သော",
    "သခုၤဘိတံ": "သင်္ခုဘိတံ",
    "အဂုၤလိပေါထ": "အင်္ဂုလိပေါထ",
    "လဃႋမာ": "လင်္ဃိမာ",
    "အဂုၤတ္တိုရ်နိကာယ်ဟူသော": "အင်္ဂုတ္တိုရ်နိကာယ်ဟူသော",
    "သင်္ခေၤပ": "သင်္ခေပ",
    "သချုႋင်း": "သင်္ချိုင်း",
    "သချုႋင်းကို": "သင်္ချိုင်းကို",
    "သချုႋင်းမြေ": "သင်္ချိုင်းမြေ",
    "သဂြုႋဟ်": "သင်္ဂြိုဟ်",
    "သဂြုႋဟ်မြှုပ်နှံမည့်သူမရှိသော": "သင်္ဂြိုဟ်မြှုပ်နှံမည့်သူမရှိသော",
    "မီးရှို့သဂြုႋဟ်ရာမီး": "မီးရှို့သင်္ဂြိုဟ်ရာမီး",
    "ခြသေ့ၤ": "ခြင်္သေ့",
    # Book 2: all other ဗျူဟ/ဗျူဠှ/ဦဟတိ entries in book 2 (and book 1 ပရိဗျူဠှ) use √ဦဟ်.
    "ဥႌဟ်": "ဦဟ်",
    # Book 2: visual spelling of standard Myanmar Unicode ဪ (U+102A, also used in book 1).
    "ေဩာ်ကောင်းစွတကား": "ဪကောင်းစွတကား",
    "ေဩာ်ကောင်းလေစွ": "ဪကောင်းလေစွ",
    "ေဩာ်": "ဪ",
    # Book 3: digit ၀ (U+1040) after leading ေ for ဝေဝစန (68x in book 1, 2x in book 2).
    "ေ၀၀စန": "ဝေဝစန",
    "ေ၀၀စနေ": "ဝေဝစနေ",
    # Book 3: ဟိင်္ဂုလ etymology ဟိင်္ဂုံ (hiṅguṃ) and
    # အင်္ဂုလိ+ဖောတနဉ္စ (အဂုၤလိ is in VERIFIED_KINZI_TOKENS).
    "ဟိဂုႍ": "ဟိင်္ဂုံ",
    "အဂုၤလိဖောတနဉ္စ": "အင်္ဂုလိဖောတနဉ္စ",
}
MYANMAR_TOKEN = re.compile(r"[\u1000-\u1040\u1060-\u1097]+")


def repair_verified_tokens(text: str) -> tuple[str, list[dict[str, str]]]:
    """Repair only exact legacy tokens verified against another source headword."""
    repairs: list[dict[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        original = match.group(0)
        repaired = VERIFIED_KINZI_TOKENS.get(original)
        rule = "kinzi_verified_against_corpus_headword"
        if repaired is None:
            repaired = VERIFIED_CONTEXT_TOKENS.get(original)
            rule = "kinzi_verified_against_corpus_definition"
        if repaired is None:
            return original
        repairs.append(
            {
                "rule": rule,
                "original_codepoints": " ".join(f"U+{ord(char):04X}" for char in original),
                "replacement": repaired,
            }
        )
        return repaired

    return MYANMAR_TOKEN.sub(replace, text), repairs


# An isolated leading vowel with no following consonant is an incomplete source
# fragment, not a recoverable syllable. Keep its code point in metadata.
ISOLATED_LEADING_E = re.compile(
    r"(?<![\u1000-\u1021\u1039\u103b-\u103f\u1050-\u1055])\u1031(?=\s|$)"
)


def mark_incomplete_fragment(text: str) -> tuple[str, int]:
    """Mark an isolated truncated vowel as U+FFFD, without guessing its text."""
    return ISOLATED_LEADING_E.subn("\ufffd", text)


UNRESOLVED_MARKER = re.compile(
    r"[\u1060-\u1097\u1033\u1034\u105a]"
    r"|(?<![\u1000-\u1021\u1039\u103b-\u103f\u1050-\u1055])\u1031"
    r"|\u1039(?![\u1000-\u1021\u1050-\u1055])"
)


def mark_unresolved_markers(text: str) -> tuple[str, int]:
    """Expose unresolvable source glyphs as replacement characters, without guessing."""
    return UNRESOLVED_MARKER.subn("\ufffd", text)


def codepoints(text: str) -> str:
    """Encode a source field as ASCII so exact original code points remain recoverable."""
    return " ".join(f"U+{ord(char):04X}" for char in text)
