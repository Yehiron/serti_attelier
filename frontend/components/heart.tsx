/** Brand heart: a symmetric outline with the SERTI monogram inside; emerald once saved (docs/marca.md). */
export function Heart({ filled = false, pop = false }: { filled?: boolean; pop?: boolean }) {
  return <span className={`heart${filled ? ' is-filled' : ''}${pop ? ' is-pop' : ''}`} aria-hidden="true">
    {/* Mirror-symmetric around x = 16. */}
    <svg viewBox="0 0 32 29"><path d="M16 27.6C7.4 21.3 1.6 15.9 1.6 9.7a7.2 7.2 0 0 1 14.4-2.4 7.2 7.2 0 0 1 14.4 2.4c0 6.2-5.8 11.6-14.4 17.9Z" /></svg>
    <span className="heart-mark" />
  </span>;
}
