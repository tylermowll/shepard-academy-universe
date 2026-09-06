import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const root = new URL("../", import.meta.url);
const expectedNode = readFileSync(
  new URL(".node-version", root),
  "utf8",
).trim();
const manifest = JSON.parse(
  readFileSync(new URL("package.json", root), "utf8"),
);
const expectedPnpm = manifest.packageManager.split("@")[1];
const actualNode = process.versions.node;
const expectedParts = expectedNode.split(".").map(Number);
const actualParts = actualNode.split(".").map(Number);
const supportedNode =
  actualParts[0] === expectedParts[0] &&
  (actualParts[1] > expectedParts[1] ||
    (actualParts[1] === expectedParts[1] &&
      actualParts[2] >= expectedParts[2]));

if (!supportedNode) {
  console.error(
    `Use Node.js ${expectedNode} or a newer patch in the same LTS line; found ${actualNode}.`,
  );
  process.exit(1);
}

const pnpm = spawnSync("pnpm", ["--version"], { encoding: "utf8" });
if (pnpm.status !== 0 || pnpm.stdout.trim() !== expectedPnpm) {
  console.error(
    `Install pnpm ${expectedPnpm}: npm install --global pnpm@${expectedPnpm}`,
  );
  process.exit(1);
}

console.log(`Toolchain: Node.js ${actualNode}, pnpm ${expectedPnpm}`);
