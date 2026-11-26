/** One observer per mounted document; no hidden state is emitted by the server. */
export function installScrollReveal(doc: Document, win: Window) {
  const media = win.matchMedia('(prefers-reduced-motion: reduce)');
  const selector = '.home-page [data-scroll-reveal], .piece-card';
  const seen = new WeakSet<Element>();
  let observer: IntersectionObserver | undefined;
  const clear = () => {
    observer?.disconnect();
    doc.querySelectorAll('.motion-pending').forEach(el => el.classList.remove('motion-pending'));
  };
  const scan = () => {
    if (media.matches || !observer) return;
    const rows = new Map<Element, Map<number, number>>();
    doc.querySelectorAll<HTMLElement>(selector).forEach(el => {
      if (!el.getClientRects().length) return;
      const rect = el.getBoundingClientRect();
      if (el.matches('.piece-card') && el.parentElement) {
        const row = Math.round(rect.top);
        const group = rows.get(el.parentElement) ?? new Map<number, number>();
        const index = group.get(row) ?? 0;
        if (!seen.has(el)) el.style.setProperty('--reveal-delay', `${Math.min(index, 7) * 70}ms`);
        group.set(row, index + 1);
        rows.set(el.parentElement, group);
      }
      if (seen.has(el)) return;
      seen.add(el);
      // Above-the-fold content, including listing cards, stays immediately visible.
      if (rect.top < win.innerHeight && rect.bottom > 0) return;
      el.classList.add('motion-pending');
      observer?.observe(el);
    });
  };
  const start = () => {
    clear();
    if (media.matches || !('IntersectionObserver' in win)) return;
    observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting || entry.intersectionRatio < .15) return;
        entry.target.classList.remove('motion-pending');
        observer?.unobserve(entry.target);
      });
    }, { threshold: .15 });
    scan();
  };
  doc.documentElement.classList.add('motion-ready');
  start();
  // Includes streamed server sections and subsequent client navigations; bursts of
  // mutations are coalesced into one layout read per frame.
  let frame = 0;
  const schedule = () => { if (!frame) frame = win.requestAnimationFrame(() => { frame = 0; scan(); }); };
  const mutations = new MutationObserver(schedule);
  mutations.observe(doc.body, { childList: true, subtree: true });
  media.addEventListener('change', start);
  return () => {
    if (frame) win.cancelAnimationFrame(frame);
    clear();
    mutations.disconnect();
    media.removeEventListener('change', start);
    doc.documentElement.classList.remove('motion-ready');
  };
}
