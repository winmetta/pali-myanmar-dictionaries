-- Shared relational + FTS5 schema for per-source SQLite DBs (<source_id>.db)
-- and the compiled master database (pali-myanmar-master.db).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  source_id        TEXT PRIMARY KEY,
  title_my         TEXT NOT NULL,
  title_pali_en    TEXT,
  author_my        TEXT,
  pub_year         TEXT,
  entry_kind       TEXT NOT NULL CHECK (entry_kind IN (
                     'lexicon', 'dhatu_root', 'topical', 'story', 'index_only', 'reverse_my_pli'
                   )),
  volume_count     INTEGER NOT NULL DEFAULT 1 CHECK (volume_count >= 1),
  license_id       TEXT NOT NULL,
  license_note     TEXT NOT NULL,
  upstream_url     TEXT NOT NULL,
  priority_rank    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_volumes (
  source_id        TEXT NOT NULL REFERENCES sources(source_id),
  volume_code      TEXT NOT NULL,
  volume_number    INTEGER,
  part_number      TEXT,
  title_my         TEXT,
  headword_range   TEXT,
  pdf_page_offset  INTEGER,
  PRIMARY KEY (source_id, volume_code)
);

CREATE TABLE IF NOT EXISTS entries (
  id               INTEGER PRIMARY KEY,
  source_id        TEXT NOT NULL REFERENCES sources(source_id),
  entry_type       TEXT NOT NULL CHECK (entry_type IN (
                     'pali_term', 'pali_root', 'topic', 'story', 'index_ref', 'myanmar_term'
                   )),
  headword         TEXT NOT NULL,
  headword_norm    TEXT NOT NULL,
  headword_iast    TEXT,
  homonym_no       INTEGER,
  pos              TEXT,
  etymology        TEXT,
  root_pali        TEXT,
  definition_text  TEXT,
  senses_json      TEXT,
  english_gloss    TEXT,
  volume_code      TEXT,
  printed_page     INTEGER,
  printed_page_end INTEGER,
  pdf_page         INTEGER,
  citations_json   TEXT,
  extra_json       TEXT,
  quality          TEXT NOT NULL DEFAULT 'proofed' CHECK (quality IN ('proofed', 'ocr')),
  license_id       TEXT NOT NULL,
  content_hash     TEXT NOT NULL,
  UNIQUE (source_id, content_hash),
  FOREIGN KEY (source_id, volume_code) REFERENCES source_volumes(source_id, volume_code)
);

CREATE INDEX IF NOT EXISTS idx_entries_headword      ON entries(headword);
CREATE INDEX IF NOT EXISTS idx_entries_headword_norm ON entries(headword_norm);
CREATE INDEX IF NOT EXISTS idx_entries_iast          ON entries(headword_iast);
CREATE INDEX IF NOT EXISTS idx_entries_source_vol    ON entries(source_id, volume_code, printed_page);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
  headword,
  headword_norm,
  headword_iast,
  definition_text,
  content='entries',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 0'
);

CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
  INSERT INTO entries_fts(rowid, headword, headword_norm, headword_iast, definition_text)
  VALUES (new.id, new.headword, new.headword_norm, new.headword_iast, new.definition_text);
END;

CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, headword, headword_norm, headword_iast, definition_text)
  VALUES ('delete', old.id, old.headword, old.headword_norm, old.headword_iast, old.definition_text);
END;

CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
  INSERT INTO entries_fts(entries_fts, rowid, headword, headword_norm, headword_iast, definition_text)
  VALUES ('delete', old.id, old.headword, old.headword_norm, old.headword_iast, old.definition_text);
  INSERT INTO entries_fts(rowid, headword, headword_norm, headword_iast, definition_text)
  VALUES (new.id, new.headword, new.headword_norm, new.headword_iast, new.definition_text);
END;
