import { createInterface } from "node:readline";
import {
  toHeadwordNorm,
  canonicalizeMyanmarSyllables,
  myanmarToIast,
  iastToMyanmar,
} from "../dist/index.js";

for await (const line of createInterface({ input: process.stdin })) {
  const text = JSON.parse(line);
  process.stdout.write(
    JSON.stringify([
      canonicalizeMyanmarSyllables(text),
      toHeadwordNorm(text),
      myanmarToIast(text),
      iastToMyanmar(myanmarToIast(text)),
    ]) + "\n",
  );
}
