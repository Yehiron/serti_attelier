(() => {
  document.documentElement.classList.add("selection-ready");
  const init = () => {
  const form = document.querySelector('#changelist-form');
  if (!form || !form.querySelector('select[name="action"]')) return;
  const root = document.documentElement;
  root.classList.add('selection-ready');
  let active = new URL(location.href).searchParams.get('select') === '1';
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'selection-toggle';
  const render = () => {
    root.classList.toggle('selection-active', active);
    button.setAttribute('aria-pressed', String(active));
    button.innerHTML = '<span class="material-symbols-outlined" aria-hidden="true">checklist</span>' + (active ? 'Cancelar selección' : 'Seleccionar');
  };
  button.addEventListener('click', () => {
    active = !active;
    if (!active) {
      const master = form.querySelector('#action-toggle');
      if (master) { master.checked = true; master.click(); master.indeterminate = false; }
      form.querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = false; });
      form.querySelectorAll('input.select-across').forEach(input => { input.value = '0'; });
      form.querySelectorAll('tr.selected').forEach(row => row.classList.remove('selected'));
    }
    const url = new URL(location.href);
    if (active) url.searchParams.set('select', '1'); else url.searchParams.delete('select');
    history.replaceState(null, '', url);
    render(); button.focus();
  });
  document.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!active || !link) return;
    const url = new URL(link.href, location.href);
    if (url.origin === location.origin && url.pathname === location.pathname) { url.searchParams.set('select', '1'); link.href = url; }
  });
  document.addEventListener('submit', event => {
    if (!active || event.target.method.toLowerCase() !== 'get') return;
    const input = document.createElement('input'); input.type = 'hidden'; input.name = 'select'; input.value = '1'; event.target.append(input);
  });
  form.before(button); render();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true }); else init();
})();
