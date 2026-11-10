(() => {
  const root = document.getElementById('visual-editor');
  if (!root) return;
  const message = document.getElementById('ve-message');
  let busy = false;
  const reload = document.getElementById('ve-reload');
  reload.addEventListener('click', () => location.reload());
  function show(text) { message.textContent = text; message.hidden = false; message.focus(); }
  const warning = sessionStorage.getItem('serti-editor-warning');
  if (warning) { show(warning); sessionStorage.removeItem('serti-editor-warning'); }
  async function send(action, fields, files) {
    if (busy) return;
    busy = true;
    root.setAttribute('aria-busy', 'true');
    const data = new FormData();
    data.set('device', root.dataset.device);
    data.set('expected_version', root.dataset.version);
    Object.entries(fields).forEach(([key, value]) => data.set(key, value));
    if (files) Array.from(files).forEach(file => data.append(action === 'hero-upload' ? 'files[]' : 'file', file));
    try {
      const response = await fetch(root.dataset.actionUrl.replace('ACTION', action), {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: {'X-CSRFToken': root.querySelector('[name=csrfmiddlewaretoken]').value}
      });
      const result = await response.json();
      if (response.status === 409) reload.hidden = false;
      if (!response.ok) throw new Error(result.error || document.getElementById('ve-failure').textContent);
      if (result.warnings?.length) sessionStorage.setItem('serti-editor-warning', result.warnings.join(' '));
      location.reload();
    } catch (error) {
      show((error instanceof SyntaxError || error instanceof TypeError) ? document.getElementById('ve-failure').textContent : error.message);
      busy = false; root.removeAttribute('aria-busy');
    }
  }
  root.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => {
    if (button.dataset.confirm && !confirm(button.dataset.confirm)) return;
    send(button.dataset.action, button.dataset);
  }));
  root.querySelectorAll('[data-upload]').forEach(zone => {
    const input = zone.querySelector('input');
    input.addEventListener('change', () => { if (input.files.length) send(zone.dataset.upload, zone.dataset, input.files); });
    zone.addEventListener('dragover', event => { event.preventDefault(); zone.classList.add('ve-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('ve-over'));
    zone.addEventListener('drop', event => {
      event.preventDefault(); event.stopPropagation(); zone.classList.remove('ve-over');
      const files = event.dataTransfer.files;
      if (files.length) send(zone.dataset.upload, zone.dataset, input.multiple ? files : [files[0]]);
    });
  });
  function saveOrder(list) {
    send(list.dataset.sort, {section: list.dataset.section || '', ids: JSON.stringify(Array.from(list.children).map(row => Number(row.dataset.id)))});
  }
  root.querySelectorAll('[data-sort]').forEach(list => {
    let dragged = null;
    list.addEventListener('dragstart', event => {
      if (!event.target.matches('.ve-handle') || event.target.closest('[data-sort]') !== list) return;
      dragged = event.target.closest('[data-id]'); event.dataTransfer.setData('text/plain', dragged.dataset.id); event.stopPropagation();
    });
    list.addEventListener('dragover', event => { if (dragged) event.preventDefault(); });
    list.addEventListener('drop', event => {
      if (!dragged) return;
      event.preventDefault(); event.stopPropagation();
      const target = event.target.closest('[data-id]');
      if (target && target.parentElement === list && target !== dragged) { list.insertBefore(dragged, target); saveOrder(list); }
      dragged = null;
    });
    list.addEventListener('dragend', () => { dragged = null; });
    list.addEventListener('click', event => {
      const button = event.target.closest('[data-move]');
      if (!button || button.closest('[data-sort]') !== list) return;
      const row = button.closest('[data-id]');
      const next = Number(button.dataset.move) < 0 ? row.previousElementSibling : row.nextElementSibling;
      if (!next) return;
      list.insertBefore(row, Number(button.dataset.move) < 0 ? next : next.nextElementSibling); saveOrder(list);
    });
  });
})();
