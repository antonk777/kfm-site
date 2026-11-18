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
  key: string;
  day: string;
  summary: string;
  notes: string[];
}

export type DaySummary = Omit<ModNote, "when" | "rev"> & { day: string };

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
  const names = MONTHS[locale] ?? MONTHS.en!;
  const name = names[month - 1];
  if (locale === "es" || locale === "pt") return `${day} de ${name} de ${year}`;
  if (locale === "de") return `${day}. ${name} ${year}`;
  return `${day} ${name} ${year}`;
}

export function noteText(entry: Pick<ModNote, "en">, locale: string): string {
  const text = (entry as unknown as Record<string, string | undefined>)[locale];
  if (text && text.trim()) return text.trim();
  return (entry.en || "").trim();
}

export function groupNotes(entries: ModNote[], locale: string, summaries: DaySummary[] = []): DayGroup[] {
  const groups: DayGroup[] = [];
  const index = new Map<string, DayGroup>();
  const byDay = new Map(summaries.map((summary) => [summary.day, summary]));
  for (const entry of entries) {
    const key = entry.when.split(" ")[0] || entry.when;
    let group = index.get(key);
    if (!group) {
      const summary = byDay.get(key);
      group = { key, day: formatDay(key, locale), summary: summary ? noteText(summary, locale) : "", notes: [] };
      index.set(key, group);
      groups.push(group);
    }
    const text = noteText(entry, locale);
    if (text) group.notes.push(text);
  }
  return groups;
}

export function previewGroups(entries: ModNote[], locale: string, limit: number, summaries: DaySummary[] = []): DayGroup[] {
  // Limit whole days, keeping every detail available inside each disclosure.
  return groupNotes(entries, locale, summaries).filter((group) => group.summary).slice(0, limit);
}

export function useModChangelog(): { entries: Ref<ModNote[] | null>; summaries: Ref<DaySummary[]> } {
  const entries = ref<ModNote[] | null>(null);
  const summaries = ref<DaySummary[]>([]);
  onMounted(() => {
    fetch("/mod-changelog.json", { cache: "no-store" })
      .then(async (res) => {
        const text = await res.text();
        if (!res.ok || !text.trim().startsWith("{")) return [];
        const data = JSON.parse(text) as { entries?: ModNote[]; summaries?: DaySummary[] };
        summaries.value = Array.isArray(data.summaries) ? data.summaries : [];
        return Array.isArray(data.entries) ? data.entries : [];
      })
      .then((rows) => {
        entries.value = rows;
      })
      .catch(() => {
        entries.value = [];
      });
  });
  return { entries, summaries };
}
