#!/usr/bin/env python3
"""Experimental Stage 2 builder; mixed-encoding inputs are not yet supported."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pali_myanmar_dicts.stage2 import SOURCES, audit_source, build_source  # noqa: E402

DEFAULT_PM3 = Path(
    ".cache/pali-dictionary/tipitaka-pali-projector/pm3_Pali_Myanmar_Dictionary_@U_Hau_Sein_2018.js"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path(".cache/pali-dictionary/pndaza/tipitaka_pali.db")
    )
    parser.add_argument(
        "--pm3",
        type=Path,
        default=None,
        help="Optional PM3 source file for unverified compound-hyphenation enrichment",
    )
    parser.add_argument(
        "--include-pm3",
        action="store_true",
        help="Include unverified PM3 compound-hyphenation enrichment from the default cache path",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    parser.add_argument(
        "--source",
        choices=[source.source_id for source in SOURCES],
        help="Build only this source (default: all Stage 2 sources)",
    )
    parser.add_argument("--audit", action="store_true", help="Report invalid rows as JSONL")
    args = parser.parse_args()
    if not args.audit:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    issue_count = 0
    for source in SOURCES:
        if args.source and source.source_id != args.source:
            continue
        if args.audit:
            for rowid, word, error in audit_source(args.input, source):
                issue_count += 1
                print(
                    json.dumps(
                        {
                            "source_id": source.source_id,
                            "rowid": rowid,
                            "word": word,
                            "error": error,
                        },
                        ensure_ascii=False,
                    )
                )
            continue
        pm3_path = args.pm3 or (DEFAULT_PM3 if args.include_pm3 else None)
        read, written = build_source(args.input, args.output_dir, source, pm3_path=pm3_path)
        print(f"{source.source_id}: {read} input rows, {written} unique entries")
    return 1 if issue_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
