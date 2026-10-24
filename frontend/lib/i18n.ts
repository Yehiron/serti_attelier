export const locales = ["es", "en"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "es";
export const localeCookie = "serti_locale";

export function isLocale(value: string | undefined | null): value is Locale {
  return value === "es" || value === "en";
}

/** First path segment if it is a supported locale (e.g. "/en/piezas" -> "en"). */
export function localeFromPath(pathname: string): Locale | null {
  const segment = pathname.split("/")[1];
  return isLocale(segment) ? segment : null;
}

/** Highest-weighted supported language in an Accept-Language header. */
export function localeFromAcceptLanguage(header: string | null): Locale | null {
  if (!header) return null;
  const ranked = header
    .split(",")
    .map((part) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params.map((p) => p.trim()).find((p) => p.startsWith("q="));
      return { lang: tag.split("-")[0].toLowerCase(), q: q ? Number(q.slice(2)) : 1 };
    })
    .filter(({ q }) => Number.isFinite(q) && q > 0)
    .sort((a, b) => b.q - a.q);
  return ranked.map(({ lang }) => lang).find(isLocale) ?? null;
}

/** Saved preference first, then the browser language, then Spanish. */
export function negotiateLocale(cookie: string | undefined, acceptLanguage: string | null): Locale {
  if (isLocale(cookie)) return cookie;
  return localeFromAcceptLanguage(acceptLanguage) ?? defaultLocale;
}
