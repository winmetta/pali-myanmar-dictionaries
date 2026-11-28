// JSON Lines adapter for the in-repository builder. Package code stays browser compatible.
import { createInterface } from "node:readline";
import { myanmarToIast, toHeadwordNorm } from "@winmetta/pali-text";

for await (const line of createInterface({ input: process.stdin })) {
  const word = JSON.parse(line);
  process.stdout.write(
    JSON.stringify([toHeadwordNorm(word), myanmarToIast(word)]) + "\n",
  );
}
