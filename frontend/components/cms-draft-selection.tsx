'use client';
import { useEffect } from 'react';
import { selectionMessage } from '@/lib/cms-selection';

/** Mounted exclusively by server components after checking real Next Draft Mode. */
export function CmsDraftSelection() {
  useEffect(() => {
    if (window.parent === window) return;
    const origin = location.origin;
    const send = (data: object) => window.parent.postMessage(data, origin);
    const click = (event: MouseEvent) => {
      const section = (event.target as Element)?.closest<HTMLElement>('[data-cms-section]');
      if (!section) return;
      event.preventDefault(); event.stopPropagation();
      send({ type: 'cms:selected', id: section.dataset.cmsSection });
    };
    const message = (event: MessageEvent) => {
      if (event.source !== window.parent) return;
      const selected = selectionMessage(event.data, event.origin, origin, true);
      if (!selected) return;
      document.querySelectorAll<HTMLElement>('[data-cms-section]').forEach(section => {
        const active = section.dataset.cmsSection === selected.id;
        section.style.outline = active ? '3px solid #b77a52' : '';
        section.style.outlineOffset = active ? '-3px' : '';
      });
      if (selected.reveal) { const section = [...document.querySelectorAll<HTMLElement>('[data-cms-section]')].find(s => s.dataset.cmsSection === selected.id); section?.scrollIntoView({behavior:'instant',block:'center'}); }
      else if (selected.scrollY !== undefined) window.scrollTo({ top: selected.scrollY, behavior: 'instant' });
    };
    let frame = 0;
    const scroll = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => send({type:'cms:scroll', y:window.scrollY})); };
    const key = (event: KeyboardEvent) => { const target = event.target as HTMLElement; if ((event.key === 'Enter' || event.key === ' ') && target.hasAttribute('data-cms-section')) { event.preventDefault(); send({type:'cms:selected', id:target.dataset.cmsSection}); } };
    document.addEventListener('keydown', key);
    document.addEventListener('click', click, true);
    window.addEventListener('message', message);
    window.addEventListener('scroll', scroll, {passive:true});
    send({type:'cms:ready'});
    return () => { cancelAnimationFrame(frame); document.removeEventListener('keydown', key); document.removeEventListener('click', click, true); window.removeEventListener('message', message); window.removeEventListener('scroll', scroll); };
  }, []);
  return null;
}
