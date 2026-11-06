(() => {
  const root = document.querySelector('[data-notifications]'); if (!root) return;
  const toggle = root.querySelector('[data-notice-toggle]'), panel = root.querySelector('.an-panel');
  const count = root.querySelector('[data-notice-count]'), list = root.querySelector('[data-notice-list]');
  const toast = root.querySelector('[data-notice-toast]'), sound = root.querySelector('[data-notice-sound]');
  const error = root.querySelector('[data-notice-error]');
  let since = 0, initialized = false, stopped = false, busy = false, timer, toastTimer, delay = 45000;
  try { sound.checked = localStorage.getItem('serti-notice-sound') === 'yes'; } catch {}
  sound.addEventListener('change', () => { try { localStorage.setItem('serti-notice-sound', sound.checked ? 'yes' : 'no'); } catch {} });
  let audio;
  // Unlock audio only after an explicit interaction; never play on initial load.
  sound.addEventListener('change', () => { if (sound.checked) { audio ||= new window.AudioContext(); audio.resume().catch(() => {}); } });
  function close() { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); }
  toggle.addEventListener('click', () => { if (!panel.hidden) return close(); panel.hidden = false; toggle.setAttribute('aria-expanded', 'true'); panel.querySelector('button').focus(); });
  root.querySelector('[data-notice-close]').addEventListener('click', close);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !panel.hidden) { e.preventDefault(); close(); } });
  document.addEventListener('click', e => { if (!panel.hidden && !root.contains(e.target)) close(); });
  panel.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const focusable = [...panel.querySelectorAll('a,button,input')].filter(x => !x.disabled);
    if (e.shiftKey && document.activeElement === focusable[0]) { e.preventDefault(); focusable.at(-1).focus(); }
    else if (!e.shiftKey && document.activeElement === focusable.at(-1)) { e.preventDefault(); focusable[0].focus(); }
  });
  function schedule() { clearTimeout(timer); if (!stopped && !document.hidden) timer = setTimeout(poll, delay); }
  function expired(response) { if ([401,403].includes(response.status) || response.redirected) { stopped = true; clearTimeout(timer); error.textContent = 'La sesión terminó. Vuelve a iniciar sesión para consultar los avisos.'; return true; } return false; }
  async function poll() {
    if (stopped || document.hidden || busy) return;
    busy = true;
    try {
      const response = await fetch(`${root.dataset.unreadUrl}?since=${since}`, { credentials: 'same-origin', cache: 'no-store', redirect: 'follow' });
      if (expired(response)) return;
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error();
      const data = await response.json(); count.textContent = data.count; count.setAttribute('aria-label', `${data.count} avisos sin leer`);
      list.replaceChildren();
      for (const item of data.items) {
        const li = document.createElement('li'), a = document.createElement('a'); a.href = item.url; a.className = 'an-button';
        a.textContent = `${item.message} — ${item.number}${item.amount ? ` — ${item.amount}` : ''}${item.read ? '' : ' · Sin leer'}`;
        li.append(a); list.append(li); since = Math.max(since, item.id);
      }
      if (!data.items.length) { const li = document.createElement('li'); li.textContent = 'No hay avisos de pedidos.'; list.append(li); }
      if (initialized && data.new.length) {
        const item = data.new[0]; toast.textContent = `${item.message} — ${item.number}${item.amount ? ` — ${item.amount}` : ''}`;
        toast.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { toast.hidden = true; }, 7000);
        if (sound.checked && audio?.state === 'running') {
          const oscillator = audio.createOscillator(), gain = audio.createGain(); oscillator.connect(gain); gain.connect(audio.destination);
          gain.gain.setValueAtTime(.04, audio.currentTime); gain.gain.exponentialRampToValueAtTime(.001, audio.currentTime + .2);
          oscillator.frequency.value = 660; oscillator.start(); oscillator.stop(audio.currentTime + .2);
        }
      }
      document.dispatchEvent(new CustomEvent('orders:notifications', { detail: { fresh: initialized && data.new.length > 0 } }));
      initialized = true; delay = 45000; error.textContent = '';
    } catch { delay = Math.min(delay * 2, 360000); error.textContent = 'No pudimos actualizar los avisos. Lo intentaremos de nuevo.'; }
    finally { busy = false; schedule(); }
  }
  root.querySelector('[data-notice-read]').addEventListener('submit', async e => {
    e.preventDefault(); if (stopped || busy) return;
    const button = e.target.querySelector('button'); button.disabled = true;
    try {
      const body = new FormData(e.target); body.set('through', String(since));
      const response = await fetch(root.dataset.readUrl, { method: 'POST', body, credentials: 'same-origin' });
      if (expired(response)) return; if (!response.ok) throw new Error(); await poll();
    } catch { error.textContent = 'No pudimos marcar los avisos. Inténtalo de nuevo.'; }
    finally { button.disabled = false; }
  });
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) schedule(); });
  window.addEventListener('pagehide', () => clearTimeout(timer));
  poll();
})();
