"""Stage 0 tests for SQLite schemas, JSONL record validation, and cache verification."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pali_myanmar_dicts.cache_verify import DEFAULT_MANIFEST_PATH, verify_cache
from pali_myanmar_dicts.schema import (
    REPO_ROOT,
    compute_content_hash,
    init_sqlite_db,
    validate_jsonl_record,
)


class Stage0SchemaTests(unittest.TestCase):
    def test_sqlite_schema_and_fts_triggers(self) -> None:
        conn = init_sqlite_db(":memory:", include_master_tables=True)
        conn.execute(
            """
            INSERT INTO sources (
              source_id, title_my, entry_kind, volume_count,
              license_id, license_note, upstream_url, priority_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "u-hoke-sein",
                "ပဒတ္ထမဉ္ဇူသာ ပါဠိ-မြန်မာ အဘိဓာန်",
                "lexicon",
                1,
                "winmetta-pd-decision",
                "Win Metta public-domain decision (2026-11-26)",
                "https://github.com/pndaza/Tipitaka_Pali_Android",
                2,
            ),
        )
        conn.execute(
            "INSERT INTO source_volumes (source_id, volume_code, volume_number) VALUES (?, ?, ?)",
            ("u-hoke-sein", "01", 1),
        )
        chash = compute_content_hash("u-hoke-sein", "စက္က", "ဘီး။ လှည်းဘီး။", extra_parts=("န",))
        conn.execute(
            """
            INSERT INTO entries (
              source_id, entry_type, headword, headword_norm, headword_iast,
              pos, definition_text, volume_code, quality, license_id, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "u-hoke-sein",
                "pali_term",
                "စက္က",
                "စကက",
                "cakka",
                "န",
                "ဘီး။ လှည်းဘီး။",
                "01",
                "proofed",
                "winmetta-pd-decision",
                chash,
            ),
        )

        # Duplicate within same source_id must be rejected by UNIQUE(source_id, content_hash)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO entries (
                  source_id, entry_type, headword, headword_norm,
                  definition_text, quality, license_id, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "u-hoke-sein",
                    "pali_term",
                    "စက္က",
                    "စကက",
                    "ဘီး။ လှည်းဘီး။",
                    "proofed",
                    "winmetta-pd-decision",
                    chash,
                ),
            )

        # FTS5 insert, update, and delete triggers keep entries_fts synchronized
        fts_hits = conn.execute(
            "SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'cakka'"
        ).fetchall()
        self.assertEqual(len(fts_hits), 1)

        conn.execute("UPDATE entries SET definition_text = ? WHERE id = 1", ("ရထားဘီး။",))
        updated_hits = conn.execute(
            "SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'ရထားဘီး'"
        ).fetchall()
        self.assertEqual(len(updated_hits), 1)

        conn.execute("DELETE FROM entries WHERE id = 1")
        after_del = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
        self.assertEqual(after_del, 0)
        conn.close()

    def test_validate_jsonl_record(self) -> None:
        chash = compute_content_hash("pali-dhatu-abhidhana", "စက", "ရောင့်ရဲခြင်း")
        valid = {
            "source_id": "pali-dhatu-abhidhana",
            "entry_type": "pali_root",
            "headword": "စက",
            "headword_norm": "စက",
            "headword_iast": "caka",
            "definition_text": "ရောင့်ရဲခြင်း",
            "citations": ["ဝါစပ္ပတိ"],
            "extra": {"gana_classes": ["ဘူ"]},
            "quality": "proofed",
            "license_id": "winmetta-pd-decision",
            "content_hash": chash,
        }
        validate_jsonl_record(valid)

        with self.assertRaises(ValueError):
            validate_jsonl_record({**valid, "unknown_col": 1})
        with self.assertRaises(ValueError):
            validate_jsonl_record({**valid, "entry_type": "bad_kind"})
        with self.assertRaises(ValueError):
            validate_jsonl_record({**valid, "printed_page": 0})
        with self.assertRaises(ValueError):
            validate_jsonl_record({**valid, "content_hash": "not-a-sha256"})

    def test_entry_json_schema_matches_validator(self) -> None:
        schema_file = REPO_ROOT / "schemas" / "entry.schema.json"
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        self.assertEqual(schema["type"], "object")
        self.assertIn("headword", schema["required"])


class Stage0CacheVerifyTests(unittest.TestCase):
    def test_manifest_is_valid_json(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest["files"]), 50)
        for item in manifest["files"]:
            self.assertEqual(len(item["sha256"]), 64)
            self.assertGreater(item["size"], 0)

    def test_verify_cache_detects_ok_missing_size_and_hash_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            cache_dir.mkdir()
            payload = b"sample dictionary bytes"
            sample_file = cache_dir / "sub" / "sample.db"
            sample_file.parent.mkdir(parents=True)
            sample_file.write_bytes(payload)

            manifest_path = root / "manifest.json"
            manifest_data = {
                "version": 1,
                "files": [
                    {
                        "path": "sub/sample.db",
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "license_id": "CC0-1.0",
                    }
                ],
            }
            manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

            ok_res = verify_cache(cache_dir, manifest_path)
            self.assertTrue(ok_res.ok)

            # Corrupt 1 byte with identical length -> SHA-256 mismatch
            sample_file.write_bytes(b"Xample dictionary bytes")
            self.assertTrue(verify_cache(cache_dir, manifest_path, quick=True).ok)
            bad_sha = verify_cache(cache_dir, manifest_path, quick=False)
            self.assertFalse(bad_sha.ok)
            self.assertTrue(bad_sha.errors[0].startswith("SHA256 MISMATCH:"))

            # Truncate -> size mismatch
            sample_file.write_bytes(b"short")
            bad_size = verify_cache(cache_dir, manifest_path)
            self.assertFalse(bad_size.ok)
            self.assertTrue(bad_size.errors[0].startswith("SIZE MISMATCH:"))

            # Delete -> missing
            sample_file.unlink()
            missing = verify_cache(cache_dir, manifest_path)
            self.assertFalse(missing.ok)
            self.assertTrue(missing.errors[0].startswith("MISSING:"))


if __name__ == "__main__":
    unittest.main()
