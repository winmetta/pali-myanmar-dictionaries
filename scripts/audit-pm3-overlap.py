#!/usr/bin/env python3
"""Compare PM3 enrichment with the primary source's displayed headword."""

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    counts: Counter[str] = Counter()
    uri = f"file:{args.database.resolve()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        for headword, extra_json in conn.execute(
            "SELECT headword, extra_json FROM entries WHERE extra_json IS NOT NULL"
        ):
            extra = json.loads(extra_json)
            compound = extra.get("compound_hyphenated")
            if not compound:
                continue
            if compound == headword:
                counts["identical"] += 1
            elif "-" in headword:
                counts["different_hyphenation"] += 1
            else:
                counts["primary_without_hyphen"] += 1
    print(json.dumps(dict(counts), sort_keys=True))


if __name__ == "__main__":
    main()
