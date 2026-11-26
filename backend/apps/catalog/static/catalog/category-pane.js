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
    if (title) title.textContent = name?.value || app.dataset.previewFallback || 'Categoría';
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
  if (app.classList.contains('stone-app')) {
    const colors = ['#1f7a55', '#a51c3a', '#244a9c', '#e9eef2', '#0f5a3c', '#3c9a6e', '#c9a96e', '#7b4fa0', '#f2b84b'];
    const field = app.querySelector('#id_color');
    const custom = app.querySelector('[data-custom-color]');
    // Keep the free colour picker and the selected swatch in step with the text field.
    const sync = () => {
      const value = (field?.value || '').toLowerCase();
      if (custom && /^#[0-9a-f]{6}$/.test(value)) custom.value = value;
      app.querySelectorAll('[data-swatch]').forEach(button => button.classList.toggle('stone-swatch-on', colors[Number(button.dataset.swatch)] === value));
    };
    app.querySelectorAll('[data-swatch]').forEach(button => { const color = colors[Number(button.dataset.swatch)]; button.style.background = color; button.setAttribute('aria-label', `Color ${color}`); button.addEventListener('click', () => { field.value = color; sync(); }); });
    custom?.addEventListener('input', event => { field.value = event.target.value; sync(); });
    app.querySelector('[data-auto-color]')?.addEventListener('click', () => { field.value = ''; sync(); });
    field?.addEventListener('input', sync);
    sync();
    const updateWarning = () => {
      let phrase = '';
      ['es', 'en'].forEach(lang => {
        const value = app.querySelector(`#id_description_${lang}`)?.value || '';
        const counter = app.querySelector(`[data-counter="${lang}"]`);
        if (counter) counter.textContent = `${value.length} caracteres`;
        const match = value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').match(/texto(?: largo)? de prueba|lorem ipsum|prueba para verificar|test text/i);
        if (!phrase && match) phrase = value.slice(match.index, match.index + match[0].length);
      });
      const warning = app.querySelector('[data-test-warning]');
      if (warning) { warning.hidden = !phrase; warning.querySelector('[data-test-phrase]').textContent = phrase; }
    };
    app.querySelectorAll('[id^="id_description_"]').forEach(input => input.addEventListener('input', updateWarning));
    updateWarning();
  }
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
