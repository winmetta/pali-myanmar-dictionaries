"""Unit and integration tests for Stage 4 29-book `tipitaka-abhidhana` ETL."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from pali_myanmar_dicts.stage4 import (
    OCR_LICENSE,
    PD_LICENSE,
    build_stage4,
    make_ocr_record,
    make_proofed_record,
    resolve_volume_code,
)


def _create_abidan_db(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE books (id TEXT, name TEXT, name_info TEXT, start_page INTEGER)")
        conn.execute("CREATE TABLE words (word TEXT, book_id TEXT, page_number INTEGER)")
        books = [
            ("01", "အတွဲ ၁", "အ - အနီဠက", 120),
            ("4a", "အတွဲ ၄-အပိုင်း ၁", "အာ - ဥတြာသေယျုံ", 42),
            ("4b", "အတွဲ ၄-အပိုင်း ၂", "ဥဒ - ဥဠုရာဇ", 16),
            ("4c", "အတွဲ ၄-အပိုင်း ၃", "ဦ - ဩဠုမ္ပိက", 27),
            ("14", "အတွဲ ၁၄-အပိုင်း ၁", "ပဋိဘံသု - ပမဇ္ဇေယျ", 21),
            ("14b", "အတွဲ ၁၄-အပိုင်း ၂", "ပမတ္တ - ပလ္လောမ", 24),
            ("14c", "အတွဲ ၁၄-အပိုင်း ၃", "ပဝ - ပ္လုတ", 27),
        ]
        # Pad remaining books to 29 for schema/volume_count completeness
        for i in range(2, 26):
            if i in (4, 14):
                continue
            books.append((f"{i:02d}", f"အတွဲ {i}", "က - ခ", 10))
        conn.executemany("INSERT INTO books VALUES (?,?,?,?)", books)
        conn.execute("INSERT INTO words VALUES (?, ?, ?)", ("ကက", "4c", 5))
        conn.commit()


class Stage4Tests(unittest.TestCase):
    def test_resolve_volume_code_handles_parts_and_fallbacks(self) -> None:
        idx = {"ကက": [("4c", 5)]}
        self.assertEqual(resolve_volume_code("၄က", None, [], "အ", idx), ("4a", None))
        self.assertEqual(resolve_volume_code("၄ခ", None, [], "အ", idx), ("4b", None))
        self.assertEqual(resolve_volume_code("၄", "၃", [], "အ", idx), ("4c", None))
        self.assertEqual(resolve_volume_code("၁၄", None, [], "ပ", idx), ("14", None))
        self.assertEqual(resolve_volume_code("၁၄", "၂", [], "ပ", idx), ("14b", None))
        self.assertEqual(resolve_volume_code(None, None, ["၁၊၁၃+၁၄"], "အ", idx), ("01", 13))
        self.assertEqual(resolve_volume_code(None, None, [], "ကက", idx), ("4c", 5))

    def test_make_proofed_and_ocr_records(self) -> None:
        from pali_myanmar_dicts.stage4 import VolumeInfo

        vols = {"01": VolumeInfo("01", 1, None, "အတွဲ ၁", "အ - အနီဠက", 120)}
        stub = make_proofed_record(
            "က",
            "<p>မူရင်းတိပိဋကပါဠိ-မြန်မာအဘိဓာန်၌ ကြည့်ပါ။</p>",
            vols,
            {},
        )
        self.assertIsNone(stub)

        rec = make_proofed_record(
            "က",
            '<p class="word">က <span class="gender">(ပု)</span></p>'
            '<div class="definition"><p>ဗြဟ္မာ။</p></div>'
            '<p class="reference">တိပိ၊၁၊၅</p>',
            vols,
            {},
        )
        assert rec is not None
        self.assertEqual(rec["volume_code"], "01")
        self.assertEqual(rec["printed_page"], 5)
        self.assertEqual(rec["pdf_page"], 125)
        self.assertEqual(rec["quality"], "proofed")
        self.assertEqual(rec["license_id"], PD_LICENSE)

        ocr = make_ocr_record(
            {
                "id": 99,
                "book": "14c",
                "index_page": 10,
                "pdf_page": 37,
                "headword": "ပဝ",
                "iast": "pava",
                "body": "အနက်။",
                "citations": ["ဝိ၊၁။၁။"],
            }
        )
        assert ocr is not None
        self.assertEqual(ocr["quality"], "ocr")
        self.assertEqual(ocr["license_id"], OCR_LICENSE)
        self.assertEqual(ocr["pdf_page"], 37)
        self.assertEqual(ocr["extra"]["ocr_source"], "bthar-mx")

    def test_build_stage4_hybrid_and_proofed_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            abidan_db = root / "abidan_new.db"
            _create_abidan_db(abidan_db)

            tp_db = root / "tipitaka_pali.db"
            with closing(sqlite3.connect(tp_db)) as conn:
                conn.execute("CREATE TABLE dictionary (word TEXT, definition TEXT, book INTEGER)")
                # Proofed entry in 01, stub entry, and one entry in 4c
                conn.executemany(
                    "INSERT INTO dictionary VALUES (?,?,?)",
                    [
                        (
                            "အ",
                            '<p class="word">အ</p><div class="definition"><p>အစ။</p></div>'
                            '<p class="reference">တိပိ၊၁၊၁</p>',
                            1,
                        ),
                        (
                            "ပဝ",
                            "<p>မူရင်းတိပိဋကပါဠိ-မြန်မာအဘိဓာန်၌ ကြည့်ပါ။</p>",
                            1,
                        ),
                        (
                            "ကက",
                            '<p class="word">ကက</p><div class="definition"><p>ကက-အနက်။</p></div>'
                            '<p class="source"><span class="volume">၄</span>'
                            '<span class="part">၃</span><span class="reference">၅</span></p>',
                            1,
                        ),
                    ],
                )
                conn.commit()

            ocr_dir = root / "ocr"
            (ocr_dir / "14c").mkdir(parents=True)
            (ocr_dir / "4c").mkdir(parents=True)
            (ocr_dir / "14c" / "articles.jsonl").write_text(
                json.dumps(
                    {
                        "id": 1,
                        "book": "14c",
                        "index_page": 2,
                        "pdf_page": 29,
                        "headword": "ပဝ",
                        "iast": "pava",
                        "body": "ပဝ-အနက်။",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            # 4c: 'ကက' already proofed (must be skipped), 'ကခ' missing (must be added)
            (ocr_dir / "4c" / "articles.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "id": 2,
                                "book": "4c",
                                "index_page": 5,
                                "pdf_page": 32,
                                "headword": "ကက",
                                "body": "OCR duplicate",
                            },
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            {
                                "id": 3,
                                "book": "4c",
                                "index_page": 6,
                                "pdf_page": 33,
                                "headword": "ကခ",
                                "body": "ကခ-အနက်။",
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            out_hybrid = root / "hybrid"
            out_hybrid.mkdir()
            c_hybrid = build_stage4(
                tipitaka_db=tp_db,
                abidan_db=abidan_db,
                bthar_ocr_dir=ocr_dir,
                output_dir=out_hybrid,
                proofed_only=False,
            )
            self.assertEqual(c_hybrid["written"], 4)
            self.assertEqual(c_hybrid["ocr_added"], 2)

            out_pd = root / "pd"
            out_pd.mkdir()
            c_pd = build_stage4(
                tipitaka_db=tp_db,
                abidan_db=abidan_db,
                bthar_ocr_dir=None,
                output_dir=out_pd,
                proofed_only=True,
            )
            self.assertEqual(c_pd["written"], 2)
            self.assertEqual(c_pd["ocr_added"], 0)
            with closing(sqlite3.connect(out_pd / "tipitaka-abhidhana-proofed.db")) as conn:
                licenses = {r[0] for r in conn.execute("SELECT DISTINCT license_id FROM entries")}
                self.assertEqual(licenses, {PD_LICENSE})
