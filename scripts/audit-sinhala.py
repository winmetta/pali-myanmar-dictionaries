#!/usr/bin/env python3
"""Report Sinhala/Myanmar headword mismatches from the U Hoke Sein source."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pali_myanmar_dicts.normalize import normalize_myanmar_text  # noqa: E402
from pali_myanmar_dicts.translit import sinhala_to_myanmar  # noqa: E402

EMBEDDED_HEADWORD = re.compile(r"^([\u1000-\u103f\-]+)(?:\s|\()")


def category(actual: str, reference: str) -> str:
    if actual.replace("ါ", "ာ") == reference.replace("ါ", "ာ"):
        return "tall_aa"
    if actual.replace("င်္", "ံ") == reference.replace("င်္", "ံ"):
        return "kinzi_anusvara"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(".cache/pali-dictionary/tipitaka-app/my-u-hoke-sein.db"),
    )
    args = parser.parse_args()
    counts: Counter[str] = Counter()
    with closing(sqlite3.connect(f"file:{args.input.resolve()}?mode=ro", uri=True)) as conn:
        for rowid, sinhala, meaning in conn.execute("SELECT rowid, word, meaning FROM dictionary"):
            match = EMBEDDED_HEADWORD.match(meaning)
            if match is None:
                counts["unmatched_format"] += 1
                continue
            actual = normalize_myanmar_text(sinhala_to_myanmar(sinhala), check_zawgyi=False)
            reference = normalize_myanmar_text(match[1].replace("-", ""), check_zawgyi=False)
            if actual == reference:
                counts["exact"] += 1
                continue
            group = category(actual, reference)
            counts[group] += 1
            house_match = group in {"tall_aa", "kinzi_anusvara"}
            counts["house_orthography_match"] += house_match
            print(
                json.dumps(
                    {
                        "rowid": rowid,
                        "sinhala": sinhala,
                        "actual": actual,
                        "reference": reference,
                        "category": group,
                        "house_orthography_match": house_match,
                    },
                    ensure_ascii=False,
                )
            )
    print(json.dumps(dict(counts), sort_keys=True), file=sys.stderr)


if __name__ == "__main__":
    main()
