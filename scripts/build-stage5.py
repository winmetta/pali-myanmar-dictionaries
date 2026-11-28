#!/usr/bin/env python3
"""Build Stage 5 topical, story, concordance, and reverse dictionaries."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pali_myanmar_dicts.stage5 import STAGE5_SOURCES, build_stage5_source  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/pali-dictionary/pndaza"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("dist/stage5"))
    parser.add_argument(
        "--source",
        choices=[source.source_id for source in STAGE5_SOURCES],
        help="Build only this source (default: all 5 Stage 5 sources)",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for source in STAGE5_SOURCES:
        if args.source and source.source_id != args.source:
            continue
        seen, written = build_stage5_source(args.cache_dir, args.output_dir, source)
        print(f"{source.source_id}: {seen} input rows, {written} unique entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
