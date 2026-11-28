"""Stage 3 ETL for `tipitaka-app/my-android.db` unique lexicons."""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
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
from pali_myanmar_dicts.parsers import split_my_android_segments
from pali_myanmar_dicts.schema import compute_content_hash, init_sqlite_db, validate_jsonl_record
from pali_myanmar_dicts.translit import myanmar_to_iast, sinhala_to_myanmar

LICENSE = "winmetta-pd-decision"
UPSTREAM = "https://github.com/pndaza/tipitaka.app"

CHOK_POS_RE = re.compile(r"^\(([^()]{1,20})\)\s*(.+)$", re.DOTALL)
_VI_POS_ATOM = r"(?:ပု|ထီ|န|တိ|အ|ဗျ|အဗျ|ကြိ|ကိတ်|သဗ္ဗ|နိ)"
VI_BRACKET_POS_RE = re.compile(r"^\[([^\[\]]{1,25})\]\s*(.+)$", re.DOTALL)
VI_PREFIX_POS_RE = re.compile(
    rf"^({_VI_POS_ATOM}(?:\s*,\s*{_VI_POS_ATOM})*)[၊။\s]+(.+)$", re.DOTALL
)
VI_UNTAGGED_HEADER_RE = re.compile(
    rf"^(?:\[[^\]]+\]|{_VI_POS_ATOM}(?:\s*,\s*{_VI_POS_ATOM})*[၊,.\s]+)"
)
VI_NUMBERED_SENSE_RE = re.compile(r"\([၁-၉]\)")
MYA_LEAK_RE = re.compile(
    r"^[။\s]*(?:ပု|ထီ|န|တိ|အ|ဗျ)?\s*။\s*\["
    r"|√"
    r"|^(?:ဘူ|ရု|ဒိ|သွာ|သု|ကီ|ကိ|ဂဟာ|ဂဟ|တနာ|တန|တ|ဇု|စု)\s*[၊=]"
)
SEIN_LEAK_RE = re.compile(r"^\((?:ပ|ဣ|န|တိ|အ|ကြိ|နပု|ထီ)\)|\((?:m|f|nt|ind|adj|v)\.\)")


@dataclass(frozen=True)
class Stage3Source:
    source_id: str
    title: str
    author: str
    pub_year: str | None
    target_tag: str
    priority_rank: int


STAGE3_SOURCES = (
    Stage3Source(
        "pali-abhidhana-chok",
        "ပါဠိအဘိဓာန်ချုပ်",
        "လယ်တီပဏ္ဍိတ ဦးမောင်ကြီး",
        "1914",
        "ချုပ်",
        5,
    ),
    Stage3Source(
        "visuddharama-abhidhana",
        "ဝိသုဒ္ဓါရုံ ပိဋကအဘိဓာန်",
        "မဟာဝိသုဒ္ဓါရုံဂဏဝါစကအဖွဲ့",
        None,
        "ဝိ",
        6,
    ),
)


def is_visuddharama_untagged(body: str) -> bool:
    """Return True only when an untagged segment strictly matches the Visuddhārāma template."""
    stripped = body.strip()
    if not stripped or MYA_LEAK_RE.search(stripped) or SEIN_LEAK_RE.search(stripped):
        return False
    return bool(VI_UNTAGGED_HEADER_RE.match(stripped) and VI_NUMBERED_SENSE_RE.search(stripped))


def parse_chok_segment(body: str) -> dict[str, str | None]:
    """Extract optional leading `(pos)` and definition text from a `♦ချုပ်` segment."""
    stripped = body.strip()
    pos: str | None = None
    definition = stripped
    match = CHOK_POS_RE.match(stripped)
    if match:
        candidate = match.group(1).strip("()[]၊။ ")
        rest = match.group(2).strip()
        if candidate and rest:
            pos = candidate
            definition = rest
    return {"pos": pos, "definition_text": definition}


def parse_visuddharama_segment(body: str) -> dict[str, str | None]:
    """Extract optional leading `[pos]` or `pos၊` and definition text from a `♦ဝိ` segment."""
    stripped = body.strip()
    pos: str | None = None
    definition = stripped
    match = VI_BRACKET_POS_RE.match(stripped) or VI_PREFIX_POS_RE.match(stripped)
    if match:
        candidate = match.group(1).strip("()[]၊။ ")
        rest = match.group(2).strip()
        if candidate and rest:
            pos = candidate
            definition = rest
    return {"pos": pos, "definition_text": definition}


