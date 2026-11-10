// The mod change log. English and Russian come from ChangeLogLocNew.uc.
// The other site languages live in tools/changelog_i18n.json. A note with no
// text for the selected language shows the English. deploy.bat writes the
// public file; until that deploy the live site keeps the previous one.
import { onMounted, ref, type Ref } from "vue";

export interface ModNote {
  when: string;
  rev?: number;
  en: string;
  ru?: string;
  zh?: string;
  ja?: string;
  es?: string;
  pt?: string;
  de?: string;
  fr?: string;
  pl?: string;
  it?: string;
  sv?: string;
}

export interface DayGroup {
  day: string;
  notes: string[];
}

const MONTHS: Record<string, readonly string[]> = {
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  ru: ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
  es: ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
  pt: ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
  de: ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"],
  fr: ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
  pl: ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września", "października", "listopada", "grudnia"],
  it: ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"],
  sv: ["januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december"],
};

// "09.11.2026 23:54" -> "9 November 2026" (and the same shape in the other site languages).
export function formatDay(stamp: string, locale: string): string {
  const raw = stamp.split(" ")[0] || stamp;
  const match = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(raw);
  if (!match) return raw;
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return raw;
  if (locale === "zh" || locale === "ja") return `${year}年${month}月${day}日`;
  const names = MONTHS[locale] ?? MONTHS.en;
  const name = names[month - 1];
  if (locale === "es" || locale === "pt") return `${day} de ${name} de ${year}`;
  if (locale === "de") return `${day}. ${name} ${year}`;
  return `${day} ${name} ${year}`;
}

export function noteText(entry: ModNote, locale: string): string {
  const text = (entry as unknown as Record<string, string | undefined>)[locale];
  if (text && text.trim()) return text.trim();
  return (entry.en || "").trim();
}

export function groupNotes(entries: ModNote[], locale: string): DayGroup[] {
  const groups: DayGroup[] = [];
  const index = new Map<string, DayGroup>();
  for (const entry of entries) {
    const day = formatDay(entry.when, locale);
    let group = index.get(day);
    if (!group) {
      group = { day, notes: [] };
      index.set(day, group);
      groups.push(group);
    }
    const text = noteText(entry, locale);
    if (text) group.notes.push(text);
  }
  return groups;
}

export function previewGroups(entries: ModNote[], locale: string, limit: number): DayGroup[] {
  return groupNotes(entries.slice(0, limit), locale);
}

export function useModChangelog(): { entries: Ref<ModNote[] | null> } {
  const entries = ref<ModNote[] | null>(null);
  onMounted(() => {
    fetch("/mod-changelog.json", { cache: "no-store" })
      .then(async (res) => {
        const text = await res.text();
        if (!text.trim().startsWith("{")) return [];
        const data = JSON.parse(text) as { entries?: ModNote[] };
        return Array.isArray(data.entries) ? data.entries : [];
      })
      .then((rows) => {
        entries.value = rows;
      })
      .catch(() => {
        entries.value = [];
      });
  });
  return { entries };
}
