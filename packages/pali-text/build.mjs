import { stripTypeScriptTypes } from "node:module";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const source = new URL("./src/index.ts", import.meta.url);
const output = new URL("./dist/", import.meta.url);
await mkdir(output, { recursive: true });
await writeFile(
  new URL("index.js", output),
  stripTypeScriptTypes(await readFile(source, "utf8")),
);
