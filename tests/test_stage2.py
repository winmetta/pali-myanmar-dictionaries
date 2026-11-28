"""Small end-to-end checks for the Stage 2 work in progress."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pali_myanmar_dicts.stage2 import Source, build_source


class Stage2Tests(unittest.TestCase):
    def test_restoration_requires_matching_book_headword_analysis_and_text(self) -> None:
        from pali_myanmar_dicts.source_restorations import RESTORATIONS, restore_definition

        (word, etymology, original), (restored, _) = next(iter(RESTORATIONS.items()))
        parsed = {"etymology": etymology, "definition_text": original}
        evidence = restore_definition(3, word, parsed)
        self.assertIsNotNone(evidence)
        self.assertEqual(parsed["definition_text"], restored)
        for book, altered_word, altered_etymology, altered_text in (
            (2, word, etymology, original),
            (3, "အခြား", etymology, original),
            (3, word, "အခြား", original),
            (3, word, etymology, original + " "),
        ):
            parsed = {"etymology": altered_etymology, "definition_text": altered_text}
            self.assertIsNone(restore_definition(book, altered_word, parsed))
            self.assertEqual(parsed["definition_text"], altered_text)

    @unittest.skipUnless(
        (
            Path(__file__).resolve().parents[1]
            / ".cache/pali-dictionary/tipitaka-app/my-android.db"
        ).is_file(),
        "Alternative digitization not present",
    )
    def test_restoration_evidence_matches_alternative_source(self) -> None:
        from pali_myanmar_dicts.normalize import normalize_myanmar_text
        from pali_myanmar_dicts.parsers import split_my_android_segments
        from pali_myanmar_dicts.source_restorations import ADDITIONAL_RESTORATIONS, RESTORATIONS

        database = (
            Path(__file__).resolve().parents[1]
            / ".cache/pali-dictionary/tipitaka-app/my-android.db"
        )
        with closing(sqlite3.connect(database)) as conn:
            word, meaning = conn.execute(
                "SELECT word, meaning FROM dictionary WHERE rowid = 18587"
            ).fetchone()
        self.assertEqual(word, "ඉණ")
        segments = {
            normalize_myanmar_text(segment.body, single_line=True)
            for segment in split_my_android_segments(meaning)
            if segment.tag == "မြ"
        }
        for _, evidence in RESTORATIONS.values():
            self.assertIn(normalize_myanmar_text(evidence, single_line=True), segments)
        with closing(sqlite3.connect(database)) as conn:
            for _, evidence, rowid, sinhala in ADDITIONAL_RESTORATIONS.values():
                actual_word, meaning = conn.execute(
                    "SELECT word, meaning FROM dictionary WHERE rowid = ?", (rowid,)
                ).fetchone()
                self.assertEqual(actual_word, sinhala)
                segments = {
                    normalize_myanmar_text(segment.body, single_line=True)
                    for segment in split_my_android_segments(meaning)
                    if segment.tag == "မြ"
                }
                self.assertIn(normalize_myanmar_text(evidence, single_line=True), segments)

    def test_pm3_overlap_audit_distinguishes_source_readings(self) -> None:
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "input.db"
            with closing(sqlite3.connect(database)) as conn:
                conn.execute("CREATE TABLE entries (headword TEXT, extra_json TEXT)")
                rows = [("a-b", "a-b"), ("ab", "a-b"), ("a-b", "ab-")]
                conn.executemany(
                    "INSERT INTO entries VALUES (?, ?)",
                    [(head, json.dumps({"compound_hyphenated": pm3})) for head, pm3 in rows],
                )
                conn.commit()
            root = Path(__file__).resolve().parents[1]
            result = subprocess.run(
                [sys.executable, "scripts/audit-pm3-overlap.py", str(database)],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                json.loads(result.stdout),
                {"identical": 1, "different_hyphenation": 1, "primary_without_hyphen": 1},
            )

    def test_incomplete_source_fragment_is_visible_and_recorded(self) -> None:
        from pali_myanmar_dicts.stage2 import SOURCES, make_record

        html = '<p class="word">အက္ခ</p><p class="root">[√အက္ခ+အစ်]</p><p>ဝင်ရိုး၊ ေ</p>'
        record = make_record(SOURCES[1], "အက္ခ", html)
        self.assertEqual(record["quality"], "incomplete")
        self.assertEqual(record["definition_text"], "ဝင်ရိုး၊ �")
        self.assertEqual(
            record["extra"]["incomplete_source_fragments"],
            [
                {
                    "field": "definition_text",
                    "original_codepoints": " ".join(f"U+{ord(c):04X}" for c in "ဝင်ရိုး၊ ေ"),
                    "replacement_count": 1,
                }
            ],
        )

    def test_header_repair_requires_exact_lookup_word(self) -> None:
        from pali_myanmar_dicts.mixed_encoding import repair_header_kinzi

        self.assertEqual(repair_header_kinzi("ကဂုၤ", "ကင်္ဂု"), ("ကင်္ဂု", True))
        self.assertEqual(repair_header_kinzi("ကဂုၤ", "အခြား"), ("ကဂုၤ", False))

    def test_verified_kinzi_tokens_keep_repair_provenance(self) -> None:
        from pali_myanmar_dicts.stage2 import SOURCES, make_record

        html = '<p class="word">စတုရင်္ဂုလ</p><p>(စတုရ်+အဂုၤလ)</p><p>လက်လေးသစ်။</p>'
        record = make_record(SOURCES[0], "စတုရင်္ဂုလ", html)
        self.assertEqual(record["etymology"], "စတုရ်+အင်္ဂုလ")
        repair = record["extra"]["verified_token_repairs"][0]
        self.assertIn("U+1064", repair["original_codepoints"])
        self.assertEqual(repair["replacement"], "အင်္ဂုလ")

    def test_context_verified_terms_repair_without_general_replacement(self) -> None:
        from pali_myanmar_dicts.mixed_encoding import repair_verified_tokens

        for original, expected in (
            ("သချုႋင်း", "သင်္ချိုင်း"),
            ("သချုႋင်းကို", "သင်္ချိုင်းကို"),
            ("သဂြုႋဟ်", "သင်္ဂြိုဟ်"),
            ("မီးရှို့သဂြုႋဟ်ရာမီး", "မီးရှို့သင်္ဂြိုဟ်ရာမီး"),
            ("အဂုၤတ္တိုရ်နိကာယ်ဟူသော", "အင်္ဂုတ္တိုရ်နိကာယ်ဟူသော"),
            ("သင်္ခေၤပ", "သင်္ခေပ"),
            ("အနီၤယ", "အနီယ"),
            ("စတုရဂုၤလံ", "စတုရင်္ဂုလံ"),
            ("သကုၤလမည်သော", "သင်္ကုလမည်သော"),
            ("သခုၤဘိတံ", "သင်္ခုဘိတံ"),
            ("အဂုၤလိပေါထ", "အင်္ဂုလိပေါထ"),
            ("လဃႋမာ", "လင်္ဃိမာ"),
            ("ဂွေ့သဘောၤဖြင့်", "ဂွေ့သင်္ဘောဖြင့်"),
            ("ဂင်္ဂၤါအကြေသို့", "ဂင်္ဂါအကြေသို့"),
            ("ခြသေ့ၤ", "ခြင်္သေ့"),
            ("√ဥႌဟ်", "√ဦဟ်"),
            ("ေဩာ်", "ဪ"),
            ("ေ၀၀စန", "ဝေဝစန"),
            ("ေ၀၀စနေ", "ဝေဝစနေ"),
            ("ဟိဂုႍ", "ဟိင်္ဂုံ"),
            ("အဂုၤလိဖောတနဉ္စ", "အင်္ဂုလိဖောတနဉ္စ"),
        ):
            repaired, details = repair_verified_tokens(original)
            self.assertEqual(repaired, expected)
            self.assertEqual(details[0]["rule"], "kinzi_verified_against_corpus_definition")
        self.assertEqual(repair_verified_tokens("မသိၤ"), ("မသိၤ", []))

    def test_pm3_match_requires_both_keys_and_one_candidate(self) -> None:
        from pali_myanmar_dicts.pm3 import matching_compound

        index = {("cakāra", "စကာရ"): {"စ-ကာရ"}}
        self.assertEqual(matching_compound("စကာရ", index), "စ-ကာရ")
        self.assertIsNone(matching_compound("စကာရ", {("cakāra", "စကာရ"): {"စ-ကာရ", "စကာ-ရ"}}))
        self.assertIsNone(matching_compound("စကာရ", {("other", "စကာရ"): {"စ-ကာရ"}}))

    def test_pm3_is_parsed_without_executing_it_and_attached_with_source(self) -> None:
        from unittest.mock import patch

        from pali_myanmar_dicts.pm3 import PM3_URL, build_pm3_index
        from pali_myanmar_dicts.stage2 import SOURCES, make_record

        with tempfile.TemporaryDirectory() as directory:
            pm3 = Path(directory) / "pm3.js"
            pm3.write_text("var pm3 = {\n'cakāra':'စ-ကာရ'};\n", encoding="utf-8")
            with patch("pali_myanmar_dicts.pm3.zawgyi_to_unicode_batch", return_value=["စ-ကာရ"]):
                index = build_pm3_index(pm3)
            record = make_record(
                SOURCES[0], "စကာရ", '<p class="word">စကာရ</p><p>အနက်။</p>', pm3_index=index
            )
            self.assertEqual(record["extra"]["compound_hyphenated"], "စ-ကာရ")
            self.assertEqual(record["extra"]["compound_hyphenated_source"], PM3_URL)
            self.assertEqual(record["extra"]["compound_hyphenated_license"], "unverified")

    def test_invalid_input_is_reported_before_output_creation(self) -> None:
        from pali_myanmar_dicts.stage2 import audit_source

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_db = root / "input.db"
            with closing(sqlite3.connect(source_db)) as conn:
                conn.execute("CREATE TABLE dictionary (word TEXT, definition TEXT, book INTEGER)")
                conn.execute(
                    "INSERT INTO dictionary VALUES (?,?,?)",
                    ("ေ", '<p class="word">ေ</p><p>အနက်။</p>', 2),
                )
                conn.commit()
            source = Source("test-source", "Test", "Test", "lexicon", 2, 1)
            self.assertEqual(len(audit_source(source_db, source)), 1)
            with self.assertRaisesRegex(ValueError, "rows failed validation"):
                build_source(source_db, root, source)
            self.assertFalse((root / "test-source.db").exists())

    def test_distinct_english_glosses_produce_distinct_hashes(self) -> None:
        from pali_myanmar_dicts.stage2 import SOURCES, make_record

        first = make_record(SOURCES[0], "စာလယမာန", '<p class="word">စာလယမာန</p><p>shaking.</p>')
        second = make_record(SOURCES[0], "စာလယမာန", '<p class="word">စာလယမာန</p><p>moving.</p>')
        self.assertNotEqual(first["content_hash"], second["content_hash"])

    def test_distinct_records_with_different_extra_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_db = root / "input.db"
            with closing(sqlite3.connect(source_db)) as conn:
                conn.execute("CREATE TABLE dictionary (word TEXT, definition TEXT, book INTEGER)")
                for see in ("က", "ခ"):
                    html = f'<p class="word">ယုဝတီ</p><p>လုံမပျို။</p><see>{see}</see>'
                    conn.execute("INSERT INTO dictionary VALUES (?,?,?)", ("ယုဝတီ", html, 2))
                conn.commit()
            source = Source("test-source", "Test", "Test", "lexicon", 2, 2)
            self.assertEqual(build_source(source_db, root, source), (2, 2))
            with closing(sqlite3.connect(root / "test-source.db")) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM entries").fetchone()[0], 2)

    def test_build_preserves_source_and_deduplicates_identical_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_db = root / "input.db"
            with closing(sqlite3.connect(source_db)) as conn:
                conn.execute("CREATE TABLE dictionary (word TEXT, definition TEXT, book INTEGER)")
                row = ("ယုဝတီ", '<p class="word">ယုဝတီ</p><p>လုံမပျို။</p>', 2)
                conn.executemany("INSERT INTO dictionary VALUES (?,?,?)", [row, row])
                conn.commit()
            source = Source("test-source", "Test", "Test", "lexicon", 2, 2)
            self.assertEqual(build_source(source_db, root, source), (2, 1))
            record = json.loads((root / "test-source.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(record["source_id"], "test-source")
            self.assertEqual(record["definition_text"], "လုံမပျို။")
            with closing(sqlite3.connect(root / "test-source.db")) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM entries").fetchone()[0], 1)
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            with self.assertRaises(FileExistsError):
                build_source(source_db, root, source)

    @unittest.skipUnless(
        (
            Path(__file__).resolve().parents[1] / ".cache/pali-dictionary/pndaza/tipitaka_pali.db"
        ).is_file(),
        "Upstream dictionary cache not present",
    )
    def test_full_pali_dhatu_build_is_reproducible(self) -> None:
        import hashlib

        from pali_myanmar_dicts.stage2 import SOURCES
        from pali_myanmar_dicts.zawgyi import assert_zero_zawgyi

        database = (
            Path(__file__).resolve().parents[1] / ".cache/pali-dictionary/pndaza/tipitaka_pali.db"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("first", "second"):
                output = root / name
                output.mkdir()
                self.assertEqual(build_source(database, output, SOURCES[2]), (1894, 1894))
            for suffix in ("db", "jsonl"):
                name = f"pali-dhatu-abhidhana.{suffix}"
                self.assertEqual(
                    hashlib.sha256((root / "first" / name).read_bytes()).digest(),
                    hashlib.sha256((root / "second" / name).read_bytes()).digest(),
                )
            db = root / "first/pali-dhatu-abhidhana.db"
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(
                    conn.execute("SELECT count(DISTINCT headword) FROM entries").fetchone()[0], 1882
                )
                for headword, definition in conn.execute(
                    "SELECT headword,definition_text FROM entries"
                ):
                    assert_zero_zawgyi(headword)
                    assert_zero_zawgyi(definition)
                    self.assertNotIn("<", definition)

    @unittest.skipUnless(
        (
            Path(__file__).resolve().parents[1] / ".cache/pali-dictionary/pndaza/tipitaka_pali.db"
        ).is_file()
        and (
            Path(__file__).resolve().parents[1] / ".cache/pali-dictionary/tipitaka-pali-projector/"
            "pm3_Pali_Myanmar_Dictionary_@U_Hau_Sein_2018.js"
        ).is_file(),
        "Full Stage 2 cache not present",
    )
    def test_full_stage2_builds_and_exports_are_reproducible(self) -> None:
        import subprocess
        import sys

        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            for output in (first, second):
                subprocess.run(
                    [sys.executable, "scripts/build-stage2.py", "--output-dir", str(output)],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/validate-stage2.py",
                    str(first),
                    "--compare-dir",
                    str(second),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("60775 entries", result.stdout)
            self.assertIn("11073 entries", result.stdout)
            self.assertIn("1894 entries", result.stdout)
            self.assertIn(
                "u-hoke-sein: 60775 entries, 58195 headwords, 3 incomplete, 0 PM3-enriched",
                result.stdout,
            )
            self.assertIn(
                "dhatuattha-pankone: 11073 entries, 9543 headwords, 3 incomplete, 0 PM3-enriched",
                result.stdout,
            )
