import type { Image, PieceDetail } from './api/types.ts';

export function largestImage(image: Image): string {
  const candidates = image.srcset.split(',').map(part => part.trim().match(/^(\S+)\s+(\d+)w$/)).filter((x): x is RegExpMatchArray => !!x);
  return candidates.sort((a, b) => Number(b[2]) - Number(a[2]))[0]?.[1] || image.src;
}
export function breadcrumbs(items: { name: string; url: string }[], base: string) {
  return { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: items.map((item, index) => ({ '@type': 'ListItem', position: index + 1, name: item.name, item: new URL(item.url, base).href })) };
}
export function itemList(items: { name: string; url: string }[], base: string) {
  return { '@context': 'https://schema.org', '@type': 'ItemList', itemListElement: items.slice(0, 20).map((item, index) => ({ '@type': 'ListItem', position: index + 1, name: item.name, url: new URL(item.url, base).href })) };
}
export function productSchema(piece: PieceDetail, url: string, base: string, returnsUrl?: string) {
  const price = piece.sale_price ?? piece.price;
  const availability = { available: 'InStock', reserved: 'OutOfStock', sold: 'SoldOut', preorder: 'PreOrder' }[piece.sale_state];
  return { '@context': 'https://schema.org', '@type': 'Product', name: piece.name, description: piece.short_description, sku: piece.sku, image: piece.gallery.map(image => new URL(largestImage(image), base).href), material: piece.materials.map(x => x.name).join(', '), brand: { '@type': 'Brand', name: 'SERTI' }, offers: { '@type': 'Offer', url: new URL(url, base).href, price: price.amount_cents / 100, priceCurrency: price.currency, itemCondition: 'https://schema.org/NewCondition', availability: `https://schema.org/${availability}`, shippingDetails: { '@type': 'OfferShippingDetails', shippingRate: { '@type': 'MonetaryAmount', value: 0, currency: 'COP' }, shippingDestination: { '@type': 'DefinedRegion', addressCountry: 'CO' } }, ...(returnsUrl ? { hasMerchantReturnPolicy: { '@type': 'MerchantReturnPolicy', applicableCountry: 'CO', merchantReturnLink: new URL(returnsUrl, base).href } } : {}) } };
}
type Language = 'es' | 'en';
const normalize = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
const limit = (s: string, max = 160) => s.length <= max ? s : s.slice(0, max - 1).replace(/\s+\S*$/, '').replace(/[,:;.]$/, '') + '…';
export function listingCopy(kind: 'catalog' | 'category' | 'stone' | 'collection', name: string, locale: Language) {
  const lower = name.toLocaleLowerCase(locale);
  const emerald = /^(esmeralda|emerald)s?$/.test(normalize(lower));
  if (kind === 'catalog') return locale === 'es' ? { title: 'Joyería en oro 18k y esmeraldas colombianas | SERTI Armenia', description: 'Explora anillos, cadenas, aretes, dijes y pulseras hechos a mano en oro 18k con esmeraldas colombianas. Piezas únicas de SERTI, joyería en Armenia, Quindío.' } : { title: '18k gold and Colombian emerald jewelry | SERTI Armenia', description: 'Explore handmade 18k gold rings, chains, earrings, pendants and bracelets with Colombian emeralds. Unique SERTI jewelry from Armenia, Colombia.' };
  const title = kind === 'stone' ? (locale === 'es' ? `Joyas con ${lower}${emerald ? ' colombiana' : ''} en oro 18k | SERTI Armenia` : `Jewelry with ${lower}${emerald ? ' from Colombia' : ''} in 18k gold | SERTI Armenia`) : kind === 'category' ? (locale === 'es' ? `${name} de oro 18k · Joyería en Armenia | SERTI` : `${name} in 18k gold · Jewelry from Armenia | SERTI`) : (locale === 'es' ? `${name} · Joyería de autor en Armenia | SERTI` : `${name} · Fine jewelry from Armenia | SERTI`);
  const known: Record<string, string> = {
    anillos: 'Anillos únicos en oro 18k con esmeraldas colombianas, diamantes y zafiros, hechos a mano en Armenia, Quindío. Diseños de autor.',
    aretes: 'Aretes hechos a mano en oro 18k con esmeraldas colombianas y diamantes. Diseños de autor de SERTI, joyería en Armenia, Quindío.',
    cadenas: 'Cadenas de oro 18k hechas a mano en Armenia, Quindío, solas o con dije de esmeralda colombiana. Piezas únicas con envío a toda Colombia.',
    dijes: 'Dijes de oro 18k con esmeraldas colombianas hechos a mano en Armenia, Quindío. Piezas únicas de SERTI con envío a toda Colombia.',
    pulseras: 'Pulseras de oro 18k con esmeraldas colombianas y diamantes, hechas a mano en Armenia, Quindío. Piezas únicas con envío a toda Colombia.',
  };
  const description = locale === 'es' ? (kind === 'category' ? known[normalize(lower)] || `Joyas de ${lower} hechas a mano en oro 18k con esmeraldas colombianas. Piezas únicas de SERTI, joyería en Armenia, Quindío. Envíos a toda Colombia.` : kind === 'stone' ? `Joyas con ${lower}${emerald ? ' colombiana' : ''} en oro 18k: anillos, aretes, dijes y pulseras hechos a mano en Armenia, Quindío. Piezas únicas de SERTI.` : `${name}: joyas de autor en oro 18k hechas a mano en Armenia, Quindío. Piezas únicas de SERTI con envío a toda Colombia.`) : (kind === 'category' ? `${name} jewelry handmade in 18k gold with Colombian emeralds. Unique SERTI pieces from Armenia, Colombia, shipped nationwide.` : kind === 'stone' ? `Jewelry with ${lower}${emerald ? ' from Colombia' : ''} in 18k gold: rings, earrings, pendants and bracelets handmade in Armenia, Colombia. Unique SERTI pieces.` : `${name}: designer 18k gold jewelry handmade in Armenia, Colombia. Unique SERTI pieces shipped nationwide.`);
  return { title, description: limit(description) };
}
export function pieceTitle(piece: PieceDetail, locale: Language) {
  const name = piece.name.trim();
  const missing = (value?: string) => value?.trim() && !normalize(name).includes(normalize(value.trim()));
  const metal = [piece.attributes.metal, piece.attributes.metal_purity].filter(missing).join(' ');
  const stones = piece.stones.map(x => x.name.trim()).filter(x => missing(x)).join(', ');
  const suffix = ' | SERTI Armenia';
  let result = name + (metal ? ` · ${metal}` : '') + (stones ? `${locale === 'es' ? ' con ' : ' with '}${stones}` : '') + suffix;
  if (result.length > 65) result = name + (metal ? ` · ${metal}` : '') + suffix;
  if (result.length > 65) result = name + suffix;
  return result.length <= 65 ? result : limit(name, 65 - suffix.length) + suffix;
}
export function pieceDescription(piece: PieceDetail, locale: Language) {
  const short = piece.short_description.trim();
  const details = [piece.attributes.metal, piece.attributes.metal_purity].filter(Boolean).join(' ');
  const stones = piece.stones.map(x => x.name).join(', ');
  const fallback = locale === 'es' ? `${piece.name}${details ? ` en ${details}` : ''}${stones ? ` con ${stones}` : ''}, hecha a mano en Armenia, Quindío.` : `${piece.name}${details ? ` in ${details}` : ''}${stones ? ` with ${stones}` : ''}, handmade in Armenia, Colombia.`;
  const base = short || fallback;
  const unique = locale === 'es' ? /pieza única/i.test(base) : /unique|one.of.a.kind/i.test(base);
  const ending = locale === 'es' ? (unique ? ' Envío a toda Colombia.' : ' Pieza única con envío a toda Colombia.') : (unique ? ' Shipping throughout Colombia.' : ' A unique piece with shipping throughout Colombia.');
  return limit(base, 160 - ending.length) + ending;
}
export function jsonLd(value: unknown) { return JSON.stringify(value).replace(/</g, '\\u003c'); }
