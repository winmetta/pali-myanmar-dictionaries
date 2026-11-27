"""Bridge to `winmetta-platform/packages/myanmar-convert/src/index.ts` and Zawgyi gates."""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = REPO_ROOT / "scripts" / "zawgyi-bridge.mjs"

# Fast code-point Zawgyi markers matching winmetta-platform/packages/myanmar-convert/src/zawgyi.ts:
# 1. U+1060-U+1097: Shan/Karen glyphs repurposed by Zawgyi-One (never in Burmese/Pāḷi Unicode).
# 2. U+1031 (ေ) not preceded by a Myanmar consonant, medial, or stacked virama.
# 3. U+1039 (္) not followed by a Myanmar consonant (Zawgyi uses U+1039 as visible asat).
ZAWGYI_GLYPH_ONLY_RE = re.compile(r"[\u1060-\u1097]")
ZAWGYI_LEADING_E_RE = re.compile(r"(?<![\u1000-\u1021\u1039\u103B-\u103F\u1050-\u1055])\u1031")
ZAWGYI_LOOSE_VIRAMA_RE = re.compile(r"\u1039(?![\u1000-\u1021\u1050-\u1055])")
ZAWGYI_MON_REPURPOSED_RE = re.compile(r"[\u1033\u1034\u105A]")


@dataclass(frozen=True)
class DetectionInfo:
    """Result of `@winmetta/myanmar-convert` `detect` + marker checks."""

    detected: str
    has_marker: bool
    marker_count: int


def has_zawgyi_codepoint_marker(text: str) -> bool:
    """Return True if `text` contains any code-point sequence illegal in Burmese/Pāḷi Unicode."""
    return bool(
        ZAWGYI_GLYPH_ONLY_RE.search(text)
        or ZAWGYI_LEADING_E_RE.search(text)
        or ZAWGYI_LOOSE_VIRAMA_RE.search(text)
        or ZAWGYI_MON_REPURPOSED_RE.search(text)
    )


def assert_zero_zawgyi(text: str, *, context: str = "") -> None:
    """Raise ValueError if `text` still contains any Zawgyi code-point marker."""
    if has_zawgyi_codepoint_marker(text):
        prefix = f"{context}: " if context else ""
        raise ValueError(f"{prefix}Residual Zawgyi sequence detected in {text[:80]!r}")


