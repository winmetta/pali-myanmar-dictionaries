import { createInterface } from "node:readline";
import { iastToMyanmar, myanmarToIast } from "../dist/index.js";

for await (const line of createInterface({ input: process.stdin })) {
  const [headword, iast] = JSON.parse(line);
  process.stdout.write(
    JSON.stringify([
      myanmarToIast(headword, { iso15919: true }),
      myanmarToIast(iastToMyanmar(iast), { iso15919: true }),
    ]) + "\n",
  );
}
