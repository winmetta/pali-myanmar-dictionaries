/** Browser-compatible text helpers. API is experimental during the Python migration. */

const ranks: Record<string, number> = {
  "\u103b": 1,
  "\u103c": 2,
  "\u103d": 3,
  "\u103e": 4,
  "\u1031": 5,
  "\u102d": 6,
  "\u102e": 6,
  "\u102f": 7,
  "\u1030": 7,
  "\u1032": 8,
  "\u102b": 9,
  "\u102c": 9,
  "\u1036": 10,
  "\u1037": 11,
  "\u103a": 12,
  "\u1038": 13,
};

/** Reorder Myanmar syllables using the current Python implementation's rules. */
export function canonicalizeMyanmarSyllables(text: string): string {
  let current = text
    .normalize("NFC")
    .replace(
      /\u1025(?=[\u102b\u102c\u1031\u1039\u103a\u103e]|\u1037\u103a)/g,
      "\u1009",
    );
  for (;;) {
    const swapped = current.replace(
      /([\u102b-\u1038\u103b-\u103e]+)((?:\u1039[\u1000-\u1021\u1050-\u1055])+)/g,
      "$2$1",
    );
    if (swapped === current) break;
    current = swapped;
  }
  return current
    .replace(
      /\u1004\u103a\u1039|([\u1000-\u102a\u103f\u104e\u1050-\u1055](?:\u1039[\u1000-\u1021\u1050-\u1055])*)([\u102b-\u1032\u1036-\u1038\u103a-\u103e]{2,})/g,
      (full: string, base: string | undefined, marks: string | undefined) => {
        if (base === undefined || marks === undefined) return full;
        const unique: string[] = [];
        for (const char of marks)
          if (!unique.includes(char) || char === "\u103a") unique.push(char);
        return (
          base +
          unique.sort((a, b) => (ranks[a] ?? 99) - (ranks[b] ?? 99)).join("")
        );
      },
    )
    .normalize("NFC");
}

/** Detect the same suspicious code-point patterns used by the Python gate. */
export function hasZawgyiCodepointMarker(text: string): boolean {
  return /[\u1060-\u1097\u1033\u1034\u105a]|(?<![\u1000-\u1021\u1039\u103b-\u103f\u1050-\u1055])\u1031|\u1039(?![\u1000-\u1021\u1050-\u1055])/.test(
    text,
  );
}

export function normalizeMyanmarText(
  text: string,
  options: { singleLine?: boolean; checkZawgyi?: boolean } = {},
): string {
  let cleaned = text
    .replace(/[\u200b-\u200d\ufeff\u00ad]/g, "")
    .replace(/\r\n?/g, "\n");
  if (options.singleLine)
    cleaned = cleaned
      .replace(/\n/g, " ")
      .replace(/[ \t\f\v]+/g, " ")
      .trim();
  else
    cleaned = cleaned
      .split("\n")
      .map((line) => line.replace(/[ \t\f\v]+/g, " ").trim())
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  const normalized = canonicalizeMyanmarSyllables(cleaned);
  if (options.checkZawgyi !== false && hasZawgyiCodepointMarker(normalized))
    throw new Error("Residual Zawgyi sequence detected");
  return normalized;
}

