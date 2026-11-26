(() => {
  const app = document.querySelector('.collection-app');
  if (!app) return;
  const dialog = app.querySelector('[data-dialog]');
  app.querySelector('[data-open]')?.addEventListener('click', () => dialog.showModal());
  app.querySelector('[data-close]')?.addEventListener('click', () => {
    if (app.dataset.id) dialog.close(); else location.href = location.pathname;
  });
  if (dialog?.hasAttribute('data-auto-open')) dialog.showModal();
  app.querySelectorAll('[data-lang]').forEach(button => button.addEventListener('click', () => {
    app.querySelectorAll('[data-lang]').forEach(b => b.classList.toggle('on', b === button));
    app.querySelectorAll('[data-language]').forEach(panel => { panel.hidden = panel.dataset.language !== button.dataset.lang; });
  }));
  const grid = app.querySelector('[data-grid]');
  if (!grid) return;
  const catalog = JSON.parse(document.getElementById('collection-catalog-data').textContent);
  const selected = JSON.parse(document.getElementById('collection-selected-data').textContent);
  const all = new Map([...catalog, ...selected].map(p => [p.id, p]));
  let ids = selected.map(p => p.id), original = [...ids], category = '', dragging = null;
  const canEdit = app.dataset.edit === 'true';
  const dirty = () => JSON.stringify(ids) !== JSON.stringify(original);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  function photo(p, cls) { const n = el(p.image ? 'img' : 'span', cls + (p.image ? '' : ' stone-noimg')); if (p.image) { n.src = p.image; n.alt = ''; } return n; }
  function move(id, index) { ids = ids.filter(x => x !== id); ids.splice(Math.max(0, Math.min(index, ids.length)), 0, id); render(); }
  function render() {
    grid.replaceChildren();
    if (!ids.length) grid.append(el('p', 'collection-empty', 'Aún no hay piezas. Búscalas a la derecha y agrégalas.'));
    ids.forEach((id, index) => {
      const p = all.get(id), card = el('article', 'collection-card');
      card.tabIndex = 0; card.draggable = canEdit; card.dataset.pieceId = id;
      card.setAttribute('aria-label', `${p.name}, posición ${index + 1}`);
      card.addEventListener('keydown', e => { if (canEdit && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); move(id, index + (e.key === 'ArrowLeft' ? -1 : 1)); grid.querySelector(`[data-piece-id="${id}"]`)?.focus(); } });
      card.addEventListener('dragstart', () => { dragging = id; });
      card.addEventListener('dragover', e => { if (canEdit) e.preventDefault(); });
      card.addEventListener('drop', e => { e.preventDefault(); e.stopPropagation(); if (dragging !== null) move(dragging, index); dragging = null; });
      card.append(photo(p, 'collection-photo'));
      const tools = el('div', 'collection-tools'); tools.append(el('span', '', String(index + 1)));
      if (canEdit) { const remove = el('button', '', '×'); remove.type = 'button'; remove.setAttribute('aria-label', `Quitar ${p.name}`); remove.addEventListener('click', () => { ids = ids.filter(x => x !== id); render(); }); tools.append(remove); }
      card.append(tools, el('b', '', p.name), el('small', '', p.price));
      if (p.sale_state === 'sold') card.append(el('span', 'collection-badge', 'Vendida'));
      if (p.status === 'hidden') card.append(el('span', 'collection-badge', 'Oculta'));
      grid.append(card);
    });
    const available = ids.filter(id => all.get(id).sale_state === 'available').length;
    const sold = ids.filter(id => all.get(id).sale_state === 'sold').length;
    app.querySelector('[data-summary]').textContent = `${ids.length} piezas · ${available} disponibles · ${sold} vendidas`;
    app.querySelector('[data-dirty]').hidden = !dirty();
    const list = app.querySelector('[data-catalog]'); list.replaceChildren();
    const query = app.querySelector('[data-search]').value.trim().toLocaleLowerCase();
    catalog.filter(p => (!category || String(p.category) === category) && `${p.name} ${p.sku}`.toLocaleLowerCase().includes(query)).forEach(p => {
      const item = el('div', 'collection-item'); item.draggable = canEdit && !ids.includes(p.id);
      item.addEventListener('dragstart', () => { dragging = p.id; });
      const info = el('div'); info.append(el('b', '', p.name), el('small', '', p.sku)); item.append(photo(p, ''), info);
      if (ids.includes(p.id)) item.append(el('small', '', '✓ ya está'));
      else if (canEdit) { const add = el('button', 'cat-button', '＋'); add.type = 'button'; add.setAttribute('aria-label', `Agregar ${p.name}`); add.addEventListener('click', () => move(p.id, ids.length)); item.append(add); }
      list.append(item);
    });
  }
  grid.addEventListener('dragover', e => { if (canEdit) e.preventDefault(); });
  grid.addEventListener('drop', e => { e.preventDefault(); if (dragging !== null) move(dragging, ids.length); dragging = null; });
  app.querySelector('[data-search]').addEventListener('input', render);
  app.querySelectorAll('[data-category]').forEach(b => b.addEventListener('click', () => { category = b.dataset.category; app.querySelectorAll('[data-category]').forEach(x => x.classList.toggle('on', x === b)); render(); }));
  app.querySelector('[data-save]')?.addEventListener('click', async e => {
    const button = e.currentTarget, message = app.querySelector('[data-message]'); button.disabled = true;
    try { const response = await fetch(app.dataset.url, { method: 'POST', headers: {'Content-Type':'application/json', 'X-CSRFToken': app.querySelector('[name=csrfmiddlewaretoken]').value}, body: JSON.stringify({collection:Number(app.dataset.id), pieces:ids}) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || 'No se pudo guardar.'); original = [...ids]; message.textContent = 'Colección guardada.'; render(); } catch (error) { message.textContent = error.message || 'No se pudo guardar.'; } finally { button.disabled = false; }
  });
  window.addEventListener('beforeunload', e => { if (dirty()) { e.preventDefault(); e.returnValue = ''; } });
  render();
})();
