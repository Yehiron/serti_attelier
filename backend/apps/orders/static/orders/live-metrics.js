// Live order-center figures (metrics, tab counts, «Hay pedidos nuevos») for the inbox.
// Keep the table stable: only summaries change until the operator refreshes it.
(() => {
  const center = document.querySelector('[data-center-url]'); if (!center) return;
  let busy = false, stopped = false, timer;
  const values = [...document.querySelectorAll('[data-metric-value]')];
  const tabs = [...document.querySelectorAll('[data-tab-count]')];
  const notice = document.querySelector('[data-new-orders]');
  const initialTotal = Number(tabs[0]?.textContent || 0);
  function schedule() { clearTimeout(timer); if (!stopped && !document.hidden) timer = setTimeout(refresh, 120000); }
  async function refresh(fresh = false) {
    if (busy || stopped || document.hidden) return;
    busy = true;
    try {
      const response = await fetch(center.dataset.centerUrl + location.search, { credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(8000) });
      if ([401,403].includes(response.status) || response.redirected) { stopped = true; return; }
      if (!response.ok) return;
      const data = await response.json();
      if (notice && (fresh || data.tabs[0].count > initialTotal)) notice.hidden = false;
      const update = (node, text) => {
        if (!node || node.textContent === String(text)) return;
        node.classList.add('oc-updating');
        setTimeout(() => { node.textContent = text; node.classList.remove('oc-updating'); }, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 180);
      };
      data.metrics.forEach((metric, i) => {
        update(values[i], `${metric.count}${metric.amount ? ` · ${metric.amount}` : ''}`);
        const small = values[i]?.parentElement.querySelector('small');
        if (small && 'payment_count' in metric) update(small, `De pago: ${metric.payment_count}`);
        if (small && 'cancelled_count' in metric) update(small, metric.cancelled_count ? `De ellos, cancelados o devueltos: ${metric.cancelled_count}${metric.cancelled_amount ? ` / ${metric.cancelled_amount}` : ''}` : '');
      });
      data.tabs.forEach((tab, i) => update(tabs[i], tab.count));
      const summary = document.querySelector('[data-center-summary]'); if (summary) summary.textContent = data.metrics.map(m => `${m.label}: ${m.count}`).join('. ');
    } catch { /* Retry while visible; the existing values remain usable. */ }
    finally { busy = false; schedule(); }
  }
  document.addEventListener('orders:notifications', e => { if (e.detail.fresh) refresh(true); });
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) refresh(); });
  window.addEventListener('pagehide', () => clearTimeout(timer));
  schedule();
})();
