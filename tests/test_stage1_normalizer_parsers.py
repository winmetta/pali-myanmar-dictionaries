"""Stage 1 unit tests: Zawgyi bridge, Myanmar normalizer, Pāḷi transliterator, and HTML parsers."""

from __future__ import annotations

import glob
import json
import re
import sqlite3
import unittest
from pathlib import Path

from pali_myanmar_dicts.normalize import (
    canonicalize_myanmar_syllables,
    normalize_myanmar_text,
    to_headword_norm,
)
from pali_myanmar_dicts.parsers import (
    parse_dhatuattha_html,
    parse_pali_dhatu_html,
    parse_tipitaka_abhidhana_html,
    parse_u_hoke_sein_html,
    split_my_android_segments,
)
from pali_myanmar_dicts.translit import (
    clean_sinhala_headword,
    iast_to_myanmar,
    myanmar_to_iast,
    sinhala_to_myanmar,
)
from pali_myanmar_dicts.zawgyi import (
    MyanmarConvertBridge,
    assert_zero_zawgyi,
    auto_zawgyi_to_unicode,
    detect_encoding,
    get_default_bridge,
    has_zawgyi_codepoint_marker,
    zawgyi_to_unicode,
    zawgyi_to_unicode_batch,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / ".cache" / "pali-dictionary"
SINHALA_RE = re.compile(r"[\u0D80-\u0DFF]")


class Stage1ZawgyiAndNormalizerTests(unittest.TestCase):
    def test_zawgyi_bridge_converts_and_preserves_pali_unicode(self) -> None:
        zg_metta = "\u1031\u1019\u1010\u1071\u102c"
        self.assertTrue(has_zawgyi_codepoint_marker(zg_metta))
        info = detect_encoding(zg_metta)
        self.assertEqual(info.detected, "zawgyi")
        self.assertTrue(info.has_marker)

        converted = zawgyi_to_unicode(zg_metta)
        self.assertEqual(converted, "မေတ္တာ")
        assert_zero_zawgyi(converted)

        # Pure Unicode Pāḷi — including Great Sa + E (`တဿေဝ`, `အဿေသ`) — must never be corrupted
        for pali_uni in ("ဓမ္မစက္ကပ္ပဝတ္တနသုတ္တံ", "တဿေဝ", "အဿေသ"):
            self.assertNotEqual(detect_encoding(pali_uni).detected, "zawgyi")
            self.assertEqual(auto_zawgyi_to_unicode(pali_uni), pali_uni)

        self.assertEqual(
            get_default_bridge().auto_to_unicode_batch(["တဿေဝ", "အဿေသ", zg_metta]),
            ["တဿေဝ", "အဿေသ", "မေတ္တာ"],
        )

        # Mon-repurposed Zawgyi code points (`U+1033`, `U+1034`, `U+105A`) auto-convert cleanly
        zg_mon = "သံ၊\u1015\u105a၊၁၂။"
        converted_mon = auto_zawgyi_to_unicode(zg_mon)
        assert_zero_zawgyi(converted_mon)

        # Mostly-Unicode string with one stray Zawgyi typo stays 'unsure' (not blindly corrupted)
        mixed_uni = "(ဗုဒ္ဓ+ဗီဇ+အကု\u1064ရ) ဘုရားလောင်း။"
        self.assertEqual(detect_encoding(mixed_uni).detected, "unsure")
        self.assertEqual(auto_zawgyi_to_unicode(mixed_uni), mixed_uni)

        burmese_uni = "မြန်မာဘာသာဖြင့် ရေးသားထားသော အဘိဓာန်"
        self.assertEqual(detect_encoding(burmese_uni).detected, "unicode")
        assert_zero_zawgyi("မနုဿေဟိ ဘိက္ၑုက")

        batch = zawgyi_to_unicode_batch([zg_metta, "\u101e\u1001\u1064\u102b\u101b"])
        self.assertEqual(batch, ["မေတ္တာ", "သင်္ခါရ"])

        bridge = MyanmarConvertBridge()
        self.assertEqual(bridge.convert_batch([zg_metta]), ["မေတ္တာ"])
        proc = bridge._proc
        bridge.close()
        self.assertIsNotNone(proc)
        assert proc is not None and proc.stdout is not None and proc.stderr is not None
        self.assertTrue(proc.stdout.closed)
        self.assertTrue(proc.stderr.closed)

    def test_assert_zero_zawgyi_rejects_markers(self) -> None:
        with self.assertRaises(ValueError):
            assert_zero_zawgyi("\u1031မတ္တာ", context="leading-e")
        with self.assertRaises(ValueError):
            assert_zero_zawgyi("သခု\u1064ဘိတ", context="zawgyi-kinzi")

    def test_canonicalize_myanmar_syllables_and_headword_norm(self) -> None:
        scrambled = "က\u200b\u102c\u1031\u103cင\u1038\u103a"
        self.assertEqual(normalize_myanmar_text(scrambled, single_line=True), "ကြောင်း")

        # Subscript placed after medial/vowel (`ဣနြ္ဒိယ`, `သြ္တီ`, `ပိနဲ္န`) reorders before medial/vowel
        self.assertEqual(canonicalize_myanmar_syllables("ဣနြ္ဒိယ"), "ဣန္ဒြိယ")
        self.assertEqual(canonicalize_myanmar_syllables("ပိနဲ္န"), "ပိန္နဲ")
        self.assertEqual(canonicalize_myanmar_syllables("မင်္ဂလာ"), "မင်္ဂလာ")
        self.assertEqual(canonicalize_myanmar_syllables("ပဥှာ"), "ပဉှာ")
        self.assertEqual(canonicalize_myanmar_syllables("ဥာဏ်မျက်စိ"), "ဉာဏ်မျက်စိ")
        self.assertEqual(canonicalize_myanmar_syllables("သံယောဇဥ်"), "သံယောဇဉ်")

        # Loose headword_norm folds tall ါ, kinzi, ဿ, medial ှ -> ဟ, stacked virama, and ဉီး -> ဦး
        self.assertEqual(to_headword_norm("ဓမ္မ"), to_headword_norm("ဓမမ"))
        self.assertEqual(to_headword_norm("ပဉှ"), to_headword_norm("ပဉဟ"))
        self.assertEqual(to_headword_norm("စက္ကသမာရူဠှ"), to_headword_norm("စကကသမာရူဠဟ"))
        self.assertEqual(to_headword_norm("သင်္ဃ"), to_headword_norm("သံဃ"))
        self.assertEqual(to_headword_norm("ဥပ္ပါဒ"), to_headword_norm("ဥပ္ပာဒ"))
        self.assertEqual(to_headword_norm("သဿတ"), to_headword_norm("သသသတ"))
        self.assertEqual(to_headword_norm("ဉပေက္ခာ"), to_headword_norm("ဥပေက္ခာ"))
        self.assertEqual(to_headword_norm("လက်ဉီး"), to_headword_norm("လက်ဦး"))
        self.assertEqual(to_headword_norm("ဥာဏ"), to_headword_norm("ဉာဏ"))
        self.assertEqual(myanmar_to_iast("ဥာဏ"), "ñāṇa")
        self.assertEqual(to_headword_norm("ဉေယျ"), "ဉေယျ")
        assert_zero_zawgyi(to_headword_norm("ဉေယျ"))


class Stage1TransliterationTests(unittest.TestCase):
    def test_tricky_myanmar_iast_roundtrip_and_edge_cases(self) -> None:
        pairs = [
            ("ဗုဒ္ဓ", "buddha"),
            ("သင်္ခါရ", "saṅkhāra"),
            ("မင်္ဂလာ", "maṅgalā"),
            ("ပညာ", "paññā"),
            ("ဉာဏ", "ñāṇa"),
            ("ပဉှာ", "pañhā"),
            ("ကမ္မဋ္ဌာန", "kammaṭṭhāna"),
            ("အဂ္ဂိဒဍ္ဎ", "aggidaḍḍha"),
            ("ဒုဿ", "dussa"),
            ("သဒ္ဓါ", "saddhā"),
            ("ဒွါရ", "dvāra"),
            ("မဂ္ဂါ", "maggā"),
            ("သင်္ချာ", "saṅkhyā"),
            ("ဗြဟ္မစရိယ", "brahmacariya"),
            ("အစ္စောဂါဠှ", "accogāḷha"),
            ("ဣန္ဒြိယ", "indriya"),
            ("ဩဃ", "ogha"),
            ("သေယျ", "seyya"),
        ]
        for my_word, iast_word in pairs:
            with self.subTest(my_word=my_word):
                self.assertEqual(myanmar_to_iast(my_word), iast_word)
                self.assertEqual(iast_to_myanmar(iast_word), my_word)

        # BTHAR `ŭ` (`ñ`), `ို`, duplicate marks, and zero-width chars never leak U+1000..U+109F
        self.assertEqual(iast_to_myanmar("paripaŭhati"), "ပရိပဉှတိ")
        self.assertEqual(iast_to_myanmar("pasannapaŭcapasāda"), "ပသန္နပဉ္စပသာဒ")
        for noisy_my in ("ပုဂ္ဂိုလ်", "စက္ကာဘိဝုဍ္ဎိုကာမ", "သစ္စပါရမိီ", "ဩာသာရိတ", "ဝေနေယျဇ္ဈာသယာနုရ\u200bောဓ"):
            roman = myanmar_to_iast(noisy_my)
            self.assertIsNone(re.search(r"[\u1000-\u109F\u200B]", roman), msg=roman)

    def test_sinhala_to_myanmar_and_stray_cleanup(self) -> None:
        vocab = {"သံဃ", "အင်္ကုရ", "သင်္ခါရ", "အနုတ္တရံပုညခေတ္တံလောကဿ"}
        self.assertEqual(sinhala_to_myanmar("අංකුර", vocabulary=vocab), "အင်္ကုရ")
        self.assertEqual(sinhala_to_myanmar("සංඝ", vocabulary=vocab), "သံဃ")
        self.assertEqual(sinhala_to_myanmar("අකතඤ්ඤුතා"), "အကတညုတာ")
        self.assertEqual(sinhala_to_myanmar("අකප්පියසඤ්ඤා"), "အကပ္ပိယသညာ")
        self.assertEqual(sinhala_to_myanmar("අජ්ඣිට්ඨපඤ්හ"), "အဇ္ဈိဋ္ဌပဉှ")
        self.assertEqual(sinhala_to_myanmar("අග්ගද්වාර"), "အဂ္ဂဒွါရ")
        self.assertEqual(sinhala_to_myanmar("අංන්හික්ඛන්ධ"), "အနှိက္ခန္ဓ")
        # Upstream Sinhala conversion artifacts (`උ්`, `ඌ්`, `ේ`, `ආා`, `අො`, stray `්`)
        self.assertEqual(sinhala_to_myanmar("අතිප්පඋ්හ"), "အတိပ္ပဉှ")
        self.assertEqual(sinhala_to_myanmar("අකිඋ්චි"), "အကိဉ္စိ")
        self.assertEqual(sinhala_to_myanmar("විපඌ්ච"), "ဝိပဉ္စ")
        self.assertIsNone(SINHALA_RE.search(sinhala_to_myanmar("අන්තේයට්ඨි")))
        self.assertIsNone(SINHALA_RE.search(sinhala_to_myanmar("ආායතනච්ඡක්ක")))
        self.assertIsNone(SINHALA_RE.search(sinhala_to_myanmar("ස්රඞ්කාරඅොඞ්කාර")))
        self.assertIsNone(SINHALA_RE.search(sinhala_to_myanmar("්මාරම්මණ")))

        cleaned, notes = clean_sinhala_headword("අනුත්තරංපුඤ්ඤඛෙත්ත့ලොකස්ස")
        self.assertIn("repaired_dot_below", notes)
        self.assertEqual(
            sinhala_to_myanmar(cleaned, vocabulary=vocab),
            "အနုတ္တရံပုညခေတ္တံလောကဿ",
        )

    @unittest.skipUnless(
        (CACHE_DIR / "tipitaka-app" / "my-android.db").is_file(),
        "Raw my-android.db cache not present (CI environment)",
    )
    def test_all_115k_my_android_sinhala_headwords_convert_cleanly(self) -> None:
        conn = sqlite3.connect(str(CACHE_DIR / "tipitaka-app" / "my-android.db"))
        try:
            for (word,) in conn.execute("SELECT word FROM dictionary"):
                converted = sinhala_to_myanmar(word)
                self.assertIsNone(SINHALA_RE.search(converted), msg=f"{word!r} -> {converted!r}")
                assert_zero_zawgyi(converted, context=word)
        finally:
            conn.close()

    @unittest.skipUnless(
        (CACHE_DIR / "tipitaka-app" / "my-u-hoke-sein.db").is_file(),
        "Raw U Hoke Sein cache not present (CI environment)",
    )
    def test_sinhala_against_embedded_myanmar_headwords(self) -> None:
        """Measure transliteration against the separate headword in the source meaning."""
        conn = sqlite3.connect(str(CACHE_DIR / "tipitaka-app" / "my-u-hoke-sein.db"))
        total = matched = exact = roman_match = variant_equivalent = 0
        try:
            for sinhala, meaning in conn.execute("SELECT word, meaning FROM dictionary"):
                match = re.match(r"^([\u1000-\u103f\-]+)(?:\s|\()", meaning)
                if match is None:
                    continue
                total += 1
                converted = sinhala_to_myanmar(sinhala)
                if to_headword_norm(converted) == to_headword_norm(match[1]):
                    matched += 1
                expected = normalize_myanmar_text(match[1].replace("-", ""), check_zawgyi=False)
                normalized = normalize_myanmar_text(converted, check_zawgyi=False)
                if normalized == expected:
                    exact += 1
                    variant_equivalent += 1
                elif normalized.replace("ါ", "ာ") == expected.replace("ါ", "ာ"):
                    # The Myanmar reference does not follow the project's tall-aa house style.
                    variant_equivalent += 1
                elif normalized.replace("င်္", "ံ") == expected.replace("င်္", "ံ"):
                    # The project writes Pāḷi nasals before velars with kinzi.
                    variant_equivalent += 1
                if myanmar_to_iast(converted) == myanmar_to_iast(expected):
                    roman_match += 1
        finally:
            conn.close()
        self.assertGreater(total, 52_000)
        self.assertGreaterEqual(matched / total, 0.995, f"Matched {matched} of {total}")
        self.assertGreaterEqual(exact / total, 0.99, f"Exactly matched {exact} of {total}")
        self.assertGreaterEqual(
            variant_equivalent / total,
            0.995,
            f"House-orthography equivalent {variant_equivalent} of {total}",
        )
        self.assertGreaterEqual(
            roman_match / total, 0.995, f"Romanized forms matched {roman_match} of {total}"
        )

    @unittest.skipUnless(
        (CACHE_DIR / "bthar-mx" / "ocr").is_dir(),
        "Raw bthar-mx cache not present (CI environment)",
    )
    def test_full_bthar_mx_221k_myanmar_to_iast_accuracy(self) -> None:
        files = sorted(glob.glob(str(CACHE_DIR / "bthar-mx" / "ocr" / "*" / "articles.jsonl")))
        total = 0
        matched = 0
        roundtrip_matched = 0
        for fp in files:
            with open(fp, encoding="utf-8") as handle:
                for line in handle:
                    obj = json.loads(line)
                    hw = obj.get("headword") or ""
                    iast = obj.get("iast") or ""
                    if not hw or not iast:
                        continue
                    total += 1
                    if myanmar_to_iast(hw, iso15919=True) == iast:
                        matched += 1
                    if myanmar_to_iast(iast_to_myanmar(iast), iso15919=True) == iast:
                        roundtrip_matched += 1
        self.assertGreater(total, 220_000)
        accuracy = matched / total
        self.assertGreaterEqual(
            accuracy,
            0.995,
            f"Expected >=99.5% accuracy on {total} bthar-mx pairs, got {accuracy:.5f}",
        )
        self.assertGreaterEqual(
            roundtrip_matched / total,
            0.995,
            f"Expected >=99.5% IAST round-trip accuracy on {total} bthar-mx pairs, "
            f"got {roundtrip_matched / total:.5f}",
        )


class Stage1ParserTests(unittest.TestCase):
    def test_parse_tipitaka_abhidhana_html_senses_alias_and_stub(self) -> None:
        raw_html = (
            '<p class="word">စကာရတ္ထ <span class="gender"> (ပု)</span></p>\n'
            '<div class="viggaha"><p>[စကာရ+အတ္ထ]</p></div>\n'
            '<div class="definition"><p><ul>\n'
            "<li>(၁) စသဒ္ဒါ၏ အနက်။ </li>\n"
            '<p class="gender">(တိ)</p>\n'
            "<li>(၂) စသဒ္ဒါ၏ အနက်ရှိသော။</ul></li>\n"
            '</p></div>\n<p class="reference">တိပိ၊၇၊၁၀</p>'
        )
        parsed = parse_tipitaka_abhidhana_html("စကာရတထ", raw_html)
        self.assertEqual(parsed.headword, "စကာရတ္ထ")
        self.assertTrue(parsed.is_alias_row)
        self.assertFalse(parsed.is_stub)
        self.assertEqual(parsed.pos, "ပု")
        self.assertEqual(parsed.etymology, "စကာရ+အတ္ထ")
        self.assertEqual(len(parsed.senses), 2)
        self.assertEqual(parsed.senses[0]["pos"], "ပု")
        self.assertEqual(parsed.senses[1]["pos"], "တိ")
        self.assertEqual(parsed.volume_hint, "၇")
        self.assertEqual(parsed.printed_page, 10)
        self.assertNotIn("<", parsed.definition_text or "")

        stub_html = '<p class="word">ပဒ</p><div class="definition"><p>မူရင်း အတွဲ ၂၀ ၌ ကြည့်ပါ။</p></div>'
        self.assertTrue(parse_tipitaka_abhidhana_html("ပဒ", stub_html).is_stub)

    def test_parse_u_hoke_sein_dhatuattha_and_pali_dhatu_html(self) -> None:
        uhs_html = (
            '<p class="word">ယုဝတီ</p>\n<p>(ဣ)</p>\n<p>(ယုဝ+တီ)</p>\n'
            "<p>လုံမပျို။</p>\n"
            "<p>(f.)– a young woman.</p>"
        )
        uhs = parse_u_hoke_sein_html("ယုဝတီ", uhs_html)
        self.assertEqual(uhs.pos, "ဣ")
        self.assertEqual(uhs.etymology, "ယုဝ+တီ")
        self.assertEqual(uhs.definition_text, "လုံမပျို။")
        self.assertEqual(uhs.english_gloss, "(f.)– a young woman.")

        uhs_verb = '<p class="word">ဗျာကရောတိ</p>\n<p>(ဝိ+အာ√ကရ်)</p>\n<p>ဖြေကြား၏။</p>'
        uhs_v = parse_u_hoke_sein_html("ဗျာကရောတိ", uhs_verb)
        self.assertIsNone(uhs_v.pos)
        self.assertEqual(uhs_v.etymology, "ဝိ+အာ√ကရ်")
        self.assertEqual(uhs_v.root_pali, "√ကရ်")

        uhs_multi = '<p class="word">စရာပေတိ</p>\n<p>(ကာ) (√စရ်+ဏာပေ)</p>\n<p>ကျင့်စေ၏။</p>'
        uhs_m = parse_u_hoke_sein_html("စရာပေတိ", uhs_multi)
        self.assertEqual((uhs_m.pos, uhs_m.etymology, uhs_m.root_pali), ("ကာ", "√စရ်+ဏာပေ", "√စရ်"))

        b3_html = (
            '<p class="word">၀၀ကဋ္ဌ <span class="gender">၊ ပု ၊</span> [ဝိ+အဝ√ကသ+တ]</p>\n'
            "<p>ကင်းဆိတ်ရာ။</p>"
        )
        b3 = parse_dhatuattha_html("ဝဝကဋ္ဌ", b3_html)
        self.assertEqual(b3.headword, "ဝဝကဋ္ဌ")
        self.assertEqual(b3.pos, "ပု")
        self.assertEqual(b3.root_pali, "√ကသ")
        self.assertEqual(b3.definition_text, "ကင်းဆိတ်ရာ။")

        b3_var = parse_dhatuattha_html(
            "စိတြ",
            '<p class="word">စိတြ<span class="gender">၊ ဝိစိတြ ၊</span> တိ ၊ </p><p>ဆန်းကြယ်သော။</p>',
        )
        self.assertEqual((b3_var.headword, b3_var.pos), ("စိတြ", "တိ"))

        b3_unbal = parse_dhatuattha_html(
            "အတိဗန္ဓိတွာ",
            '<p class="word">အတိဗန္ဓိတွာ ။ ဗျ ။ အတိ√ဗန္ဓ+တွာ]</p><p>ဖွဲ့၍။</p>',
        )
        self.assertEqual(
            (b3_unbal.headword, b3_unbal.pos, b3_unbal.root_pali), ("အတိဗန္ဓိတွာ", "ဗျ", "√ဗန္ဓ")
        )

        b3_post = parse_dhatuattha_html(
            "မစ္ဆရာယတိ",
            '<p class="word">မစ္ဆရာယတိ [မစ္ဆရ+အာယ = မစ္ဆရာယ+တိ] နာမ ဓာတု။</p><p>ဝန်တို၏။</p>',
        )
        self.assertEqual((b3_post.headword, b3_post.pos), ("မစ္ဆရာယတိ", "နာမဓာတု"))

        b4_html = '<p class="definition">စကိ၊ စင်္က ဘူ = သဉ္စလေ-တုန်လှုပ်ခြင်း၌။ စင်္ကတိ။</p>'
        b4 = parse_pali_dhatu_html("စကိ", b4_html)
        self.assertEqual(b4.root_variants, ["စကိ", "စင်္က"])
        self.assertEqual(b4.gana_classes, ["ဘူ"])
        self.assertEqual(b4.pali_sense, "သဉ္စလေ")
        self.assertEqual(b4.burmese_sense, "တုန်လှုပ်ခြင်း၌။")
        self.assertEqual(b4.sample_verbs, "စင်္ကတိ")

        b4_slash = '<p class="definition">အပ/တ+သွာ = ပါပုဏနေ-ရောက်ခြင်း၌။ အပေါတိ။</p>'
        self.assertEqual(parse_pali_dhatu_html("အပ", b4_slash).gana_classes, ["တ", "သွာ"])

    def test_split_my_android_preserves_plus_inside_etymology_and_post_tag_notes(self) -> None:
        raw = (
            "။ပု+န။[√ အံက+ဥရ] အညွန့်အညှောက်။♦မြ+"
            "(ပ) ၁-အဘို့။♦ချုပ်+"
            "ထီ၊ အာကတိ-ဆဒ+ဏှောတ။ (၁) သပွတ်ခါးနွယ်။။+"
            "ထီ၊ အာကတိ-ဆဒ+ဏှောတ။ (၁) သပွတ်ခါးနွယ်။။"
        )
        segs = split_my_android_segments(raw)
        self.assertEqual([s.tag for s in segs], ["မြ", "ချုပ်", ""])
        self.assertIn("[√ အံက+ဥရ]", segs[0].body)

        # Trailing post-tag note without `+` and repeated `+♦` / `♦...+++` stay clean
        with_note = split_my_android_segments("(ပ) လမင်း။♦စိန် ဥ")
        self.assertEqual(len(with_note), 1)
        self.assertEqual(with_note[0].tag, "စိန်")
        self.assertNotIn("♦", with_note[0].body)

        multi_plus = split_my_android_segments("အဝတ်+♦မြ++ဘူ၊ တေဇနေ။♦စိန်+++")
        self.assertEqual(
            [(s.tag, s.body) for s in multi_plus], [("မြ", "အဝတ်"), ("စိန်", "ဘူ၊ တေဇနေ။")]
        )


if __name__ == "__main__":
    unittest.main()
