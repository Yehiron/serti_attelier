/**
 * Owners edit titles in single-line fields, so " / " marks a line break
 * ("Un poco de tierra. / Un poco de eternidad."). Newlines are accepted too.
 */
export function titleLines(text: string): string[] {
  return text.split(/\s+\/\s+|\n/).map((line) => line.trim()).filter(Boolean);
}
