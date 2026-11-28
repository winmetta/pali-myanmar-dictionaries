"""Unit and corpus reproducibility tests for Stage 3 `my-android.db` lexicons."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pali_myanmar_dicts.stage3 import (
    STAGE3_SOURCES,
    build_stage3_source,
    is_visuddharama_untagged,
    make_stage3_record,
    parse_chok_segment,
    parse_visuddharama_segment,
)


class Stage3Tests(unittest.TestCase):
    def test_parse_chok_and_visuddharama_segments(self) -> None:
        chok = parse_chok_segment("(ပ) ၁-အဘို့၊ အပိုင်းအစု။")
        self.assertEqual(chok["pos"], "ပ")
        self.assertEqual(chok["definition_text"], "၁-အဘို့၊ အပိုင်းအစု။")

        vi_bracket = parse_visuddharama_segment("[ပု] (၁) ခွဲဝေခြင်း။")
        self.assertEqual(vi_bracket["pos"], "ပု")
        self.assertEqual(vi_bracket["definition_text"], "(၁) ခွဲဝေခြင်း။")

        vi_prefix = parse_visuddharama_segment("ပု၊ အနှိနော ခန္ဓော ဝိယ။ (၁) ခြေဖမျက်။")
        self.assertEqual(vi_prefix["pos"], "ပု")
        self.assertEqual(vi_prefix["definition_text"], "အနှိနော ခန္ဓော ဝိယ။ (၁) ခြေဖမျက်။")

    def test_untagged_visuddharama_rule_rejects_mya_and_sein_patterns(self) -> None:
        self.assertTrue(is_visuddharama_untagged("ထီ၊ အာ-ကင်္ခ+အ။ (၁) လိုချင်တောင့်တခြင်း။"))
        self.assertTrue(is_visuddharama_untagged("[ပု] (၁) ခွဲဝေခြင်း။"))
        self.assertFalse(is_visuddharama_untagged("။တိ။[န+ကတညူ] ကတံ န ဇာနာတီတိ။"))
        self.assertFalse(is_visuddharama_untagged("ထီ ။ [ အာရုပ္ပ+စုတိ ] အရူပါဝစရစုတိ။"))
        self.assertFalse(is_visuddharama_untagged("ဘူ၊ ဂတိယံ-လားခြင်း၌၊ ၏။"))
        self.assertFalse(is_visuddharama_untagged("(ပ) အနက်။ (m.) meaning."))

    def test_make_stage3_record_transliterates_and_flags_inferred_untagged(self) -> None:
        record = make_stage3_record(
            STAGE3_SOURCES[1],
            "අංස",
            "[ပု] (၁) ခွဲဝေခြင်း။",
            inferred_untagged=True,
        )
        self.assertEqual(record["source_id"], "visuddharama-abhidhana")
        self.assertEqual(record["headword"], "အံသ")
        self.assertEqual(record["pos"], "ပု")
        self.assertEqual(record["quality"], "proofed")
        self.assertTrue(record["extra"]["inferred_untagged"])
        self.assertEqual(record["extra"]["source_headword_sinhala"], "අංස")

    def test_build_stage3_source_deduplicates_and_excludes_other_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / "my-android.db"
            with closing(sqlite3.connect(db)) as conn:
                conn.execute("CREATE TABLE dictionary (word TEXT, meaning TEXT)")
                conn.execute(
                    "INSERT INTO dictionary VALUES (?, ?)",
                    (
                        "අ",
                        "(ဗျ) မ- မဟုတ်။♦ချုပ်+[ပု] (၁) ဗိသဏိုး။♦ဝိ+။တိ။[န+ကတညူ] မြန်မာ။♦မြ+(ပ) စိန်။♦စိန်",
                    ),
                )
                conn.commit()
            seen, written = build_stage3_source(db, root, STAGE3_SOURCES[0])
            self.assertEqual((seen, written), (1, 1))
            record = json.loads((root / "pali-abhidhana-chok.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(record["headword"], "အ")
            self.assertEqual(record["definition_text"], "မ- မဟုတ်။")

    @unittest.skipUnless(
        (
            Path(__file__).resolve().parents[1]
            / ".cache/pali-dictionary/tipitaka-app/my-android.db"
        ).is_file(),
        "Stage 3 my-android.db cache not present",
    )
    def test_full_stage3_builds_and_exports_are_reproducible(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            for output in (first, second):
                subprocess.run(
                    [sys.executable, "scripts/build-stage3.py", "--output-dir", str(output)],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate-stage3.py",
                    str(first),
                    "--compare-dir",
                    str(second),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn(
                "pali-abhidhana-chok: 13740 entries, 13695 headwords, "
                "1 incomplete, 0 inferred_untagged",
                result.stdout,
            )
            self.assertIn(
                "visuddharama-abhidhana: 9287 entries, 9189 headwords, "
                "24 incomplete, 6151 inferred_untagged",
                result.stdout,
            )
