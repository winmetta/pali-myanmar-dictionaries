# AGENTS.md: Pāḷi–Myanmar Dictionaries Open Dataset Repository

This repository (`winmetta/pali-myanmar-dictionaries`) compiles open-source Pāḷi–Myanmar and Theravāda Buddhist reference dictionaries into clean, deduplicated **Myanmar Unicode** SQLite databases (`.db`) and JSON Lines (`.jsonl`) files, with explicit **source-book, volume, and page attribution**, so Win Metta and any external developer or monastic project can build offline or web Pāḷi–Myanmar dictionary applications.

Read [README.md](README.md) for the public overview and [docs/implementation-plan.md](docs/implementation-plan.md) for the full source audit, SQLite/JSONL schema specification, normalization rules, and staged implementation roadmap.

## 1. Repository Layout

- `docs/implementation-plan.md`: authoritative source catalog, schema design, deduplication rules, storage decision, and implementation stages (Stages 0–7).
- `.cache/pali-dictionary/`: **gitignored** local cache (`~6.2 GB`) holding raw upstream SQLite databases, JSONL corpora, CSVs, and JS dumps downloaded for extraction. Read `.cache/pali-dictionary/AGENTS.md` (when present locally) for download URLs and raw table notes. **Never commit `.cache/` or force-add raw upstream archives.**
- `dist/` (planned, gitignored): compiled per-source `.db` / `.jsonl` outputs and `pali-myanmar-master.db`, published via **GitHub Releases** (compressed with Zstandard `.zst`) rather than plain Git or Git LFS.
- `scripts/` / `src/` (Stages 0–6): reproducible extraction, Zawgyi/Sinhala/Roman-to-Unicode conversion, validation, and SQLite/FTS5 build scripts.

## 2. Core Data & Engineering Rules

- **Public repository — zero secrets or personal data:** never commit credentials, API keys, personal emails, or private repo details.
- **Strict Myanmar Unicode (`U+1000`–`U+109F`):** every output string in compiled `.db` and `.jsonl` files must be valid NFC Myanmar Unicode in canonical syllable storage order (follow the `burmese-pali-orthography` skill). Convert all Zawgyi inputs (`pmd_drive.db`, `vatthuguide.db`, `pitakaguide.db`, `pm1..pm4`) using [`winmetta-platform/packages/myanmar-convert/src/index.ts`](https://github.com/winmetta/winmetta-platform/blob/main/packages/myanmar-convert/src/index.ts) (`convert` and `detect` in sibling `../winmetta-platform/packages/myanmar-convert/src/index.ts`), and transliterate Sinhala/Roman Pāḷi headwords (`my-android.db`, `tipitaka-pali-reader`) before insertion, with automated zero-Zawgyi verification gates.
- **Preserve source-book attribution:**
  - Deduplicate **within** each `source_id` (for example, collapse the `17,140` unstacked lookup-alias rows in `pndaza/tipitaka_pali.db` `book=1`).
  - **Never** merge or overwrite definitions **across** different `source_id` books in `pali-myanmar-master.db` — every definition row retains its exact `source_id` (plus `volume_code`, `printed_page`, and `pdf_page` where available) so readers always know which dictionary a definition came from.
  - **Never** import `datarrx/data.jsonl` (`306,063` rows): it is an unlabeled concatenation of `tipitaka_pali.db` `books 1–7` that stripped `book` attribution and mixed `47,683` English-only entries into the Pāḷi–Myanmar corpus.
- **License & provenance separation:**
  - Repository code, schemas, and build scripts are licensed under **MIT** ([LICENSE](LICENSE)).
  - Upstream data licenses vary by source and must be recorded in `sources.license_note` and `DATA-LICENSES.md`:
    - **Win Metta public-domain decision (2026-11-26):** `pndaza` repositories carry no `LICENSE` file; Win Metta treats the digitized traditional dictionary text from `pndaza` as public domain and documents that decision wherever shipped.
    - **CC0 1.0:** `freococo/pali-words-myanmar-script`.
    - **CC BY-SA 4.0 + required attribution (`bthar-mx/tipitaka-abhidhana`):** applies to the article segmentation, field structure, and romanization added by IEBH / BTHAR (not the underlying dictionary text of the Masoeyein Board & Ministry of Religious Affairs). Either keep `bthar-mx` OCR fallback entries in a clearly marked CC BY-SA 4.0 build/flag (`quality = 'ocr'`) or attribute `"Tipiṭaka Pāḷi-Myanmā Abhidhāna — digitised, IEBH / BTHAR, https://github.com/bthar-mx/tipitaka-abhidhana"`.
    - **Non-commercial (`digitalpalidictionary/dpd-db`):** DPD is non-commercial (`dpdict.net`); do not mix DPD English definitions into public-domain/MIT builds without explicit license separation.
- **No binary bloat in Git history:** keep `.db`, `.sqlite`, and bulk `.jsonl` files out of Git commits (and out of Git LFS, whose monthly bandwidth quota breaks public clones when exhausted). Publish versioned `.zst` archives to **GitHub Releases** with `SHA256SUMS`.
- **Tooling & commits:** use `mise` (never `nvm`), Conventional Commits, and run the `local-change-review` skill before every commit.
