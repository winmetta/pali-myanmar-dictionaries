# Implementation Plan: `pali-myanmar-dictionaries`

| Field     | Value                                                                                                                                                                                               |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Status    | Planned (Stage 0 complete: repo & research baseline initialized 2026-11-27)                                                                                                                         |
| Scope     | Extract, normalize to Myanmar Unicode, deduplicate, and package 11 Pāḷi–Myanmar / Buddhist reference sources into per-source SQLite + JSONL datasets and one compiled master SQLite + FTS5 database |
| Raw cache | `.cache/pali-dictionary/` (`~6.2 GB`, gitignored)                                                                                                                                                   |

---

## 1. Goals & Design Principles

1. **Preserve book provenance everywhere:** readers looking up a Pāḷi word in Myanmar script must see _which_ dictionary each definition comes from (book title, author, and volume/page when available).
2. **Per-source databases before the master database:** every distinct book or multi-volume book group is cleaned, validated, and packaged into its own standalone `<source_id>.db` and `<source_id>.jsonl` first. `pali-myanmar-master.db` is then compiled deterministically from the per-source databases.
3. **100% canonical Myanmar Unicode (`U+1000`–`U+109F`):** all legacy Zawgyi text, Sinhala-script Pāḷi headwords, and Roman Pāḷi headwords are converted/transliterated and normalized to NFC + canonical Myanmar syllable order before insertion.
4. **Two-level deduplication:**
   - **Within a single `source_id`:** collapse duplicate rows (such as unstacked search-alias duplicates or repeated upstream scrapes).
   - **Across different `source_id` books:** never merge or overwrite definitions from different books; each book's definition remains an independent, attributed row under the shared headword.
5. **Reusable by any open-source project:** clean SQLite schema with zero proprietary dependencies, portable FTS5 search index, and clear per-source license metadata so external developers can ship subsets matching their license needs (e.g., public-domain-only vs. CC BY-SA 4.0 OCR-complete builds).

---

## 2. Upstream Audit & Source-Book Mapping

### 2.1 Critical Cross-File Findings

1. **Exclude `datarrx/data.jsonl` (`306,063` rows):**
   - Exact row-count verification shows `DatarrX/data.jsonl` is an unlabeled export of `tipitaka_pali.db` `books 1–7` (`184,617 + 60,782 + 11,086 + 1,894 + 14,054 + 20,128 + 13,501 = 306,062`), which stripped the `book` column, flattened HTML fields, and mixed **47,683 English-only entries** (`books 5–7`: PTS, Buddhadatta Concise, and Pali-English) into the dataset. `pndaza/tipitaka_pali.db` completely supersedes it.
2. **Extract two unique dictionaries hidden inside `tipitaka-app/my-android.db` (`115,357` rows):**
   - `my-android.db` concatenates entries separated by `+` with trailing `♦` source markers:
     - `♦မြ` (`78,071` segments): abridged merge of _တိပိဋက ပါဠိ-မြန်မာ အဘိဓာန်_, _ဓာတွတ္ထပန်းကုံး_, and _ပါဠိဓာတ်အဘိဓာန်_ → **skip** (use full versions in `pndaza/tipitaka_pali.db`).
     - `♦စိန်` (`49,219` segments): _ဦးဟုတ်စိန် ပါဠိ-မြန်မာ အဘိဓာန်_ → **skip** (use full `60,782`-row version in `pndaza/tipitaka_pali.db` `book=2`).
     - **`♦ချုပ်` (`13,745` segments):** **ပါဠိအဘိဓာန်ချုပ်** (လယ်တီပဏ္ဍိတ ဦးမောင်ကြီး, 1914) → **extract as `pali-abhidhana-chok`** (unique to this file; spans the full alphabet).
     - **`♦ဝိ` / `♦ဝိသုဒ္ဓါရုံ` (`3,135` tagged + `3,643` untagged segments in identical template = `~6,778` entries):** **ဝိသုဒ္ဓါရုံ ပိဋကအဘိဓာန်** (မဟာဝိသုဒ္ဓါရုံ) → **extract as `visuddharama-abhidhana`** (unique to this file).
