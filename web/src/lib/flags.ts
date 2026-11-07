// Public session lists and pages. Recording keeps running either way.
// Set this to false to hide them again, then redeploy the site.
// Keep stats-server.py SESSIONS_PUBLIC in step with this.
export const SESSIONS_PUBLIC = true;

// Session lists and player histories omit maps that started before this.
// 7 Nov 2026 19:00 Moscow (UTC+3). Keep stats-server.py in step with this.
export const SESSIONS_VISIBLE_SINCE = 1_794_067_200;
