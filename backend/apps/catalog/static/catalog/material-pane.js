(() => {
  const app = document.querySelector('.mat-app');
  if (!app) return;
  app.querySelectorAll('.mat-form').forEach(form => {
    const field = form.querySelector('[name="color"]');
    const preview = form.querySelector('.mat-preview');
    const custom = form.querySelector('[data-custom-color]');
    const sync = () => { if (/^#[0-9a-f]{6}$/i.test(field.value)) { preview.style.setProperty('--mat-color', field.value); custom.value = field.value; } };
    form.querySelectorAll('[data-color]').forEach(button => { button.style.background = button.dataset.color; button.addEventListener('click', () => { field.value = button.dataset.color; sync(); }); });
    custom.addEventListener('input', () => { field.value = custom.value; sync(); });
    field.addEventListener('input', sync); sync();
  });
  const grid = app.querySelector('.mat-grid');
  let dragged;
  const save = async () => {
    const ids = [...grid.querySelectorAll('[data-id]')].map(card => Number(card.dataset.id));
    const body = new URLSearchParams({ids: JSON.stringify(ids)});
    const csrf = document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || app.querySelector('[name=csrfmiddlewaretoken]')?.value;
    const response = await fetch(app.dataset.reorderUrl, {method:'POST', headers:{'X-CSRFToken':csrf || '', 'Content-Type':'application/x-www-form-urlencoded'}, body});
    if (!response.ok) { alert('No se pudo guardar el orden.'); location.reload(); }
  };
  grid.querySelectorAll('[data-id][draggable=true]').forEach(card => {
    card.addEventListener('dragstart', e => { dragged = card; e.dataTransfer.effectAllowed = 'move'; });
    card.addEventListener('dragover', e => e.preventDefault());
    card.addEventListener('drop', e => { e.preventDefault(); if (dragged && dragged !== card) { grid.insertBefore(dragged, card); save(); } });
    card.addEventListener('keydown', e => { if (e.target !== card || !['ArrowLeft','ArrowRight'].includes(e.key)) return; const cards = [...grid.querySelectorAll('[data-id]')]; const i = cards.indexOf(card); const other = cards[i + (e.key === 'ArrowLeft' ? -1 : 1)]; if (!other) return; e.preventDefault(); grid.insertBefore(card, e.key === 'ArrowLeft' ? other : other.nextSibling); card.focus(); save(); });
  });
})();
