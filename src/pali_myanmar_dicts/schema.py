"""SQLite schema initialization and JSONL entry record validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SQLITE_SCHEMA_PATH = REPO_ROOT / "schemas" / "sqlite-schema.sql"
MASTER_EXTRA_SCHEMA_PATH = REPO_ROOT / "schemas" / "master-extra-schema.sql"

VALID_ENTRY_TYPES = frozenset(
    {"pali_term", "pali_root", "topic", "story", "index_ref", "myanmar_term"}
)
VALID_QUALITIES = frozenset({"proofed", "ocr"})
HEX64_RE = re.compile(r"[0-9a-f]{64}")

REQUIRED_JSONL_FIELDS = (
    "source_id",
    "entry_type",
    "headword",
    "headword_norm",
    "quality",
    "license_id",
    "content_hash",
)
OPTIONAL_STR_FIELDS = (
    "headword_iast",
    "pos",
    "etymology",
    "root_pali",
    "definition_text",
    "english_gloss",
    "volume_code",
)
OPTIONAL_INT_FIELDS = ("homonym_no", "printed_page", "printed_page_end", "pdf_page")
ALLOWED_JSONL_FIELDS = frozenset(
    REQUIRED_JSONL_FIELDS
    + OPTIONAL_STR_FIELDS
    + OPTIONAL_INT_FIELDS
    + ("senses", "citations", "extra")
)
HASH_KEY_FIELDS = (
    "source_id",
    "headword",
    "homonym_no",
    "pos",
    "etymology",
    "definition_text",
    "volume_code",
    "printed_page",
)


def init_sqlite_db(
    db_path: Path | str, *, include_master_tables: bool = False
) -> sqlite3.Connection:
    """Create or open a dictionary SQLite database and apply the shared DDL."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SQLITE_SCHEMA_PATH.read_text(encoding="utf-8"))
    if include_master_tables:
        conn.executescript(MASTER_EXTRA_SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def compute_content_hash(
    entry: Mapping[str, Any],
    *,
    extra_parts: tuple[str | int | None, ...] = (),
) -> str:
    """Compute a deterministic SHA-256 over the canonical 8-field tuple plus optional extras."""
    canonical = [entry.get(key) for key in HASH_KEY_FIELDS]
    if extra_parts:
        canonical.extend(extra_parts)
    payload = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _check_optional_scalars(record: Mapping[str, Any]) -> None:
    for str_field in OPTIONAL_STR_FIELDS:
        val = record.get(str_field)
        if val is not None and not isinstance(val, str):
            raise ValueError(f"{str_field} must be a string or None")
    for int_field in OPTIONAL_INT_FIELDS:
        val = record.get(int_field)
        if val is not None and (isinstance(val, bool) or not isinstance(val, int) or val < 1):
            raise ValueError(f"{int_field} must be a positive integer or None")


def _check_optional_containers(record: Mapping[str, Any]) -> None:
    senses = record.get("senses")
    if senses is not None and (
        not isinstance(senses, list) or not all(isinstance(item, dict) for item in senses)
    ):
        raise ValueError("senses must be a list of objects or None")
    citations = record.get("citations")
    if citations is not None and (
        not isinstance(citations, list) or not all(isinstance(item, str) for item in citations)
    ):
        raise ValueError("citations must be a list of strings or None")
    if record.get("extra") is not None and not isinstance(record["extra"], dict):
        raise ValueError("extra must be a dict or None")


def validate_jsonl_record(record: Mapping[str, Any]) -> None:
    """Validate a dictionary JSONL record against `schemas/entry.schema.json` invariants."""
    unknown = set(record) - ALLOWED_JSONL_FIELDS
    if unknown:
        raise ValueError(f"Unknown JSONL fields: {sorted(unknown)}")
    for req in REQUIRED_JSONL_FIELDS:
        val = record.get(req)
        if not isinstance(val, str) or not val:
            raise ValueError(f"Missing or empty required string field: {req}")
    if record["entry_type"] not in VALID_ENTRY_TYPES:
        raise ValueError(f"Invalid entry_type: {record['entry_type']}")
    if record["quality"] not in VALID_QUALITIES:
        raise ValueError(f"Invalid quality: {record['quality']}")
    if not HEX64_RE.fullmatch(record["content_hash"]):
        raise ValueError(f"Invalid SHA-256 content_hash: {record['content_hash']}")
    _check_optional_scalars(record)
    _check_optional_containers(record)
