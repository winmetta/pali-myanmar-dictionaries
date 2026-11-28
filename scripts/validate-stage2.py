#!/usr/bin/env python3
"""Validate generated Stage 2 SQLite and JSONL artifacts and optional repeat builds."""

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
from pali_myanmar_dicts.stage2 import SOURCES  # noqa: E402
from pali_myanmar_dicts.zawgyi import has_zawgyi_codepoint_marker  # noqa: E402

EXPECTED_COUNTS = {
    "u-hoke-sein": (60775, 58195),
    "dhatuattha-pankone": (11073, 9543),
    "pali-dhatu-abhidhana": (1894, 1882),
}
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


def check_record(record: dict, source_id: str) -> None:
    validate_jsonl_record(record)
    if record["source_id"] != source_id:
        raise ValueError(f"Wrong source for {record['headword']}")
    for text in strings(record):
        if (
            has_zawgyi_codepoint_marker(text)
            or unicodedata.normalize("NFC", text) != text
            or canonicalize_myanmar_syllables(text) != text
        ):
            raise ValueError(f"Invalid Unicode for {record['headword']}")
    if HTML_TAG.search(record["definition_text"] or ""):
        raise ValueError(f"HTML in definition for {record['headword']}")
    if record["quality"] == "incomplete" and not (record.get("extra") or {}).get(
        "incomplete_source_fragments"
    ):
        raise ValueError(f"Missing incomplete-source details for {record['headword']}")


def validate_source(directory: Path, source_id: str) -> None:
    db = directory / f"{source_id}.db"
    export = directory / f"{source_id}.jsonl"
    with (
        closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as conn,
        export.open(encoding="utf-8") as lines,
    ):
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"SQLite integrity failure: {db}")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError(f"SQLite foreign-key failure: {db}")
        counts = tuple(
            conn.execute("SELECT count(*),count(DISTINCT headword) FROM entries").fetchone()
        )
        if counts != EXPECTED_COUNTS[source_id]:
            raise ValueError(f"Unexpected entry/headword counts: {source_id} {counts}")
        headword = "ကက" if source_id == "pali-dhatu-abhidhana" else "က"
        fts_hit = conn.execute(
            "SELECT count(*) FROM entries WHERE headword = ? AND id IN "
            "(SELECT rowid FROM entries_fts WHERE entries_fts MATCH ?)",
            (headword, f'headword : "{headword}"'),
        ).fetchone()[0]
        if not fts_hit:
            raise ValueError(f"FTS lookup failed: {source_id} {headword}")
        rows = conn.execute(
            "SELECT * FROM entries ORDER BY headword,homonym_no,printed_page,content_hash"
        )
        incomplete = enriched = 0
        for row, line in zip(rows, lines, strict=True):
            record = record_from_row(row)
            if record != json.loads(line):
                raise ValueError(f"SQLite/JSONL mismatch for {record['headword']}")
            check_record(record, source_id)
            incomplete += record["quality"] == "incomplete"
            enriched += bool((record.get("extra") or {}).get("compound_hyphenated"))
        print(
            f"{source_id}: {counts[0]} entries, {counts[1]} headwords, "
            f"{incomplete} incomplete, {enriched} PM3-enriched"
        )


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_manifest(directory: Path, target: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    package = root / "packages/pali-text"
    version = json.loads((package / "package.json").read_text(encoding="utf-8"))["version"]
    raw = root / ".cache/pali-dictionary"
    inputs = {
        "pndaza/tipitaka_pali.db": digest(raw / "pndaza/tipitaka_pali.db"),
    }
    files = {}
    sources = {}
    pm3_enriched_total = 0
    for source in SOURCES:
        db = directory / f"{source.source_id}.db"
        with closing(sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)) as conn:
            entries, headwords, incomplete = conn.execute(
                "SELECT count(*), count(DISTINCT headword), sum(quality = 'incomplete') "
                "FROM entries"
            ).fetchone()
            enriched = conn.execute(
                "SELECT count(*) FROM entries "
                "WHERE json_extract(extra_json, '$.compound_hyphenated') IS NOT NULL"
            ).fetchone()[0]
            pm3_enriched_total += enriched
            license_id = conn.execute("SELECT license_id FROM sources").fetchone()[0]
            sources[source.source_id] = {
                "entries": entries,
                "headwords": headwords,
                "incomplete": incomplete,
                "license_id": license_id,
            }
        for suffix in ("db", "jsonl"):
            filename = f"{source.source_id}.{suffix}"
            path = directory / filename
            files[filename] = {"sha256": digest(path), "bytes": path.stat().st_size}
    if pm3_enriched_total > 0:
        inputs["tipitaka-pali-projector/pm3_Pali_Myanmar_Dictionary_@U_Hau_Sein_2018.js"] = digest(
            raw / "tipitaka-pali-projector/pm3_Pali_Myanmar_Dictionary_@U_Hau_Sein_2018.js"
        )
        pm3_status = "unverified; do not publish without resolving upstream rights"
    else:
        pm3_status = "none; omitted until upstream PM3 rights are verified"
    manifest = {
        "status": (
            "release-ready Stage 2 builds; 6 unrecoverable source fragments are marked incomplete"
        ),
        "pm3_enrichment_license": pm3_status,
        "pali_text": {"version": version, "compiled_sha256": digest(package / "dist/index.js")},
        "input_sha256": inputs,
        "sources": sources,
        "files": files,
    }
    with target.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare-dir", type=Path)
    parser.add_argument("--write-manifest", type=Path)
    args = parser.parse_args()
    for source in SOURCES:
        validate_source(args.directory, source.source_id)
        if args.compare_dir:
            for suffix in ("db", "jsonl"):
                filename = f"{source.source_id}.{suffix}"
                if digest(args.directory / filename) != digest(args.compare_dir / filename):
                    raise ValueError(f"Builds differ: {filename}")
    if args.compare_dir:
        print("SQLite and JSONL files match the repeat build byte-for-byte")
    if args.write_manifest:
        write_manifest(args.directory, args.write_manifest)


if __name__ == "__main__":
    main()
