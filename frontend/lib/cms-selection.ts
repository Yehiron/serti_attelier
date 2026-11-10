/** Fixed, same-origin protocol. Never evaluate messages or interpolate ids in selectors. */
export function sectionAttributes(draft: boolean, id: string | number): Record<string, string | number> {
  return draft ? { 'data-cms-section': String(id), tabIndex: 0 } : {};
}
export function selectionMessage(data: unknown, origin: string, panelOrigin: string, draft: boolean): { id: string; scrollY?: number; reveal?: boolean } | null {
  if (!draft || origin !== panelOrigin || !data || typeof data !== 'object') return null;
  const message = data as Record<string, unknown>;
  if (message.type !== 'cms:select' || typeof message.id !== 'string' || message.id.length > 100) return null;
  return { id: message.id, ...(message.reveal === true ? { reveal: true } : {}), ...(typeof message.scrollY === 'number' && Number.isFinite(message.scrollY) && message.scrollY >= 0 ? { scrollY: message.scrollY } : {}) };
}
