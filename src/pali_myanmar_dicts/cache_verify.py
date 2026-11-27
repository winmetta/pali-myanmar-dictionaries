"""Verify raw upstream files in `.cache/pali-dictionary/` against `cache-manifest.json`."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pali_myanmar_dicts.schema import REPO_ROOT

DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "pali-dictionary"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "schemas" / "cache-manifest.json"


@dataclass(frozen=True)
class CacheCheckResult:
    checked_count: int
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of `path`."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_cache(
    cache_dir: Path = DEFAULT_CACHE_DIR,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    *,
    quick: bool = False,
) -> CacheCheckResult:
    """Verify every entry in `manifest_path` exists in `cache_dir` with matching size and hash."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", [])
    errors: list[str] = []

    for item in files:
        rel_path = item["path"]
        expected_size = item["size"]
        expected_sha = item["sha256"]
        target = cache_dir / rel_path
        if not target.is_file():
            errors.append(f"MISSING: {rel_path}")
            continue
        actual_size = target.stat().st_size
        if actual_size != expected_size:
            errors.append(
                f"SIZE MISMATCH: {rel_path} (got {actual_size}, expected {expected_size})"
            )
            continue
        if not quick:
            actual_sha = sha256_file(target)
            if actual_sha != expected_sha:
                errors.append(
                    f"SHA256 MISMATCH: {rel_path} (got {actual_sha}, expected {expected_sha})"
                )

    return CacheCheckResult(checked_count=len(files), errors=errors)
