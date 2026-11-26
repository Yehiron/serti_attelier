(() => {
  const dialog = document.querySelector('.pe-dialog');
  if (dialog) {
    const frame = dialog.querySelector('iframe');
    let opener = null;
    let dirty = false;
    function close() {
      if (dirty && !window.confirm('Tienes cambios sin guardar. ¿Salir sin guardar?')) return;
      dialog.close();
      frame.removeAttribute('src');
      if (opener) opener.focus();
    }
    function open(link) {
      opener = link;
      dirty = false;
      const url = new URL(link.href, location.href);
      url.searchParams.set('_modal', '1');
      frame.src = url.href;
      dialog.showModal();
      dialog.focus();
    }
    document.addEventListener('click', (event) => {
      const edit = event.target.closest('a[aria-label="Editar"]');
      if (edit) { event.preventDefault(); open(edit); return; }
      const row = event.target.closest('tr');
      if (!row || event.target.closest('a, button, input, select, textarea, label')) return;
      const link = row.querySelector('a[aria-label="Editar"]');
      if (link) open(link);
    });
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); close(); });
    window.addEventListener('message', (event) => {
      if (event.origin !== location.origin || event.source !== frame.contentWindow) return;
      if (event.data.type === 'serti:piece-dirty') dirty = event.data.dirty;
      if (event.data.type === 'serti:piece-close') close();
      if (event.data.type === 'serti:piece-saved') { dirty = false; close(); location.reload(); }
    });
  }
  const editor = document.querySelector('[data-pe-editor]');
  if (!editor) return;
  const form = editor.querySelector('form');
  const notify = (type, extra = {}) => window.parent.postMessage({type, ...extra}, location.origin);
  const snapshot = () => JSON.stringify([...new FormData(form)].map(([key, value]) => [key, value instanceof File ? [value.name, value.size, value.lastModified] : value]));
  let initial = snapshot();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { initial = snapshot(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); notify('serti:piece-close'); } });
  editor.querySelectorAll('.pe-menu a').forEach(link => link.addEventListener('click', event => {
    if (snapshot() !== initial && !window.confirm('Tienes cambios sin guardar. ¿Salir sin guardar?')) event.preventDefault();
  }));
  const update = () => {
    const changed = snapshot() !== initial;
    editor.querySelector('[data-pe-dirty]').textContent = changed ? 'Cambios sin guardar' : 'Sin cambios pendientes';
    notify('serti:piece-dirty', {dirty: changed});
  };
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  editor.querySelectorAll('[data-pe-close]').forEach((button) => button.addEventListener('click', () => notify('serti:piece-close')));
  editor.querySelectorAll('[data-pe-section]').forEach((button) => button.addEventListener('click', () => {
    const section = [...editor.querySelectorAll('.pe-section')].find((item) => item.dataset.peTitle.startsWith(button.dataset.peSection));
    if (section) { section.open = true; section.scrollIntoView({behavior: 'smooth'}); }
  }));
  const missing = JSON.parse(document.getElementById('pe-publication-missing').textContent);
  const requirements = [
    ['nombre en español', 'name_es', 'Información'],
    ['descripción corta en español', 'short_description_es', 'Información'],
    ['categoría', 'category', 'Clasificación'],
    ['precio', 'price_cents', 'Precio'],
    ['dirección web en español', 'slug_es', 'Avanzado'],
  ];
  function completions() {
    editor.querySelectorAll('.pe-section').forEach(section => {
      const completion = section.querySelector('[data-pe-completion]');
      if (!completion) return;
      const count = requirements.filter(([label, name, title]) => {
        if (!section.dataset.peTitle.startsWith(title)) return false;
        const input = form.elements.namedItem(name);
        return input && !input.disabled ? !input.value : missing.includes(label);
      }).length;
      completion.textContent = count ? `${count} campos vacíos` : '✓ completa';
      completion.classList.toggle('pe-complete', !count);
    });
  }
  form.addEventListener('input', completions);
  form.addEventListener('change', completions);
  completions();
  const photoCompletion = editor.querySelector('[data-pe-photo-completion]');
  if (photoCompletion) {
    const photoMissing = missing.filter(item => /imagen|foto/.test(item)).length;
    photoCompletion.textContent = photoMissing ? `${photoMissing} campos vacíos` : '✓ completa';
    photoCompletion.classList.toggle('pe-complete', !photoMissing);
  }
  editor.querySelectorAll('.pe-section').forEach(section => {
    if (section.querySelector('.errorlist, .errors, [aria-invalid="true"]')) section.open = true;
  });
  const error = editor.querySelector('.errorlist, .errors, [aria-invalid="true"]');
  if (error) requestAnimationFrame(() => error.scrollIntoView({block: 'center'}));
  const toggle = editor.querySelector('[data-pe-toggle]');
  toggle.addEventListener('change', async () => {
    toggle.disabled = true;
    try {
      const response = await fetch(toggle.dataset.url, {method: 'POST', credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'X-CSRFToken': form.elements.csrfmiddlewaretoken.value}});
      const result = await response.json();
      if (!response.ok) {
        toggle.checked = !toggle.checked;
        editor.querySelector('[data-pe-missing]').textContent = result.missing?.length ? `Para publicar: ${result.missing.join(', ')}` : result.error;
      } else {
        toggle.dataset.url = result.toggle_url;
        editor.querySelector('[data-pe-missing]').textContent = '';
      }
    } catch (_) {
      toggle.checked = !toggle.checked;
      editor.querySelector('[data-pe-missing]').textContent = 'No se pudo cambiar el estado. Intenta de nuevo.';
    } finally { toggle.disabled = false; }
  });
})();
