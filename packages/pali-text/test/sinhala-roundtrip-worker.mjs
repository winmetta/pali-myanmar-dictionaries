import { createInterface } from "node:readline";
import { sinhalaToMyanmar, myanmarToSinhala } from "../dist/index.js";
for await (const line of createInterface({ input: process.stdin })) {
  const word = JSON.parse(line);
  const myanmar = sinhalaToMyanmar(word);
  process.stdout.write(
    JSON.stringify([myanmar, sinhalaToMyanmar(myanmarToSinhala(myanmar))]) +
      "\n",
  );
}
