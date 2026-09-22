// Download the latest companion .exe from the private repo and write release.json.
// Caddy: run on the host (deploy.sh / systemd timer), output into SITE_ROOT.
// Env:
//   COMPANION_GITHUB_TOKEN = PAT with Contents: Read on antonk777/KFMLauncher
//   COMPANION_REPO         = antonk777/KFMLauncher (optional)
//   SITE_ROOT              = directory Caddy serves (default: this script's dir)

import { copyFile, mkdir, readdir, unlink, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const outDir = process.env.SITE_ROOT || scriptDir;
const repo = process.env.COMPANION_REPO || "antonk777/KFMLauncher";
const token = process.env.COMPANION_GITHUB_TOKEN || process.env.GITHUB_TOKEN;

if (!token) {
  console.error("Set COMPANION_GITHUB_TOKEN (PAT with read access to " + repo + ").");
  process.exit(1);
}

const headers = {
  Authorization: "Bearer " + token,
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "kfm-site-deploy",
};

await mkdir(outDir, { recursive: true });

const latest = await getJson("https://api.github.com/repos/" + repo + "/releases/latest");
if (!latest.tag_name) {
  console.error("No GitHub Release found in " + repo + ".");
  process.exit(1);
}

const tag = String(latest.tag_name).replace(/[^A-Za-z0-9._-]+/g, "-");
const outName = "KFM-Companion-" + tag + ".exe";
const assets = latest.assets || [];
const preferred = [
  outName,
  "KFM-Companion.exe",
  "KFM-Launcher.exe",
  "KFM Companion.exe",
  "KFM Launcher.exe",
];
const asset =
  preferred.map((name) => assets.find((item) => item.name === name)).find(Boolean) ||
  assets.find((item) => /^KFM-Companion-.+\.exe$/i.test(item.name)) ||
  assets.find((item) => /\.exe$/i.test(item.name));
if (!asset) {
  const names = assets.map((item) => item.name).join(", ") || "(none)";
  console.error("Release " + latest.tag_name + " has no .exe asset. Found: " + names);
  process.exit(1);
}

const file = await getBuffer(
  "https://api.github.com/repos/" + repo + "/releases/assets/" + asset.id,
  { ...headers, Accept: "application/octet-stream" }
);

const versionedPath = join(outDir, outName);
const stablePath = join(outDir, "KFM-Companion.exe");
await writeFile(versionedPath, file);
await copyFile(versionedPath, stablePath);

const meta = {
  tag: latest.tag_name,
  name: latest.name || ("KFM Companion " + latest.tag_name),
  body: releaseNotes(latest.body),
  published: latest.published_at || "",
  file: outName,
  download: "/download",
};

await writeFile(join(outDir, "release.json"), JSON.stringify(meta, null, 2) + "\n");

// Drop older versioned builds so the web root does not grow forever.
const keep = new Set([outName, "KFM-Companion.exe"]);
for (const name of await readdir(outDir)) {
  if (!/^KFM-Companion-.+\.exe$/i.test(name)) continue;
  if (keep.has(name)) continue;
  await unlink(join(outDir, name));
  console.log("Removed old " + name);
}

console.log(
  "Wrote " + versionedPath + " (+ KFM-Companion.exe) from " + repo + " " +
    latest.tag_name + " asset " + asset.name + " (" + file.length + " bytes)"
);

function releaseNotes(raw) {
  let text = String(raw || "");
  text = text.replace(/<!--[\s\S]*?-->/g, "");
  text = text.replace(/^\s*\*{0,2}Full Changelog\*{0,2}\s*:\s*\S+\s*$/gim, "");
  text = text.replace(/https?:\/\/github\.com\/[^\s]+\/compare\/[^\s]+/g, "");
  text = text.replace(/\n{3,}/g, "\n\n").trim();
  if (/^#{1,6}\s+\S.*$/.test(text) && !/\n/.test(text)) return "";
  return text;
}

async function getJson(url) {
  const res = await fetch(url, { headers: { ...headers, Accept: "application/vnd.github+json" } });
  if (!res.ok) {
    throw new Error(url + " -> " + res.status + " " + (await res.text()));
  }
  return res.json();
}

async function getBuffer(url, extraHeaders) {
  const res = await fetch(url, { headers: extraHeaders, redirect: "follow" });
  if (!res.ok) {
    throw new Error(url + " -> " + res.status + " " + (await res.text()));
  }
  return Buffer.from(await res.arrayBuffer());
}