3. **Combine `pndaza` (proofed) + `abidan_new.db` (page index) + `bthar-mx` (2026 OCR) for _တိပိဋက ပါဠိ-မြန်မာ အဘိဓာန်_ (29 books):**
   - `pndaza/tipitaka_pali.db` `book=1` (`201,757` rows, including `17,140` unstacked alias duplicates) has clean human-typed definitions across **24 of the 29 books**, but **5 books have virtually zero definitions**: `14c` (8 real entries), `20` (7,005 `"မူရင်း...၌ ကြည့်ပါ"` stubs), `21` (7,889 stubs), `24` (0), and `25` (0).
   - `bthar-mx/ocr/*/articles.jsonl` (`221,764` rows; `208,358` with OCR body) covers **all 29 books**, filling ~`35,400` missing articles in `14c, 20, 21, 24, 25` (plus partial gaps in `4c` and `14b`) and providing `pdf_page` + `index_page` + `iast` for all 29 books.
4. **`pitakaguide.db` is _ပိဋကလမ်းညွှန်_ (ဦးသီဟဗလ), not _ပါဠိပဒ ပိဋကကျမ်းညွန်း_:**
   - Per `pndaza/pitaka_guide_cross_platform/assets/info.html`, `pitakaguide.db` (`18,398` rows across 3 volumes) is Sayadaw U Sīhabala's _ပိဋကလမ်းညွှန်_, distinct from the un-digitized 3-volume _ပါဠိပဒ ပိဋကကျမ်းညွန်း_ in Dhamma Library folder `f008`.

### 2.2 Master Catalog of Target Per-Source Databases

