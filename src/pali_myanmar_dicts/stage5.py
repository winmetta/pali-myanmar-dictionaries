"""Stage 5 ETL for topical, story, concordance, and reverse Pāḷi–Myanmar dictionaries."""

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
from pali_myanmar_dicts.schema import compute_content_hash, init_sqlite_db, validate_jsonl_record
from pali_myanmar_dicts.zawgyi import zawgyi_to_unicode_batch

LICENSE = "winmetta-pd-decision"
_TRAILING_HOMONYM_RE = re.compile(r"^(.*?)\s*\(([၀-၉0-9]+)\)\s*$")
_CIT_PAREN_RE = re.compile(r"\(([^()]+)\)")
_HTML_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MYANMAR_DIGITS = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")


@dataclass(frozen=True)
class Stage5Source:
    source_id: str
    title_my: str
    author_my: str
    entry_kind: str
    entry_type: str
    upstream_url: str
    volume_count: int
    priority_rank: int


STAGE5_SOURCES = (
    Stage5Source(
        "sutethana-thayokpya",
        "သုတေသနသရုပ်ပြအဘိဓာန်",
        "ဖျာပုံတိုက်သစ်ဆရာတော် အရှင်ဩဘာသာဘိဝံသ",
        "topical",
        "topic",
        "https://github.com/pndaza/tupya-abidan",
        1,
        7,
    ),
    Stage5Source(
        "pitaka-thayokson",
        "ပိဋကတ်သုံးပုံ သရုပ်စုံအဘိဓာန်",
        "စိန်ရတနာဆရာတော် ဘဒ္ဒန္တသာသနဝရ & ဓမ္မဗိမာန်အဖွဲ့",
        "topical",
        "topic",
        "https://github.com/pndaza/pitaka-sarupa",
        1,
        8,
    ),
    Stage5Source(
        "pitaka-vatthu-lamnyun",
        "ပိဋကဝတ္ထုလမ်းညွှန်",
        "Ven. Indobhāsa (Pitaka Guide)",
        "story",
        "story",
        "https://github.com/pndaza/Vatthu_Guide",
        1,
        9,
    ),
    Stage5Source(
        "pitaka-lamnyun",
        "ပိဋကလမ်းညွှန် (အတွဲ ၁–၃)",
        "ဆရာတော် ဦးသီဟဗလ",
        "index_only",
        "index_ref",
        "https://github.com/pndaza/pitaka_guide_cross_platform",
        3,
        10,
    ),
    Stage5Source(
        "u-hoke-sein-mep",
        "အများသုံး မြန်မာ-အင်္ဂလိပ်-ပါဠိ အဘိဓာန်",
        "ဦးဟုတ်စိန်",
        "reverse_my_pli",
        "myanmar_term",
        "https://github.com/pndaza/mep_dictionary",
        1,
        11,
    ),
)
STAGE5_BY_ID = {s.source_id: s for s in STAGE5_SOURCES}


def _clean_text(
    value: str,
    field: str,
    incomplete: list[dict[str, str | int]],
    repairs: list[dict[str, str]],
    *,
    single_line: bool = False,
) -> str:
    repaired, applied = repair_verified_tokens(value)
    partial, c1 = mark_incomplete_fragment(repaired)
    cleaned, c2 = mark_unresolved_markers(partial)
    repairs.extend(applied)
    if c1 or c2:
        incomplete.append(
            {
                "field": field,
                "original_codepoints": codepoints(repaired),
                "replacement_count": c1 + c2,
            }
        )
    return normalize_myanmar_text(cleaned, single_line=single_line)


