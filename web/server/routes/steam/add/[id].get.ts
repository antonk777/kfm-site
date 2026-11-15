// The game can only open http://. This page hands the browser to the Steam
// client profile (steam://url/SteamIDPage/<SteamID64>). friends/add ignores
// the target and opens the logged-in player's own Add a Friend page.
export default defineEventHandler((event) => {
  const id = String(event.context.params?.id || "");
  if (!/^\d{16,20}$/.test(id)) {
    throw createError({ statusCode: 404, statusMessage: "Not found" });
  }
  const url = `steam://url/SteamIDPage/${id}`;
  const web = `https://steamcommunity.com/profiles/${id}`;
  setResponseHeader(event, "content-type", "text/html; charset=utf-8");
  setResponseHeader(event, "cache-control", "no-store");
  return `<!doctype html><html><head><meta charset="utf-8"><title>Steam</title><script>location.replace(${JSON.stringify(url)})</script></head><body><p><a href="${url}">Open in Steam</a></p><p><a href="${web}">Open in the browser</a></p></body></html>`;
});