class MyanmarConvertBridge:
    """Persistent Node 24 subprocess calling `@winmetta/myanmar-convert/src/index.ts`."""

    def __init__(self, *, entry_path: Path | str | None = None) -> None:
        self._entry_path = str(entry_path) if entry_path else None
        self._proc: subprocess.Popen[str] | None = None

    def _ensure_proc(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        env = os.environ.copy()
        if self._entry_path:
            env["MYANMAR_CONVERT_ENTRY"] = self._entry_path
        node_bin = shutil.which("node") or str(
            Path.home() / ".local" / "share" / "mise" / "shims" / "node"
        )
        self._proc = subprocess.Popen(
            [node_bin, str(BRIDGE_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
        )
        return self._proc

    def request(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Send one batch request over JSONL and return its `results` list."""
        proc = self._ensure_proc()
        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("zawgyi-bridge stdio pipes are unavailable")
        encoded = (
            json.dumps(payload, ensure_ascii=False)
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )
        try:
            proc.stdin.write(encoded + "\n")
            proc.stdin.flush()
        except BrokenPipeError as exc:
            stderr = proc.stderr.read() if proc.stderr is not None else ""
            self.close()
            raise RuntimeError(f"zawgyi-bridge pipe closed: {stderr.strip()}") from exc
        line = proc.stdout.readline()
        if not line:
            stderr = proc.stderr.read() if proc.stderr is not None else ""
            self.close()
            raise RuntimeError(f"zawgyi-bridge exited unexpectedly: {stderr.strip()}")
        resp = json.loads(line)
        if not resp.get("ok"):
            raise RuntimeError(f"zawgyi-bridge error: {resp.get('error')}")
        return list(resp["results"])

    def convert_batch(
        self,
        texts: Sequence[str],
        *,
        from_enc: str = "zawgyi",
        to_enc: str = "unicode",
        chunk_size: int = 2000,
    ) -> list[str]:
        """Convert a batch of strings via `@winmetta/myanmar-convert` `convert()`."""
        if not texts:
            return []
        out: list[str] = []
        for start in range(0, len(texts), chunk_size):
            batch = list(texts[start : start + chunk_size])
            rows = self.request({"op": "convert", "texts": batch, "from": from_enc, "to": to_enc})
            out.extend(row["text"] for row in rows)
        return out

    def auto_to_unicode_batch(self, texts: Sequence[str], *, chunk_size: int = 2000) -> list[str]:
        """Convert only strings detected as Zawgyi via Pāḷi-safe marker + `detect()`."""
        if not texts:
            return []
        results = [unicodedata.normalize("NFC", t) for t in texts]
        flagged = [i for i, t in enumerate(texts) if has_zawgyi_codepoint_marker(t)]
        for start in range(0, len(flagged), chunk_size):
            idx_chunk = flagged[start : start + chunk_size]
            batch = [texts[i] for i in idx_chunk]
            rows = self.request({"op": "auto_to_unicode", "texts": batch})
            for idx, row in zip(idx_chunk, rows, strict=True):
                results[idx] = row["text"]
        return results

    def detect_batch(self, texts: Sequence[str], *, chunk_size: int = 2000) -> list[DetectionInfo]:
        """Classify strings using `@winmetta/myanmar-convert` `detect()`."""
        if not texts:
            return []
        out: list[DetectionInfo] = []
        for start in range(0, len(texts), chunk_size):
            batch = list(texts[start : start + chunk_size])
            rows = self.request({"op": "detect", "texts": batch})
            out.extend(
                DetectionInfo(
                    detected=row["detected"],
                    has_marker=bool(row["hasMarker"]),
                    marker_count=int(row["markerCount"]),
                )
                for row in rows
            )
        return out

    def close(self) -> None:
        """Shut down the persistent Node worker process cleanly."""
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


_DEFAULT_BRIDGE: MyanmarConvertBridge | None = None


def get_default_bridge() -> MyanmarConvertBridge:
    """Return a process-wide shared `MyanmarConvertBridge` registered with `atexit`."""
    global _DEFAULT_BRIDGE
    if _DEFAULT_BRIDGE is None:
        _DEFAULT_BRIDGE = MyanmarConvertBridge()
        atexit.register(_DEFAULT_BRIDGE.close)
    return _DEFAULT_BRIDGE


def zawgyi_to_unicode(text: str) -> str:
    """Convert a known Zawgyi string to NFC Myanmar Unicode via `@winmetta/myanmar-convert`."""
    if not text:
        return text
    return get_default_bridge().convert_batch([text], from_enc="zawgyi", to_enc="unicode")[0]


def zawgyi_to_unicode_batch(texts: Sequence[str]) -> list[str]:
    """Convert a sequence of known Zawgyi strings to NFC Myanmar Unicode."""
    return get_default_bridge().convert_batch(texts, from_enc="zawgyi", to_enc="unicode")


def auto_zawgyi_to_unicode(text: str) -> str:
    """Convert `text` to NFC Unicode only when `@winmetta/myanmar-convert` detects Zawgyi."""
    if not text:
        return text
    if not has_zawgyi_codepoint_marker(text):
        return unicodedata.normalize("NFC", text)
    return get_default_bridge().auto_to_unicode_batch([text])[0]


def detect_encoding(text: str) -> DetectionInfo:
    """Classify `text` with `@winmetta/myanmar-convert` `detect()`."""
    return get_default_bridge().detect_batch([text])[0]
