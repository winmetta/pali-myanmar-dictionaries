#!/usr/bin/env python3
"""Validate Stage 5 SQLite and JSONL outputs and optional repeat builds."""

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
from pali_myanmar_dicts.stage5 import STAGE5_SOURCES, Stage5Source  # noqa: E402
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


def check_record(record: dict, source: Stage5Source) -> None:
    validate_jsonl_record(record)
    if record["source_id"] != source.source_id:
        raise ValueError(f"Wrong source_id for {record['headword']}")
    for key, value in record.items():
        for text in strings(value):
            if has_zawgyi_codepoint_marker(text) or unicodedata.normalize("NFC", text) != text:
                raise ValueError(f"Invalid Unicode for {record['headword']} ({key})")
            if key != "headword_norm" and canonicalize_myanmar_syllables(text) != text:
                raise ValueError(f"Non-canonical syllables for {record['headword']} ({key})")
    if HTML_TAG.search(record["definition_text"] or ""):
        raise ValueError(f"HTML in definition for {record['headword']}")
    if source.entry_type == "index_ref" and record["definition_text"] is not None:
        raise ValueError(f"Expected NULL definition_text for index_ref: {record['headword']}")
    if record["quality"] == "incomplete" and not (record.get("extra") or {}).get(
        "incomplete_source_fragments"
    ):
        raise ValueError(f"Missing incomplete-source details for {record['headword']}")


def validate_source(directory: Path, source: Stage5Source) -> None:
    db = directory / f"{source.source_id}.db"
    export = directory / f"{source.source_id}.jsonl"
    with (
        closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as conn,
        export.open(encoding="utf-8") as lines,
    ):
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"SQLite integrity failure: {db}")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError(f"SQLite foreign-key failure: {db}")
        entries, headwords = conn.execute(
            "SELECT count(*), count(DISTINCT headword) FROM entries"
        ).fetchone()
        rows = conn.execute(
            "SELECT * FROM entries ORDER BY headword,homonym_no,printed_page,content_hash"
        )
        incomplete = 0
        for row, line in zip(rows, lines, strict=True):
            record = record_from_row(row)
            if record != json.loads(line):
                raise ValueError(f"SQLite/JSONL mismatch for {record['headword']}")
            check_record(record, source)
            incomplete += record["quality"] == "incomplete"
        print(
            f"{source.source_id}: {entries} entries, {headwords} headwords, {incomplete} incomplete"
        )


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare-dir", type=Path)
    args = parser.parse_args()
    for source in STAGE5_SOURCES:
        validate_source(args.directory, source)
        if args.compare_dir:
            for suffix in ("db", "jsonl"):
                filename = f"{source.source_id}.{suffix}"
                if digest(args.directory / filename) != digest(args.compare_dir / filename):
                    raise ValueError(f"Builds differ: {filename}")
    if args.compare_dir:
        print("SQLite and JSONL files match the repeat build byte-for-byte")


if __name__ == "__main__":
    main()
