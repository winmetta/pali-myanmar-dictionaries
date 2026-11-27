#!/usr/bin/env node
// Persistent JSONL stdin/stdout worker wrapping winmetta-platform/packages/myanmar-convert/src/index.ts.

import { existsSync } from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

function resolveConvertEntry() {
  const candidates = [
    process.env.MYANMAR_CONVERT_ENTRY,
    path.resolve(repoRoot, "..", "winmetta-platform", "packages", "myanmar-convert", "src", "index.ts"),
    path.resolve(repoRoot, ".vendor-ci", "winmetta-platform", "packages", "myanmar-convert", "src", "index.ts"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error(
    `Could not locate winmetta-platform/packages/myanmar-convert/src/index.ts (checked: ${candidates.join(", ")})`,
  );
}

const entryPath = resolveConvertEntry();
const googlePath = path.resolve(path.dirname(entryPath), "google.ts");
const { convert, CONVERT_THRESHOLD } = await import(pathToFileURL(entryPath).href);
const { zawgyiDetector } = await import(pathToFileURL(googlePath).href);
const detector = zawgyiDetector();

// Pāḷi-safe Zawgyi markers matching `src/pali_myanmar_dicts/zawgyi.py`:
// Allows Great Sa `ဿ` (U+103F) before `ေ` (U+1031) and Sanskrit extensions U+1050-U+1055,
// while flagging Zawgyi-only U+1060-U+1097 and Mon-repurposed U+1033/U+1034/U+105A.
const MYANMAR_RE = /[\u1000-\u109F]/;
const UNAMBIGUOUS_ZAWGYI_CP = /[\u1033\u1034\u105A\u1060-\u1097]/g;
const LEADING_E_PALI_SAFE = /(?<![\u1000-\u1021\u1039\u103B-\u103F\u1050-\u1055])\u1031/g;
const LOOSE_VIRAMA_PALI_SAFE = /\u1039(?![\u1000-\u1021\u1050-\u1055])/g;

function countPaliSafeMarkers(s) {
  return (
    (s.match(UNAMBIGUOUS_ZAWGYI_CP)?.length ?? 0) +
    (s.match(LEADING_E_PALI_SAFE)?.length ?? 0) +
    (s.match(LOOSE_VIRAMA_PALI_SAFE)?.length ?? 0)
  );
}

function classifyWithPaliGuard(s) {
  if (!MYANMAR_RE.test(s)) {
    return { detected: "no-myanmar", hasMarker: false, markerCount: 0 };
  }
  const markerCount = countPaliSafeMarkers(s);
  const hasMarker = markerCount > 0;
  const prob = detector.getZawgyiProbability(s);
  if (hasMarker && prob >= CONVERT_THRESHOLD) {
    return { detected: "zawgyi", hasMarker: true, markerCount };
  }
  if (hasMarker || prob > 0.5) {
    return { detected: "unsure", hasMarker, markerCount };
  }
  return { detected: "unicode", hasMarker: false, markerCount: 0 };
}

function handleRequest(req) {
  const op = req.op;
  const texts = Array.isArray(req.texts) ? req.texts : [];

  if (op === "convert") {
    const from = req.from ?? "zawgyi";
    const to = req.to ?? "unicode";
    return {
      ok: true,
      results: texts.map((t) => convert(String(t), from, to)),
    };
  }

  if (op === "detect") {
    return {
      ok: true,
      results: texts.map((t) => classifyWithPaliGuard(String(t))),
    };
  }

  if (op === "auto_to_unicode") {
    return {
      ok: true,
      results: texts.map((t) => {
        const s = String(t);
        const info = classifyWithPaliGuard(s);
        if (info.detected === "zawgyi") {
          const res = convert(s, "zawgyi", "unicode");
          return { text: res.text, converted: true, detected: info.detected, notes: res.notes };
        }
        return { text: s.normalize("NFC"), converted: false, detected: info.detected, notes: [] };
      }),
    };
  }

  throw new Error(`Unsupported operation: ${String(op)}`);
}

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

for await (const line of rl) {
  const trimmed = line.trim();
  if (!trimmed) continue;
  try {
    const req = JSON.parse(trimmed);
    const resp = handleRequest(req);
    process.stdout.write(`${JSON.stringify(resp)}\n`);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    process.stdout.write(`${JSON.stringify({ ok: false, error: message })}\n`);
  }
}
