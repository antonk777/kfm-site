import { i18n, localeFromAcceptLanguage, setLocale, type Locale, LOCALES } from "~/i18n";

export default defineNuxtPlugin(() => {
  if (import.meta.server) {
    const header = useRequestHeaders(["accept-language"])["accept-language"];
    setLocale(localeFromAcceptLanguage(header));
    return;
  }
  // Client: prefer the saved choice, else the browser list (already applied
  // when the module loaded). Re-apply so <html lang> matches.
  const stored = (() => {
    try {
      return localStorage.getItem("kfm-lang");
    } catch {
      return null;
    }
  })();
  if (stored && (LOCALES as readonly string[]).includes(stored)) {
    setLocale(stored as Locale);
  } else {
    setLocale(i18n.locale);
  }
});
