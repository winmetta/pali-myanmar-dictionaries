#!/usr/bin/env python3
"""Build Stage 3 `my-android.db` unique lexicons."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pali_myanmar_dicts.stage3 import STAGE3_SOURCES, build_stage3_source  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(".cache/pali-dictionary/tipitaka-app/my-android.db"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("dist/stage3"))
    parser.add_argument(
        "--source",
        choices=[source.source_id for source in STAGE3_SOURCES],
        help="Build only this source (default: all Stage 3 sources)",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for source in STAGE3_SOURCES:
        if args.source and source.source_id != args.source:
            continue
        seen, written = build_stage3_source(args.input, args.output_dir, source)
        print(f"{source.source_id}: {seen} segments, {written} unique entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
