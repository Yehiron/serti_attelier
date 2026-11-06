(() => {
  "use strict";
  function init() {
    const search = document.querySelector('#searchbar');
    if (search) search.placeholder = "Buscar por nombre o referencia";
    const form = document.querySelector('[data-catalog-form]');
    if (!form) return;
    document.querySelector('.ca-editor').classList.add('ca-js');
    let dirty = false, submitting = false;
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('change', () => { dirty = true; });
    window.addEventListener('beforeunload', event => {
      if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
    });
    form.addEventListener('submit', event => {
      // A retry has its own fetch handler and must not lock the editing form.
      if (event.submitter?.hasAttribute('data-photo-retry')) return;
      if (submitting) { event.preventDefault(); return; }
      submitting = true;
      // Preserve the submitter's name/value before disabling it.
      if (event.submitter?.name) {
        const input = document.createElement('input');
        input.type = 'hidden'; input.name = event.submitter.name; input.value = event.submitter.value;
        form.append(input);
      }
      form.querySelectorAll('button[type=submit]').forEach(button => { button.disabled = true; });
      form.querySelector('[data-save-feedback]').textContent = 'Guardando…';
    });
    const cardsRoot = form.querySelector('.ca-photo-grid');
    const cards = () => Array.from(form.querySelectorAll('[data-photo-card]'))
      .filter(card => card.querySelector('[name$="-position"]'));

    function syncPositions() {
      cards().forEach((card, index) => {
        card.querySelector('[name$="-position"]').value = index;
        const buttons = card.querySelectorAll('[data-photo-move]');
        buttons[0].disabled = index === 0;
        buttons[1].disabled = index === cards().length - 1;
      });
    }
    cards().forEach((card, index) => {
      const choices = card.querySelector('[data-photo-choices]');
      [['is_primary', 'Principal', 'star'], ['is_hover', 'Al pasar el mouse', 'mouse']].forEach(([key, text, icon]) => {
        const source = card.querySelector(`[name$="-${key}"]`);
        if (!source) return;
        const label = document.createElement('label'), radio = document.createElement('input');
        radio.type = 'radio'; radio.name = `visual-${key}`; radio.value = String(index); radio.checked = source.checked;
        const symbol = document.createElement('span'); symbol.className = 'material-symbols-outlined'; symbol.textContent = icon; symbol.setAttribute('aria-hidden', 'true');
        label.append(radio, symbol, document.createTextNode(text)); choices.append(label);
        radio.addEventListener('change', () => {
          cards().forEach(other => {
            const checked = other === card;
            other.querySelector(`[name$="-${key}"]`).checked = checked;
            if (checked) {
              const opposite = key === 'is_primary' ? 'is_hover' : 'is_primary';
              other.querySelector(`[name$="-${opposite}"]`).checked = false;
              other.querySelector(`[name="visual-${opposite}"]`).checked = false;
            }
          });
          dirty = true;
        });
      });
      // A hover image is optional; selecting it should be reversible.
      const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'ca-button'; clear.textContent = 'Sin efecto al pasar el mouse';
      if (index === 0) {
        choices.append(clear);
        clear.addEventListener('click', () => {
          cards().forEach(other => {
            other.querySelector('[name$="-is_hover"]').checked = false;
            other.querySelector('[name="visual-is_hover"]').checked = false;
          }); dirty = true;
        });
      }
      card.querySelectorAll('[data-photo-move]').forEach(button => button.addEventListener('click', () => {
        const order = cards(), target = order[order.indexOf(card) + Number(button.dataset.photoMove)];
        if (!target) return;
        if (Number(button.dataset.photoMove) < 0) cardsRoot.insertBefore(card, target);
        else cardsRoot.insertBefore(target, card);
        syncPositions(); dirty = true; button.focus();
      }));
    });
    if (cards().length) syncPositions();
    const upload = form.querySelector('[name=new_photos]'), previews = form.querySelector('[data-local-previews]');
    let urls = [];
    function showFiles() {
      urls.forEach(url => URL.revokeObjectURL(url)); urls = []; previews.replaceChildren();
      form.querySelector('[data-upload-count]').textContent = `${upload.files.length} fotos nuevas seleccionadas`;
      Array.from(upload.files).forEach((file, index) => {
        const card = document.createElement('div'), img = document.createElement('img'), remove = document.createElement('button'), name = document.createElement('p');
        const url = URL.createObjectURL(file); urls.push(url); img.src = url; img.alt = file.name;
        img.addEventListener('error', () => { img.hidden = true; });
        name.textContent = file.name;
        remove.type = 'button'; remove.className = 'ca-button'; remove.textContent = 'Quitar'; remove.setAttribute('aria-label', `Quitar ${file.name}`);
        if (typeof DataTransfer === 'function') remove.addEventListener('click', () => {
          const transfer = new DataTransfer(); Array.from(upload.files).forEach((item, i) => { if (i !== index) transfer.items.add(item); });
          upload.files = transfer.files; dirty = true; showFiles(); upload.focus();
        }); else remove.hidden = true;
        card.append(img, name, remove); previews.append(card);
      });
    }
    if (upload) upload.addEventListener('change', showFiles);
    window.addEventListener('pagehide', () => urls.forEach(url => URL.revokeObjectURL(url)), {once: true});
    document.addEventListener('catalog:photo-status', event => {
      const data = event.detail;
      form.querySelectorAll('[data-missing-key], [data-check-photo]').forEach(item => {
        const photo = item.hasAttribute('data-check-photo');
        const ready = photo ? !data.missing.some(key => /imagen|foto/.test(key)) : !data.missing.includes(item.dataset.missingKey);
        item.dataset.ready = String(ready); item.querySelector('[data-check-symbol]').textContent = ready ? '✓' : '✗';
        item.querySelector('[data-check-note]').textContent = ready ? 'Lista' : photo && data.photos.some(p => p.is_primary && p.status === 'pending') ? 'Procesando…' : 'Falta';
      });
      const button = form.querySelector('[data-publish-button]');
      if (button && !submitting) {
        button.disabled = !data.ready_to_publish;
        form.querySelector('[data-publish-reason]').textContent = data.ready_to_publish ? 'Todo listo para publicar.' : 'Completa lo que falta y guarda los cambios para publicar.';
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
