(() => {
  const root = document.documentElement;
  const grid = document.querySelector('.showcase-grid');
  const buttons = document.querySelectorAll('[data-view]');
  const key = 'serti:piezas-vista';
  function setView(view) {
    const showcase = view !== 'list';
    root.classList.toggle('showcase-mode', showcase);
    if (grid) grid.hidden = !showcase;
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === (showcase ? 'showcase' : 'list'))));
    try { localStorage.setItem(key, showcase ? 'showcase' : 'list'); } catch (_) {}
  }
  let saved;
  try { saved = localStorage.getItem(key); } catch (_) {}
  setView(saved);
  buttons.forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
  document.querySelector('#showcase-order')?.addEventListener('change', event => {
    const url = new URL(location.href);
    if (event.target.value) url.searchParams.set('o', event.target.value); else url.searchParams.delete('o');
    url.searchParams.delete('p'); location.href = url;
  });
  const boxes = document.querySelectorAll('.showcase-check');
  boxes.forEach(box => box.addEventListener('change', () => {
    if (box.checked && !root.classList.contains('selection-active')) document.querySelector('.selection-toggle')?.click();
    const row = [...document.querySelectorAll('#result_list input[name="_selected_action"]')].find(input => input.value === box.dataset.pieceId);
    if (row && row.checked !== box.checked) { row.checked = box.checked; row.dispatchEvent(new Event('change', { bubbles: true })); }
  }));
  document.addEventListener('change', event => {
    if (event.target.matches('#result_list input[type="checkbox"]')) boxes.forEach(box => {
      const row = [...document.querySelectorAll('#result_list input[name="_selected_action"]')].find(input => input.value === box.dataset.pieceId);
      if (row) box.checked = row.checked;
    });
  });
  document.addEventListener('click', event => document.querySelectorAll('.showcase-actions details[open]').forEach(menu => { if (!menu.contains(event.target)) menu.open = false; }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape') document.querySelectorAll('.showcase-actions details[open]').forEach(menu => { menu.open = false; menu.querySelector('summary').focus(); }); });
})();
