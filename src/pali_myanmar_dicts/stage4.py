"""Stage 4 ETL for the 29-book `tipitaka-abhidhana` dataset."""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from pali_myanmar_dicts.mixed_encoding import (
    codepoints,
    mark_incomplete_fragment,
    mark_unresolved_markers,
    repair_verified_tokens,
)
from pali_myanmar_dicts.normalize import normalize_myanmar_text, to_headword_norm
from pali_myanmar_dicts.pali_text_worker import PaliTextWorker
from pali_myanmar_dicts.parsers import extract_root_pali, parse_tipitaka_abhidhana_html
from pali_myanmar_dicts.schema import compute_content_hash, init_sqlite_db, validate_jsonl_record
from pali_myanmar_dicts.translit import myanmar_to_iast

SOURCE_ID = "tipitaka-abhidhana"
PD_LICENSE = "winmetta-pd-decision"
OCR_LICENSE = "CC-BY-SA-4.0"
UPSTREAM_PD = "https://github.com/pndaza/Tipitaka_Pali_Android"
UPSTREAM_OCR = "https://github.com/bthar-mx/tipitaka-abhidhana"
BTHAR_ATTRIBUTION = (
    "Tipiṭaka Pāḷi-Myanmā Abhidhāna — digitised, IEBH / BTHAR, "
    "https://github.com/bthar-mx/tipitaka-abhidhana"
)
OCR_FULL_BOOKS = frozenset({"14c", "20", "21", "24", "25"})
OCR_PARTIAL_BOOKS = frozenset({"4c", "14b"})

_MYANMAR_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
_RAW_VOL_PAGE_RE = re.compile(r"([၀-၉0-9]+)\s*၊\s*(?:မုခဒေါသ)?\s*([၀-၉0-9]+)")
_PART_NUM_RE = re.compile(r"အပိုင်း\s*([၀-၉0-9]+)")


@dataclass(frozen=True)
class VolumeInfo:
    volume_code: str
    volume_number: int | None
    part_number: str | None
    title_my: str
    headword_range: str
    pdf_page_offset: int


