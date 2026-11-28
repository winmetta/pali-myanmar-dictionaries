import { createInterface } from "node:readline";
import { cleanSinhalaHeadword, sinhalaToMyanmar } from "../dist/index.js";

for await (const line of createInterface({ input: process.stdin })) {
  const text = JSON.parse(line);
  process.stdout.write(
    JSON.stringify([cleanSinhalaHeadword(text), sinhalaToMyanmar(text)]) + "\n",
  );
}
