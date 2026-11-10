export function focalPosition(image: { focal?: { x: number; y: number } }): string | undefined {
  const focal = image.focal;
  if (!focal || !Number.isFinite(focal.x) || !Number.isFinite(focal.y)) return undefined;
  return `${Math.min(1, Math.max(0, focal.x)) * 100}% ${Math.min(1, Math.max(0, focal.y)) * 100}%`;
}
