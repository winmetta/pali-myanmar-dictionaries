# pali-myanmar-dictionaries

Open, normalized **Myanmar Unicode** Pāḷi–Myanmar (ပါဠိ-မြန်မာ) and Theravāda Buddhist reference dictionary datasets — packaged both as **per-book / per-book-group SQLite databases and JSONL files** and as one **compiled master SQLite + FTS5 database** with full source-book, volume, and page attribution.

Maintained by [Win Metta](https://winmetta.org/about/) so anyone building an offline, mobile, desktop, or web Pāḷi–Myanmar dictionary can use clean Unicode data without re-solving Zawgyi conversion, Sinhala/Roman script transliteration, cross-dump deduplication, or lost book provenance.

- **Implementation & schema specification:** [docs/implementation-plan.md](docs/implementation-plan.md)
- **Research & upstream audit:** [`Pali-Myanmar-Dictionary-Research`](https://github.com/winmetta/winmetta-platform/wiki/Pali-Myanmar-Dictionary-Research) (in `winmetta-platform` wiki)

The shared `@winmetta/pali-text` package and Stage 2 builder are experimental.
To prepare the workspace for local tests or builds, run `npm ci` and then
`npm run build:pali-text`. Run `npm run test:pali-text` and
`PYTHONPATH=src python3 -m unittest discover -s tests -v` for the tests. The
Stage 2 builder accepts `--audit` to report invalid source rows as JSON Lines;
it refuses to build a source when its preflight validation fails. Corpus tests
require the local cache, and the Zawgyi bridge has additional dependencies
described in the implementation plan.

Stage 2 builds preserve the 6 unrecoverable source fragments as `U+FFFD` (`�`), mark affected
entries `incomplete`, and record the pre-masking parsed field (after any verified
repairs) as Unicode code points in `extra.incomplete_source_fragments`. PM3 enrichment
is omitted by default; only opt-in `--include-pm3` / `--pm3` builds carry unverified
PM3 data and must not be distributed until its rights are resolved.

---

## Planned Datasets (Per Source & Master)

Before compiling the unified master database (`pali-myanmar-master.db`), each printed dictionary or multi-volume dictionary series is built as its own standalone SQLite database (`<source_id>.db`) and JSON Lines export (`<source_id>.jsonl`):

### A. Core Pāḷi → Burmese Lexicons

| `source_id`              | Burmese Title             | Author / Compiler                                  | Scope                                                                |
| ------------------------ | ------------------------- | -------------------------------------------------- | -------------------------------------------------------------------- |
| `tipitaka-abhidhana`     | တိပိဋက ပါဠိ-မြန်မာ အဘိဓာန်      | သာသနာရေးဝန်ကြီးဌာန / မစိုးရိမ်စသည့် အဖွဲ့ ၅ ဖွဲ့ (1964–2023)     | 25 volumes (29 books), ~221,764 headwords with volume & page numbers |
| `u-hoke-sein`            | ပဒတ္ထမဉ္ဇူသာ ပါဠိ-မြန်မာ အဘိဓာန် | ဦးဟုတ်စိန် (U Hoke Sein, 1954–1959)                    | 4-part lexicon, ~58,144 headwords (60,782 entries)                   |
| `pali-abhidhana-chok`    | ပါဠိအဘိဓာန်ချုပ်               | လယ်တီပဏ္ဍိတ ဦးမောင်ကြီး (Ledi Paṇḍita U Maung Gyi, 1914) | ~13,745 concise Pāḷi–Burmese entries                                 |
| `dhatuattha-pankone`     | ဓာတွတ္ထပန်းကုံး                | အရှင်ကုမာရ (Ashin Kumāra)                             | ~9,553 headwords (11,086 root/derivation entries)                    |
| `visuddharama-abhidhana` | ဝိသုဒ္ဓါရုံ ပိဋကအဘိဓာန်           | မဟာဝိသုဒ္ဓါရုံဂဏဝါစကအဖွဲ့                                  | ~6,778 Pāḷi–Burmese entries (partial coverage)                       |
| `pali-dhatu-abhidhana`   | ပါဠိဓာတ်အဘိဓာန်               | ပါဠိပါမောက္ခ ဆရာဉာဏ် (Prof. Sayā Ñāṇ)                 | ~1,882 Pāḷi dhātu roots (1,894 entries)                              |

### B. Topical, Story & Concordance Reference Works

| `source_id`             | Burmese Title     | Author / Compiler                            | Scope                                                                    |
| ----------------------- | ----------------- | -------------------------------------------- | ------------------------------------------------------------------------ |
| `sutethana-thayokpya`   | သုတေသနသရုပ်ပြအဘိဓာန်   | ဖျာပုံတိုက်သစ်ဆရာတော် အရှင်ဩဘာသာဘိဝံသ                   | 2,269 numbered/topical Buddhist reference entries                        |
| `pitaka-thayokson`      | ပိဋကတ်သုံးပုံ သရုပ်စုံအဘိဓာန် | စိန်ရတနာဆရာတော် ဘဒ္ဒန္တသာသနဝရ နှင့် ဓမ္မဗိမာန်အဖွဲ့        | 6,984 canonical enumerative entries with citations                       |
| `pitaka-vatthu-lamnyun` | ပိဋကဝတ္ထုလမ်းညွှန်       | Ven. Indobhāsa (`Pitaka Guide` digitization) | 3,005 Jātaka and canonical narrative summaries                           |
| `pitaka-lamnyun`        | ပိဋကလမ်းညွှန် (အတွဲ ၁–၃) | ဆရာတော် ဦးသီဟဗလ (Sayadaw U Sīhabala)           | 3 volumes, 18,398 Tipiṭaka topic/phrase index entries with volume & page |

### C. Reverse Lexicon (Burmese → English → Pāḷi)

| `source_id`       | Burmese Title                 | Author / Compiler    | Scope                                                                 |
| ----------------- | ----------------------------- | -------------------- | --------------------------------------------------------------------- |
| `u-hoke-sein-mep` | အများသုံး မြန်မာ-အင်္ဂလိပ်-ပါဠိ အဘိဓာန် | ဦးဟုတ်စိန် (U Hoke Sein) | 71,427 Burmese headwords mapped to English and Pāḷi with page numbers |

---

## Distribution & Large-File Storage

Compiled `.db` and `.jsonl` files are **not** stored in plain Git commits or Git LFS:

- **Primary distribution — GitHub Releases:** versioned Zstandard-compressed assets (`<source_id>.db.zst`, `<source_id>.jsonl.zst`, `pali-myanmar-master.db.zst`, and `SHA256SUMS`) attached to tagged releases on this repository (free, unmetered public downloads, immutable version URLs, up to 2 GiB per asset).
- **Why not Git LFS or Google Drive?** Git LFS bills/throttles the repository owner's monthly bandwidth quota whenever external users clone a public repository, and Google Drive injects HTML virus-scan confirmation pages and 24-hour download rate limits on files over 100 MB. See [docs/implementation-plan.md §6](docs/implementation-plan.md#6-large-file-storage--distribution-decision) for the full comparison.

---

## Licensing & Attribution

- **Code, schemas, and build scripts:** [MIT License](LICENSE).
- **Compiled dictionary datasets:** each `source_id` records its exact upstream provenance and license in the `sources` table and release notes:
  - **`pndaza` digitizations:** upstream repositories contain no `LICENSE` file; treated as public domain by a documented Win Metta maintainer decision (2026-11-26) for traditional Burmese lexicographical works, crediting Ven. Paññadhaja (`pndaza`) and the upstream digitizers (Ven. Indobhāsa, Merit Sharer, PCED).
  - **`bthar-mx/tipitaka-abhidhana` (2026 OCR gap-fill & page mappings):** added segmentation, fields, and romanization are licensed under **CC BY-SA 4.0** by IEBH / BTHAR (underlying dictionary text belongs to the Masoeyein Board of Scholar-Elders and the Ministry of Religious Affairs). Required attribution: _"Tipiṭaka Pāḷi-Myanmā Abhidhāna — digitised, IEBH / BTHAR, [github.com/bthar-mx/tipitaka-abhidhana](https://github.com/bthar-mx/tipitaka-abhidhana)"_.
  - **`freococo/pali-words-myanmar-script`:** **CC0 1.0 Universal**.
  - **Auxiliary non-commercial tools (`dpd`):** Digital Pāḷi Dictionary is non-commercial (`dpdict.net`) and kept strictly separate from permissive/public-domain dictionary builds.
