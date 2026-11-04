const fs = require("fs");
const path = require("path");

const pnpmDir = path.join(__dirname, "..", "node_modules", ".pnpm");
const esbuildDir = fs.readdirSync(pnpmDir).find((d) => d.startsWith("esbuild@"));
const esbuild = require(path.join(pnpmDir, esbuildDir, "node_modules", "esbuild"));

esbuild.buildSync({
  entryPoints: [path.join(__dirname, "..", "src", "lib", "search.ts")],
  bundle: true,
  format: "cjs",
  platform: "node",
  outfile: path.join(__dirname, "search.cjs"),
  logLevel: "error",
});

const { parseSearch } = require("./search.cjs");
const cases = [
  ["https://steamcommunity.com/profiles/76561198006804047/", "steam 76561198006804047"],
  ["https://steamcommunity.com/id/antonk777/home", "vanity antonk777"],
  ["steamcommunity.com/id/Some_Name-123", "vanity Some_Name-123"],
  ["STEAM_0:1:12345678", "steam 76561197984957085"],
  ["[U:1:12345678]", "steam 76561197984957085"],
  ["76561198006804047", "steam 76561198006804047"],
  ["1050366", "account 1050366"],
  ["random words", null],
  ["", null],
];
let ok = true;
for (const [input, expect] of cases) {
  const r = parseSearch(input);
  const got =
    r === null ? null : r.type + " " + (r.type === "account" ? r.account : r.type === "vanity" ? r.name : r.id);
  const pass = got === expect;
  ok = ok && pass;
  console.log(pass ? "OK  " : "FAIL", JSON.stringify(input), "->", got, pass ? "" : "expected " + expect);
}
process.exit(ok ? 0 : 1);
