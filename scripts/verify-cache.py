#!/usr/bin/env python3
"""CLI to verify raw dictionary cache files against `schemas/cache-manifest.json`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pali_myanmar_dicts.cache_verify import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEFAULT_MANIFEST_PATH,
    verify_cache,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify raw files in .cache/pali-dictionary against cache-manifest.json"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Path to raw pali-dictionary cache directory",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to cache-manifest.json",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Verify file existence and byte size only (skip SHA-256 hashing)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify_cache(args.cache_dir, args.manifest, quick=args.quick)
    if not result.ok:
        for err in result.errors:
            print(err, file=sys.stderr)
        err_count = len(result.errors)
        print(
            f"Cache check FAILED ({err_count} errors across {result.checked_count} files).",
            file=sys.stderr,
        )
        return 1
    mode = "size-only" if args.quick else "full SHA-256"
    print(f"Cache check OK ({result.checked_count} files verified, {mode}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
