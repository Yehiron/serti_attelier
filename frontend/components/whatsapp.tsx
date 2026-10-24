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
  return <a className={`floating-whatsapp ${piece ? 'with-sticky' : ''}`} href={pieceUrl || settings.whatsapp.general_url} aria-label={dict.ui.whatsapp} rel="noopener noreferrer" target="_blank"><svg viewBox="0 0 32 32" aria-hidden="true"><path d="M6 26l1-6a11 11 0 1 1 5 6l-6 1z"/><path d="M12 10c-3 3 5 11 8 8l-3-2-2 1-2-3 1-2z"/></svg></a>;
}