| #   | `source_id`              | Book / Book Group Title & Author                             | Kind             | Primary Cache Input(s)                                                                           | Duplicate Cache Files Excluded                                                                                                                    |
| --- | ------------------------ | ------------------------------------------------------------ | ---------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `tipitaka-abhidhana`     | **တိပိဋက ပါဠိ-မြန်မာ အဘိဓာန်** (25 vols / 29 books, 1964–2023)     | `lexicon`        | `pndaza/tipitaka_pali.db` (`book=1`), `pndaza/abidan_new.db`, `bthar-mx/ocr/*/articles.jsonl`    | `pmd_drive.db` (`book=1`), `abidan_old.db`, `my-23-vol.db`, `tpr` (`book_id=1`), `dictionaries.db` (`source_id=3`), `pm1`, `pm2`, `rcy` (`B`,`K`) |
| 2   | `u-hoke-sein`            | **ပဒတ္ထမဉ္ဇူသာ ပါဠိ-မြန်မာ အဘိဓာန်** — ဦးဟုတ်စိန် (1954–1959)           | `lexicon`        | `pndaza/tipitaka_pali.db` (`book=2`) + compound hyphen enrichment from `pm3`                     | `pmd_drive.db` (`book=2`), `tpr` (`book_id=2`), `my-u-hoke-sein.db`, `my-android.db` (`♦စိန်`), `rcy` (`R`)                                         |
| 3   | `dhatuattha-pankone`     | **ဓာတွတ္ထပန်းကုံး** — အရှင်ကုမာရ                                     | `lexicon`        | `pndaza/tipitaka_pali.db` (`book=3`)                                                             | `pmd_drive.db` (`book=3`), `tpr` (`book_id=3`), `my-android.db` (`♦မြ`)                                                                           |
| 4   | `pali-dhatu-abhidhana`   | **ပါဠိဓာတ်အဘိဓာန်** — ပါဠိပါမောက္ခ ဆရာဉာဏ်                          | `dhatu_root`     | `pndaza/tipitaka_pali.db` (`book=4`)                                                             | `pmd_drive.db` (`book=4`), `pm4`, `rcy` (`O`), `my-android.db` (`♦မြ`)                                                                            |
| 5   | `pali-abhidhana-chok`    | **ပါဠိအဘိဓာန်ချုပ်** — လယ်တီပဏ္ဍိတ ဦးမောင်ကြီး (1914)                   | `lexicon`        | `tipitaka-app/my-android.db` (`♦ချုပ်` / `♦ချုပ`)                                                   | None                                                                                                                                              |
| 6   | `visuddharama-abhidhana` | **ဝိသုဒ္ဓါရုံ ပိဋကအဘိဓာန်** — မဟာဝိသုဒ္ဓါရုံဂဏဝါစကအဖွဲ့                      | `lexicon`        | `tipitaka-app/my-android.db` (`♦ဝိ`, `♦ဝိသုဒ္ဓါရုံ`, verified untagged segments)                       | None                                                                                                                                              |
| 7   | `sutethana-thayokpya`    | **သုတေသနသရုပ်ပြအဘိဓာန်** — ဖျာပုံတိုက်သစ်ဆရာတော် အရှင်ဩဘာသာဘိဝံသ             | `topical`        | `pndaza/tupya.db`                                                                                | `pndaza/tupya_words.db`                                                                                                                           |
| 8   | `pitaka-thayokson`       | **ပိဋကတ်သုံးပုံ သရုပ်စုံအဘိဓာန်** — စိန်ရတနာဆရာတော် ဘဒ္ဒန္တသာသနဝရ & ဓမ္မဗိမာန်အဖွဲ့ | `topical`        | `pndaza/sarupa.db`                                                                               | `pndaza/pitaka_sarupa_android.db`                                                                                                                 |
| 9   | `pitaka-vatthu-lamnyun`  | **ပိဋကဝတ္ထုလမ်းညွှန်** — Ven. Indobhāsa (`Pitaka Guide`)            | `story`          | `pndaza/vatthuguide.db` (Zawgyi `content` → Unicode)                                             | None                                                                                                                                              |
| 10  | `pitaka-lamnyun`         | **ပိဋကလမ်းညွှန် (အတွဲ ၁–၃)** — ဆရာတော် ဦးသီဟဗလ                        | `index_only`     | `pndaza/pitakaguide.db` + `pndaza/pitaka_guide_topic.csv`                                        | None                                                                                                                                              |
| 11  | `u-hoke-sein-mep`        | **အများသုံး မြန်မာ-အင်္ဂလိပ်-ပါဠိ အဘိဓာန်** — ဦးဟုတ်စိန်                   | `reverse_my_pli` | `pndaza/mep.db` (has `page_number`; cross-check 4,383 extra rows in `tipitaka_pali.db` `book=8`) | None                                                                                                                                              |