/** Create a loose lookup key compatible with the current Python dataset builder. */
export function toHeadwordNorm(text: string): string {
  return normalizeMyanmarText(text, { singleLine: true, checkZawgyi: false })
    .replace(
      /(?:(?<![\u1000-\u103f])\u1009(?![\u102b-\u102d\u102f-\u103e])|(?<!\u1039)\u1009(?=\u102e))/g,
      "\u1025",
    )
    .normalize("NFC")
    .replace(/[\s\-–—_.,;:!?"'“”‘’()\[\]{}၊။…/\\+=0-9၀-၉]+/g, "")
    .replace(/\u1004\u103a\u1039(?=[\u1000-\u1004])/g, "\u1036")
    .replaceAll("\u102b", "\u102c")
    .replaceAll("\u103f", "သသ")
    .replaceAll("\u103e", "ဟ")
    .replaceAll("\u1039", "")
    .normalize("NFC");
}

const romanToMyanmar: Record<string, string> = {
  kh: "ခ",
  gh: "ဃ",
  ch: "ဆ",
  jh: "ဈ",
  ṭh: "ဌ",
  ḍh: "ဎ",
  th: "ထ",
  dh: "ဓ",
  ph: "ဖ",
  bh: "ဘ",
  k: "က",
  g: "ဂ",
  ṅ: "င",
  c: "စ",
  j: "ဇ",
  ñ: "ဉ",
  ṭ: "ဋ",
  ḍ: "ဍ",
  ṇ: "ဏ",
  t: "တ",
  d: "ဒ",
  n: "န",
  p: "ပ",
  b: "ဗ",
  m: "မ",
  y: "ယ",
  r: "ရ",
  l: "လ",
  v: "ဝ",
  s: "သ",
  h: "ဟ",
  ḷ: "ဠ",
};
const independentVowels: Record<string, string> = {
  ā: "အာ",
  a: "အ",
  ī: "ဤ",
  i: "ဣ",
  ū: "ဦ",
  u: "ဥ",
  e: "ဧ",
  o: "ဩ",
};
const dependentVowels: Record<string, string> = {
  a: "",
  i: "ိ",
  ī: "ီ",
  u: "ု",
  ū: "ူ",
  e: "ေ",
};
const myanmarToRoman = Object.fromEntries(
  Object.entries(romanToMyanmar).map(([a, b]) => [b, a]),
);
myanmarToRoman["ည"] = "ññ";
myanmarToRoman["ဿ"] = "ss";
const myIndependent: Record<string, string> = {
  ဣ: "i",
  ဤ: "ī",
  ဥ: "u",
  ဦ: "ū",
  ဧ: "e",
  ဩ: "o",
  ဪ: "au",
};
const myMedials: Record<string, string> = {
  "ျ": "y",
  "ြ": "r",
  "ွ": "v",
  "ှ": "h",
};
const myVowels: Record<string, string> = {
  "ါ": "ā",
  "ာ": "ā",
  "ိ": "i",
  "ီ": "ī",
  "ု": "u",
  "ူ": "ū",
  "ေ": "e",
  "ဲ": "ai",
};

function renderCluster(consonants: string[], vowel?: string): string {
  const remaining = [...consonants];
  let prefix = "";
  if (
    remaining.length >= 2 &&
    remaining[0] === "ṅ" &&
    ["k", "kh", "g", "gh", "ṅ"].includes(remaining[1])
  ) {
    prefix = "င်္";
    remaining.shift();
  }
  const medials: string[] = [];
  if (
    remaining.length >= 2 &&
    remaining.at(-1) === "h" &&
    ["ñ", "ṇ", "n", "m", "y", "l", "v", "ḷ"].includes(remaining.at(-2)!)
  ) {
    medials.unshift("ှ");
    remaining.pop();
  }
  if (
    remaining.length >= 2 &&
    remaining.at(-1) === "v" &&
    remaining.at(-2) !== "v"
  ) {
    medials.unshift("ွ");
    remaining.pop();
  }
  if (
    remaining.length >= 2 &&
    remaining.at(-1) === "r" &&
    remaining.at(-2) !== "r"
  ) {
    medials.unshift("ြ");
    remaining.pop();
  }
  if (remaining.length >= 2 && remaining.at(-1) === "y") {
    medials.unshift("ျ");
    remaining.pop();
  }
  const med = medials.join("");
  let base: string;
  let subs: string;
  if (remaining.join(" ") === "s s" && !prefix) {
    base = "ဿ";
    subs = "";
  } else if (remaining.join(" ") === "ñ ñ" && !prefix) {
    base = "ည";
    subs = "";
  } else {
    base = romanToMyanmar[remaining[0]];
    subs = remaining
      .slice(1)
      .map((c) => "္" + romanToMyanmar[c])
      .join("");
  }
  const cluster = base + subs + med;
  if (vowel === undefined) return prefix + cluster + "်";
  if (vowel in dependentVowels)
    return prefix + cluster + dependentVowels[vowel];
  const tall =
    (["ခ", "ဂ", "င", "ဒ", "ပ", "ဝ"].includes(base) && !subs && !med) ||
    (base === "ဒ" && !subs && med === "ွ") ||
    (base === "ဒ" && ["္ဒ", "္ဓ"].includes(subs) && !med) ||
    (base === "ဂ" && subs === "္ဂ" && !med);
  return prefix + cluster + (vowel === "o" ? "ေ" : "") + (tall ? "ါ" : "ာ");
}

/** Transliterate Roman Pāḷi to Myanmar script. */
export function iastToMyanmar(text: string): string {
  const normalized = text
    .normalize("NFC")
    .toLowerCase()
    .replaceAll("l\u0324", "ḷ")
    .replaceAll("l\u02f3", "ḷ")
    .replaceAll("ṁ", "ṃ")
    .replaceAll("ï", "i")
    .replaceAll("ü", "u")
    .replaceAll("ŭ", "ñ");
  const tokens =
    normalized.match(
      /kh|gh|ch|jh|ṭh|ḍh|th|dh|ph|bh|[kgṅcjñṭḍṇtdnpbmyrlvshḷāīūaiueoṃ]|[\s\S]/g,
    ) ?? [];
  const output: string[] = [];
  for (let index = 0; index < tokens.length;) {
    const token = tokens[index];
    if (token in romanToMyanmar) {
      const consonants: string[] = [];
      while (index < tokens.length && tokens[index] in romanToMyanmar)
        consonants.push(tokens[index++]);
      const vowel =
        tokens[index] in independentVowels ? tokens[index++] : undefined;
      output.push(renderCluster(consonants, vowel));
    } else if (token in independentVowels) {
      output.push(independentVowels[token]);
      index++;
    } else {
      output.push(token === "ṃ" ? "ံ" : token);
      index++;
    }
  }
  return canonicalizeMyanmarSyllables(output.join(""));
}

function renderMyanmarMatch(
  kinzi: string,
  base: string,
  subs: string,
  medials: string,
  e: string,
  vowels: string,
  aa: string,
  killer: string,
): string {
  let vowel = "";
  if (killer && !e && !vowels && !aa) vowel = "";
  else if (e && aa && !vowels) vowel = "o";
  else if (!e && !vowels && !aa) vowel = "a";
  else
    vowel =
      (e ? "e" : "") +
      [...vowels].map((v) => myVowels[v]).join("") +
      (aa ? "ā" : "");
  if (base === "အ" && !kinzi && !subs && !medials && !killer) return vowel;
  return (
    (kinzi ? "ṅ" : "") +
    (myanmarToRoman[base] ?? base) +
    [...subs]
      .filter((_, i) => i % 2 === 1)
      .map((c) => myanmarToRoman[c] ?? c)
      .join("") +
    [...medials].map((c) => myMedials[c]).join("") +
    vowel
  );
}

/** Transliterate Myanmar-script Pāḷi to IAST or BTHAR's ISO 15919 convention. */
export function myanmarToIast(
  text: string,
  options: { iso15919?: boolean } = {},
): string {
  const norm = canonicalizeMyanmarSyllables(
    text.replace(/[\u200b-\u200d\ufeff\u00ad]/g, ""),
  );
  const regex =
    /(\u1004\u103a\u1039)?([\u1000-\u1021\u103f])((?:\u1039[\u1000-\u1021])*)([\u103b-\u103e]*)(\u1031)?([\u102d-\u1030\u1032]*)([\u102b\u102c]*)(\u103a)?/g;
  let result = "";
  let position = 0;
  function nonSyllable(span: string): void {
    for (const char of span) {
      if (char === "ံ") result += "ṃ";
      else if (char in myIndependent) {
        const vowel = myIndependent[char];
        result +=
          options.iso15919 && result.endsWith("a") && ["i", "u"].includes(vowel)
            ? vowel === "i"
              ? "ï"
              : "ü"
            : vowel;
      } else if (char in myVowels) result += myVowels[char];
      else if (char in myMedials) result += myMedials[char];
      else if (char >= "၀" && char <= "၉")
        result += String(char.codePointAt(0)! - "၀".codePointAt(0)!);
      else if (!["့", "း", "္", "်"].includes(char)) result += char;
    }
  }
  for (const match of norm.matchAll(regex)) {
    nonSyllable(norm.slice(position, match.index));
    result += renderMyanmarMatch(
      ...(match.slice(1).map((value) => value ?? "") as [
        string,
        string,
        string,
        string,
        string,
        string,
        string,
        string,
      ]),
    );
    position = match.index + match[0].length;
  }
  nonSyllable(norm.slice(position));
  return options.iso15919
    ? result.replaceAll("ṃ", "ṁ").replaceAll("ḷ", "l\u0324")
    : result;
}

const sinhalaConsonants: Record<string, string> = {
  ක: "k",
  ඛ: "kh",
  ග: "g",
  ඝ: "gh",
  ඞ: "ṅ",
  ච: "c",
  ඡ: "ch",
  ජ: "j",
  ඣ: "jh",
  ඤ: "ñ",
  ට: "ṭ",
  ඨ: "ṭh",
  ඩ: "ḍ",
  ඪ: "ḍh",
  ණ: "ṇ",
  ත: "t",
  ථ: "th",
  ද: "d",
  ධ: "dh",
  න: "n",
  ප: "p",
  ඵ: "ph",
  බ: "b",
  භ: "bh",
  ම: "m",
  ය: "y",
  ර: "r",
  ල: "l",
  ව: "v",
  ස: "s",
  හ: "h",
  ළ: "ḷ",
};
const sinhalaIndependent: Record<string, string> = {
  අ: "a",
  ආ: "ā",
  ඉ: "i",
  ඊ: "ī",
  උ: "u",
  ඌ: "ū",
  එ: "e",
  ඒ: "e",
  ඔ: "o",
  ඕ: "o",
};
const sinhalaDependent: Record<string, string> = {
  "ා": "ā",
  "ි": "i",
  "ී": "ī",
  "ු": "u",
  "ූ": "ū",
  "ෙ": "e",
  "ේ": "e",
  "ො": "o",
  "ෝ": "o",
};
const sinhalaIndependentFromDependent: Record<string, string> = {
  "ා": "ආ",
  "ි": "ඉ",
  "ී": "ඊ",
  "ු": "උ",
  "ූ": "ඌ",
  "ෙ": "එ",
  "ේ": "එ",
  "ො": "ඔ",
  "ෝ": "ඔ",
};
const velars = ["k", "kh", "g", "gh", "ṅ"];

/** Repair source-specific encoding artifacts, returning each repair applied. */
export function cleanSinhalaHeadword(text: string): {
  text: string;
  notes: string[];
} {
  let raw = text.trim().normalize("NFC");
  const notes: string[] = [];
  for (const [old, replacement, note] of [
    ["උ්", "ඤ්", "repaired_indep_u_virama_to_nya"],
    ["ඌ්", "ඤ්", "repaired_indep_uu_virama_to_nya"],
    ["අංන්හි", "අන්හි", "repaired_anhi_prefix"],
  ]) {
    if (raw.includes(old)) {
      raw = raw.replaceAll(old, replacement);
      notes.push(note);
    }
  }
  const cleaned: string[] = [];
  const chars = [...raw];
  for (let i = 0; i < chars.length; i++) {
    const char = chars[i],
      prev = cleaned.at(-1) ?? "",
      next = chars[i + 1] ?? "";
    let emitted = char,
      note = "";
    if (char === "්" && !(prev in sinhalaConsonants)) {
      emitted = "";
      note = "dropped_stray_virama";
    } else if (char in sinhalaDependent && prev === "අ") {
      cleaned.pop();
      emitted = sinhalaIndependentFromDependent[char];
      note = "folded_a_plus_dep_vowel";
    } else if (
      char in sinhalaDependent &&
      (prev in sinhalaDependent || prev in sinhalaIndependent)
    ) {
      emitted = "";
      note = "dropped_duplicate_dep_vowel";
    } else if (char in sinhalaDependent && !(prev in sinhalaConsonants)) {
      emitted = "";
      note = "dropped_orphan_dep_vowel";
    } else if (char === "–") {
      emitted = "-";
      note = "normalized_en_dash";
    } else if (char === "\u1064") {
      emitted =
        next in sinhalaConsonants && velars.includes(sinhalaConsonants[next])
          ? "ඞ්"
          : prev in sinhalaDependent && next
            ? "ං"
            : "";
      note = "repaired_zawgyi_kinzi";
    } else if (char === "\u108d") {
      emitted = "ං";
      note = "repaired_zawgyi_108d";
    } else if (char === "\u1037") {
      emitted = prev === "ං" ? "" : "ං";
      note = "repaired_dot_below";
    } else if (["၌", "၏"].includes(char)) {
      emitted = "";
      note = `stripped_stray_${char.codePointAt(0)!.toString(16).padStart(4, "0")}`;
    } else if (char === "ං" && prev === "ං") {
      emitted = "";
      note = "collapsed_duplicate_anusvara";
    }
    cleaned.push(...emitted);
    if (note) notes.push(note);
  }
  return { text: cleaned.join(""), notes };
}

type PaliToken = ["C" | "V" | "M" | "O", string];
function sinhalaTokens(text: string, kinzi: boolean): PaliToken[] {
  const chars = [...text],
    tokens: PaliToken[] = [];
  for (let i = 0; i < chars.length;) {
    const char = chars[i++];
    if (char in sinhalaConsonants) {
      tokens.push(["C", sinhalaConsonants[char]]);
      if (chars[i] === "්") i++;
      else if (chars[i] in sinhalaDependent)
        tokens.push(["V", sinhalaDependent[chars[i++]]]);
      else tokens.push(["V", "a"]);
    } else if (char in sinhalaIndependent)
      tokens.push(["V", sinhalaIndependent[char]]);
    else if (char === "ං") {
      const next = chars[i] ?? "";
      if (
        kinzi &&
        next in sinhalaConsonants &&
        velars.includes(sinhalaConsonants[next])
      )
        tokens.push(["C", "ṅ"]);
      else tokens.push(["M", "ṃ"]);
    } else tokens.push(["O", char]);
  }
  return tokens;
}
function renderPaliTokens(tokens: PaliToken[]): string {
  const output: string[] = [];
  for (let i = 0; i < tokens.length;) {
    const [kind, value] = tokens[i++];
    if (kind === "C") {
      const consonants = [value];
      while (i < tokens.length && tokens[i][0] === "C")
        consonants.push(tokens[i++][1]);
      const vowel =
        i < tokens.length && tokens[i][0] === "V" ? tokens[i++][1] : undefined;
      output.push(renderCluster(consonants, vowel));
    } else if (kind === "V") output.push(independentVowels[value]);
    else output.push(kind === "M" ? "ံ" : value);
  }
  return canonicalizeMyanmarSyllables(output.join(""));
}
/** Transliterate Sinhala Pāḷi, optionally choosing the spelling in a reference vocabulary. */
export function sinhalaToMyanmar(
  text: string,
  options: { vocabulary?: ReadonlySet<string> } = {},
): string {
  const cleaned = cleanSinhalaHeadword(text).text;
  const kinzi = renderPaliTokens(sinhalaTokens(cleaned, true));
  if (
    !options.vocabulary ||
    !cleaned.includes("ං") ||
    options.vocabulary.has(kinzi)
  )
    return kinzi;
  const anusvara = renderPaliTokens(sinhalaTokens(cleaned, false));
  return options.vocabulary.has(anusvara) ? anusvara : kinzi;
}

const romanToSinhala = Object.fromEntries(
  Object.entries(sinhalaConsonants).map(([sinhala, roman]) => [roman, sinhala]),
);
const romanToSinhalaIndependent: Record<string, string> = {
  a: "අ",
  ā: "ආ",
  i: "ඉ",
  ī: "ඊ",
  u: "උ",
  ū: "ඌ",
  e: "එ",
  o: "ඔ",
};
const romanToSinhalaDependent: Record<string, string> = {
  a: "",
  ā: "ා",
  i: "ි",
  ī: "ී",
  u: "ු",
  ū: "ූ",
  e: "ෙ",
  o: "ො",
};

/** Transliterate IAST Pāḷi to canonical Sinhala spelling. */
export function iastToSinhala(text: string): string {
  const normalized = text
    .normalize("NFC")
    .toLowerCase()
    .replaceAll("ṁ", "ṃ")
    .replaceAll("ï", "i")
    .replaceAll("ü", "u")
    .replaceAll("ŭ", "ñ");
  const tokens =
    normalized.match(
      /kh|gh|ch|jh|ṭh|ḍh|th|dh|ph|bh|[kgṅcjñṭḍṇtdnpbmyrlvshḷāīūaiueoṃ]|[\s\S]/g,
    ) ?? [];
  const output: string[] = [];
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (token in romanToSinhala) {
      output.push(romanToSinhala[token]);
      if (i + 1 < tokens.length && tokens[i + 1] in romanToSinhalaDependent)
        output.push(romanToSinhalaDependent[tokens[++i]]);
      else output.push("්");
    } else if (token in romanToSinhalaIndependent)
      output.push(romanToSinhalaIndependent[token]);
    else output.push(token === "ṃ" ? "ං" : token);
  }
  return output.join("").normalize("NFC");
}

/** Transliterate Myanmar-script Pāḷi to Sinhala via IAST. */
export function myanmarToSinhala(text: string): string {
  return iastToSinhala(myanmarToIast(text));
}
