#!/usr/bin/env python3
"""Validate Stage 4 `tipitaka-abhidhana` SQLite and JSONL outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pali_myanmar_dicts.normalize import canonicalize_myanmar_syllables  # noqa: E402
from pali_myanmar_dicts.schema import validate_jsonl_record  # noqa: E402
from pali_myanmar_dicts.stage4 import SOURCE_ID  # noqa: E402
from pali_myanmar_dicts.zawgyi import has_zawgyi_codepoint_marker  # noqa: E402

HTML_TAG = re.compile(r"<[^>]+>")


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def record_from_row(row: sqlite3.Row) -> dict:
    record = dict(row)
    del record["id"]
    for field in ("senses", "citations", "extra"):
        value = record.pop(f"{field}_json")
        record[field] = json.loads(value) if value is not None else None
    return record


def check_record(record: dict) -> None:
    validate_jsonl_record(record)
    if record["source_id"] != SOURCE_ID:
        raise ValueError(f"Wrong source_id for {record['headword']}")
    for key, value in record.items():
        for text in strings(value):
            if has_zawgyi_codepoint_marker(text) or unicodedata.normalize("NFC", text) != text:
                raise ValueError(f"Invalid Unicode for {record['headword']} ({key})")
            if key != "headword_norm" and canonicalize_myanmar_syllables(text) != text:
                raise ValueError(
                    f"Non-canonical Myanmar syllables for {record['headword']} ({key})"
                )
    if HTML_TAG.search(record["definition_text"] or ""):
        raise ValueError(f"HTML in definition for {record['headword']}")
    if record["quality"] == "incomplete" and not (record.get("extra") or {}).get(
        "incomplete_source_fragments"
    ):
        raise ValueError(f"Missing incomplete-source details for {record['headword']}")


def validate_stage4(directory: Path, *, proofed_only: bool = False) -> dict[str, int]:
    stem = f"{SOURCE_ID}-proofed" if proofed_only else SOURCE_ID
    db = directory / f"{stem}.db"
    export = directory / f"{stem}.jsonl"
    with (
        closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as conn,
        export.open(encoding="utf-8") as lines,
    ):
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"SQLite integrity failure: {db}")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError(f"SQLite foreign-key failure: {db}")
        vol_count = conn.execute("SELECT count(*) FROM source_volumes").fetchone()[0]
        if vol_count != 29:
            raise ValueError(f"Expected 29 source_volumes, got {vol_count}")
        entries, headwords = conn.execute(
            "SELECT count(*), count(DISTINCT headword) FROM entries"
        ).fetchone()
        fts_hit = conn.execute(
            "SELECT count(*) FROM entries WHERE headword = 'အ' AND id IN "
            "(SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'headword : \"အ\"')"
        ).fetchone()[0]
        if not fts_hit:
            raise ValueError("FTS lookup failed for 'အ'")
        rows = conn.execute(
            "SELECT * FROM entries ORDER BY headword,homonym_no,printed_page,content_hash"
        )
        proofed = ocr = incomplete = 0
        for row, line in zip(rows, lines, strict=True):
            record = record_from_row(row)
            if record != json.loads(line):
                raise ValueError(f"SQLite/JSONL mismatch for {record['headword']}")
            check_record(record)
            proofed += record["quality"] == "proofed"
            ocr += record["quality"] == "ocr"
            incomplete += record["quality"] == "incomplete"
            if proofed_only and record["license_id"] != "winmetta-pd-decision":
                raise ValueError(f"Non-PD row in proofed-only build: {record['headword']}")
        print(
            f"{stem}: {entries} entries, {headwords} headwords, "
            f"{proofed} proofed, {ocr} ocr, {incomplete} incomplete"
        )
        return {
            "entries": entries,
            "headwords": headwords,
            "proofed": proofed,
            "ocr": ocr,
            "incomplete": incomplete,
        }


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--proofed-only", action="store_true")
    parser.add_argument("--compare-dir", type=Path)
    args = parser.parse_args()
    validate_stage4(args.directory, proofed_only=args.proofed_only)
    stem = f"{SOURCE_ID}-proofed" if args.proofed_only else SOURCE_ID
    if args.compare_dir:
        for suffix in ("db", "jsonl"):
            filename = f"{stem}.{suffix}"
            if digest(args.directory / filename) != digest(args.compare_dir / filename):
                raise ValueError(f"Builds differ: {filename}")
        print("SQLite and JSONL files match the repeat build byte-for-byte")


if __name__ == "__main__":
    main()
