'use client';

import Link from 'next/link';
import { useRef, useState, type ReactNode } from 'react';

/** Native horizontal scrolling keeps vertical panning and ordinary taps intact. */
export function PiecePhotoLink({ href, label, alternate, children }: { href: string; label: string; alternate: boolean; children: ReactNode }) {
  const [current, setCurrent] = useState(0);
  const gesture = useRef({ x: 0, y: 0, swiped: false });
  return <>
    <Link href={href} aria-label={label} className={alternate ? 'piece-photo-link has-alternate' : 'piece-photo-link'}
      onTouchStart={event => { const touch = event.touches[0]; gesture.current = { x: touch.clientX, y: touch.clientY, swiped: false }; }}
      onTouchMove={event => { const touch = event.touches[0]; if (Math.abs(touch.clientX - gesture.current.x) > 10 || Math.abs(touch.clientY - gesture.current.y) > 10) gesture.current.swiped = true; }}
      onClick={event => { if (gesture.current.swiped) { event.preventDefault(); gesture.current.swiped = false; } }}
      onScroll={event => { const el = event.currentTarget; setCurrent(el.scrollLeft > el.clientWidth / 2 ? 1 : 0); }}>
      {children}
    </Link>
    {alternate && <span className="piece-photo-dots" aria-hidden="true"><span data-current={current === 0} /><span data-current={current === 1} /></span>}
  </>;
}
