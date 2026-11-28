#!/usr/bin/env python3
"""Build Stage 4 29-book `tipitaka-abhidhana` SQLite and JSONL outputs."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pali_myanmar_dicts.stage4 import build_stage4  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tipitaka-db",
        type=Path,
        default=Path(".cache/pali-dictionary/pndaza/tipitaka_pali.db"),
    )
    parser.add_argument(
        "--abidan-db",
        type=Path,
        default=Path(".cache/pali-dictionary/pndaza/abidan_new.db"),
    )
    parser.add_argument(
        "--bthar-ocr-dir",
        type=Path,
        default=Path(".cache/pali-dictionary/bthar-mx/ocr"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("dist/stage4"))
    parser.add_argument(
        "--proofed-only",
        action="store_true",
        help="Emit tipitaka-abhidhana-proofed.{db,jsonl} without CC-BY-SA-4.0 OCR gap-fills",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    counts = build_stage4(
        tipitaka_db=args.tipitaka_db,
        abidan_db=args.abidan_db,
        bthar_ocr_dir=None if args.proofed_only else args.bthar_ocr_dir,
        output_dir=args.output_dir,
        proofed_only=args.proofed_only,
    )
    print(
        f"tipitaka-abhidhana: {counts['written']} entries "
        f"(proofed_read={counts['proofed_read']}, stubs_skipped={counts['stubs_skipped']}, "
        f"ocr_added={counts['ocr_added']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
