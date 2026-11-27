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
    ALLOWED_JSONL_FIELDS,
    REPO_ROOT,
    compute_content_hash,
    init_sqlite_db,
    validate_jsonl_record,
)


class Stage0SchemaTests(unittest.TestCase):
    def test_sqlite_schema_fts_myanmar_categories_and_triggers(self) -> None:
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

        rec_metta = {
            "source_id": "u-hoke-sein",
            "headword": "မေတ္တာ",
            "pos": "ထီ",
            "definition_text": "ဘီး။ လှည်းဘီး။",
            "volume_code": "01",
        }
        chash_metta = compute_content_hash(rec_metta)
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
                "မေတ္တာ",
                "မေတတာ",
                "mettā",
                "ထီ",
                "ဘီး။ လှည်းဘီး။",
                "01",
                "proofed",
                "winmetta-pd-decision",
                chash_metta,
            ),
        )

        rec_mitta = {
            "source_id": "u-hoke-sein",
            "headword": "မိတ္တ",
            "pos": "ပု",
            "definition_text": "အဆွေခင်ပွန်း။",
            "volume_code": "01",
        }
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
                "မိတ္တ",
                "မိတတ",
                "mitta",
                "ပု",
                "အဆွေခင်ပွန်း။",
                "01",
                "proofed",
                "winmetta-pd-decision",
                compute_content_hash(rec_mitta),
            ),
        )

        # Combining marks M* are kept inside Myanmar tokens: မေတ္တာ must not match မိတ္တ
        metta_hits = conn.execute(
            "SELECT headword FROM entries WHERE id IN "
            "(SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'မေတ္တာ')"
        ).fetchall()
        self.assertEqual(metta_hits, [("မေတ္တာ",)])

        # Duplicate within same source_id rejected by UNIQUE(source_id, content_hash)
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
                    "မေတ္တာ",
                    "မေတတာ",
                    "ဘီး။ လှည်းဘီး။",
                    "proofed",
                    "winmetta-pd-decision",
                    chash_metta,
                ),
            )

        # FTS5 update and delete triggers keep entries_fts synchronized
        conn.execute("UPDATE entries SET definition_text = ? WHERE id = 1", ("ရထားဘီး။",))
        updated_hits = conn.execute(
            "SELECT rowid FROM entries_fts WHERE entries_fts MATCH 'ရထားဘီး'"
        ).fetchall()
        self.assertEqual(len(updated_hits), 1)

        conn.execute("DELETE FROM entries")
        after_del = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
        self.assertEqual(after_del, 0)
        conn.close()

    def test_pali_lemmatizer_unique_coalesces_nulls(self) -> None:
        conn = init_sqlite_db(":memory:", include_master_tables=True)
        sql = (
            "INSERT INTO pali_lemmatizer "
            "(inflected_my, inflected_norm, lemma_my, breakup_my, source_tag) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        conn.execute(sql, ("ဓမ္မဿ", "ဓမမဿ", "ဓမ္မ", None, "dpr_stem"))
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(sql, ("ဓမ္မဿ", "ဓမမဿ", "ဓမ္မ", None, "dpr_stem"))
        conn.close()

    def test_compute_content_hash_uses_canonical_8_tuple(self) -> None:
        rec_p1 = {
            "source_id": "pitaka-lamnyun",
            "headword": "ကကစူပမသုတ်",
            "volume_code": "1",
            "printed_page": 300,
        }
        rec_p2 = {
            "source_id": "pitaka-lamnyun",
            "headword": "ကကစူပမသုတ်",
            "volume_code": "3",
            "printed_page": 485,
        }
        self.assertNotEqual(compute_content_hash(rec_p1), compute_content_hash(rec_p2))

    def test_validate_jsonl_record(self) -> None:
        base = {
            "source_id": "pali-dhatu-abhidhana",
            "entry_type": "pali_root",
            "headword": "စက",
            "headword_norm": "စက",
            "headword_iast": "caka",
            "definition_text": "ရောင့်ရဲခြင်း",
            "senses": [{"num": "၁", "text": "ရောင့်ရဲခြင်း"}],
            "citations": ["ဝါစပ္ပတိ"],
            "extra": {"gana_classes": ["ဘူ"]},
            "quality": "proofed",
            "license_id": "winmetta-pd-decision",
        }
        valid = {**base, "content_hash": compute_content_hash(base)}
        validate_jsonl_record(valid)

        invalid_cases = [
            {**valid, "unknown_col": 1},
            {**valid, "entry_type": "bad_kind"},
            {**valid, "printed_page": 0},
            {**valid, "volume_code": 1},
            {**valid, "senses": ["not-an-object"]},
            {**valid, "citations": [123]},
            {**valid, "content_hash": ("a" * 64) + "\n"},
        ]
        for bad in invalid_cases:
            with self.assertRaises(ValueError):
                validate_jsonl_record(bad)

    def test_entry_json_schema_matches_validator(self) -> None:
        schema_file = REPO_ROOT / "schemas" / "entry.schema.json"
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
        self.assertEqual(schema["type"], "object")
        self.assertEqual(set(schema["properties"]), ALLOWED_JSONL_FIELDS)


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

            self.assertTrue(verify_cache(cache_dir, manifest_path).ok)

            sample_file.write_bytes(b"Xample dictionary bytes")
            self.assertTrue(verify_cache(cache_dir, manifest_path, quick=True).ok)
            bad_sha = verify_cache(cache_dir, manifest_path, quick=False)
            self.assertFalse(bad_sha.ok)
            self.assertTrue(bad_sha.errors[0].startswith("SHA256 MISMATCH:"))

            sample_file.write_bytes(b"short")
            bad_size = verify_cache(cache_dir, manifest_path)
            self.assertFalse(bad_size.ok)
            self.assertTrue(bad_size.errors[0].startswith("SIZE MISMATCH:"))

            sample_file.unlink()
            missing = verify_cache(cache_dir, manifest_path)
            self.assertFalse(missing.ok)
            self.assertTrue(missing.errors[0].startswith("MISSING:"))


if __name__ == "__main__":
    unittest.main()
