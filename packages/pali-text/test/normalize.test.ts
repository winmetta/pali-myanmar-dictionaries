import { test } from "node:test";
import { strict as assert } from "node:assert";
import {
  canonicalizeMyanmarSyllables,
  hasZawgyiCodepointMarker,
  normalizeMyanmarText,
  toHeadwordNorm,
} from "../dist/index.js";

test("normalizes canonical and loose Myanmar forms", () => {
  assert.equal(
    normalizeMyanmarText("က\u200b\u102c\u1031\u103cင\u1038\u103a", {
      singleLine: true,
    }),
    "ကြောင်း",
  );
  assert.equal(canonicalizeMyanmarSyllables("ဣနြ္ဒိယ"), "ဣန္ဒြိယ");
  for (const [left, right] of [
    ["ဓမ္မ", "ဓမမ"],
    ["ပဉှ", "ပဉဟ"],
    ["သင်္ဃ", "သံဃ"],
    ["သဿတ", "သသသတ"],
  ]) {
    assert.equal(toHeadwordNorm(left), toHeadwordNorm(right));
  }
  assert.equal(hasZawgyiCodepointMarker("\u1031မတ္တာ"), true);
  assert.throws(() => normalizeMyanmarText("\u1031မတ္တာ"));
});

test("transliterates reference words in both directions", async () => {
  const { iastToMyanmar, myanmarToIast } = await import("../dist/index.js");
  for (const [myanmar, iast] of [
    ["ဗုဒ္ဓ", "buddha"],
    ["သင်္ခါရ", "saṅkhāra"],
    ["ပညာ", "paññā"],
    ["ကမ္မဋ္ဌာန", "kammaṭṭhāna"],
    ["ဒုဿ", "dussa"],
  ]) {
    assert.equal(myanmarToIast(myanmar), iast);
    assert.equal(iastToMyanmar(iast), myanmar);
  }
});

test("transliterates Sinhala Pāḷi in both directions", async () => {
  const { sinhalaToMyanmar, myanmarToSinhala } =
    await import("../dist/index.js");
  for (const [sinhala, myanmar] of [
    ["බුද්ධ", "ဗုဒ္ဓ"],
    ["සඞ්ඛාර", "သင်္ခါရ"],
    ["අකතඤ්ඤුතා", "အကတညုတာ"],
  ]) {
    assert.equal(sinhalaToMyanmar(sinhala), myanmar);
    assert.equal(myanmarToSinhala(myanmar), sinhala);
  }
  assert.equal(sinhalaToMyanmar("සංඝ", { vocabulary: new Set(["သံဃ"]) }), "သံဃ");
});
