import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const source = resolve("src/preload/preload.cjs");
const target = resolve("dist/preload/preload.cjs");

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
