"""Open Pāḷi–Myanmar dictionary normalization, schema, and compilation toolkit."""

from pali_myanmar_dicts.normalize import (
    canonicalize_myanmar_syllables,
    normalize_myanmar_text,
    to_headword_norm,
)
from pali_myanmar_dicts.schema import (
    compute_content_hash,
    init_sqlite_db,
    validate_jsonl_record,
)
from pali_myanmar_dicts.translit import (
    clean_sinhala_headword,
    iast_to_myanmar,
    myanmar_to_iast,
    sinhala_to_myanmar,
)
from pali_myanmar_dicts.zawgyi import (
    assert_zero_zawgyi,
    auto_zawgyi_to_unicode,
    detect_encoding,
    has_zawgyi_codepoint_marker,
    zawgyi_to_unicode,
    zawgyi_to_unicode_batch,
)

__all__ = [
    "assert_zero_zawgyi",
    "auto_zawgyi_to_unicode",
    "canonicalize_myanmar_syllables",
    "clean_sinhala_headword",
    "compute_content_hash",
    "detect_encoding",
    "has_zawgyi_codepoint_marker",
    "iast_to_myanmar",
    "init_sqlite_db",
    "myanmar_to_iast",
    "normalize_myanmar_text",
    "sinhala_to_myanmar",
    "to_headword_norm",
    "validate_jsonl_record",
    "zawgyi_to_unicode",
    "zawgyi_to_unicode_batch",
]
