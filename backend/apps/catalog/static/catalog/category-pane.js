(() => {
  const app = document.querySelector('.cat-app');
  if (!app) return;
  const search = app.querySelector('.cat-search');
  search?.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    app.querySelectorAll('.cat-row').forEach(row => { row.hidden = !row.dataset.name.includes(query); });
  });
  let language = 'es';
  const updatePreview = () => {
    const name = app.querySelector(`#id_name_${language}`);
    const description = app.querySelector(`#id_description_${language}`);
    const title = app.querySelector('[data-preview-name]');
    const text = app.querySelector('[data-preview-description]');
    if (title) title.textContent = name?.value || 'Categoría';
    if (text) text.textContent = description?.value || '';
  };
  app.querySelectorAll('[data-lang]').forEach(button => button.addEventListener('click', () => {
    language = button.dataset.lang;
    app.querySelectorAll('[data-language]').forEach(group => { group.hidden = group.dataset.language !== language; });
    app.querySelectorAll('[data-lang]').forEach(tab => tab.classList.toggle('cat-lang-active', tab === button));
    updatePreview();
  }));
  app.querySelectorAll('[id^="id_name_"], [id^="id_description_"]').forEach(input => input.addEventListener('input', updatePreview));
  app.querySelector('#id_cover_image')?.addEventListener('change', event => {
    const file = event.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    app.querySelectorAll('.cat-cover, .cat-preview').forEach(element => { element.style.backgroundImage = `url("${url}")`; });
  });
  let dragged;
  app.querySelectorAll('.cat-row[draggable="true"]').forEach(row => {
    row.addEventListener('dragstart', () => { dragged = row; });
    row.addEventListener('dragover', event => { if (dragged && dragged.dataset.parent === row.dataset.parent) event.preventDefault(); });
    row.addEventListener('drop', async event => {
      event.preventDefault();
      if (!dragged || dragged === row || dragged.dataset.parent !== row.dataset.parent) return;
      const siblings = [...app.querySelectorAll('.cat-row')].filter(item => item.dataset.parent === row.dataset.parent);
      const ids = siblings.map(item => Number(item.dataset.id));
      ids.splice(ids.indexOf(Number(dragged.dataset.id)), 1);
      ids.splice(ids.indexOf(Number(row.dataset.id)), 0, Number(dragged.dataset.id));
      const body = new FormData(); body.append('ids', JSON.stringify(ids));
      const csrf = app.querySelector('[name=csrfmiddlewaretoken]')?.value;
      try {
        const response = await fetch(app.dataset.reorderUrl, {method: 'POST', headers: {'X-CSRFToken': csrf}, body});
        if (!response.ok) throw new Error();
        window.location.reload();
      } catch (_) { window.alert('No se pudo guardar el orden.'); }
    });
  });
})();
