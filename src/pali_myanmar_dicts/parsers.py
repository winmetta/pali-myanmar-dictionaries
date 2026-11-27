"""Structured HTML and `♦`-segment parsers for `pndaza/tipitaka_pali.db` and `my-android.db`."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from pali_myanmar_dicts.normalize import normalize_myanmar_text

TAG_STRIP_RE = re.compile(r"<[^>]+>")
WORD_P_RE = re.compile(r'<p\s+class="word"[^>]*>(.*?)</p>', re.DOTALL)
GENDER_SPAN_RE = re.compile(r'<span\s+class="gender"[^>]*>(.*?)</span>', re.DOTALL)
VIGGAHA_DIV_RE = re.compile(r'<div\s+class="?viggaha"?[^>]*>(.*?)</div>', re.DOTALL)
ROOT_P_RE = re.compile(r'<p\s+class="root"[^>]*>(.*?)</p>', re.DOTALL)
DEF_DIV_RE = re.compile(r'<div\s+class="definition"[^>]*>(.*?)</div>', re.DOTALL)
DEF_P_RE = re.compile(r'<p\s+class="definition"[^>]*>(.*?)</p>', re.DOTALL)
REF_P_RE = re.compile(r'<p\s+class="reference"[^>]*>(.*?)</p>', re.DOTALL)
SOURCE_P_RE = re.compile(r'<p\s+class="source"[^>]*>(.*?)</p>', re.DOTALL)
SOURCE_VOL_RE = re.compile(r'<span\s+class="volume"[^>]*>(.*?)</span>', re.DOTALL)
SOURCE_PART_RE = re.compile(r'<span\s+class="part"[^>]*>(.*?)</span>', re.DOTALL)
SOURCE_REF_RE = re.compile(r'<span\s+class="reference"[^>]*>(.*?)</span>', re.DOTALL)
P_BLOCK_RE = re.compile(r"<p(?:\s+[^>]*)?>(.*?)</p>", re.DOTALL)
LI_OR_GENDER_RE = re.compile(
    r'<p\s+class="gender"[^>]*>(.*?)</p>|<li>(.*?)</li>',
    re.DOTALL,
)
SEE_TAG_RE = re.compile(r"<see>(.*?)</see>", re.DOTALL)

# Citation and homonym patterns
TIPI_REF_RE = re.compile(
    r"တိပိ၊\s*([၀-၉0-9]+(?:\s*[က-ဃa-c+-]*)?)၊\s*([၀-၉0-9]+)(?:\s*[-–+]\s*([၀-၉0-9]+))?"
)
TRAILING_NUM_RE = re.compile(r"^(.*?)\s*[-(]?\s*([၀-၉0-9]+)\s*\)?$")
BRACKET_WRAP_RE = re.compile(r"^\[(.*)\]$", re.DOTALL)
PAREN_POS_RE = re.compile(r"^\(([^()]{1,20})\)$")
ROOT_EXTRACT_RE = re.compile(r"√\s*([^\s+\]\),၊။]+)")
STUB_DEFINITION_RE = re.compile(r"^(?:မူရင်း[^\n။]*၌\s*ကြည့်ပါ|ဖတ်မရပါ)။?$")
LATIN_DOMINANT_RE = re.compile(r"^[\x00-\x7F\u0080-\u024F\u1E00-\u1EFF\s.,;:!?()\[\]'\"/-]+$")
MYANMAR_CHAR_RE = re.compile(r"[\u1000-\u109F]")

# Pāḷi Dhātu Abhidhāna (book=4) pattern: `<roots> <gaṇas> = <pali_sense>-<burmese_sense>။ <verbs>`
_GANA_ATOM = r"(?:ဘူ|ရု|ဒိ|သွာ|သု|ကီ|ကိ|ဂဟာ|ဂဟ|ဂ|တနာ|တန|တ|ဇု|စု)"
DHATU_BOOK4_RE = re.compile(
    rf"^(.+?)(?:[\s/]+)({_GANA_ATOM}(?:\s*[+,၊/]\s*{_GANA_ATOM})*)\s*=\s*(.+)$"
)
# Myanmar digit zero `၀` (`U+1040`) mistyped for consonant `ဝ` (`U+101D`) inside Pāḷi headwords:
ZERO_AS_WA_RE = re.compile(r"\u1040+(?=[\u1000-\u103F])|(?<=[\u1000-\u103F])\u1040+")

# `my-android.db` segment boundary: `♦<tag>` / `%ဝိသုဒ္ဓါရုံ` plus inline post-tag note up to `+`.
MY_ANDROID_TAG_RE = re.compile(
    r"(?:%♦(စိန်)|%(ဝိသုဒ္ဓါရုံ)|♦(ဝိသုဒ္ဓါရုံ|ချုပ်♦ချုပ်|မြ♦မြ|မြဗာရာဏသိသာမန္တ|ချုပ်|ချုပ|စိန်|မြျ|မြ|ဝိ|))"
    r"([^\n+♦]*?)(?:\+|$)"
)
UNTAGGED_DUP_SPLIT_RE = re.compile(r"(?<=။)\+(?=\s*(?:\[|\(|ပု|ထီ|န|တိ|အ|ဗျ))")


def _clean_html_fragment(raw: str, *, single_line: bool = True) -> str:
    without_tags = TAG_STRIP_RE.sub("", html.unescape(raw))
    return normalize_myanmar_text(without_tags, single_line=single_line, check_zawgyi=False)


def _myanmar_digits_to_int(raw: str) -> int | None:
    digits = "".join(
        chr(ord("0") + (ord(c) - ord("၀"))) if "၀" <= c <= "၉" else c for c in raw.strip()
    )
    return int(digits) if digits.isdigit() and int(digits) >= 1 else None


def _clean_pos(raw: str) -> str | None:
    cleaned = _clean_html_fragment(raw).strip("()[]၊။ ")
    return cleaned or None


def _clean_etymology(raw: str) -> str | None:
    cleaned = _clean_html_fragment(raw)
    m = BRACKET_WRAP_RE.match(cleaned)
    if m:
        cleaned = m.group(1).strip()
    return cleaned or None


def extract_root_pali(etymology: str | None) -> str | None:
    """Extract a `√<root>` Pāḷi dhātu marker when present in `etymology`."""
    if not etymology:
        return None
    m = ROOT_EXTRACT_RE.search(etymology)
    return f"√{m.group(1)}" if m else None


@dataclass(frozen=True)
class ParsedTipitakaAbhidhana:
    """Parsed fields from a `pndaza/tipitaka_pali.db` `book=1` HTML entry."""

    lookup_word: str
    headword: str
    homonym_no: int | None
    is_alias_row: bool
    is_stub: bool
    pos: str | None
    etymology: str | None
    root_pali: str | None
    definition_text: str | None
    senses: list[dict[str, object]] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    volume_hint: str | None = None
    part_hint: str | None = None
    printed_page: int | None = None
    printed_page_end: int | None = None


def _repair_headword_zero_as_wa(headword: str) -> str:
    return ZERO_AS_WA_RE.sub(lambda m: "ဝ" * len(m.group(0)), headword)


def _parse_word_header(lookup_word: str, raw_html: str) -> tuple[str, int | None, str | None]:
    fallback_hw = _repair_headword_zero_as_wa(
        normalize_myanmar_text(lookup_word, single_line=True, check_zawgyi=False)
    )
    word_m = WORD_P_RE.search(raw_html)
    if not word_m:
        return fallback_hw, None, None
    inner = word_m.group(1)
    pos: str | None = None
    gender_m = GENDER_SPAN_RE.search(inner)
    if gender_m:
        pos = _clean_pos(gender_m.group(1))
        inner = inner[: gender_m.start()] + inner[gender_m.end() :]
    hw_raw = _repair_headword_zero_as_wa(_clean_html_fragment(inner))
    homonym_no: int | None = None
    num_m = TRAILING_NUM_RE.match(hw_raw)
    if num_m and num_m.group(1).strip():
        hw_raw = num_m.group(1).strip()
        homonym_no = _myanmar_digits_to_int(num_m.group(2))
    return (hw_raw or fallback_hw, homonym_no, pos)


def _parse_definition_senses(
    def_inner_html: str, default_pos: str | None
) -> tuple[str, list[dict[str, object]]]:
    senses: list[dict[str, object]] = []
    current_pos = default_pos
    for m in LI_OR_GENDER_RE.finditer(def_inner_html):
        g_raw, li_raw = m.groups()
        if g_raw is not None:
            current_pos = _clean_pos(g_raw) or current_pos
        elif li_raw is not None:
            txt = _clean_html_fragment(li_raw)
            if txt:
                item: dict[str, object] = {"text": txt}
                if current_pos:
                    item["pos"] = current_pos
                senses.append(item)
    block_text = re.sub(r"</?(?:p|li|ul|div|br)[^>]*>", "\n", def_inner_html)
    def_text = _clean_html_fragment(block_text, single_line=False)
    return def_text, senses


def _parse_tipitaka_provenance(
    raw_html: str,
) -> tuple[list[str], str | None, str | None, int | None, int | None]:
    citations: list[str] = []
    vol_hint: str | None = None
    part_hint: str | None = None
    page_start: int | None = None
    page_end: int | None = None

    ref_m = REF_P_RE.search(raw_html)
    if ref_m:
        ref_txt = _clean_html_fragment(ref_m.group(1))
        if ref_txt:
            citations.append(ref_txt)
        tipi_m = TIPI_REF_RE.search(ref_txt)
        if tipi_m:
            vol_hint = tipi_m.group(1).strip()
            page_start = _myanmar_digits_to_int(tipi_m.group(2))
            if tipi_m.group(3):
                page_end = _myanmar_digits_to_int(tipi_m.group(3))

    src_m = SOURCE_P_RE.search(raw_html)
    if src_m:
        src_inner = src_m.group(1)
        src_txt = _clean_html_fragment(src_inner)
        if src_txt and src_txt not in citations:
            citations.append(src_txt)
        vm = SOURCE_VOL_RE.search(src_inner)
        pm = SOURCE_PART_RE.search(src_inner)
        rm = SOURCE_REF_RE.search(src_inner)
        if vm:
            vol_hint = _clean_html_fragment(vm.group(1)) or vol_hint
        if pm:
            part_hint = _clean_html_fragment(pm.group(1)) or None
        if rm and page_start is None:
            page_start = _myanmar_digits_to_int(_clean_html_fragment(rm.group(1)))

    return citations, vol_hint, part_hint, page_start, page_end


def parse_tipitaka_abhidhana_html(lookup_word: str, raw_html: str) -> ParsedTipitakaAbhidhana:
    """Parse a `pndaza/tipitaka_pali.db` `book=1` HTML row into clean structured fields."""
    norm_lookup = normalize_myanmar_text(lookup_word, single_line=True, check_zawgyi=False)
    headword, homonym_no, pos = _parse_word_header(norm_lookup, raw_html)
    vig_m = VIGGAHA_DIV_RE.search(raw_html)
    etymology = _clean_etymology(vig_m.group(1)) if vig_m else None
    def_m = DEF_DIV_RE.search(raw_html)
    def_inner = def_m.group(1) if def_m else raw_html
    def_text, senses = _parse_definition_senses(def_inner, pos)
    citations, vol_hint, part_hint, page_start, page_end = _parse_tipitaka_provenance(raw_html)
    is_stub = bool(not def_text or STUB_DEFINITION_RE.match(def_text.strip()))
    return ParsedTipitakaAbhidhana(
        lookup_word=norm_lookup,
        headword=headword,
        homonym_no=homonym_no,
        is_alias_row=(norm_lookup != headword),
        is_stub=is_stub,
        pos=pos,
        etymology=etymology,
        root_pali=extract_root_pali(etymology),
        definition_text=def_text or None,
        senses=senses,
        citations=citations,
        volume_hint=vol_hint,
        part_hint=part_hint,
        printed_page=page_start,
        printed_page_end=page_end,
    )


@dataclass(frozen=True)
class ParsedUHokeSein:
    """Parsed fields from a `pndaza/tipitaka_pali.db` `book=2` (U Hoke Sein) HTML row."""

    headword: str
    homonym_no: int | None
    pos: str | None
    etymology: str | None
    root_pali: str | None
    definition_text: str | None
    english_gloss: str | None
    see_also: list[str] = field(default_factory=list)


def parse_u_hoke_sein_html(lookup_word: str, raw_html: str) -> ParsedUHokeSein:
    """Parse U Hoke Sein (`book=2`), cleanly separating English/botanical glosses from Burmese."""
    headword, homonym_no, header_pos = _parse_word_header(lookup_word, raw_html)
    see_also = [_clean_html_fragment(m.group(1)) for m in SEE_TAG_RE.finditer(raw_html)]
    see_also = [s for s in see_also if s]

    pos = header_pos
    etymology: str | None = None
    burmese_lines: list[str] = []
    english_lines: list[str] = []

    for m in P_BLOCK_RE.finditer(raw_html):
        full_tag = m.group(0)
        if 'class="word"' in full_tag:
            continue
        line = _clean_html_fragment(m.group(1))
        if not line:
            continue
        if pos is None and PAREN_POS_RE.match(line) and MYANMAR_CHAR_RE.search(line):
            pos = _clean_pos(line)
            continue
        if etymology is None and line.startswith("[") and line.endswith("]"):
            etymology = _clean_etymology(line)
            continue
        if LATIN_DOMINANT_RE.match(line) and not MYANMAR_CHAR_RE.search(line):
            english_lines.append(line)
        else:
            burmese_lines.append(line)

    return ParsedUHokeSein(
        headword=headword,
        homonym_no=homonym_no,
        pos=pos,
        etymology=etymology,
        root_pali=extract_root_pali(etymology),
        definition_text="\n".join(burmese_lines) if burmese_lines else None,
        english_gloss="; ".join(english_lines) if english_lines else None,
        see_also=see_also,
    )


@dataclass(frozen=True)
class ParsedDhatuattha:
    """Parsed fields from `pndaza/tipitaka_pali.db` `book=3` (*Dhātvattha Pankone*)."""

    headword: str
    pos: str | None
    etymology: str | None
    root_pali: str | None
    definition_text: str


def parse_dhatuattha_html(lookup_word: str, raw_html: str) -> ParsedDhatuattha:
    """Parse *Dhātvattha Pankone* (`book=3`) HTML row."""
    headword, _, pos = _parse_word_header(lookup_word, raw_html)
    etymologies: list[str] = []
    # Some book=3 rows place `[...√...]` inline at the end of `<p class="word">`.
    word_m = WORD_P_RE.search(raw_html)
    if word_m:
        inline_text = _clean_html_fragment(GENDER_SPAN_RE.sub("", word_m.group(1)))
        br_m = re.search(r"\[([^\[\]]+)\]", inline_text)
        if br_m:
            cand_hw = _repair_headword_zero_as_wa(inline_text[: br_m.start()].strip())
            num_m = TRAILING_NUM_RE.match(cand_hw)
            if num_m and num_m.group(1).strip():
                cand_hw = num_m.group(1).strip()
            headword = cand_hw or headword
            etymologies.append(br_m.group(1).strip())

    for rm in ROOT_P_RE.finditer(raw_html):
        et = _clean_etymology(rm.group(1))
        if et and et not in etymologies:
            etymologies.append(et)

    body_lines: list[str] = []
    for pm in P_BLOCK_RE.finditer(raw_html):
        tag = pm.group(0)
        if 'class="word"' in tag or 'class="root"' in tag:
            continue
        txt = _clean_html_fragment(pm.group(1))
        if txt:
            body_lines.append(txt)

    joined_etym = " ; ".join(etymologies) if etymologies else None
    return ParsedDhatuattha(
        headword=headword,
        pos=pos,
        etymology=joined_etym,
        root_pali=extract_root_pali(joined_etym),
        definition_text="\n".join(body_lines),
    )


@dataclass(frozen=True)
class ParsedPaliDhatu:
    """Parsed fields from `pndaza/tipitaka_pali.db` `book=4` (*Pāḷi Dhātu Abhidhāna*)."""

    headword: str
    root_variants: list[str]
    gana_classes: list[str]
    pali_sense: str | None
    burmese_sense: str
    sample_verbs: str | None
    definition_text: str


def parse_pali_dhatu_html(lookup_word: str, raw_html: str) -> ParsedPaliDhatu:
    """Parse *Pāḷi Dhātu Abhidhāna* (`book=4`) root entry into gaṇa class, senses, and verbs."""
    hw = normalize_myanmar_text(lookup_word, single_line=True, check_zawgyi=False)
    def_m = DEF_P_RE.search(raw_html)
    body = _clean_html_fragment(def_m.group(1) if def_m else raw_html)
    dm = DHATU_BOOK4_RE.match(body)
    if not dm:
        return ParsedPaliDhatu(
            headword=hw,
            root_variants=[hw],
            gana_classes=[],
            pali_sense=None,
            burmese_sense=body,
            sample_verbs=None,
            definition_text=body,
        )

    roots_raw, ganas_raw, rhs = dm.groups()
    variants = [
        _repair_headword_zero_as_wa(r.strip()) for r in re.split(r"[,၊]", roots_raw) if r.strip()
    ]
    ganas = [g.strip() for g in re.split(r"[+,၊/]", ganas_raw) if g.strip()]
    pali_sense: str | None = None
    burmese_part = rhs.strip()
    if "-" in rhs:
        lhs_s, rhs_s = rhs.split("-", 1)
        pali_sense = lhs_s.strip() or None
        burmese_part = rhs_s.strip()
    sample_verbs: str | None = None
    if "။" in burmese_part:
        first_sent, rest_sent = burmese_part.split("။", 1)
        burmese_part = f"{first_sent.strip()}။"
        sample_verbs = rest_sent.strip(" ။") or None

    return ParsedPaliDhatu(
        headword=hw,
        root_variants=variants or [hw],
        gana_classes=ganas,
        pali_sense=pali_sense,
        burmese_sense=burmese_part,
        sample_verbs=sample_verbs,
        definition_text=body,
    )


@dataclass(frozen=True)
class MyAndroidSegment:
    """A single dictionary segment split from `tipitaka-app/my-android.db` `meaning`."""

    tag: str  # canonicalized: 'မြ' | 'စိန်' | 'ချုပ်' | 'ဝိ' | '' (untagged)
    raw_tag: str
    body: str


def _canonicalize_diamond_tag(raw_tag: str) -> str:
    if raw_tag in {"ချုပ်", "ချုပ", "ချုပ်♦ချုပ်"}:
        return "ချုပ်"
    if raw_tag in {"ဝိ", "ဝိသုဒ္ဓါရုံ"}:
        return "ဝိ"
    if raw_tag.startswith("မြ"):
        return "မြ"
    if raw_tag == "စိန်":
        return "စိန်"
    return ""


def _split_untagged_duplicates(chunk: str) -> list[str]:
    parts = [p.strip() for p in UNTAGGED_DUP_SPLIT_RE.split(chunk) if p.strip()]
    unique: list[str] = []
    for p in parts:
        if p not in unique:
            unique.append(p)
    return unique


def split_my_android_segments(meaning: str) -> list[MyAndroidSegment]:
    """Split a `my-android.db` `meaning` string on `♦<tag>` boundaries without breaking `[a+b]`."""
    if not meaning or not meaning.strip():
        return []
    segments: list[MyAndroidSegment] = []
    pos = 0
    for match in MY_ANDROID_TAG_RE.finditer(meaning):
        tag_groups = match.groups()[:-1]
        trailing_note = (match.groups()[-1] or "").strip()
        raw_tag = next((g for g in tag_groups if g is not None), "")
        chunk = meaning[pos : match.start()].strip()
        if trailing_note:
            chunk = f"{chunk} {trailing_note}".strip()
        pos = match.end()
        if not chunk:
            continue
        subparts = _split_untagged_duplicates(chunk)
        for subpart in subparts[:-1]:
            segments.append(MyAndroidSegment(tag="", raw_tag="", body=subpart))
        segments.append(
            MyAndroidSegment(
                tag=_canonicalize_diamond_tag(raw_tag),
                raw_tag=raw_tag,
                body=subparts[-1],
            )
        )

    trailing = meaning[pos:].strip()
    if trailing:
        for subpart in _split_untagged_duplicates(trailing):
            segments.append(MyAndroidSegment(tag="", raw_tag="", body=subpart))
    return segments
