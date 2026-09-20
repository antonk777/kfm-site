// Download the latest KFM Companion.exe from the private companion repo.
// Cloudflare Pages: Build command `node fetch-companion.mjs`, output `/`
// Env: COMPANION_GITHUB_TOKEN = fine-grained PAT with Contents: Read on antonk777/KFMLauncher

const repo = process.env.COMPANION_REPO || "antonk777/KFMLauncher";
const token = process.env.COMPANION_GITHUB_TOKEN || process.env.GITHUB_TOKEN;
const outName = "KFM-Companion.exe";

if (!token) {
  console.error("Set COMPANION_GITHUB_TOKEN (PAT with read access to " + repo + ").");
  process.exit(1);
}

const headers = {
  Authorization: "Bearer " + token,
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "kfm-site-deploy",
};

const latest = await getJson("https://api.github.com/repos/" + repo + "/releases/latest");
if (!latest.tag_name) {
  console.error("No GitHub Release found in " + repo + ".");
  process.exit(1);
}

const asset = (latest.assets || []).find((item) => item.name === outName);
if (!asset) {
  console.error("Release " + latest.tag_name + " has no " + outName + ".");
  process.exit(1);
}

const file = await getBuffer(
  "https://api.github.com/repos/" + repo + "/releases/assets/" + asset.id,
  { ...headers, Accept: "application/octet-stream" }
);
await import("node:fs/promises").then((fs) => fs.writeFile(outName, file));
console.log("Wrote " + outName + " from " + repo + " " + latest.tag_name + " (" + file.length + " bytes)");

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
