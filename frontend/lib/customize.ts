import type { Locale } from './i18n.ts';

const kinds: Record<string, [string, string]> = {
  anillos: ['anillo', 'ring'], rings: ['ring', 'ring'], aretes: ['aretes', 'earrings'], earrings: ['earrings', 'earrings'],
  cadenas: ['cadena', 'necklace'], chains: ['chain', 'necklace'], collares: ['collar', 'necklace'], necklaces: ['necklace', 'necklace'],
  dijes: ['dije', 'pendant'], pendants: ['pendant', 'pendant'], pulseras: ['pulsera', 'bracelet'], bracelets: ['bracelet', 'bracelet'],
};
export function categoryKind(slug: string, name: string) {
  const entry = kinds[slug.toLowerCase()];
  return { singular: entry?.[0] ?? name, icon: entry?.[1] ?? 'generic' };
}
export function customizeMessage(locale: Locale, type: string, stone: string | null, metal: string | null, note: string) {
  const lower = (value: string) => value.toLocaleLowerCase(locale);
  const advice = locale === 'es'
    ? [!stone && 'la piedra', !metal && 'el metal'].filter(Boolean).join(' y ')
    : [!stone && 'the stone', !metal && 'the metal'].filter(Boolean).join(' and ');
  const base = locale === 'es'
    ? `Hola SERTI, vengo de la página de personalización. Quiero una joya: ${lower(type)}${stone ? ` con ${lower(stone)}` : ''}${metal ? ` en ${lower(metal)}` : ''}${advice ? ` y me gustaría que me asesoren con ${advice}` : ''}.`
    : `Hello SERTI, I’m coming from the customization page. I would like a piece of jewelry: ${lower(type)}${stone ? ` with ${lower(stone)}` : ''}${metal ? ` in ${lower(metal)}` : ''}${advice ? ` and I would like advice on ${advice}` : ''}.`;
  const trimmed = note.slice(0, 300).trim();
  return base + (trimmed ? ` ${trimmed}` : '');
}

export function customizeColor(name: string, metal = false, gemColor?: string) {
  if (gemColor) return gemColor;
  const n = name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  if (metal) return /blanco|plata|white|silver/.test(n) ? '#dcdcd8' : /rosa|rose|pink/.test(n) ? '#e3a98e' : '#d9b25f';
  return /esmeralda|emerald/.test(n) ? '#1f7a55' : /rubi|ruby/.test(n) ? '#a51c3a' : /zafiro|sapphire/.test(n) ? '#244a9c' : /diamante|diamond/.test(n) ? '#e9eef2' : '#c9a96e';
}
