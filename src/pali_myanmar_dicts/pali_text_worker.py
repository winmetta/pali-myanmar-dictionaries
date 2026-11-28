"""Line-oriented adapter to the compiled @winmetta/pali-text workspace package."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import TracebackType

WORKER = Path(__file__).resolve().parents[2] / "scripts" / "pali-text-worker.mjs"


class PaliTextWorker:
    """Use a single Node process throughout a dictionary build."""

    def __enter__(self) -> PaliTextWorker:
        self.process = subprocess.Popen(
            ["node", str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
        )
        return self

    def lookup_keys(self, headword: str) -> tuple[str, str]:
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(headword, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("pali-text worker stopped; run npm run build:pali-text")
        result = json.loads(line)
        if (
            not isinstance(result, list)
            or len(result) != 2
            or not all(isinstance(v, str) for v in result)
        ):
            raise RuntimeError("pali-text worker returned an invalid response")
        return result[0], result[1]

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.process.wait()