def _to_ascii_int(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = raw.strip().translate(_MYANMAR_DIGITS)
    return int(digits) if digits.isdigit() else None


def load_volumes(abidan_db: Path) -> dict[str, VolumeInfo]:
    """Load the 29 `source_volumes` metadata rows from `abidan_new.db`."""
    volumes: dict[str, VolumeInfo] = {}
    with closing(sqlite3.connect(f"file:{abidan_db.resolve()}?mode=ro", uri=True)) as conn:
        for book_id, name, name_info, start_page in conn.execute(
            "SELECT id, name, name_info, start_page FROM books ORDER BY id"
        ):
            vol_num = _to_ascii_int(re.sub(r"[a-c]$", "", book_id))
            part_m = _PART_NUM_RE.search(name)
            part_num = str(_to_ascii_int(part_m.group(1))) if part_m else None
            volumes[book_id] = VolumeInfo(
                volume_code=book_id,
                volume_number=vol_num,
                part_number=part_num,
                title_my=normalize_myanmar_text(name, single_line=True, check_zawgyi=False),
                headword_range=normalize_myanmar_text(
                    name_info, single_line=True, check_zawgyi=False
                ),
                pdf_page_offset=int(start_page),
            )
    return volumes


def load_abidan_index(abidan_db: Path) -> dict[str, list[tuple[str, int]]]:
    """Map normalized headwords in `abidan_new.db` to `(volume_code, page_number)`."""
    index: dict[str, list[tuple[str, int]]] = defaultdict(list)
    with closing(sqlite3.connect(f"file:{abidan_db.resolve()}?mode=ro", uri=True)) as conn:
        for word, book_id, page_number in conn.execute(
            "SELECT word, book_id, page_number FROM words"
        ):
            key = to_headword_norm(word)
            index[key].append((book_id, int(page_number)))
    return dict(index)


_HINT_VOL_MAP = {
    ("၄က", None): "4a",
    ("၄ခ", None): "4b",
    ("၄", "၃"): "4c",
    ("၁၄", "၂"): "14b",
    ("၁၄", "၃"): "14c",
}


def resolve_volume_code(
    volume_hint: str | None,
    part_hint: str | None,
    citations: list[str],
    headword_norm: str,
    abidan_index: dict[str, list[tuple[str, int]]],
) -> tuple[str | None, int | None]:
    """Resolve canonical 29-book `volume_code` and fallback `printed_page`."""
    if volume_hint:
        hint = volume_hint.strip()
        mapped = _HINT_VOL_MAP.get((hint, part_hint)) or _HINT_VOL_MAP.get((hint, None))
        if mapped:
            return mapped, None
        num = _to_ascii_int(hint)
        if num is not None:
            return f"{num:02d}", None

    for cit in citations:
        m = _RAW_VOL_PAGE_RE.search(cit)
        if m:
            num, page = _to_ascii_int(m.group(1)), _to_ascii_int(m.group(2))
            if num is not None:
                return f"{num:02d}", page

    candidates = abidan_index.get(headword_norm)
    return (candidates[0][0], candidates[0][1]) if candidates else (None, None)


def _clean_text_field(
    value: str, field: str, incomplete: list[dict[str, str | int]]
) -> tuple[str, list[dict[str, str]]]:
    repaired, applied = repair_verified_tokens(value)
    partial, count = mark_incomplete_fragment(repaired)
    cleaned, other_count = mark_unresolved_markers(partial)
    if count or other_count:
        incomplete.append(
            {
                "field": field,
                "original_codepoints": codepoints(repaired),
                "replacement_count": count + other_count,
            }
        )
    return cleaned, applied


def _normalize_nested(value):
    if isinstance(value, str):
        return normalize_myanmar_text(value)
    if isinstance(value, list):
        return [_normalize_nested(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_nested(item) for key, item in value.items()}
    return value


def _finalize_record(
    record: dict[str, object],
    worker: PaliTextWorker | None,
) -> dict[str, object]:
    headword = normalize_myanmar_text(str(record["headword"]), single_line=True)
    record["headword"] = headword
    if worker is None:
        hw_norm, hw_iast = to_headword_norm(headword), myanmar_to_iast(headword)
    else:
        hw_norm, hw_iast = worker.lookup_keys(headword)
    record["headword_norm"] = hw_norm
    if not record.get("headword_iast"):
        record["headword_iast"] = hw_iast
    if record.get("extra"):
        record["extra"] = _normalize_nested(record["extra"])
    supplemental = {
        key: record.get(key)
        for key in ("entry_type", "headword_iast", "root_pali", "senses", "citations", "extra")
    }
    extra_hash = json.dumps(supplemental, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record["content_hash"] = compute_content_hash(record, extra_parts=(extra_hash,))
    validate_jsonl_record(record)
    return record


def _clean_senses(
    raw_senses: list[dict[str, object]],
    incomplete: list[dict[str, str | int]],
    repairs: list[dict[str, str]],
) -> list[dict[str, object]] | None:
    if not raw_senses:
        return None
    cleaned: list[dict[str, object]] = []
    for idx, item in enumerate(raw_senses):
        out: dict[str, object] = {}
        for skey, sval in item.items():
            if isinstance(sval, str):
                cval, applied = _clean_text_field(sval, f"senses[{idx}].{skey}", incomplete)
                repairs.extend(applied)
                out[skey] = normalize_myanmar_text(cval)
            else:
                out[skey] = sval
        cleaned.append(out)
    return cleaned


def _clean_citations(
    raw_citations: list[str],
    incomplete: list[dict[str, str | int]],
    repairs: list[dict[str, str]],
) -> list[str] | None:
    if not raw_citations:
        return None
    cleaned: list[str] = []
    for idx, cit in enumerate(raw_citations):
        if cit and str(cit).strip():
            ccit, applied = _clean_text_field(str(cit).strip(), f"citations[{idx}]", incomplete)
            repairs.extend(applied)
            cleaned.append(normalize_myanmar_text(ccit, single_line=True))
    return cleaned or None


def make_proofed_record(
    word: str,
    html: str,
    volumes: dict[str, VolumeInfo],
    abidan_index: dict[str, list[tuple[str, int]]],
    worker: PaliTextWorker | None = None,
) -> dict[str, object] | None:
    """Parse one `pndaza` `book=1` row, returning None for stub entries."""
    parsed = parse_tipitaka_abhidhana_html(word, html)
    if parsed.is_stub or not parsed.definition_text:
        return None

    incomplete: list[dict[str, str | int]] = []
    repairs: list[dict[str, str]] = []
    headword, applied_hw = _clean_text_field(parsed.headword, "headword", incomplete)
    defn, applied_def = _clean_text_field(parsed.definition_text, "definition_text", incomplete)
    repairs.extend(applied_hw + applied_def)

    etym = None
    if parsed.etymology:
        etym, applied_etym = _clean_text_field(parsed.etymology, "etymology", incomplete)
        repairs.extend(applied_etym)
    pos = None
    if parsed.pos:
        pos, applied_pos = _clean_text_field(parsed.pos, "pos", incomplete)
        repairs.extend(applied_pos)

    hw_norm = to_headword_norm(headword)
    vol_code, fallback_page = resolve_volume_code(
        parsed.volume_hint, parsed.part_hint, parsed.citations, hw_norm, abidan_index
    )
    printed_page = parsed.printed_page or fallback_page
    if printed_page is None and vol_code:
        printed_page = next((p for v, p in abidan_index.get(hw_norm, ()) if v == vol_code), None)
    pdf_page = (
        printed_page + volumes[vol_code].pdf_page_offset
        if printed_page is not None and vol_code in volumes
        else None
    )

    senses = _clean_senses(parsed.senses, incomplete, repairs)
    citations = _clean_citations(parsed.citations, incomplete, repairs)
    extra: dict[str, object] = {}
    if incomplete:
        extra["incomplete_source_fragments"] = incomplete
    if repairs:
        extra["verified_token_repairs"] = repairs
    record: dict[str, object] = {
        "source_id": SOURCE_ID,
        "entry_type": "pali_term",
        "headword": headword,
        "homonym_no": parsed.homonym_no,
        "pos": normalize_myanmar_text(pos, single_line=True) if pos else None,
        "etymology": normalize_myanmar_text(etym, single_line=True) if etym else None,
        "root_pali": normalize_myanmar_text(parsed.root_pali, single_line=True)
        if parsed.root_pali
        else None,
        "definition_text": normalize_myanmar_text(defn),
        "senses": senses,
        "volume_code": vol_code,
        "printed_page": printed_page,
        "printed_page_end": parsed.printed_page_end,
        "pdf_page": pdf_page,
        "citations": citations,
        "quality": "incomplete" if incomplete else "proofed",
        "license_id": PD_LICENSE,
        "extra": extra or None,
    }
    return _finalize_record(record, worker)


def make_ocr_record(
    article: dict,
    worker: PaliTextWorker | None = None,
) -> dict[str, object] | None:
    """Convert one `bthar-mx/ocr/*/articles.jsonl` article into a Stage 4 record."""
    body = (article.get("body") or "").strip()
    raw_hw = (article.get("headword") or "").strip()
    if not body or not raw_hw:
        return None

    incomplete: list[dict[str, str | int]] = []
    repairs: list[dict[str, str]] = []
    headword, applied_hw = _clean_text_field(raw_hw, "headword", incomplete)
    repairs.extend(applied_hw)
    defn, applied_def = _clean_text_field(body, "definition_text", incomplete)
    repairs.extend(applied_def)

    analysis_raw = (article.get("analysis") or "").strip()
    etym = None
    if analysis_raw:
        etym, applied_etym = _clean_text_field(analysis_raw, "etymology", incomplete)
        repairs.extend(applied_etym)

    label_raw = (article.get("label") or "").strip()
    pos = None
    if label_raw:
        pos, applied_pos = _clean_text_field(label_raw, "pos", incomplete)
        repairs.extend(applied_pos)

    citations = []
    for idx, c in enumerate(article.get("citations") or []):
        if c and str(c).strip():
            ccit, applied_c = _clean_text_field(str(c).strip(), f"citations[{idx}]", incomplete)
            repairs.extend(applied_c)
            citations.append(normalize_myanmar_text(ccit, single_line=True))

    extra: dict[str, object] = {"ocr_source": "bthar-mx", "bthar_id": article.get("id")}
    if incomplete:
        extra["incomplete_source_fragments"] = incomplete
    if repairs:
        extra["verified_token_repairs"] = repairs
    record: dict[str, object] = {
        "source_id": SOURCE_ID,
        "entry_type": "pali_term",
        "headword": headword,
        "headword_iast": (article.get("iast") or "").strip() or None,
        "pos": normalize_myanmar_text(pos, single_line=True) if pos else None,
        "etymology": normalize_myanmar_text(etym, single_line=True) if etym else None,
        "root_pali": extract_root_pali(etym) if etym else None,
        "definition_text": normalize_myanmar_text(defn),
        "volume_code": article.get("book"),
        "printed_page": article.get("index_page"),
        "pdf_page": article.get("pdf_page"),
        "citations": citations or None,
        "quality": "incomplete" if incomplete else "ocr",
        "license_id": OCR_LICENSE,
        "extra": extra,
    }
    return _finalize_record(record, worker)


def _insert_metadata(
    conn: sqlite3.Connection, volumes: dict[str, VolumeInfo], *, proofed_only: bool
) -> None:
    license_id = PD_LICENSE if proofed_only else OCR_LICENSE
    license_note = (
        "Win Metta public-domain decision (2026-11-26) for pndaza digitized text."
        if proofed_only
        else f"Hybrid build: proofed entries under {PD_LICENSE}; OCR gap-fills under "
        f"{OCR_LICENSE} ({BTHAR_ATTRIBUTION})."
    )
    conn.execute(
        "INSERT INTO sources (source_id,title_my,title_pali_en,author_my,pub_year,"
        "entry_kind,volume_count,license_id,license_note,upstream_url,priority_rank) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            SOURCE_ID,
            "တိပိဋက ပါဠိ-မြန်မာ အဘိဓာန်",
            "Tipiṭaka Pāḷi-Myanmā Abhidhāna",
            "မစိုးရိမ်တိုက်သစ်ဆရာတော်ဘုရားကြီးများ (သာသနာရေးဝန်ကြီးဌာန)",
            "1964–2023",
            "lexicon",
            len(volumes),
            license_id,
            license_note,
            UPSTREAM_PD if proofed_only else f"{UPSTREAM_PD} ; {UPSTREAM_OCR}",
            1,
        ),
    )
    conn.executemany(
        "INSERT INTO source_volumes (source_id,volume_code,volume_number,part_number,"
        "title_my,headword_range,pdf_page_offset) VALUES (?,?,?,?,?,?,?)",
        [
            (
                SOURCE_ID,
                v.volume_code,
                v.volume_number,
                v.part_number,
                v.title_my,
                v.headword_range,
                v.pdf_page_offset,
            )
            for v in volumes.values()
        ],
    )


def _insert_record(conn: sqlite3.Connection, record: dict[str, object]) -> None:
    columns = list(record)
    values = [
        json.dumps(record[k], ensure_ascii=False, sort_keys=True)
        if k in {"extra", "senses", "citations"} and record[k] is not None
        else record[k]
        for k in columns
    ]
    db_columns = [f"{k}_json" if k in {"extra", "senses", "citations"} else k for k in columns]
    placeholders = ",".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO entries ({','.join(db_columns)}) VALUES ({placeholders}) "
        "ON CONFLICT(source_id, content_hash) DO NOTHING",
        values,
    )


def _write_jsonl(conn: sqlite3.Connection, jsonl_path: Path) -> None:
    with jsonl_path.open("x", encoding="utf-8") as output:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT * FROM entries ORDER BY headword, homonym_no, printed_page, content_hash"
        ):
            record = dict(row)
            del record["id"]
            for key in ("senses", "citations", "extra"):
                value = record.pop(f"{key}_json")
                record[key] = json.loads(value) if value is not None else None
            validate_jsonl_record(record)
            output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _ingest_proofed_rows(
    raw: sqlite3.Connection,
    conn: sqlite3.Connection,
    volumes: dict[str, VolumeInfo],
    abidan_index: dict[str, list[tuple[str, int]]],
    worker: PaliTextWorker,
) -> tuple[dict[str, int], dict[str, set[str]]]:
    counts = {"proofed_read": 0, "stubs_skipped": 0}
    keys_by_vol: dict[str, set[str]] = defaultdict(set)
    sql = "SELECT word, definition FROM dictionary WHERE book = 1 ORDER BY word, definition"
    for word, html in raw.execute(sql):
        counts["proofed_read"] += 1
        record = make_proofed_record(word, html, volumes, abidan_index, worker)
        if record is None:
            counts["stubs_skipped"] += 1
            continue
        _insert_record(conn, record)
        if record.get("volume_code"):
            keys_by_vol[str(record["volume_code"])].add(str(record["headword_norm"]))
    return counts, keys_by_vol


