"""Experimental pndaza lexicon builder; not yet suitable for release."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

from pali_myanmar_dicts.mixed_encoding import (
    codepoints,
    mark_incomplete_fragment,
    mark_unresolved_markers,
    repair_header_kinzi,
    repair_verified_tokens,
)
from pali_myanmar_dicts.normalize import normalize_myanmar_text, to_headword_norm
from pali_myanmar_dicts.pali_text_worker import PaliTextWorker
from pali_myanmar_dicts.parsers import (
    parse_dhatuattha_html,
    parse_pali_dhatu_html,
    parse_u_hoke_sein_html,
)
from pali_myanmar_dicts.pm3 import PM3_URL, build_pm3_index, matching_compound
from pali_myanmar_dicts.schema import compute_content_hash, init_sqlite_db, validate_jsonl_record
from pali_myanmar_dicts.source_restorations import restore_definition
from pali_myanmar_dicts.translit import myanmar_to_iast
from pali_myanmar_dicts.zawgyi import has_zawgyi_codepoint_marker

LICENSE = "winmetta-pd-decision"
UPSTREAM = "https://github.com/pndaza/Tipitaka_Pali_Android"


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    author: str
    kind: str
    book: int
    expected: int


SOURCES = (
    Source("u-hoke-sein", "ပဒတ္ထမဉ္ဇူသာ ပါဠိ-မြန်မာ အဘိဓာန်", "ဦးဟုတ်စိန်", "lexicon", 2, 60782),
    Source("dhatuattha-pankone", "ဓာတွတ္ထပန်းကုံး", "အရှင်ကုမာရ", "dhatu_root", 3, 11086),
    Source("pali-dhatu-abhidhana", "ပါဠိဓာတ်အဘိဓာန်", "ဆရာဉာဏ်", "dhatu_root", 4, 1894),
)


def normalize_extra(value):
    """Normalize and check strings in nested source-specific data too."""
    if isinstance(value, str):
        return normalize_myanmar_text(value)
    if isinstance(value, list):
        return [normalize_extra(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_extra(item) for key, item in value.items()}
    return value


def pm3_extra(
    word: str, headword: str, index: dict[tuple[str, str], set[str]] | None
) -> dict[str, str]:
    if index is None or to_headword_norm(word) != to_headword_norm(headword):
        return {}
    if not (compound := matching_compound(word, index)):
        return {}
    return {
        "compound_hyphenated": compound,
        "compound_hyphenated_source": PM3_URL,
        "compound_hyphenated_license": "unverified",
    }


def repair_parsed_text(parsed: dict) -> tuple[list[dict[str, str]], list[dict[str, str | int]]]:
    repairs: list[dict[str, str]] = []
    incomplete: list[dict[str, str | int]] = []
    for key, value in parsed.items():
        if key != "headword" and isinstance(value, str):
            repaired, applied = repair_verified_tokens(value)
            partial, count = mark_incomplete_fragment(repaired)
            parsed[key], other_count = mark_unresolved_markers(partial)
            repairs.extend(applied)
            if count or other_count:
                incomplete.append(
                    {
                        "field": key,
                        "original_codepoints": codepoints(repaired),
                        "replacement_count": count + other_count,
                    }
                )
    return repairs, incomplete


def parse_source_record(source: Source, word: str, html: str) -> tuple[dict, dict]:
    if source.book == 2:
        parsed = asdict(parse_u_hoke_sein_html(word, html))
    elif source.book == 3:
        parsed = asdict(parse_dhatuattha_html(word, html))
    else:
        parsed = asdict(parse_pali_dhatu_html(word, html))
        parsed["root_pali"] = parsed["headword"]
    extra = {}
    parsed["headword"], repaired = repair_header_kinzi(parsed["headword"], word)
    if not repaired and has_zawgyi_codepoint_marker(parsed["headword"]):
        original_headword = parsed["headword"]
        parsed["headword"] = normalize_myanmar_text(word, single_line=True)
        extra["incomplete_source_fragments"] = [
            {
                "field": "headword",
                "original_codepoints": codepoints(original_headword),
                "replacement_count": 0,
                "fallback": "source_lookup_word",
            }
        ]
    if repaired:
        extra["encoding_repairs"] = ["header_kinzi_verified_against_lookup_word"]
    restoration = restore_definition(source.book, word, parsed)
    if restoration:
        extra["source_restoration"] = restoration
    verified, incomplete = repair_parsed_text(parsed)
    if incomplete:
        extra.setdefault("incomplete_source_fragments", []).extend(incomplete)
    if verified:
        extra["verified_token_repairs"] = verified
    for key in (
        "see_also",
        "root_variants",
        "gana_classes",
        "pali_sense",
        "burmese_sense",
        "sample_verbs",
    ):
        value = parsed.pop(key, None)
        if value:
            extra[key] = value
    return parsed, extra


def make_record(
    source: Source,
    word: str,
    html: str,
    worker: PaliTextWorker | None = None,
    pm3_index: dict[tuple[str, str], set[str]] | None = None,
) -> dict:
    """Parse one upstream row while retaining structured book-specific fields."""
    parsed, extra = parse_source_record(source, word, html)
    extra.update(pm3_extra(word, parsed["headword"], pm3_index))
    record = {
        "source_id": source.source_id,
        "entry_type": "pali_root" if source.book == 4 else "pali_term",
        "quality": "incomplete" if "incomplete_source_fragments" in extra else "proofed",
        "license_id": LICENSE,
        **parsed,
    }
    for key, value in record.items():
        if isinstance(value, str) and key not in {
            "source_id",
            "entry_type",
            "quality",
            "license_id",
        }:
            record[key] = normalize_myanmar_text(value)
    if worker is None:
        keys = (to_headword_norm(record["headword"]), myanmar_to_iast(record["headword"]))
    else:
        keys = worker.lookup_keys(record["headword"])
    record["headword_norm"], record["headword_iast"] = keys
    if extra:
        record["extra"] = normalize_extra(extra)
    # The shared base tuple omits fields such as English gloss and see-also links.
    # Include all remaining payload fields so distinct source entries cannot collide.
    supplemental = {
        key: record.get(key)
        for key in ("entry_type", "headword_iast", "root_pali", "english_gloss", "extra")
    }
    extra_hash = json.dumps(supplemental, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record["content_hash"] = compute_content_hash(record, extra_parts=(extra_hash,))
    validate_jsonl_record(record)
    return record


def audit_source(input_db: Path, source: Source) -> list[tuple[int, str, str]]:
    """Find records that fail validation without creating any output files."""
    issues: list[tuple[int, str, str]] = []
    with closing(sqlite3.connect(f"file:{input_db.resolve()}?mode=ro", uri=True)) as raw:
        rows = raw.execute(
            "SELECT rowid, word, definition FROM dictionary WHERE book = ? ORDER BY rowid",
            (source.book,),
        )
        for rowid, word, html in rows:
            try:
                make_record(source, word, html)
            except ValueError as error:
                issues.append((rowid, word, str(error)))
    return issues


def load_source_pm3(
    source: Source, pm3_path: Path | None
) -> dict[tuple[str, str], set[str]] | None:
    if source.source_id != "u-hoke-sein" or pm3_path is None:
        return None
    return build_pm3_index(pm3_path)


def _insert_source_metadata(conn: sqlite3.Connection, source: Source) -> None:
    conn.execute(
        "INSERT INTO sources (source_id,title_my,author_my,entry_kind,license_id,"
        "license_note,upstream_url,priority_rank) VALUES (?,?,?,?,?,?,?,?)",
        (
            source.source_id,
            source.title,
            source.author,
            source.kind,
            LICENSE,
            "Win Metta public-domain decision (2026-11-26); upstream provides no "
            "license. Credit pndaza and upstream digitizers.",
            UPSTREAM,
            source.book,
        ),
    )


def _insert_entries(
    conn: sqlite3.Connection,
    rows,
    source: Source,
    worker: PaliTextWorker,
    pm3_index: dict[tuple[str, str], set[str]] | None,
) -> int:
    seen = 0
    for word, html in rows:
        seen += 1
        record = make_record(source, word, html, worker, pm3_index)
        columns = list(record)
        values = [
            json.dumps(record[k], ensure_ascii=False, sort_keys=True)
            if k in {"extra", "senses", "citations"}
            else record[k]
            for k in columns
        ]
        db_columns = [f"{k}_json" if k in {"extra", "senses", "citations"} else k for k in columns]
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
                    f"Distinct records share a content hash: {source.source_id}: {word}"
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


def _build_staged_outputs(
    input_db: Path,
    staged_db: Path,
    staged_jsonl: Path,
    source: Source,
    pm3_index: dict[tuple[str, str], set[str]] | None,
) -> tuple[int, int]:
    with (
        closing(sqlite3.connect(f"file:{input_db.resolve()}?mode=ro", uri=True)) as raw,
        PaliTextWorker() as worker,
    ):
        rows = raw.execute(
            "SELECT word, definition FROM dictionary WHERE book = ? ORDER BY word, definition",
            (source.book,),
        )
        conn = init_sqlite_db(staged_db)
        try:
            _insert_source_metadata(conn, source)
            seen = _insert_entries(conn, rows, source, worker, pm3_index)
            if seen != source.expected:
                raise ValueError(
                    f"{source.source_id}: expected {source.expected} input rows, got {seen}"
                )
            conn.commit()
            _write_jsonl(conn, staged_jsonl)
            count = conn.execute("SELECT count(*) FROM entries").fetchone()[0]
        finally:
            conn.close()
    return seen, count


def _publish_staged_outputs(
    staged_db: Path, staged_jsonl: Path, db_path: Path, jsonl_path: Path
) -> None:
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


def build_source(
    input_db: Path, output_dir: Path, source: Source, *, pm3_path: Path | None = None
) -> tuple[int, int]:
    """Stage both outputs, then publish them; refuse to overwrite existing files."""
    db_path = output_dir / f"{source.source_id}.db"
    jsonl_path = output_dir / f"{source.source_id}.jsonl"
    if db_path.exists() or jsonl_path.exists():
        raise FileExistsError(f"Output already exists: {db_path} or {jsonl_path}")
    issues = audit_source(input_db, source)
    if issues:
        raise ValueError(
            f"{source.source_id}: {len(issues)} rows failed validation; "
            "run build-stage2.py --audit to inspect them"
        )
    pm3_index = load_source_pm3(source, pm3_path)
    with tempfile.TemporaryDirectory(prefix=f".{source.source_id}-", dir=output_dir) as staging:
        staged_db = Path(staging) / db_path.name
        staged_jsonl = Path(staging) / jsonl_path.name
        seen, count = _build_staged_outputs(input_db, staged_db, staged_jsonl, source, pm3_index)
        _publish_staged_outputs(staged_db, staged_jsonl, db_path, jsonl_path)
        return seen, count
