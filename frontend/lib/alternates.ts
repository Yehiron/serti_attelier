/** Site-relative path of an alternate (the API may return absolute URLs for another host). */
export function alternatePath(url: string): string {
  try {
    const parsed = new URL(url, 'https://relative.invalid');
    return parsed.pathname + parsed.search;
  } catch {
    return url;
  }
}
