import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

const ROOT = fileURLToPath(new URL(".", import.meta.url));
// Dev talks to the live stats API on the public site (same payloads Caddy
// serves). SSH tunnel is opt-in: NUXT_USE_TUNNEL=1 plus
// NUXT_STATS_PROXY=http://127.0.0.1:18765. Local Python: …:8765.
const STATS_PROXY = process.env.NUXT_STATS_PROXY || "https://kf-maniacs.com";
const MAPS_DIR = resolve(ROOT, "..", "maps");

export default defineNuxtConfig({
  compatibilityDate: "2025-11-11",
  srcDir: "src/",
  modules: ["./modules/dev-stats-tunnel"],
  css: [
    "flag-icons/css/flag-icons.min.css",
    "~/styles/fonts.css",
    "~/styles/base.css",
  ],
  app: {
    head: {
      htmlAttrs: { lang: "en" },
      meta: [
        { charset: "utf-8" },
        { name: "viewport", content: "width=device-width, initial-scale=1" },
        { name: "robots", content: "noindex,nofollow" },
      ],
      link: [{ rel: "icon", href: "/favicon.ico" }],
      title: "KF-Maniacs · Home",
      // Umami. /umami-website-id is a UUID written on deploy; anything else
      // leaves the tracker off.
      script: [
        {
          children: `(function(){fetch("/umami-website-id",{cache:"no-store"}).then(function(r){return r.ok?r.text():""}).then(function(raw){var id=(raw||"").trim();if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))return;var el=document.createElement("script");el.defer=true;el.src="/kf.js";el.setAttribute("data-website-id",id);el.setAttribute("data-domains","kf-maniacs.com,kfm.manul.lol");el.setAttribute("data-do-not-track","true");el.setAttribute("data-exclude-search","true");document.head.appendChild(el)}).catch(function(){})})();`,
          tagPosition: "head",
        },
      ],
    },
  },
  runtimeConfig: {
    mapsDir: MAPS_DIR,
    statsProxy: STATS_PROXY,
  },
  // Production node server. Dev does not use these: the Vite proxy below
  // owns /api so a UI reload does not restart the connection.
  routeRules: {
    "/api/stats/**": { proxy: `${STATS_PROXY}/api/stats/**` },
    "/release.json": { proxy: "https://kf-maniacs.com/release.json" },
    "/mod-changelog.json": { proxy: "https://kf-maniacs.com/mod-changelog.json" },
  },
  typescript: {
    strict: true,
    typeCheck: false,
  },
  vite: {
    server: {
      // Map previews live in site/maps (shared with the old site), not public/.
      fs: { allow: [ROOT, resolve(ROOT, "..")] },
      // Stays up across Vue hot reload. Nitro's own proxy died on every
      // server restart, and the pages then kept the failed response.
      proxy: {
        "/api/stats": { target: STATS_PROXY, changeOrigin: true },
        "/release.json": { target: "https://kf-maniacs.com", changeOrigin: true },
        "/mod-changelog.json": { target: "https://kf-maniacs.com", changeOrigin: true },
      },
    },
  },
});
