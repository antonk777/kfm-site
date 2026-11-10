// Bare numeric path (/76561198006804047/) → canonical player URL.
export default defineEventHandler((event) => {
  const path = getRequestURL(event).pathname;
  const m = /^\/(\d{16,20})\/?$/.exec(path);
  if (!m) return;
  return sendRedirect(event, `/players/${m[1]}`, 302);
});