def _normalize_nested(value):
    if isinstance(value, str):
        return normalize_myanmar_text(value)
    if isinstance(value, list):
        return [_normalize_nested(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_nested(item) for key, item in value.items()}
    return value


def _finalize_record(
    source: Stage5Source,
    record: dict[str, object],
    incomplete: list[dict[str, str | int]],
    repairs: list[dict[str, str]],
    worker: PaliTextWorker | None,
) -> dict[str, object]:
    extra = dict(record.get("extra") or {})
    if incomplete:
        extra["incomplete_source_fragments"] = incomplete
    if repairs:
        extra["verified_token_repairs"] = repairs

    headword = str(record["headword"])
    if worker is None:
        hw_norm = to_headword_norm(headword)
    else:
        hw_norm, _ = worker.lookup_keys(headword)

    record["source_id"] = source.source_id
    record["entry_type"] = source.entry_type
    record["headword_norm"] = hw_norm
    record["quality"] = "incomplete" if incomplete else "proofed"
    record["license_id"] = LICENSE
    record["extra"] = _normalize_nested(extra) if extra else None

    supplemental = {
        key: record.get(key) for key in ("entry_type", "english_gloss", "citations", "extra")
    }
    extra_hash = json.dumps(supplemental, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record["content_hash"] = compute_content_hash(record, extra_parts=(extra_hash,))
    validate_jsonl_record(record)
    return record


def _iter_tupya(cache_dir: Path):
    source = STAGE5_BY_ID["sutethana-thayokpya"]
    with closing(
        sqlite3.connect(f"file:{(cache_dir / 'tupya.db').resolve()}?mode=ro", uri=True)
    ) as conn:
        for row_id, name, detail in conn.execute("SELECT id, name, detail FROM topic ORDER BY id"):
            incomplete: list[dict[str, str | int]] = []
            repairs: list[dict[str, str]] = []
            hw = _clean_text(name or "", "headword", incomplete, repairs, single_line=True)
            defn = _clean_text(
                (detail or "").replace("\\n", "\n"), "definition_text", incomplete, repairs
            )
            yield (
                {"headword": hw, "definition_text": defn, "extra": {"topic_id": row_id}},
                incomplete,
                repairs,
                source,
            )


def _iter_sarupa(cache_dir: Path):
    source = STAGE5_BY_ID["pitaka-thayokson"]
    db = cache_dir / "sarupa.db"
    with closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as conn:
        for row_id, name, detail, reference in conn.execute(
            "SELECT id, name, detail, reference FROM topic ORDER BY id"
        ):
            incomplete: list[dict[str, str | int]] = []
            repairs: list[dict[str, str]] = []
            hw = _clean_text(name or "", "headword", incomplete, repairs, single_line=True)
            defn = _clean_text(
                (detail or "").replace("\\n", "\n"), "definition_text", incomplete, repairs
            )
            cits = []
            if reference:
                for idx, m in enumerate(_CIT_PAREN_RE.finditer(reference)):
                    c_txt = _clean_text(
                        m.group(1), f"citations[{idx}]", incomplete, repairs, single_line=True
                    )
                    if c_txt:
                        cits.append(c_txt)
                if not cits:
                    c_txt = _clean_text(
                        reference, "citations[0]", incomplete, repairs, single_line=True
                    )
                    if c_txt:
                        cits.append(c_txt)
            yield (
                {
                    "headword": hw,
                    "definition_text": defn,
                    "citations": cits or None,
                    "extra": {"topic_id": row_id},
                },
                incomplete,
                repairs,
                source,
            )


def _convert_zawgyi_safe(texts: list[str]) -> list[str]:
    if not texts:
        return []
    converted = zawgyi_to_unicode_batch(texts)
    return converted


def _iter_vatthu(cache_dir: Path):
    source = STAGE5_BY_ID["pitaka-vatthu-lamnyun"]
    db = cache_dir / "vatthuguide.db"
    with closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as conn:
        rows = conn.execute(
            "SELECT _id, item_uni, content, bref FROM vatthuguide ORDER BY _id"
        ).fetchall()
    contents = _convert_zawgyi_safe([r[2] or "" for r in rows])
    brefs = _convert_zawgyi_safe([r[3] or "" for r in rows])
    for (row_id, item_uni, _, _), content_uni, bref_uni in zip(rows, contents, brefs, strict=True):
        incomplete: list[dict[str, str | int]] = []
        repairs: list[dict[str, str]] = []
        hw = _clean_text(item_uni or "", "headword", incomplete, repairs, single_line=True)
        defn = _clean_text(content_uni, "definition_text", incomplete, repairs)
        cits = None
        if bref_uni.strip():
            cit = _clean_text(
                bref_uni.strip("() "), "citations[0]", incomplete, repairs, single_line=True
            )
            if cit:
                cits = [cit]
        yield (
            {
                "headword": hw,
                "definition_text": defn,
                "citations": cits,
                "extra": {"story_id": row_id},
            },
            incomplete,
            repairs,
            source,
        )


def _iter_pitakaguide(cache_dir: Path):
    source = STAGE5_BY_ID["pitaka-lamnyun"]
    db = cache_dir / "pitakaguide.db"
    with closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as conn:
        raw_tags = conn.execute("SELECT _id, name FROM tags ORDER BY _id").fetchall()
        tag_unis = _convert_zawgyi_safe([t[1] or "" for t in raw_tags])
        tag_map = {
            tid: normalize_myanmar_text(tuni, single_line=True, check_zawgyi=False)
            for (tid, _), tuni in zip(raw_tags, tag_unis, strict=True)
        }
        idx_tags: dict[int, list[str]] = defaultdict(list)
        for idx_id, tid in conn.execute("SELECT index_id, tag_id FROM index_tag"):
            if tid in tag_map:
                idx_tags[idx_id].append(tag_map[tid])
        rows = conn.execute(
            "SELECT _id, name_uni, volume, page FROM indexes ORDER BY _id"
        ).fetchall()

    for row_id, name_uni, volume, page in rows:
        incomplete: list[dict[str, str | int]] = []
        repairs: list[dict[str, str]] = []
        hw = _clean_text(name_uni or "", "headword", incomplete, repairs, single_line=True)
        tags = sorted(set(idx_tags.get(row_id, ())))
        extra: dict[str, object] = {"index_id": row_id}
        if tags:
            extra["tags"] = tags
        yield (
            {
                "headword": hw,
                "definition_text": None,
                "volume_code": f"{int(volume):02d}" if volume is not None else None,
                "printed_page": int(page) if page is not None and int(page) >= 1 else None,
                "extra": extra,
            },
            incomplete,
            repairs,
            source,
        )


def _parse_homonym(raw_my: str) -> tuple[str, int | None]:
    m = _TRAILING_HOMONYM_RE.match(raw_my.strip())
    if not m:
        return raw_my.strip(), None
    num_str = m.group(2).translate(_MYANMAR_DIGITS)
    num = int(num_str) if num_str.isdigit() and int(num_str) >= 1 else None
    return m.group(1).strip(), num


def _iter_mep(cache_dir: Path):
    source = STAGE5_BY_ID["u-hoke-sein-mep"]
    seen_keys: set[tuple[str, str, str]] = set()
    mep_db = cache_dir / "mep.db"
    with closing(sqlite3.connect(f"file:{mep_db.resolve()}?mode=ro", uri=True)) as conn:
        for row_id, my, eng, pli, page_number in conn.execute(
            "SELECT id, my, eng, pli, page_number FROM definition ORDER BY id"
        ):
            incomplete: list[dict[str, str | int]] = []
            repairs: list[dict[str, str]] = []
            base_hw, homonym = _parse_homonym(my or "")
            hw = _clean_text(base_hw, "headword", incomplete, repairs, single_line=True)
            if not to_headword_norm(hw):
                continue
            pli_clean = _clean_text(pli or "", "definition_text", incomplete, repairs)
            eng_clean = (
                _clean_text(eng.strip(), "english_gloss", incomplete, repairs, single_line=True)
                if eng and eng.strip()
                else None
            )
            seen_keys.add((to_headword_norm(hw), eng_clean or "", to_headword_norm(pli_clean)))
            yield (
                {
                    "headword": hw,
                    "homonym_no": homonym,
                    "definition_text": pli_clean,
                    "english_gloss": eng_clean,
                    "printed_page": (
                        int(page_number)
                        if page_number is not None and int(page_number) >= 1
                        else None
                    ),
                    "extra": {"mep_id": row_id, "pli_equivalents": pli_clean},
                },
                incomplete,
                repairs,
                source,
            )

    tp_db = cache_dir / "tipitaka_pali.db"
    if not tp_db.is_file():
        return
    with closing(sqlite3.connect(f"file:{tp_db.resolve()}?mode=ro", uri=True)) as conn:
        for word, html in conn.execute(
            "SELECT word, definition FROM dictionary WHERE book = 8 ORDER BY rowid"
        ):
            ps = [_HTML_TAG_RE.sub("", p).strip() for p in _HTML_P_RE.findall(html or "")]
            eng = ps[0] if len(ps) >= 1 else ""
            pli = ps[1] if len(ps) >= 2 else ""
            incomplete = []
            repairs = []
            hw = _clean_text(word or "", "headword", incomplete, repairs, single_line=True)
            if not to_headword_norm(hw):
                continue
            pli_clean = _clean_text(pli, "definition_text", incomplete, repairs)
            eng_clean = (
                _clean_text(eng, "english_gloss", incomplete, repairs, single_line=True)
                if eng
                else None
            )
            key = (to_headword_norm(hw), eng_clean or "", to_headword_norm(pli_clean))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            yield (
                {
                    "headword": hw,
                    "definition_text": pli_clean or None,
                    "english_gloss": eng_clean,
                    "extra": {"supplemental_source": "tipitaka_pali.db:book=8"},
                },
                incomplete,
                repairs,
                source,
            )


_ITERATORS = {
    "sutethana-thayokpya": _iter_tupya,
    "pitaka-thayokson": _iter_sarupa,
    "pitaka-vatthu-lamnyun": _iter_vatthu,
    "pitaka-lamnyun": _iter_pitakaguide,
    "u-hoke-sein-mep": _iter_mep,
}


def _insert_source_metadata(conn: sqlite3.Connection, source: Stage5Source) -> None:
    conn.execute(
        "INSERT INTO sources (source_id,title_my,author_my,entry_kind,volume_count,"
        "license_id,license_note,upstream_url,priority_rank) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            source.source_id,
            source.title_my,
            source.author_my,
            source.entry_kind,
            source.volume_count,
            LICENSE,
            "Win Metta public-domain decision (2026-11-26); upstream provides no "
            "license. Credit pndaza and upstream digitizers.",
            source.upstream_url,
            source.priority_rank,
        ),
    )
    if source.source_id == "pitaka-lamnyun":
        conn.executemany(
            "INSERT INTO source_volumes (source_id,volume_code,volume_number,title_my) "
            "VALUES (?,?,?,?)",
            [(source.source_id, f"{v:02d}", v, f"အတွဲ {v}") for v in range(1, 4)],
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


def build_stage5_source(cache_dir: Path, output_dir: Path, source: Stage5Source) -> tuple[int, int]:
    """Build and atomically publish one Stage 5 `<source_id>.{db,jsonl}` pair."""
    db_path = output_dir / f"{source.source_id}.db"
    jsonl_path = output_dir / f"{source.source_id}.jsonl"
    if db_path.exists() or jsonl_path.exists():
        raise FileExistsError(f"Output already exists: {db_path} or {jsonl_path}")

    iterator = _ITERATORS[source.source_id]
    with tempfile.TemporaryDirectory(prefix=f".{source.source_id}-", dir=output_dir) as staging:
        staged_db = Path(staging) / db_path.name
        staged_jsonl = Path(staging) / jsonl_path.name
        with PaliTextWorker() as worker:
            conn = init_sqlite_db(staged_db)
            seen = 0
            try:
                _insert_source_metadata(conn, source)
                for raw_rec, incomplete, repairs, src in iterator(cache_dir):
                    seen += 1
                    record = _finalize_record(src, raw_rec, incomplete, repairs, worker)
                    _insert_record(conn, record)
                conn.commit()
                _write_jsonl(conn, staged_jsonl)
                written = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
            finally:
                conn.close()
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
        return seen, written