def _normalize_extra(value):
    if isinstance(value, str):
        return normalize_myanmar_text(value)
    if isinstance(value, list):
        return [_normalize_extra(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_extra(item) for key, item in value.items()}
    return value


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


def make_stage3_record(
    source: Stage3Source,
    sinhala_word: str,
    body: str,
    *,
    inferred_untagged: bool = False,
    worker: PaliTextWorker | None = None,
) -> dict:
    """Build and validate one Stage 3 dictionary record from a `my-android.db` segment."""
    parsed = (
        parse_chok_segment(body)
        if source.source_id == "pali-abhidhana-chok"
        else parse_visuddharama_segment(body)
    )
    extra: dict[str, object] = {"source_headword_sinhala": sinhala_word}
    if inferred_untagged:
        extra["inferred_untagged"] = True

    incomplete: list[dict[str, str | int]] = []
    repairs: list[dict[str, str]] = []
    for field in ("pos", "definition_text"):
        val = parsed.get(field)
        if isinstance(val, str):
            cleaned, applied = _clean_text_field(val, field, incomplete)
            parsed[field] = cleaned
            repairs.extend(applied)

    if incomplete:
        extra["incomplete_source_fragments"] = incomplete
    if repairs:
        extra["verified_token_repairs"] = repairs

    headword = normalize_myanmar_text(sinhala_to_myanmar(sinhala_word), single_line=True)
    definition = normalize_myanmar_text(parsed["definition_text"] or "")
    pos = normalize_myanmar_text(parsed["pos"], single_line=True) if parsed["pos"] else None

    if worker is None:
        headword_norm, headword_iast = to_headword_norm(headword), myanmar_to_iast(headword)
    else:
        headword_norm, headword_iast = worker.lookup_keys(headword)

    record: dict[str, object] = {
        "source_id": source.source_id,
        "entry_type": "pali_term",
        "headword": headword,
        "headword_norm": headword_norm,
        "headword_iast": headword_iast,
        "pos": pos,
        "definition_text": definition,
        "quality": "incomplete" if incomplete else "proofed",
        "license_id": LICENSE,
        "extra": _normalize_extra(extra),
    }
    supplemental = {key: record.get(key) for key in ("entry_type", "headword_iast", "extra")}
    extra_hash = json.dumps(supplemental, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record["content_hash"] = compute_content_hash(record, extra_parts=(extra_hash,))
    validate_jsonl_record(record)
    return record


def _iter_source_segments(conn: sqlite3.Connection, source: Stage3Source):
    for sinhala_word, meaning in conn.execute(
        "SELECT word, meaning FROM dictionary ORDER BY rowid"
    ):
        for seg in split_my_android_segments(meaning):
            if seg.tag == source.target_tag:
                yield sinhala_word, seg.body, False
            elif (
                source.source_id == "visuddharama-abhidhana"
                and seg.tag == ""
                and is_visuddharama_untagged(seg.body)
            ):
                yield sinhala_word, seg.body, True


def _insert_source_metadata(conn: sqlite3.Connection, source: Stage3Source) -> None:
    conn.execute(
        "INSERT INTO sources (source_id,title_my,author_my,pub_year,entry_kind,license_id,"
        "license_note,upstream_url,priority_rank) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            source.source_id,
            source.title,
            source.author,
            source.pub_year,
            "lexicon",
            LICENSE,
            "Win Metta public-domain decision (2026-11-26); upstream provides no "
            "license. Credit pndaza and upstream digitizers.",
            UPSTREAM,
            source.priority_rank,
        ),
    )


def _insert_entries(
    conn: sqlite3.Connection,
    segments,
    source: Stage3Source,
    worker: PaliTextWorker,
) -> int:
    seen = 0
    for sinhala_word, body, inferred in segments:
        seen += 1
        record = make_stage3_record(
            source, sinhala_word, body, inferred_untagged=inferred, worker=worker
        )
        columns = list(record)
        values = [
            json.dumps(record[k], ensure_ascii=False, sort_keys=True) if k == "extra" else record[k]
            for k in columns
        ]
        db_columns = ["extra_json" if k == "extra" else k for k in columns]
        placeholders = ",".join("?" for _ in values)
        inserted = conn.execute(
            f"INSERT INTO entries ({','.join(db_columns)}) VALUES ({placeholders}) "
            "ON CONFLICT(source_id, content_hash) DO NOTHING",
            values,
        )
        if inserted.rowcount == 0:
            existing = conn.execute(
                f"SELECT {','.join(db_columns)} FROM entries "
                "WHERE source_id = ? AND content_hash = ?",
                (record["source_id"], record["content_hash"]),
            ).fetchone()
            if existing != tuple(values):
                raise ValueError(
                    f"Distinct records share a content hash: {source.source_id}: {sinhala_word}"
                )
    return seen


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


def build_stage3_source(input_db: Path, output_dir: Path, source: Stage3Source) -> tuple[int, int]:
    """Build and atomically publish `<source_id>.db` and `<source_id>.jsonl`."""
    db_path = output_dir / f"{source.source_id}.db"
    jsonl_path = output_dir / f"{source.source_id}.jsonl"
    if db_path.exists() or jsonl_path.exists():
        raise FileExistsError(f"Output already exists: {db_path} or {jsonl_path}")

    with tempfile.TemporaryDirectory(prefix=f".{source.source_id}-", dir=output_dir) as staging:
        staged_db = Path(staging) / db_path.name
        staged_jsonl = Path(staging) / jsonl_path.name
        with (
            closing(sqlite3.connect(f"file:{input_db.resolve()}?mode=ro", uri=True)) as raw,
            PaliTextWorker() as worker,
        ):
            conn = init_sqlite_db(staged_db)
            try:
                _insert_source_metadata(conn, source)
                seen = _insert_entries(conn, _iter_source_segments(raw, source), source, worker)
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