def _ingest_ocr_rows(
    bthar_ocr_dir: Path,
    conn: sqlite3.Connection,
    proofed_keys_by_vol: dict[str, set[str]],
    worker: PaliTextWorker,
) -> int:
    added = 0
    for book in sorted(OCR_FULL_BOOKS | OCR_PARTIAL_BOOKS):
        art_path = bthar_ocr_dir / book / "articles.jsonl"
        if not art_path.is_file():
            continue
        with art_path.open(encoding="utf-8") as handle:
            for line in handle:
                article = json.loads(line)
                hw = (article.get("headword") or "").strip()
                if (
                    book in OCR_PARTIAL_BOOKS
                    and hw
                    and to_headword_norm(hw) in proofed_keys_by_vol[book]
                ):
                    continue
                record = make_ocr_record(article, worker)
                if record is not None:
                    _insert_record(conn, record)
                    added += 1
    return added


def build_stage4(
    *,
    tipitaka_db: Path,
    abidan_db: Path,
    bthar_ocr_dir: Path | None,
    output_dir: Path,
    proofed_only: bool = False,
) -> dict[str, int]:
    """Build `tipitaka-abhidhana` (or `tipitaka-abhidhana-proofed`) SQLite + JSONL."""
    stem = f"{SOURCE_ID}-proofed" if proofed_only else SOURCE_ID
    db_path = output_dir / f"{stem}.db"
    jsonl_path = output_dir / f"{stem}.jsonl"
    if db_path.exists() or jsonl_path.exists():
        raise FileExistsError(f"Output already exists: {db_path} or {jsonl_path}")

    volumes = load_volumes(abidan_db)
    abidan_index = load_abidan_index(abidan_db)

    with tempfile.TemporaryDirectory(prefix=f".{stem}-", dir=output_dir) as staging:
        staged_db = Path(staging) / db_path.name
        staged_jsonl = Path(staging) / jsonl_path.name
        with (
            closing(sqlite3.connect(f"file:{tipitaka_db.resolve()}?mode=ro", uri=True)) as raw,
            PaliTextWorker() as worker,
        ):
            conn = init_sqlite_db(staged_db)
            try:
                _insert_metadata(conn, volumes, proofed_only=proofed_only)
                counts, keys_by_vol = _ingest_proofed_rows(raw, conn, volumes, abidan_index, worker)
                ocr_added = (
                    _ingest_ocr_rows(bthar_ocr_dir, conn, keys_by_vol, worker)
                    if not proofed_only and bthar_ocr_dir is not None
                    else 0
                )
                conn.commit()
                _write_jsonl(conn, staged_jsonl)
                written = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
            finally:
                conn.close()
        _publish_outputs(staged_db, staged_jsonl, db_path, jsonl_path)
    return {**counts, "ocr_added": ocr_added, "written": written}


def _publish_outputs(staged_db: Path, staged_jsonl: Path, db_path: Path, jsonl_path: Path) -> None:
    published: list[Path] = []
    try:
        staged_db.replace(db_path)
        published.append(db_path)
        staged_jsonl.replace(jsonl_path)
        published.append(jsonl_path)
    except BaseException:
        for path in published:
            path.unlink(missing_ok=True)
        raise
