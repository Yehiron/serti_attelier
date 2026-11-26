type Named = { slug: string; name: string };
type Chip = { label: string; href: string; active: boolean };

export function listingBannerChips({ kind, base, query, children, stones, facets, all, categoryHref }: {
  kind: string; base: string; query: URLSearchParams; children: Named[]; stones: Named[];
  facets: { slug: string; count: number }[]; all: string; categoryHref: (slug: string) => string;
}): Chip[] {
  if (kind === 'stone') return [];
  const selected = (query.get('stone') ?? '').split(',').filter(Boolean);
  const url = (stone?: string) => {
    const next = new URLSearchParams(query);
    next.delete('stone'); next.delete('page');
    if (stone) next.set('stone', stone);
    const suffix = next.toString();
    return suffix ? `${base}?${suffix}` : base;
  };
  if (kind === 'category' && children.length) return [
    { label: all, href: base, active: ![...query.keys()].some(key => !['page', 'sort', 'availability'].includes(key)) },
    ...children.map(child => ({ label: child.name, href: categoryHref(child.slug), active: false })),
  ];
  const chips = [
    { label: all, href: url(), active: selected.length === 0 },
    ...facets.filter(f => f.count > 0).flatMap(f => {
      const stone = stones.find(s => s.slug === f.slug);
      if (!stone) return [];
      const active = selected.length === 1 && selected[0] === stone.slug;
      return [{ label: stone.name, href: url(active ? undefined : stone.slug), active }];
    }),
  ];
  // A lone «All» chip filters nothing.
  return chips.length > 1 ? chips : [];
}

export function listingBannerCount(count: number, copy: { singular: string; plural: string }): string {
  return count > 0 ? (count === 1 ? copy.singular : copy.plural).replace('{count}', String(count)) : '';
}
