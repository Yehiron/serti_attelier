'use client';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import type { Settings } from '@/lib/api/types';
import type { Dictionary } from '@/app/[locale]/dictionaries';
export function FloatingWhatsApp({ settings, dict }: { settings: Settings; dict: Dictionary }) {
  const path = usePathname();
  const [pieceUrl, setPieceUrl] = useState<string | null>(null);
  const piece = /\/(pieces|piezas)\//.test(path);
  useEffect(() => {
    const update = () => setPieceUrl(document.querySelector<HTMLElement>('[data-page-whatsapp]')?.dataset.pageWhatsapp ?? null);
    update(); const observer = new MutationObserver(update); observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-page-whatsapp'] }); return () => observer.disconnect();
  }, [path]);
  if (/\/checkout\/?$/.test(path) || !settings.whatsapp.general_url) return null;
  // Burbuja: centro (16,16), radio 14, caja [2,2]–[30,30].
  // Cola (3,29) dentro de esa caja; auricular [9,9]–[23,23], centro (16,16).
  return <a className={`floating-whatsapp ${piece ? 'with-sticky' : ''}`} href={pieceUrl || settings.whatsapp.general_url} aria-label={dict.ui.whatsapp} rel="noopener noreferrer" target="_blank">
    <svg viewBox="0 0 32 32" aria-hidden="true">
      <path d="M4.8 24.4 A14 14 0 1 1 7.6 27.2 L3 29 Z" />
      <path style={{ fill: 'currentColor', stroke: 'none' }} d="M11 9 H12.5 Q13 9 13.3 9.6 L14.8 12.6 Q15.1 13.2 14.6 13.7 L13 15.3 Q14.3 17.7 16.7 19 L18.3 17.4 Q18.8 16.9 19.4 17.2 L22.4 18.7 Q23 19 23 19.5 V21 Q23 23 21 23 C15 23 9 17 9 11 Q9 9 11 9 Z" />
    </svg>
  </a>;
}
