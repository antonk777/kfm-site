import { createReadStream, existsSync } from "node:fs";
import { resolve } from "node:path";
import { sendStream, setHeader, createError } from "h3";

// Map previews live in site/maps (shared with the old site), not in public/.
export default defineEventHandler((event) => {
  const rel = (event.context.params?.path || "").replace(/^\/+/, "");
  if (!rel || !rel.toLowerCase().endsWith(".jpg") || rel.includes("..")) {
    throw createError({ statusCode: 404, statusMessage: "Not found" });
  }
  const mapsDir = useRuntimeConfig().mapsDir as string;
  const file = resolve(mapsDir, rel);
  if (!file.startsWith(mapsDir) || !existsSync(file)) {
    throw createError({ statusCode: 404, statusMessage: "Not found" });
  }
  setHeader(event, "Content-Type", "image/jpeg");
  setHeader(event, "Cache-Control", "public, max-age=3600");
  return sendStream(event, createReadStream(file));
});
