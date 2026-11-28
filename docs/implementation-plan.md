# Implementation Plan: `pali-myanmar-dictionaries`

| Field     | Value                                                                                                                                                                                               |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Status    | Stages 0–2 complete; Stage 3 `my-android.db` unique lexicons built and validated (`stage3-v1`); ready for Stage 4 (`tipitaka-abhidhana`).                                                           |
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
  quality          TEXT NOT NULL CHECK (quality IN ('proofed', 'ocr', 'incomplete')),
  license_id       TEXT NOT NULL,    -- per-row license ('winmetta-pd-decision' vs 'CC-BY-SA-4.0' in hybrid tipitaka-abhidhana)
  content_hash     TEXT NOT NULL,    -- SHA-256 of canonical base tuple plus source-specific supplemental payload

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
  tokenize='unicode61 remove_diacritics 0 categories ''L* N* Co M*'''
);
```

### 3.2 JSONL Export Record Format

Each `<source_id>.jsonl` emits one UTF-8 JSON object per `entries` row (sorted deterministically by `headword`, `homonym_no`, `printed_page`, `content_hash`), omitting `id` and expanding `senses_json`, `citations_json`, and `extra_json` as native JSON arrays/objects so downstream developers in Python, Rust, Go, or JavaScript can ingest them without parsing nested JSON strings.

The canonical hash base tuple is `(source_id, headword, homonym_no, pos,
etymology, definition_text, volume_code, printed_page)`. Stage 2 appends a
deterministic JSON encoding of its remaining parsed fields, including the English
gloss and source-specific payload, before hashing. This preserves entries whose
base tuple matches but whose English gloss or other extracted content differs.
Each extractor must document its supplemental fields and compare complete records
before treating a repeated hash as a duplicate.

---

## 4. Text Normalization & Transliteration Rules

1. **Zawgyi Detection & Conversion:** convert known Zawgyi columns (`vatthuguide.content`, `pitakaguide.tags`/`ranges`, `pm3` hyphenated headwords) using `convert` and `detect` from [`@winmetta/myanmar-convert`](https://github.com/winmetta/winmetta-platform/tree/main/packages/myanmar-convert), and run a post-conversion detector check asserting `0` remaining Zawgyi code-point patterns (`U+1060`–`U+1097`, leading `U+1031`, malformed kinzi). The current Python bridge uses a Node worker; replace its sibling-checkout dependency with the reproducible package path described below.
2. **Sinhala → Myanmar Pāḷi Transliteration (`my-android.db`):**
   - Map Sinhala Pāḷi vowels, consonants, virama (`්` `U+0DCA` → `္` `U+1039`), and anusvara (`ං` `U+0D82` → `ံ` `U+1036`, or kinzi `င်္` before velars `က/ခ/ဂ/ဃ/င` where standard Myanmar Pāḷi orthography writes kinzi, e.g., `අංකුර` → `အင်္ကုရ`, verified against `freococo/pali-words-myanmar-script.jsonl` and `abidan_new.db`).
   - Apply tall `ါ` (`U+102B`) vs. standard `ာ` (`U+102C`) contextually per `burmese-pali-orthography` rules (`ါ` after unclustered `ခ, ဂ, င, ဒ, ပ, ဝ`, except where subscripted/medialed).
3. **Canonical Myanmar Syllable Ordering:** normalize every syllable to `Base → Subscript (U+1039 + C) → Medials (ျ ြ ွ ှ) → ေ (U+1031) → Upper/Lower (ိ ီ ဲ / ု ူ) → ံ (U+1036) → ါ/ာ → Final+် → Tone (့ း)` and strip `U+200B` / `U+200C` / `U+FEFF`.
4. **Loose Search Key (`headword_norm`):** fold `ါ`→`ာ`, `ဉ`/`ဥ` equivalence at syllable boundaries (note NFC already normalizes decomposed `ဥ`+`ီ` `U+1025 U+102E` to `ဦ` `U+1026`), strip hyphens/spaces, and flatten stacked virama `U+1039` → `U+103A` (or bare consonant sequence) so learners typing unstacked `ပဉဟ` or `သမ္မာ` variants still match `ပဉှ` and `သမ္မာ`.

### 4.1 Shared TypeScript package and migration

Initially develop a browser-compatible `@winmetta/pali-text` package in this
repository, alongside the corpus and validation tests. It will own reusable text
normalization, lookup-key generation, validation and Pāḷi transliteration. Keep
source-specific parsers and ETL, SQLite/JSONL generation, and release packaging in
this dictionary project. The dictionary builder consumes the package as an npm
workspace dependency; `winmetta-platform` consumes a versioned package release
with its dependency recorded in its lockfile. The package must run in browsers
without Node-only APIs or a dependency on raw dictionary data.

**Migration status:** the experimental workspace package currently ports Myanmar
normalization, loose lookup keys, and Myanmar/IAST/Sinhala transliteration. Local tests
compare those functions against Python on distinct Stage 2 source headwords and
compare the IAST conversions across all 221,764 BTHAR reference pairs. The
Sinhala-to-Myanmar output and cleanup also match Python on all 115,357 cached
`my-android.db` headwords. The experimental Stage 2 builder uses the package for
lookup keys through a Node worker. Remaining corpus-wide checks, reproducible
`myanmar-convert` distribution, and a versioned package release are still
outstanding. Its current Node type-stripping build uses an
experimental Node API and needs a stable, pinned TypeScript build tool before a
package release.

1. Define the public API and fixtures, then port the existing Python behavior to
   TypeScript incrementally. Keep the Python implementation and existing corpus
   tests during migration; compare both implementations on the same corpus and
   edge cases, investigate every difference, and record intentional changes.
2. Run the existing accuracy and Unicode gates against the TypeScript package,
   including the full local corpus checks, and exercise its public entry point in
   a browser-compatible test. The migration itself does not resolve the outstanding
   Sinhala accuracy/round-trip validation or mixed-encoding issues described in
   Stages 1 and 2; those remain separate acceptance requirements.
3. Establish a reproducible cross-repository consumption path for the currently
   private `@winmetta/myanmar-convert` package. Choose and document a versioned,
   immutable distribution or pinned package artifact, its build and integrity
   verification, and lockfile-based installation in a clean checkout and CI.
   Do not depend on a sibling checkout or its internal TypeScript source paths.
   Verify browser compatibility for any conversion functionality exposed by
   `pali-text`; keep Node-only build tooling outside its browser entry point.
4. Before publishing either package under `@winmetta`, verify npm scope ownership
   and obtain explicit approval for publishing. Until a release is available,
   validate the consumer integration against a reproducibly built, pinned package
   artifact rather than assuming registry access.
5. Record the exact `@winmetta/pali-text` version and artifact identity in the
   dataset manifest. Treat lookup-key behavior changes and regenerated datasets as
   matched releases: test package-generated keys against the corresponding SQLite
   and JSONL outputs, including exact, loose and IAST lookup cases, and verify that
   the platform uses the matching package and dataset versions.

#### Consumer requirements (added 2026-11-27 from the `winmetta-platform` design)

`winmetta-platform` will consume this package from two places: the Pāḷi
Dictionary mini app (the lookup key, now with a mock) and a generic input
package, `@winmetta/myanmar-input`, that lets a person type Burmese or Pāḷi in
Burmese script and returns clean Unicode (design in the platform's
`docs/myanmar-input.md` and `docs/pali-dictionary.md`). A later lookup service
or static-shard builder is a third consumer. The items below are what those
consumers need before they can depend on a release. They refine items 1–5
above (they do not replace them) and are numbered R1–R6.

- **R1. Separate entry points for the browser and the builder.** Expose subpath
  exports: `.` (normalization and the lookup key), `./translit` (Myanmar and
  IAST) and `./sinhala` (builder only, never imported by a browser), and set
  `"sideEffects": false`. Give the browser entry point a size budget, because
  the platform's web app enforces budgets on its search code and phones are a
  main audience. Roman IAST lookup is a Stage 6 feature, so `./translit` must
  stay browser-safe; Sinhala tables must not ship to browsers.
- **R2. Version the lookup key.** Export `HEADWORD_KEY_VERSION` (an integer) and
  write it to the dataset manifest, to each per-source and master database
  (for example a `meta` table), and to any shard index used for static lookup.
  A change to the key's behavior is a semver-major package change, bumps the
  key version and requires regenerated datasets and shards. A client that finds
  a key version different from the dataset it queries must stop and report the
  mismatch rather than silently miss entries. Test vectors for the key (pairs
  and groups that must collide, such as `ဓမ္မ` / `ဓမမ`, `ပဉှ` / `ပဉဟ`,
  `သင်္ဃ` / `သံဃ`, `သဿတ` / `သသသတ`) are generated from the Python
  implementation, committed as a fixture file and consumed by both this
  repository's tests and the platform's.
- **R3. A non-throwing canonicalizer that reports what it changed.** Keep
  `normalizeMyanmarText` strict for the builder (it throws on a Zawgyi marker).
  Add a tolerant function that never throws and returns the canonical text and a
  list of fix codes (for example `moved-e`, `reordered-marks`, `moved-stack`,
  `merged-nya-u`, `removed-zero-width`). User input needs this for its notices;
  the codes are data, never sentences. It must give the same text as the strict
  canonicalizer wherever that one does not throw, which a test enforces.
- **R4. A reproducible build and a release path that needs no account.**
  - Replace the experimental `stripTypeScriptTypes` step with a pinned
    compiler (`tsc`) that emits JavaScript and `.d.ts` files, so the compiled
    output does not depend on the Node version that built it.
  - Make `exports` resolve in a clean checkout. `dist/` is git-ignored for the
    datasets, so either build in `prepack` and point consumers only at the
    packed artifact, or move the package's output outside the ignored path. The
    `types` condition must point at the emitted `.d.ts`, not `src/`.
  - Commit `package-lock.json` (CI already runs `npm ci`).
  - Publish each release as a tarball from `npm pack`, attached to a GitHub
    Release of this repository (the same channel as the datasets). A consumer's
    lockfile pins it by URL and integrity hash, so no registry account or token
    is needed. Do not use GitHub Packages (it needs a token to read). Publishing
    to the npm registry stays a later, separately approved step (item 4).
  - Add a CI smoke test that packs the package, installs the tarball into an
    empty project and imports every public entry point, and a browser-runtime
    check of the browser entry point (item 2).
  - Record the git commit, package version and tarball integrity hash in the
    dataset manifest instead of only the SHA-256 of `dist/index.js`, which
    today depends on the build tool and the package version stays `0.0.0`.
- **R5. State the end of the Python key function.** The Stage 2 builder already
  computes lookup keys through the TypeScript package, so Python's
  `to_headword_norm` is a test oracle. Keep it as such, with the corpus
  comparison as a standing gate, and do not call it from production build
  paths. Remove it only after the TypeScript package has been released and the
  datasets regenerated with it.
- **R6. Dependency direction.** `@winmetta/pali-text` may depend on
  `@winmetta/myanmar-convert` (Zawgyi conversion) once that package has a
  pinned distribution (item 3). It must never depend on `@winmetta/myanmar-input`
  or on any application. The platform's input package depends on both.

**Lookup shards are keyed by the loose key (proposed, not decided).** If the
platform serves headword lookup as static files on a CDN, with an API fallback
for searching inside definitions, the files are split by the loose key
(`headword_norm`), not the display headword, so spelling variants such as `ဓမ္မ`,
`ဓမမ` and `ဓမ္မာ` fall in the same file. The shard scheme must be chosen and the
key frozen (R2) before shards are generated. Shard sizes have not been
measured: common starting syllables (`ဓမ္မ`, `သ`, `ပ`) may give uneven files at
about 350,000 entries, so measure on the compiled master database first. This
choice is open; Stage 6 should not assume it.

After the master database and JSONL files have been generated, revisit the
package's long-term home: a separate `winmetta/pali-text` repository or
`winmetta-platform`. (`@winmetta/myanmar-convert` lives in
`winmetta-platform/packages/`; there is no separate repository for it.) Decide
then based on the actual consumers, ownership and release workflow; neither move
is assumed now. Until then the key stays with the dataset, because its version
must travel with the data it indexes.

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

  **Validation status (2026-11-27):** the BTHAR corpus test checks 221,764 pairs:
  Myanmar-to-IAST matched 221,518 (99.889%) and IAST-to-Myanmar-to-IAST matched
  221,693 (99.968%). The TypeScript package now also converts Myanmar to Sinhala.
  For 53,020 Sinhala source headwords, Sinhala → Myanmar → Sinhala → Myanmar
  preserved the intermediate Myanmar form in every case. This measures stability,
  not accuracy against an independently verified Sinhala corpus.

  A separate U Hoke Sein source also embeds Myanmar headwords in its meanings.
  A test compares these with converted Sinhala headwords using the loose lookup key:
  52,932 of 52,951 extracted pairs match (99.964%) after applying the reviewed
  Myanmar Pāḷi house conventions for tall `ါ` and kinzi. The strict exact comparison
  remains 52,448 of 52,951 (99.050%).
  Removing only source hyphens and applying the existing canonical normalizer,
  52,448 pairs match exactly (99.050%). Their generated IAST forms match on 52,785
  pairs (99.687%); the latter shares a transliterator between both sides and is
  not an independent phonetic reference. Review of all 503 strict mismatches found
  336 tall-aa variants and 148 kinzi/anusvara variants. The output spelling follows
  the project's house rules: use standard `ာ` after stacked consonants or bases
  outside the tall-aa set, and kinzi before velars in Pāḷi. In all 336 tall-aa
  pairs the embedded reference uses tall `ါ` where that house style calls for
  standard `ာ` (311 follow a stack; 25 follow a base outside the tall-aa set).
  All 148 nasal variants are kinzi before a velar in the output and anusvara in
  the embedded reference. The 19 remaining pairs were reviewed: the generated
  form occurs as an exact headword in the independent `abidan_new.db` index in
  10 cases; the other nine embedded forms contain malformed or misplaced Myanmar
  sequences and were checked against the Sinhala spelling and Unicode syllable
  order. Their row IDs are 4872, 14686, 18374, 32204, 32569, 37396, 40454, 43900,
  and 51867. `scripts/audit-sinhala.py` reports the house-orthography comparison and
  emits the source row IDs and both forms for review;
  69 source rows do not have a headword in the extractable format.
  A cross-check of the 19 other mismatches against the cached `abidan_new.db`
  The variant-aware corpus score passes the ≥99.5% Stage 1 threshold; the strict
  exact score and lack of a native-reviewed Sinhala parallel corpus remain explicit
  limitations. The 69 unextractable rows are not included in the score.

### Stage 2: Per-Book ETL — Clean Single-Book Pāḷi→Burmese Lexicons

- **Targets:**
  1. `u-hoke-sein.db` & `.jsonl` (`60,782` rows from `pndaza/tipitaka_pali.db` `book=2`, separating `english_gloss` from Burmese `definition_text` and enriching `compound_hyphenated` from `pm3`).
  2. `dhatuattha-pankone.db` & `.jsonl` (`11,086` rows from `book=3`, extracting `root_pali`, `viggaha`, grammar citations, and Burmese glosses).
  3. `pali-dhatu-abhidhana.db` & `.jsonl` (`1,894` rows from `book=4`, extracting `gana_classes`, Pāḷi sense locatives, Burmese root meanings, and sample verbs).
- **Exit criteria:** All 3 SQLite DBs and JSONL files build deterministically with 0 Zawgyi characters, 0 HTML tags in `definition_text`, and verified row/headword counts.

  **Input audit (2026-11-27):** the primary Unicode HTML contains Zawgyi markers in
  95 book 2 and 68 book 3 definitions. Mixed strings are sometimes classified as
  `unsure` by the converter; blindly converting the whole string can corrupt Unicode
  Pāḷi. Resolve and test these cases before accepting a build. Book 4 has no detected
  markers in the upstream definitions. These counts use the current marker detector.
  A later parsed-row audit found 94 invalid book 2 rows and 44 invalid book 3 rows.
  Targeted kinzi repairs, accepted only against the row's lookup word or a listed
  exact headword elsewhere in the primary corpus, reduced the unresolved rows to
  23 and 40 respectively. Repairs are recorded in `extra`. Some book 3 source
  definitions end with a lone `ေ`; the same truncated text appears in the alternate
  `pmd_drive.db` digitization, so missing text is not reconstructed. For an
  unresolved glyph the experimental build inserts `�`, marks the row
  `quality = 'incomplete'`, and records the pre-masking parsed field's code points
  in `extra.incomplete_source_fragments`. Where the source header cannot be
  repaired, it uses the separate source lookup word and records that fallback.
  Thirteen further exact-term repairs are corroborated by clean occurrences in
  definitions of the same primary corpus; observed compounds preserve their
  surrounding text. Fourteen book 3 definitions have been restored from `♦မြ`
  segments in `my-android.db` that match the headword, grammatical analysis and,
  where present, the surrounding citation. Each restoration records the alternate
  source row, segment and original parsed code points. The latest build retains
  30 incomplete entries (6 book 2 and 24 book 3); those entries still need review
  and are not proofed definitions.
  A lookup of the six remaining incomplete U Hoke Sein entries in the cached
  `my-u-hoke-sein.db`, using the existing Sinhala transliterator and loose Myanmar
  key, found five candidate records for four headwords; all relevant definitions
  contain Zawgyi markers, one headword has a homonym candidate, and two have none.
  The corresponding `pmd_drive.db` rows repeat the same damaged fragments. No
  candidate supplies a clean, independently corroborated replacement.
  PM3 enrichment now converts known-Zawgyi headword candidates and attaches a
  unique match only when both Roman and Myanmar lookup keys agree, with source
  attribution. The current build enriches 31,258 output entries. The separate
  PM3 source's license has not been verified; enrichment is marked `unverified`
  per entry and requires a rights decision before distribution.
  `scripts/audit-pm3-overlap.py` compares the built enrichment with the primary
  source's parsed display headword: 31,178 enriched entries have identical
  hyphenation, 7 have different hyphenation, and 73 have no hyphen in the primary
  display headword. This identifies potential primary-source alternatives but does
  not establish PM3's license or authorize discarding its distinct readings.
  The parser-level audit also found 43 pairs of entries whose original hash tuple
  matched while their other parsed fields differed; the Stage 2 hash now includes
  those supplemental fields, and repeated hashes are checked before deduplication.
  Two fresh full builds (`stage2-release-v1` and `stage2-release-v1-repeat`)
  produced byte-identical SQLite and JSONL files:
  60,775 U Hoke Sein entries (58,195 display headwords; 3 incomplete; 0 PM3-enriched),
  11,073 Dhātuattha entries (9,543 display headwords; 3 incomplete), and 1,894 Pāḷi
  Dhātu entries (1,882 headwords; 0 incomplete). Counts differ from upstream
  lookup-word counts because display headwords are parsed and exact duplicates
  are collapsed. `scripts/validate-stage2.py` checks integrity, attribution,
  Unicode, FTS, JSONL equivalence and repeat-build hashes, and writes
  `dist/stage2-release-v1/manifest.json`.

  **Stage 2 release-readiness review (2026-11-27):**
  - **Incomplete entries (30 → 6):** 24 of the 30 previously incomplete entries
    were resolved with corpus-verified evidence:
    - 7 via `src/pali_myanmar_dicts/mixed_encoding.py` (`√ဥႌဟ်` → `√ဦဟ်` in
      `သမုပဗျူဠှ`, `ေဩာ်` → `ဪ` in `အဟော` and `အာမန္တာ`, `ေ၀၀စန`/`ေ၀၀စနေ` →
      `ဝေဝစန`/`ဝေဝစနေ` in `ဝိဝစန` and `ဝိဝိတ္တ`, `ဟိဂုႍ` → `ဟိင်္ဂုံ` in `ဟိင်္ဂုလ`,
      and `အဂုၤလိဖောတနဉ္စ` → `အင်္ဂုလိဖောတနဉ္စ` in `အစ္ဆရာ`).
    - 17 via exact `my-android.db` `♦မြ` restorations in
      `src/pali_myanmar_dicts/source_restorations.py` (bringing total `my-android.db`
      restorations to 31): `ကောလာဟလ`, `ဂဇ္ဇတိ`, `ဃောသတိ`, `ဃောသာပေတိ`, `ဃောသေတိ`,
      `ဇူတ` (`√ဇု+တ` and `√ဇုတ+အ`), `ဓရတိ`, `ပရိယုဒဉ္စန`, `ဖလတိ`, `သမုဂ္ဃောသယန္တ`,
      `သာဓက`, `အက္ခ`, `ဣဏာယက`, `ဥဒ္ဓါရ` (`ဥ√ဓရ+ဏ` and `ဥ√ဟရ+ဏ`), and `ဥန္နဒတိ`.
    - **6 remaining unrecoverable `quality = 'incomplete'` entries** (preserved
      with `U+FFFD` (``) and original code points in `extra.incomplete_source_fragments`):
      - `u-hoke-sein` (3): `ကောင်္ဉ္စီ` (primary `<p class="word">ကောဉ္စီၤ</p>` has
        trailing `U+1064` and corrupted lookup word `ကောင်္ဉ္စီ`), `ဗိမ္ဗ-ဇာလက-သဉ္ဆန္န`
        (`ရတ္တကုရကဝနေန` with `U+1064`, no exact primary-corpus match), and
        `သင်္ကုဥက` (both `<p class="word">သကုၤု-က</p>` and lookup word are corrupted).
      - `dhatuattha-pankone` (3): `ဃောသ` (`my-android.db` rowid 40486 only has the
        `ဃောသအက္ခရာ` entry), `သဋ` (`my-android.db` rowid 106833 only has
        `ကျင်နာကိုက်ခဲ၏။`), and `ဥဂ္ဃေါသတိ` (`my-android.db` has `ဥဂ္ဃေါသတိ` and
        `ဥဂ္ဃေါသာပေတိ`, but `ဥဂ္ဃေါသေတိ` rowid 19700 has no `♦မြ` segment).
  - **PM3 reuse rights:** `bksubhuti/Tipitaka-Pali-Projector` has no root
    `LICENSE` file and its 2018 terms do not grant reuse rights for PM3 (and
    99.74% of its hyphenated headwords already match `pndaza` primary display
    headwords). `scripts/build-stage2.py` and `src/pali_myanmar_dicts/stage2.py`
    now omit PM3 enrichment by default (`--include-pm3` / `--pm3` opt-in only),
    keeping the Stage 2 release build 100% `winmetta-pd-decision`.

  **Source leads (2026-11-27):** [Dhamma Download's book index](https://www.dhammadownload.com/Others-eBookInMyanmar.htm)
  links a [U Hoke Sein dictionary PDF](https://dhammadownload.com/File-Library/other/U-HoteSein-Parli-Myanmar-Dictionary.pdf).
  The PDF could not be fetched in this environment, so its edition, completeness,
  legibility, and relevance to the incomplete entries have not been verified.
  The [projector's Snap listing](https://snapcraft.io/install/tipitaka-pali-projector/arch)
  shows its license as unset; this does not establish rights for the PM3 data.
  The projector's 2018 [terms and credits](https://pdfhost.io/v/nU.ZPQ2Ti_Pi_Tipiaka_Projector_License_Note_version_10_20180501.pdf)
  say the app is for free distribution only and third-party materials may carry
  rights reserved by their owners. Those terms do not grant reuse rights for PM3.
  The GitHub repository has no root `LICENSE` file listed. PM3 remains
  `unverified` and must not be distributed until PM3-specific rights are confirmed
  or the enrichment is removed from the release build.

### Stage 3: Per-Book ETL — `my-android.db` Unique Lexicons

- **Targets:**
  1. `pali-abhidhana-chok.db` & `.jsonl` (`~13,745` `♦ချုပ်` segments, Sinhala headwords transliterated to Myanmar Unicode + cross-checked against known Pāḷi headword lists).
  2. `visuddharama-abhidhana.db` & `.jsonl` (`3,135` `♦ဝိ`/`♦ဝိသုဒ္ဓါရုံ` segments + rule-verified untagged segments matching the Visuddhārāma template, flagged with `inferred_untagged` in `extra_json`).
- **Exit criteria:** Sinhala→Myanmar headword transliteration audited on all out-of-vocabulary headwords; zero `♦မြ` or `♦စိန်` leakage into either DB.

  **Build status (2026-11-27):** `scripts/build-stage3.py` and `scripts/validate-stage3.py`
  (`stage3-v1` and `stage3-v1-repeat`) produced byte-identical SQLite and JSONL files:
  - `pali-abhidhana-chok`: `13,740` entries (`13,695` distinct headwords; `1` `incomplete`
    with `U+FFFD` masking; `0` `inferred_untagged`).
  - `visuddharama-abhidhana`: `9,287` entries (`9,189` distinct headwords; `24` `incomplete`
    with `U+FFFD` masking; `6,151` `inferred_untagged` matching the strict Visuddhārāma
    POS + numbered-sense template and excluding all `♦မြ`/`♦စိန်` patterns).
  - `tests/test_stage3.py` verifies segment parsing, untagged filtering, deduplication,
    zero `♦မြ`/`♦စိန်` leakage, and byte-for-byte repeat-build reproducibility.

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
  - A master compiler: attaches the selected per-source SQLite DBs, populates `sources`, `source_volumes`, `entries`, and `entries_fts`, and builds `pali_lemmatizer` (permissive Myanmar-script inflection→lemma & sandhi breakup lookup from `dpr_stem` / `dpr_breakup` / `palinlp2` / `freococo`). Keep this dataset-specific compiler in this repository as the builder migrates to TypeScript.
  - Produce two master variants if needed:
    1. `pali-myanmar-master.db` (all sources, including `CC-BY-SA-4.0` OCR gap-fills in `tipitaka-abhidhana`, clearly labeled).
    2. `pali-myanmar-master-pd.db` (`winmetta-pd-decision` & `CC0-1.0` rows only).
  - Golden query test suite verifying exact lookup, loose/unstacked lookup, Roman IAST lookup, inflected Pāḷi lookup, and multi-book attribution ordering (`VACUUM` + `ANALYZE` + `PRAGMA integrity_check`).
- **Exit criteria:** Sub-10ms local lookup latency across ~350k+ rows; all golden tests pass.

### Stage 7: Release Packaging, Documentation & Checksums

- **Deliverables:**
  - Compress every `<source_id>.db`, `<source_id>.jsonl`, and `pali-myanmar-master*.db` with `zstd -19` (`.zst`), generate `SHA256SUMS` and `manifest.json` (row counts, byte sizes, SHA-256, license per file, and the exact `pali-text` version and artifact identity used), and write `DATA-LICENSES.md`.
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
