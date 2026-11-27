-- Auxiliary morphological lookup table included in pali-myanmar-master.db
-- for resolving inflected Myanmar-script Pāḷi forms and sandhi compounds.

CREATE TABLE IF NOT EXISTS pali_lemmatizer (
  id             INTEGER PRIMARY KEY,
  inflected_my   TEXT NOT NULL,
  inflected_norm TEXT NOT NULL,
  inflected_iast TEXT,
  lemma_my       TEXT,
  breakup_my     TEXT,
  source_tag     TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_lemmatizer_unique
  ON pali_lemmatizer(inflected_my, COALESCE(lemma_my, ''), COALESCE(breakup_my, ''), source_tag);

CREATE INDEX IF NOT EXISTS idx_lemmatizer_inflected_my   ON pali_lemmatizer(inflected_my);
CREATE INDEX IF NOT EXISTS idx_lemmatizer_inflected_norm ON pali_lemmatizer(inflected_norm);
CREATE INDEX IF NOT EXISTS idx_lemmatizer_inflected_iast ON pali_lemmatizer(inflected_iast);
