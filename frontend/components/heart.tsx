import { useId } from 'react';

const heartPath = 'M16 27.6C7.4 21.3 1.6 15.9 1.6 9.7a7.2 7.2 0 0 1 14.4-2.4 7.2 7.2 0 0 1 14.4 2.4c0 6.2-5.8 11.6-14.4 17.9Z';

/** Brand heart: a symmetric outline, filled emerald once saved (docs/marca.md). */
export function Heart({ filled = false, pop = false }: { filled?: boolean; pop?: boolean }) {
  const id = useId();
  return <span className={`heart${filled ? ' is-filled' : ''}${pop ? ' is-pop' : ''}`} aria-hidden="true">
    {/* Mirror-symmetric around x = 16. */}
    <svg viewBox="0 0 32 29">
      <path className="heart-stone" d={heartPath} />
      {pop && filled && <>
        <defs>
          <clipPath id={`${id}-clip`}><path d={heartPath} /></clipPath>
          <linearGradient id={`${id}-light`} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="8" y2="8">
            <stop offset="0" stopColor="white" stopOpacity="0" />
            <stop offset=".5" stopColor="white" stopOpacity=".55" />
            <stop offset="1" stopColor="white" stopOpacity="0" />
          </linearGradient>
        </defs>
        <g clipPath={`url(#${id}-clip)`}>
          <path className="heart-sweep" d="M-20 20L20-20L28-12L-12 28Z" fill={`url(#${id}-light)`} />
        </g>
        <path className="heart-sparkle" d="M25 1.5L26.1 5.9L30.5 7L26.1 8.1L25 12.5L23.9 8.1L19.5 7L23.9 5.9Z" />
      </>}
    </svg>
  </span>;
}
