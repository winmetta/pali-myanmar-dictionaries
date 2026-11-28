"""Compare shared TypeScript lookup behavior with Python using the local corpus."""

import json
import sqlite3
import subprocess
import unittest
from contextlib import closing
from pathlib import Path

from pali_myanmar_dicts.normalize import canonicalize_myanmar_syllables, to_headword_norm
from pali_myanmar_dicts.translit import (
    clean_sinhala_headword,
    iast_to_myanmar,
    myanmar_to_iast,
    sinhala_to_myanmar,
)

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / ".cache/pali-dictionary/pndaza/tipitaka_pali.db"


class TypeScriptParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(["npm", "run", "build:pali-text"], cwd=ROOT, check=True, capture_output=True)

    @unittest.skipUnless(DATABASE.is_file(), "Upstream corpus not present")
    def test_stage2_headwords_match_python(self) -> None:
        with closing(sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True)) as conn:
            words = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT word FROM dictionary WHERE book IN (2,3,4) ORDER BY word"
                )
            ]
        process = subprocess.run(
            ["node", str(ROOT / "packages/pali-text/test/parity-worker.mjs")],
            input="".join(json.dumps(word, ensure_ascii=False) + "\n" for word in words),
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )
        actual = process.stdout.splitlines()
        self.assertEqual(len(actual), len(words))
        for word, result in zip(words, actual, strict=True):
            self.assertEqual(
                json.loads(result),
                [
                    canonicalize_myanmar_syllables(word),
                    to_headword_norm(word),
                    myanmar_to_iast(word),
                    iast_to_myanmar(myanmar_to_iast(word)),
                ],
                msg=repr(word),
            )

    @unittest.skipUnless(
        (ROOT / ".cache/pali-dictionary/bthar-mx/ocr").is_dir(), "BTHAR corpus not present"
    )
    def test_bthar_corpus_matches_python(self) -> None:
        corpus = ROOT / ".cache/pali-dictionary/bthar-mx/ocr"
        pairs = []
        for path in sorted(corpus.glob("*/articles.jsonl")):
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    if row.get("headword") and row.get("iast"):
                        pairs.append((row["headword"], row["iast"]))
        self.assertGreater(len(pairs), 220_000)
        process = subprocess.run(
            ["node", str(ROOT / "packages/pali-text/test/corpus-worker.mjs")],
            input="".join(json.dumps(pair, ensure_ascii=False) + "\n" for pair in pairs),
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )
        results = process.stdout.splitlines()
        self.assertEqual(len(results), len(pairs))
        for (headword, iast), result in zip(pairs, results, strict=True):
            self.assertEqual(
                json.loads(result),
                [
                    myanmar_to_iast(headword, iso15919=True),
                    myanmar_to_iast(iast_to_myanmar(iast), iso15919=True),
                ],
                msg=repr((headword, iast)),
            )

    @unittest.skipUnless(
        (ROOT / ".cache/pali-dictionary/tipitaka-app/my-android.db").is_file(),
        "Sinhala corpus not present",
    )
    def test_sinhala_corpus_matches_python(self) -> None:
        path = ROOT / ".cache/pali-dictionary/tipitaka-app/my-android.db"
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            words = [row[0] for row in conn.execute("SELECT word FROM dictionary")]
        process = subprocess.run(
            ["node", str(ROOT / "packages/pali-text/test/sinhala-worker.mjs")],
            input="".join(json.dumps(word, ensure_ascii=False) + "\n" for word in words),
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )
        results = process.stdout.splitlines()
        self.assertEqual(len(results), len(words))
        for word, result in zip(words, results, strict=True):
            cleaned, notes = clean_sinhala_headword(word)
            self.assertEqual(
                json.loads(result),
                [{"text": cleaned, "notes": notes}, sinhala_to_myanmar(word)],
                msg=repr(word),
            )

    @unittest.skipUnless(
        (ROOT / ".cache/pali-dictionary/tipitaka-app/my-u-hoke-sein.db").is_file(),
        "Sinhala reference corpus not present",
    )
    def test_sinhala_myanmar_sinhala_stability(self) -> None:
        path = ROOT / ".cache/pali-dictionary/tipitaka-app/my-u-hoke-sein.db"
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            words = [row[0] for row in conn.execute("SELECT word FROM dictionary")]
        process = subprocess.run(
            ["node", str(ROOT / "packages/pali-text/test/sinhala-roundtrip-worker.mjs")],
            input="".join(json.dumps(word, ensure_ascii=False) + "\n" for word in words),
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )
        results = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(results), len(words))
        self.assertGreater(len(results), 53000)
        matches = sum(first == second for first, second in results)
        self.assertGreaterEqual(matches / len(results), 0.995, f"Matched {matches}/{len(results)}")
