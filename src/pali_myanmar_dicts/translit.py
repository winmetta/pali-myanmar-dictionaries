"""Deterministic Pāḷi script transliteration: Sinhala <-> Myanmar Unicode <-> IAST Roman."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection

from pali_myanmar_dicts.normalize import ZERO_WIDTH_RE, canonicalize_myanmar_syllables

# --- 1. Shared Pāḷi Phoneme Token -> Myanmar Unicode Renderer ---

_ROMAN_CONSONANTS_TO_MY: dict[str, str] = {
    "kh": "ခ",
    "gh": "ဃ",
    "ch": "ဆ",
    "jh": "ဈ",
    "ṭh": "ဌ",
    "ḍh": "ဎ",
    "th": "ထ",
    "dh": "ဓ",
    "ph": "ဖ",
    "bh": "ဘ",
    "k": "က",
    "g": "ဂ",
    "ṅ": "င",
    "c": "စ",
    "j": "ဇ",
    "ñ": "ဉ",
    "ṭ": "ဋ",
    "ḍ": "ဍ",
    "ṇ": "ဏ",
    "t": "တ",
    "d": "ဒ",
    "n": "န",
    "p": "ပ",
    "b": "ဗ",
    "m": "မ",
    "y": "ယ",
    "r": "ရ",
    "l": "လ",
    "v": "ဝ",
    "s": "သ",
    "h": "ဟ",
    "ḷ": "ဠ",
}

_INDEP_VOWEL_TO_MY: dict[str, str] = {
    "ā": "အာ",
    "a": "အ",
    "ī": "ဤ",
    "i": "ဣ",
    "ū": "ဦ",
    "u": "ဥ",
    "e": "ဧ",
    "o": "ဩ",
}

_DEP_VOWEL_TO_MY: dict[str, str] = {
    "a": "",
    "i": "\u102d",
    "ī": "\u102e",
    "u": "\u102f",
    "ū": "\u1030",
    "e": "\u1031",
}

_VELAR_STOPS = frozenset({"k", "kh", "g", "gh", "ṅ"})
_HA_MEDIAL_BASES = frozenset({"ñ", "ṇ", "n", "m", "y", "l", "v", "ḷ"})
_TALL_AA_SIMPLE_BASES = frozenset({"ခ", "ဂ", "င", "ဒ", "ပ", "ဝ"})


def _uses_tall_aa(base_my: str, sub_my: str, med_my: str) -> bool:
    """Return True when a Pāḷi cluster takes tall `ါ` (`U+102B`) instead of `ာ` (`U+102C`)."""
    if base_my in _TALL_AA_SIMPLE_BASES and not sub_my and not med_my:
        return True
    if base_my == "ဒ" and not sub_my and med_my == "\u103d":
        return True
    if base_my == "ဒ" and sub_my in {"\u1039ဒ", "\u1039ဓ"} and not med_my:
        return True
    return base_my == "ဂ" and sub_my == "\u1039ဂ" and not med_my


def _render_cluster_vowel(base_my: str, sub_my: str, med_my: str, vowel: str | None) -> str:
    if vowel is None:
        return f"{base_my}{sub_my}{med_my}\u103a"
    if vowel in _DEP_VOWEL_TO_MY:
        return f"{base_my}{sub_my}{med_my}{_DEP_VOWEL_TO_MY[vowel]}"
    tall = _uses_tall_aa(base_my, sub_my, med_my)
    aa_sign = "\u102b" if tall else "\u102c"
    if vowel == "ā":
        return f"{base_my}{sub_my}{med_my}{aa_sign}"
    if vowel == "o":
        return f"{base_my}{sub_my}{med_my}\u1031{aa_sign}"
    return f"{base_my}{sub_my}{med_my}"


def _render_consonant_cluster_to_my(consonants: list[str], vowel: str | None) -> str:
    """Render a Pāḷi onset consonant cluster + vowel into canonical Myanmar Unicode."""
    prefix = ""
    rem = list(consonants)
    if len(rem) >= 2 and rem[0] == "ṅ" and rem[1] in _VELAR_STOPS:
        prefix = "\u1004\u103a\u1039"
        rem = rem[1:]

    med_parts: list[str] = []
    if len(rem) >= 2 and rem[-1] == "h" and rem[-2] in _HA_MEDIAL_BASES:
        med_parts.insert(0, "\u103e")
        rem.pop()
    if len(rem) >= 2 and rem[-1] == "v" and rem[-2] != "v":
        med_parts.insert(0, "\u103d")
        rem.pop()
    if len(rem) >= 2 and rem[-1] == "r" and rem[-2] != "r":
        med_parts.insert(0, "\u103c")
        rem.pop()
    if len(rem) >= 2 and rem[-1] == "y":
        med_parts.insert(0, "\u103b")
        rem.pop()

    med_my = "".join(med_parts)
    if len(rem) == 2 and rem[0] == "s" and rem[1] == "s" and not prefix:
        base_my, sub_my = "ဿ", ""
    elif len(rem) == 2 and rem[0] == "ñ" and rem[1] == "ñ" and not prefix:
        base_my, sub_my = "ည", ""
    else:
        base_my = _ROMAN_CONSONANTS_TO_MY[rem[0]]
        sub_my = "".join(f"\u1039{_ROMAN_CONSONANTS_TO_MY[c]}" for c in rem[1:])

    return prefix + _render_cluster_vowel(base_my, sub_my, med_my, vowel)


# --- 2. IAST Roman -> Myanmar Unicode ---

_IAST_TOKEN_RE = re.compile(
    r"(kh|gh|ch|jh|ṭh|ḍh|th|dh|ph|bh|k|g|ṅ|c|j|ñ|ṭ|ḍ|ṇ|t|d|n|p|b|m|y|r|l|v|s|h|ḷ)"
    r"|(ā|ī|ū|a|i|u|e|o)"
    r"|(ṃ)"
    r"|(.)",
    re.DOTALL,
)


def _normalize_iast_input(text: str) -> str:
    """Fold ISO-15919 / BTHAR romanization variants onto standard lowercase Pāḷi IAST."""
    s = unicodedata.normalize("NFC", text).lower()
    s = s.replace("l\u0324", "ḷ").replace("l\u02f3", "ḷ")
    # Note: in BTHAR OCR romanization, `ŭ` (`U+016D`) encodes `ဉ` (`ñ` misread as `ဥ` before c/j/h).
    s = s.replace("ṁ", "ṃ").replace("ï", "i").replace("ü", "u").replace("ŭ", "ñ")
    return s


def _tokens_to_myanmar(tokens: list[tuple[str, str]]) -> str:
    out: list[str] = []
    idx = 0
    total = len(tokens)
    while idx < total:
        kind, val = tokens[idx]
        if kind == "C":
            cons = [val]
            idx += 1
            while idx < total and tokens[idx][0] == "C":
                cons.append(tokens[idx][1])
                idx += 1
            vowel: str | None = None
            if idx < total and tokens[idx][0] == "V":
                vowel = tokens[idx][1]
                idx += 1
            out.append(_render_consonant_cluster_to_my(cons, vowel))
        elif kind == "V":
            out.append(_INDEP_VOWEL_TO_MY[val])
            idx += 1
        elif kind == "M":
            out.append("\u1036")
            idx += 1
        else:
            out.append(val)
            idx += 1
    return canonicalize_myanmar_syllables("".join(out))


def iast_to_myanmar(text: str) -> str:
    """Transliterate IAST / ISO-15919 Roman Pāḷi into canonical Myanmar Unicode."""
    if not text:
        return ""
    s = _normalize_iast_input(text)
    tokens: list[tuple[str, str]] = []
    for match in _IAST_TOKEN_RE.finditer(s):
        c_tok, v_tok, m_tok, other = match.groups()
        if c_tok:
            tokens.append(("C", c_tok))
        elif v_tok:
            tokens.append(("V", v_tok))
        elif m_tok:
            tokens.append(("M", m_tok))
        else:
            tokens.append(("O", other))
    return _tokens_to_myanmar(tokens)


# --- 3. Myanmar Unicode -> IAST Roman ---

_MY_CONSONANT_TO_IAST: dict[str, str] = {v: k for k, v in _ROMAN_CONSONANTS_TO_MY.items()}
_MY_CONSONANT_TO_IAST["ည"] = "ññ"
_MY_CONSONANT_TO_IAST["ဿ"] = "ss"

_MY_INDEP_VOWELS: dict[str, str] = {
    "ဣ": "i",
    "ဤ": "ī",
    "ဥ": "u",
    "ဦ": "ū",
    "ဧ": "e",
    "ဩ": "o",
    "ဪ": "au",
}

_MY_MEDIAL_TO_IAST: dict[str, str] = {
    "\u103b": "y",
    "\u103c": "r",
    "\u103d": "v",
    "\u103e": "h",
}

_MY_SINGLE_DEP_VOWEL_IAST: dict[str, str] = {
    "\u102b": "ā",
    "\u102c": "ā",
    "\u102d": "i",
    "\u102e": "ī",
    "\u102f": "u",
    "\u1030": "ū",
    "\u1031": "e",
    "\u1032": "ai",
}

_MY_SYLLABLE_RE = re.compile(
    r"(\u1004\u103A\u1039)?"
    r"([\u1000-\u1021\u103F])"
    r"((?:\u1039[\u1000-\u1021])*)"
    r"([\u103B-\u103E]*)"
    r"(\u1031)?"
    r"([\u102D-\u1030\u1032]*)"
    r"([\u102B\u102C]*)"
    r"(\u103A)?"
)


def _decode_myanmar_vowel(has_e: bool, uvs: str, aas: str, killed: bool) -> str:
    if killed and not has_e and not uvs and not aas:
        return ""
    if has_e and aas and not uvs:
        return "o"
    if not has_e and not uvs and not aas:
        return "a"
    parts: list[str] = []
    if has_e:
        parts.append("e")
    for ch in uvs:
        parts.append(_MY_SINGLE_DEP_VOWEL_IAST[ch])
    if aas:
        parts.append("ā")
    return "".join(parts)


def _render_myanmar_syllable_to_iast(match: re.Match[str]) -> str:
    kinzi, base, subs, meds, ev, uvs, aas, killer = match.groups()
    vowel = _decode_myanmar_vowel(bool(ev), uvs, aas, bool(killer))
    if base == "အ" and not kinzi and not subs and not meds and not killer:
        return vowel
    parts: list[str] = []
    if kinzi:
        parts.append("ṅ")
    parts.append(_MY_CONSONANT_TO_IAST.get(base, base))
    for idx in range(1, len(subs), 2):
        sub_ch = subs[idx]
        parts.append(_MY_CONSONANT_TO_IAST.get(sub_ch, sub_ch))
    for med_ch in meds:
        parts.append(_MY_MEDIAL_TO_IAST[med_ch])
    parts.append(vowel)
    return "".join(parts)


def myanmar_to_iast(text: str, *, iso15919: bool = False) -> str:
    """Transliterate canonical Myanmar-script Pāḷi into IAST (or ISO-15919 when `iso15919=True`)."""
    if not text:
        return ""
    norm = canonicalize_myanmar_syllables(ZERO_WIDTH_RE.sub("", text))
    out: list[str] = []
    pos = 0
    for match in _MY_SYLLABLE_RE.finditer(norm):
        if match.start() > pos:
            out.append(_convert_non_syllable_span(norm[pos : match.start()], out, iso15919))
        out.append(_render_myanmar_syllable_to_iast(match))
        pos = match.end()
    if pos < len(norm):
        out.append(_convert_non_syllable_span(norm[pos:], out, iso15919))
    rendered = "".join(out)
    if iso15919:
        rendered = rendered.replace("ṃ", "ṁ").replace("ḷ", "l\u0324")
    return rendered


def _convert_non_syllable_char(ch: str, prev_tail: str, iso15919: bool) -> str | None:
    if ch == "\u1036":
        return "ṃ"
    if ch in _MY_INDEP_VOWELS:
        v = _MY_INDEP_VOWELS[ch]
        if iso15919 and prev_tail == "a" and v in {"i", "u"}:
            return "ï" if v == "i" else "ü"
        return v
    if ch in _MY_SINGLE_DEP_VOWEL_IAST:
        return _MY_SINGLE_DEP_VOWEL_IAST[ch]
    if ch in _MY_MEDIAL_TO_IAST:
        return _MY_MEDIAL_TO_IAST[ch]
    if "၀" <= ch <= "၉":
        return chr(ord("0") + (ord(ch) - ord("၀")))
    if ch in {"\u1037", "\u1038", "\u1039", "\u103a"}:
        return None
    return ch


def _convert_non_syllable_span(span: str, prev_parts: list[str], iso15919: bool) -> str:
    buf: list[str] = []
    prev_tail = prev_parts[-1][-1:] if prev_parts else ""
    for ch in span:
        mapped = _convert_non_syllable_char(ch, prev_tail, iso15919)
        if mapped is not None:
            buf.append(mapped)
            prev_tail = mapped[-1:]
    return "".join(buf)


# --- 4. Sinhala Pāḷi -> Myanmar Unicode ---

_SINHALA_CONSONANTS: dict[str, str] = {
    "ක": "k",
    "ඛ": "kh",
    "ග": "g",
    "ඝ": "gh",
    "ඞ": "ṅ",
    "ච": "c",
    "ඡ": "ch",
    "ජ": "j",
    "ඣ": "jh",
    "ඤ": "ñ",
    "ට": "ṭ",
    "ඨ": "ṭh",
    "ඩ": "ḍ",
    "ඪ": "ḍh",
    "ණ": "ṇ",
    "ත": "t",
    "ථ": "th",
    "ද": "d",
    "ධ": "dh",
    "න": "n",
    "ප": "p",
    "ඵ": "ph",
    "බ": "b",
    "භ": "bh",
    "ම": "m",
    "ය": "y",
    "ර": "r",
    "ල": "l",
    "ව": "v",
    "ස": "s",
    "හ": "h",
    "ළ": "ḷ",
}

_SINHALA_INDEP_VOWELS: dict[str, str] = {
    "අ": "a",
    "ආ": "ā",
    "ඉ": "i",
    "ඊ": "ī",
    "උ": "u",
    "ඌ": "ū",
    "එ": "e",
    "ඒ": "e",
    "ඔ": "o",
    "ඕ": "o",
}

_SINHALA_DEP_VOWELS: dict[str, str] = {
    "\u0dcf": "ā",  # ා
    "\u0dd2": "i",  # ි
    "\u0dd3": "ī",  # ී
    "\u0dd4": "u",  # ු
    "\u0dd6": "ū",  # ූ
    "\u0dd9": "e",  # ෙ
    "\u0dda": "e",  # ේ (NFC of ෙ + ්)
    "\u0ddc": "o",  # ො
    "\u0ddd": "o",  # ෝ (NFC of ො + ්)
}

_SINHALA_A_PLUS_DEP_TO_INDEP: dict[str, str] = {
    "\u0dcf": "ආ",
    "\u0dd2": "ඉ",
    "\u0dd3": "ඊ",
    "\u0dd4": "උ",
    "\u0dd6": "ඌ",
    "\u0dd9": "එ",
    "\u0dda": "එ",
    "\u0ddc": "ඔ",
    "\u0ddd": "ඔ",
}

_SINHALA_VIRAMA = "\u0dca"
_SINHALA_ANUSVARA = "\u0d82"
_SINHALA_PRECLEAN_SUBS: tuple[tuple[str, str, str], ...] = (
    # Upstream converter mapped Myanmar `ဥ`/`ဦ` + virama (`ဉ္`) to Sinhala `උ්`/`ඌ්`:
    ("\u0d8b\u0dca", "\u0da4\u0dca", "repaired_indep_u_virama_to_nya"),
    ("\u0d8c\u0dca", "\u0da4\u0dca", "repaired_indep_uu_virama_to_nya"),
    ("අංන්හි", "අන්හි", "repaired_anhi_prefix"),
)


def _repair_zawgyi_kinzi_in_sinhala(prev: str, nxt: str) -> tuple[str, ...]:
    if nxt in _SINHALA_CONSONANTS and _SINHALA_CONSONANTS[nxt] in _VELAR_STOPS:
        return ("ඞ", _SINHALA_VIRAMA)
    if prev in _SINHALA_DEP_VOWELS and nxt:
        return (_SINHALA_ANUSVARA,)
    return ()


def _repair_sinhala_dep_or_virama(
    ch: str, cleaned: list[str]
) -> tuple[tuple[str, ...], str | None] | None:
    prev = cleaned[-1] if cleaned else ""
    if ch == _SINHALA_VIRAMA and prev not in _SINHALA_CONSONANTS:
        return (), "dropped_stray_virama"
    if ch in _SINHALA_DEP_VOWELS:
        if prev == "අ" and ch in _SINHALA_A_PLUS_DEP_TO_INDEP:
            cleaned.pop()
            return (_SINHALA_A_PLUS_DEP_TO_INDEP[ch],), "folded_a_plus_dep_vowel"
        if prev in _SINHALA_DEP_VOWELS or prev in _SINHALA_INDEP_VOWELS:
            return (), "dropped_duplicate_dep_vowel"
        if prev not in _SINHALA_CONSONANTS:
            return (), "dropped_orphan_dep_vowel"
    return None


def _repair_sinhala_char(ch: str, prev: str, nxt: str) -> tuple[tuple[str, ...], str | None]:
    if ch == "–":
        return ("-",), "normalized_en_dash"
    if ch == "\u1064":
        return _repair_zawgyi_kinzi_in_sinhala(prev, nxt), "repaired_zawgyi_kinzi"
    if ch == "\u108d":
        return (_SINHALA_ANUSVARA,), "repaired_zawgyi_108d"
    if ch == "\u1037":
        emit = () if prev == _SINHALA_ANUSVARA else (_SINHALA_ANUSVARA,)
        return emit, "repaired_dot_below"
    if ch in {"၌", "၏"}:
        return (), f"stripped_stray_{ord(ch):04x}"
    if ch == _SINHALA_ANUSVARA and prev == _SINHALA_ANUSVARA:
        return (), "collapsed_duplicate_anusvara"
    return (ch,), None


def clean_sinhala_headword(text: str) -> tuple[str, list[str]]:
    """Clean stray Myanmar/Zawgyi/Sinhala artifacts in `my-android.db` Sinhala headwords."""
    notes: list[str] = []
    raw = unicodedata.normalize("NFC", text.strip())
    for old, new, label in _SINHALA_PRECLEAN_SUBS:
        if old in raw:
            raw = raw.replace(old, new)
            notes.append(label)
    cleaned: list[str] = []
    chars = list(raw)
    for idx, ch in enumerate(chars):
        dep_fix = _repair_sinhala_dep_or_virama(ch, cleaned)
        if dep_fix is not None:
            emitted, note = dep_fix
        else:
            nxt = chars[idx + 1] if idx + 1 < len(chars) else ""
            prev = cleaned[-1] if cleaned else ""
            emitted, note = _repair_sinhala_char(ch, prev, nxt)
        cleaned.extend(emitted)
        if note is not None:
            notes.append(note)
    return "".join(cleaned), notes


def _sinhala_to_tokens(text: str, *, anusvara_velar_as_kinzi: bool) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    idx = 0
    total = len(text)
    while idx < total:
        ch = text[idx]
        if ch in _SINHALA_CONSONANTS:
            tokens.append(("C", _SINHALA_CONSONANTS[ch]))
            idx += 1
            if idx < total and text[idx] == _SINHALA_VIRAMA:
                idx += 1
            elif idx < total and text[idx] in _SINHALA_DEP_VOWELS:
                tokens.append(("V", _SINHALA_DEP_VOWELS[text[idx]]))
                idx += 1
            else:
                tokens.append(("V", "a"))
        elif ch in _SINHALA_INDEP_VOWELS:
            tokens.append(("V", _SINHALA_INDEP_VOWELS[ch]))
            idx += 1
        elif ch == _SINHALA_ANUSVARA:
            nxt = text[idx + 1] if idx + 1 < total else ""
            if (
                anusvara_velar_as_kinzi
                and nxt in _SINHALA_CONSONANTS
                and _SINHALA_CONSONANTS[nxt] in _VELAR_STOPS
            ):
                tokens.append(("C", "ṅ"))
            else:
                tokens.append(("M", "ṃ"))
            idx += 1
        else:
            tokens.append(("O", ch))
            idx += 1
    return tokens


def sinhala_to_myanmar(
    text: str,
    *,
    vocabulary: Collection[str] | None = None,
) -> str:
    """Transliterate Sinhala-script Pāḷi (`my-android.db`) into canonical Myanmar Unicode."""
    if not text:
        return ""
    cleaned, _ = clean_sinhala_headword(text)
    kinzi_form = _tokens_to_myanmar(_sinhala_to_tokens(cleaned, anusvara_velar_as_kinzi=True))
    if vocabulary is None or _SINHALA_ANUSVARA not in cleaned or kinzi_form in vocabulary:
        return kinzi_form
    anusvara_form = _tokens_to_myanmar(_sinhala_to_tokens(cleaned, anusvara_velar_as_kinzi=False))
    if anusvara_form in vocabulary:
        return anusvara_form
    return kinzi_form