_(Optional Stage 6/7 auxiliary module: `pali_lemmatizer` built from permissive stem/compound breakup tables in `tipitaka-pali-reader/tipitaka_pali.db` (`dpr_stem`, `dpr_breakup`) and `pndaza/palinlp2/`, plus `freococo/pali-words-myanmar-script.jsonl` (`CC0-1.0`). Keep `dpd/dpd.db` strictly out of permissive builds due to DPD's non-commercial license.)_

---

## 3. Shared Schema Specification (SQLite & JSONL)

Using **one shared core schema** across every `<source_id>.db` and `pali-myanmar-master.db` — with `extra_json` carrying book-specific attributes — keeps per-source specifics intact while making master compilation a trivial `ATTACH DATABASE` + `INSERT`.

### 3.1 SQLite DDL

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE sources (
  source_id        TEXT PRIMARY KEY,
  title_my         TEXT NOT NULL,
  title_pali_en    TEXT,
  author_my        TEXT,
  pub_year         TEXT,
  entry_kind       TEXT NOT NULL CHECK (entry_kind IN (
                     'lexicon', 'dhatu_root', 'topical', 'story', 'index_only', 'reverse_my_pli'
                   )),
  volume_count     INTEGER NOT NULL DEFAULT 1,
  license_id       TEXT NOT NULL,    -- 'winmetta-pd-decision' | 'CC-BY-SA-4.0' | 'CC0-1.0'
  license_note     TEXT NOT NULL,
  upstream_url     TEXT NOT NULL,
  priority_rank    INTEGER NOT NULL
);

CREATE TABLE source_volumes (
  source_id        TEXT NOT NULL REFERENCES sources(source_id),
  volume_code      TEXT NOT NULL,    -- e.g. '01', '4a', '14c', '25'
  volume_number    INTEGER,          -- 1..25
  part_number      TEXT,             -- '1', '2', '3' where applicable
  title_my         TEXT,
  headword_range   TEXT,
  pdf_page_offset  INTEGER,
  PRIMARY KEY (source_id, volume_code)
);

CREATE TABLE entries (
  id               INTEGER PRIMARY KEY,
  source_id        TEXT NOT NULL REFERENCES sources(source_id),
  entry_type       TEXT NOT NULL CHECK (entry_type IN (
                     'pali_term', 'pali_root', 'topic', 'story', 'index_ref', 'myanmar_term'
                   )),

  -- Normalized lookup keys
  headword         TEXT NOT NULL,    -- display headword in canonical Myanmar Unicode
  headword_norm    TEXT NOT NULL,    -- loose lookup key (unstacked / tall-aa folded / zero-width stripped)
  headword_iast    TEXT,             -- IAST Roman Pāḷi (NULL for Burmese-only headwords)
  homonym_no       INTEGER,          -- e.g. 1, 2 when numbered in the source

  -- Grammatical & morphological fields
  pos              TEXT,             -- e.g. 'ပု', 'ထီ', 'န', 'တိ', 'ကြိ', 'ဗျ'
  etymology        TEXT,             -- viggaha / morpheme breakdown, e.g. 'စက္က+အ' or '√စက+ဩရ'
  root_pali        TEXT,             -- Pāḷi dhātu root, e.g. '√စက'

  -- Definition payload
  definition_text  TEXT,             -- clean Myanmar Unicode text (NULL only for index_ref)
  senses_json      TEXT,             -- JSON array of structured senses when parsed
  english_gloss    TEXT,             -- separated English/botanical glosses (U Hoke Sein, MEP)

  -- Volume & page provenance
  volume_code      TEXT,
  printed_page     INTEGER,
  printed_page_end INTEGER,
  pdf_page         INTEGER,

  -- Citations, book-specific fields & quality/license tier
  citations_json   TEXT,             -- JSON array of canonical scripture/grammar citations
  extra_json       TEXT,             -- JSON object for source-specific fields (gaṇa class, tags, pli_equivalents, etc.)
  quality          TEXT NOT NULL CHECK (quality IN ('proofed', 'ocr')),
  license_id       TEXT NOT NULL,    -- per-row license ('winmetta-pd-decision' vs 'CC-BY-SA-4.0' in hybrid tipitaka-abhidhana)
  content_hash     TEXT NOT NULL,    -- SHA-256 of canonical (source_id, headword, homonym_no, pos, etymology, definition_text, volume_code, printed_page)

  UNIQUE (source_id, content_hash)
);

CREATE INDEX idx_entries_headword      ON entries(headword);
CREATE INDEX idx_entries_headword_norm ON entries(headword_norm);
CREATE INDEX idx_entries_iast          ON entries(headword_iast);
CREATE INDEX idx_entries_source_vol    ON entries(source_id, volume_code, printed_page);

CREATE VIRTUAL TABLE entries_fts USING fts5(
  headword,
  headword_norm,
  headword_iast,
  definition_text,
  content='entries',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 0'
);
```

### 3.2 JSONL Export Record Format

Each `<source_id>.jsonl` emits one UTF-8 JSON object per `entries` row (sorted deterministically by `headword`, `homonym_no`, `printed_page`, `content_hash`), omitting `id` and expanding `senses_json`, `citations_json`, and `extra_json` as native JSON arrays/objects so downstream developers in Python, Rust, Go, or JavaScript can ingest them without parsing nested JSON strings.

---

## 4. Text Normalization & Transliteration Rules

1. **Zawgyi Detection & Conversion:** convert known Zawgyi columns (`vatthuguide.content`, `pitakaguide.tags`/`ranges`, `pm3` hyphenated headwords) by invoking [`winmetta-platform/packages/myanmar-convert/src/index.ts`](https://github.com/winmetta/winmetta-platform/blob/main/packages/myanmar-convert/src/index.ts) (`convert` and `detect` via Node 24 batch worker over JSONL stdin/stdout), and run a post-conversion detector check asserting `0` remaining Zawgyi code-point patterns (`U+1060`–`U+1097`, leading `U+1031`, malformed kinzi).
2. **Sinhala → Myanmar Pāḷi Transliteration (`my-android.db`):**
   - Map Sinhala Pāḷi vowels, consonants, virama (`්` `U+0DCA` → `္` `U+1039`), and anusvara (`ං` `U+0D82` → `ံ` `U+1036`, or kinzi `င်္` before velars `က/ခ/ဂ/ဃ/င` where standard Myanmar Pāḷi orthography writes kinzi, e.g., `අංකුර` → `အင်္ကုရ`, verified against `freococo/pali-words-myanmar-script.jsonl` and `abidan_new.db`).
   - Apply tall `ါ` (`U+102B`) vs. standard `ာ` (`U+102C`) contextually per `burmese-pali-orthography` rules (`ါ` after unclustered `ခ, ဂ, င, ဒ, ပ, ဝ`, except where subscripted/medialed).
3. **Canonical Myanmar Syllable Ordering:** normalize every syllable to `Base → Subscript (U+1039 + C) → Medials (ျ ြ ွ ှ) → ေ (U+1031) → Upper/Lower (ိ ီ ဲ / ု ူ) → ံ (U+1036) → ါ/ာ → Final+် → Tone (့ း)` and strip `U+200B` / `U+200C` / `U+FEFF`.
4. **Loose Search Key (`headword_norm`):** fold `ါ`→`ာ`, `ဉ`/`ဥ` equivalence at syllable boundaries (note NFC already normalizes decomposed `ဥ`+`ီ` `U+1025 U+102E` to `ဦ` `U+1026`), strip hyphens/spaces, and flatten stacked virama `U+1039` → `U+103A` (or bare consonant sequence) so learners typing unstacked `ပဉဟ` or `သမ္မာ` variants still match `ပဉှ` and `သမ္မာ`.

---

## 5. Implementation Stages

### Stage 0: Repository Scaffold, Tooling & Raw Cache Checksums

- **Deliverables:**
  - Initialize repo structure (`src/`, `scripts/`, `schemas/`, `tests/`, `docs/`), `mise.toml` (pinning current Python 3 / Node LTS as verified at implementation time), and pre-commit / CI lint checks.
  - Write `scripts/verify-cache.py` to verify presence, file sizes, and SHA-256 checksums of the primary upstream files in `.cache/pali-dictionary/`.
  - Create `schemas/sqlite-schema.sql` and JSON Schema `schemas/entry.schema.json`.
- **Exit criteria:** `verify-cache` passes against `.cache/pali-dictionary/`; empty schema builds cleanly in SQLite and passes schema tests.

### Stage 1: Myanmar Unicode Normalization, Pāḷi Transliteration & HTML Parser Library

- **Deliverables:**
  - Canonical Myanmar Unicode normalizer + validator enforcing `burmese-pali-orthography` rules and rejecting any residual Zawgyi sequences.
  - Deterministic Pāḷi script transliterator: `Sinhala ↔ Myanmar ↔ IAST Roman` (including kinzi `င်္`, `ဉာ`/`ည`/`ဉ္ဇ`, `ဋ္ဌ`, `ဍ္ဎ`, `ဿ`, and tall `ါ` context rules), validated against the `221,154` `(Myanmar, IAST)` pairs in `abidan_new.db` + `bthar-mx`.
  - Clean HTML/text parser for `pndaza/tipitaka_pali.db` (`<p class="word">`, `<span class="gender">`, `<div class="viggaha">`, `<ul><li>`, `<p class="reference">`, `<p class="source">`) and `my-android.db` (`+` / `♦` segment splitter).
- **Exit criteria:** ≥99.5% round-trip accuracy on known Myanmar↔IAST/Sinhala headword pairs; 100% unit test coverage on tricky ligatures, kinzi, tall `ါ`, and Zawgyi edge cases.

### Stage 2: Per-Book ETL — Clean Single-Book Pāḷi→Burmese Lexicons

- **Targets:**
  1. `u-hoke-sein.db` & `.jsonl` (`60,782` rows from `pndaza/tipitaka_pali.db` `book=2`, separating `english_gloss` from Burmese `definition_text` and enriching `compound_hyphenated` from `pm3`).
  2. `dhatuattha-pankone.db` & `.jsonl` (`11,086` rows from `book=3`, extracting `root_pali`, `viggaha`, grammar citations, and Burmese glosses).
  3. `pali-dhatu-abhidhana.db` & `.jsonl` (`1,894` rows from `book=4`, extracting `gana_classes`, Pāḷi sense locatives, Burmese root meanings, and sample verbs).
- **Exit criteria:** All 3 SQLite DBs and JSONL files build deterministically with 0 Zawgyi characters, 0 HTML tags in `definition_text`, and verified row/headword counts.

### Stage 3: Per-Book ETL — `my-android.db` Unique Lexicons

- **Targets:**
  1. `pali-abhidhana-chok.db` & `.jsonl` (`~13,745` `♦ချုပ်` segments, Sinhala headwords transliterated to Myanmar Unicode + cross-checked against known Pāḷi headword lists).
  2. `visuddharama-abhidhana.db` & `.jsonl` (`3,135` `♦ဝိ`/`♦ဝိသုဒ္ဓါရုံ` segments + rule-verified untagged segments matching the Visuddhārāma template, flagged with `inferred_untagged` in `extra_json`).
- **Exit criteria:** Sinhala→Myanmar headword transliteration audited on all out-of-vocabulary headwords; zero `♦မြ` or `♦စိန်` leakage into either DB.

### Stage 4: Book-Group ETL — 29-Book `tipitaka-abhidhana.db`

- **Targets:**
  - Build `source_volumes` for all 29 books (`01..03, 4a..4c, 05..14, 14b, 14c, 15..25`) with `pdf_page_offset`.
  - Ingest `pndaza/tipitaka_pali.db` `book=1` (`proofed`), collapsing the `17,140` unstacked alias duplicates onto their canonical `<p class="word">` headwords and discarding `"မူရင်း...၌ ကြည့်ပါ"` / `"ဖတ်မရပါ"` stubs.
  - Attach `volume_code`, `printed_page`, and `pdf_page` using embedded `တိပိ၊<vol>၊<page>` citations, `<p class="source">`, `abidan_new.db`, and `bthar-mx`.
  - Fill missing books (`14c`, `20`, `21`, `24`, `25`, plus missing entries in `4c` and `14b`) from `bthar-mx/ocr/*/articles.jsonl` with `quality = 'ocr'` and `license_id = 'CC-BY-SA-4.0'`.
  - Support a `--proofed-only` build flag so users who want a pure `winmetta-pd-decision` build (without CC BY-SA 4.0 OCR rows) can generate `tipitaka-abhidhana-proofed.db` with one flag.
- **Exit criteria:** Coverage report across all 29 books matches expected ~208k–221k entries; page numbers spot-checked against PDFs.

### Stage 5: Per-Book ETL — Topical, Story, Concordance & Reverse Dictionaries

- **Targets:**
  1. `sutethana-thayokpya.db` & `.jsonl` (`2,269` topical entries from `tupya.db`).
  2. `pitaka-thayokson.db` & `.jsonl` (`6,984` enumerative entries + canonical citations from `sarupa.db`).
  3. `pitaka-vatthu-lamnyun.db` & `.jsonl` (`3,005` story entries from `vatthuguide.db`, Zawgyi `content` converted to Unicode).
  4. `pitaka-lamnyun.db` & `.jsonl` (`18,398` 3-volume index entries + category tags from `pitakaguide.db` & `pitaka_guide_topic.csv`).
  5. `u-hoke-sein-mep.db` & `.jsonl` (`71,427` Burmese→English→Pāḷi rows with `page_number` from `mep.db`, plus reconciled extra rows from `tipitaka_pali.db` `book=8`).
- **Exit criteria:** All 5 DBs pass Unicode, citation, and schema validation checks.

### Stage 6: Master Database Compiler, FTS5 Index & Pāḷi Lemmatizer

- **Deliverables:**
  - `scripts/compile-master.py`: attaches the selected per-source SQLite DBs, populates `sources`, `source_volumes`, `entries`, and `entries_fts`, and builds `pali_lemmatizer` (permissive Myanmar-script inflection→lemma & sandhi breakup lookup from `dpr_stem` / `dpr_breakup` / `palinlp2` / `freococo`).
  - Produce two master variants if needed:
    1. `pali-myanmar-master.db` (all sources, including `CC-BY-SA-4.0` OCR gap-fills in `tipitaka-abhidhana`, clearly labeled).
    2. `pali-myanmar-master-pd.db` (`winmetta-pd-decision` & `CC0-1.0` rows only).
  - Golden query test suite verifying exact lookup, loose/unstacked lookup, Roman IAST lookup, inflected Pāḷi lookup, and multi-book attribution ordering (`VACUUM` + `ANALYZE` + `PRAGMA integrity_check`).
- **Exit criteria:** Sub-10ms local lookup latency across ~350k+ rows; all golden tests pass.

### Stage 7: Release Packaging, Documentation & Checksums

- **Deliverables:**
  - Compress every `<source_id>.db`, `<source_id>.jsonl`, and `pali-myanmar-master*.db` with `zstd -19` (`.zst`), generate `SHA256SUMS` and `manifest.json` (row counts, byte sizes, SHA-256, license per file), and write `DATA-LICENSES.md`.
  - Publish `v0.1.0` via `gh release create` on `winmetta/pali-myanmar-dictionaries` with a small helper script (`scripts/download-release.sh`) for downstream apps (including `winmetta-platform`).
- **Exit criteria:** Clean download + checksum verification from public GitHub Release URLs without authentication.

---

## 6. Large-File Storage & Distribution Decision

| Option                                         | Cost & Quota                                                                                                        | Developer / CI Experience                                                                                                                                                           | Verdict                                                                       |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **GitHub Releases (`.db.zst` / `.jsonl.zst`)** | **Free & unmetered bandwidth** on public repos; max **2 GiB per asset**, unlimited assets per release.              | Direct, immutable HTTPS URLs (`releases/download/v0.1.0/...`); works with plain `curl -fLO`; keeps `git clone` `< 1 MB`; built-in SHA-256 digests.                                  | **Recommended Primary** (same model used by `tipitakapali.org` and `dpd-db`). |
| **Git LFS**                                    | Metered against **repo owner's** quota (**10 GiB/month** free bandwidth & storage on GitHub Free; 250 GiB on Team). | Once external users/bots clone 10 GiB in a month, GitHub blocks all LFS clones (`This repository is over its data quota`) or bills overages; old DB rebuilds bloat storage forever. | **Do NOT use.**                                                               |
| **Google Drive**                               | Uses Google Workspace storage; undocumented ~24h per-file download rate-limit lockouts on popular files.            | Files `>100 MB` return an HTML virus-scan confirmation page (`uuid=` token) that breaks `curl`/`wget` scripts; no version tags; tied to account/folder lifecycle.                   | **Do NOT use as primary** (optional manual backup only).                      |
| **Hugging Face Datasets**                      | Free public dataset hosting (up to 300 GB+, 50 GB/file), Git/HTTP/Parquet viewer.                                   | Great for Python/NLP users (`load_dataset`) and browser SQL preview over `.jsonl` / Parquet.                                                                                        | **Recommended Optional Mirror** for the `.jsonl` files once Stage 7 ships.    |
