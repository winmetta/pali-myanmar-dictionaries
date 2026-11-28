"""Unit and integration tests for Stage 5 reference and reverse dictionaries."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from pali_myanmar_dicts.stage5 import STAGE5_BY_ID, build_stage5_source


class Stage5Tests(unittest.TestCase):
    def test_tupya_and_sarupa_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            with closing(sqlite3.connect(cache / "tupya.db")) as conn:
                conn.execute("CREATE TABLE topic (id INTEGER, name TEXT, detail TEXT)")
                conn.execute("INSERT INTO topic VALUES (1, 'ကံ ၃-ပါး ', 'ကာယကံ\\nဝစီကံ')")
                conn.commit()
            with closing(sqlite3.connect(cache / "sarupa.db")) as conn:
                conn.execute(
                    "CREATE TABLE topic (id INTEGER, name TEXT, detail TEXT, reference TEXT)"
                )
                conn.execute(
                    "INSERT INTO topic VALUES (1, 'ဓမ္မာဘိသမယ', '၁။ ...\\n၂။ ...', '(အပ၊၂။၃၇၁။)')"
                )
                conn.commit()

            out = root / "out"
            out.mkdir()
            self.assertEqual(
                build_stage5_source(cache, out, STAGE5_BY_ID["sutethana-thayokpya"]), (1, 1)
            )
            self.assertEqual(
                build_stage5_source(cache, out, STAGE5_BY_ID["pitaka-thayokson"]), (1, 1)
            )
            sarupa_rec = json.loads((out / "pitaka-thayokson.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(sarupa_rec["citations"], ["အပ၊၂။၃၇၁။"])
            self.assertIn("\n", sarupa_rec["definition_text"])

    def test_vatthu_and_pitakaguide_builds_with_mocked_zawgyi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            with closing(sqlite3.connect(cache / "vatthuguide.db")) as conn:
                conn.execute(
                    "CREATE TABLE vatthuguide "
                    "(_id INTEGER, item TEXT, item_uni TEXT, content TEXT, bref TEXT)"
                )
                conn.execute(
                    "INSERT INTO vatthuguide VALUES (1, 'z', 'အကတညုဇာတက', 'zawgyi', '(ဇာ)')"
                )
                conn.commit()
            with closing(sqlite3.connect(cache / "pitakaguide.db")) as conn:
                conn.execute("CREATE TABLE tags (_id INTEGER, name TEXT)")
                conn.execute("CREATE TABLE index_tag (index_id INTEGER, tag_id INTEGER)")
                conn.execute(
                    "CREATE TABLE indexes "
                    "(_id INTEGER, name TEXT, name_uni TEXT, volume INTEGER, page INTEGER)"
                )
                conn.execute("INSERT INTO tags VALUES (1, 'ztag')")
                conn.execute("INSERT INTO index_tag VALUES (1, 1)")
                conn.execute("INSERT INTO indexes VALUES (1, 'z', 'ကကစူပမသုတ်', 1, 320)")
                conn.commit()

            out = root / "out"
            out.mkdir()
            with patch(
                "pali_myanmar_dicts.stage5.zawgyi_to_unicode_batch",
                side_effect=[["အနက်။"], ["ဇာ၊၁"], ["သုတ္တန်"]],
            ):
                self.assertEqual(
                    build_stage5_source(cache, out, STAGE5_BY_ID["pitaka-vatthu-lamnyun"]), (1, 1)
                )
                self.assertEqual(
                    build_stage5_source(cache, out, STAGE5_BY_ID["pitaka-lamnyun"]), (1, 1)
                )

            idx_rec = json.loads((out / "pitaka-lamnyun.jsonl").read_text(encoding="utf-8"))
            self.assertIsNone(idx_rec["definition_text"])
            self.assertEqual(idx_rec["volume_code"], "01")
            self.assertEqual(idx_rec["printed_page"], 320)
            self.assertEqual(idx_rec["extra"]["tags"], ["သုတ္တန်"])

    def test_mep_reconciles_book8_and_skips_placeholder_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "cache"
            cache.mkdir()
            with closing(sqlite3.connect(cache / "mep.db")) as conn:
                conn.execute(
                    "CREATE TABLE definition "
                    "(id INTEGER, my TEXT, eng TEXT, pli TEXT, page_number INTEGER)"
                )
                conn.executemany(
                    "INSERT INTO definition VALUES (?,?,?,?,?)",
                    [
                        (1, "က (၁)", "a saddle frame", "ပလျာဏ", 1),
                        (2, "ခ", "zero page", "ခ", 0),
                        (3, "-", "-", "-", 1),
                    ],
                )
                conn.commit()
            with closing(sqlite3.connect(cache / "tipitaka_pali.db")) as conn:
                conn.execute("CREATE TABLE dictionary (word TEXT, definition TEXT, book INTEGER)")
                conn.executemany(
                    "INSERT INTO dictionary VALUES (?,?,?)",
                    [
                        ("က", "<p>a saddle frame</p><p>ပလျာဏ</p>", 8),
                        ("ဂ", "<p>extra</p><p>ဂ</p>", 8),
                        ("-", "<p>-</p><p>-</p>", 8),
                    ],
                )
                conn.commit()

            out = root / "out"
            out.mkdir()
            seen, written = build_stage5_source(cache, out, STAGE5_BY_ID["u-hoke-sein-mep"])
            self.assertEqual((seen, written), (3, 3))
            rows = [
                json.loads(line)
                for line in (out / "u-hoke-sein-mep.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            by_hw = {r["headword"]: r for r in rows}
            self.assertEqual(by_hw["က"]["homonym_no"], 1)
            self.assertIsNone(by_hw["ခ"]["printed_page"])
            self.assertEqual(by_hw["ဂ"]["extra"]["supplemental_source"], "tipitaka_pali.db:book=8")
