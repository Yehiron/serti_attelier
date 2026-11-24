(() => {
  "use strict";
  function init() {
    const search = document.querySelector('#searchbar');
    if (search) search.placeholder = "Buscar por nombre o referencia";
    const form = document.querySelector('[data-catalog-form]');
    if (!form) return;
    document.querySelector('.ca-editor').classList.add('ca-js');
    let dirty = false, submitting = false;
    const category = form.querySelector('#id_category');
    const dialog = document.querySelector('[data-category-dialog]');
    const opener = document.querySelector('[data-category-open]');
    if (category && dialog && typeof dialog.showModal === 'function') {
      category.closest('.field-line, .form-row')?.append(opener, document.querySelector('[data-category-notice]'));
      opener.addEventListener('click', event => { event.preventDefault(); dialog.showModal(); });
      dialog.querySelector('[data-category-close]').addEventListener('click', () => dialog.close());
      dialog.addEventListener('close', () => opener.focus());
      const quickForm = dialog.querySelector('form');
      let saving = false;
      quickForm.addEventListener('submit', async event => {
        event.preventDefault();
        if (saving) return;
        saving = true;
        const button = quickForm.querySelector('[type=submit]'); button.disabled = true;
        quickForm.querySelectorAll('[data-category-error]').forEach(el => { el.textContent = ''; });
        quickForm.querySelectorAll('[aria-invalid]').forEach(el => el.removeAttribute('aria-invalid'));
        try {
          const response = await fetch(quickForm.action, {method: 'POST', body: new FormData(quickForm), credentials: 'same-origin'});
          if (!response.ok) {
            const data = response.status === 400 ? await response.json() : {errors: {__all__: ['No se pudo crear. Revisa tus permisos o recarga la página en otra pestaña.']}};
            Object.entries(data.errors).forEach(([key, messages]) => {
              const error = quickForm.querySelector(`[data-category-error="${key}"]`) || quickForm.querySelector('[data-category-error="__all__"]');
              error.textContent = messages.join(' ');
              quickForm.elements.namedItem(key)?.setAttribute('aria-invalid', 'true');
            });
            quickForm.querySelector('[aria-invalid]')?.focus();
            return;
          }
          const data = await response.json();
          const option = new Option(data.label, data.id, true, true);
          // Keep Django's position order: children follow their parent's existing options.
          const parent = quickForm.elements.namedItem('parent');
          const rootLabel = parent.selectedOptions[0].textContent;
          let after = null;
          if (parent.value) Array.from(category.options).forEach(item => {
            if (item.textContent === rootLabel || item.textContent.startsWith(`${rootLabel} → `)) after = item;
          });
          if (after) after.after(option); else category.append(option);
          if (!parent.value) parent.append(new Option(data.label, data.id));
          category.value = String(data.id); category.dispatchEvent(new Event('change', {bubbles: true}));
          document.querySelector('[data-category-notice]').textContent = `Categoría «${data.label}» creada.`;
          quickForm.reset(); dialog.close();
        } catch (_) {
          quickForm.querySelector('[data-category-error="__all__"]').textContent = 'No se pudo conectar. Intenta de nuevo.';
        } finally { saving = false; button.disabled = false; }
      });
    }
    function categoryCheck() {
      const item = form.querySelector('[data-missing-key="categoría"]');
      if (!item || !category) return;
      const ready = Boolean(category.value);
      item.dataset.ready = String(ready); item.querySelector('[data-check-symbol]').textContent = ready ? '✓' : '✗';
      item.querySelector('[data-check-note]').textContent = ready ? 'Lista' : 'Falta';
    }
    category?.addEventListener('change', categoryCheck);
    const replacementUrls = new Map();
    form.querySelectorAll('.ca-photo-original input[type=file]').forEach(input => {
      const originalPreview = input.closest('[data-photo-card]').querySelector('[data-photo-preview]')?.cloneNode(true);
      input.addEventListener('change', () => {
        const card = input.closest('[data-photo-card]'), preview = card.querySelector('[data-photo-preview]');
        if (!preview) return;
        if (replacementUrls.has(input)) { URL.revokeObjectURL(replacementUrls.get(input)); replacementUrls.delete(input); }
        if (!input.files.length) {
          if (originalPreview) preview.replaceChildren(...Array.from(originalPreview.cloneNode(true).childNodes));
          delete preview.dataset.localReplacement;
          card.querySelector('[data-replacement-note]').textContent = '';
          return;
        }
        const url = URL.createObjectURL(input.files[0]); replacementUrls.set(input, url);
        const img = document.createElement('img'); img.src = url; img.alt = input.files[0].name;
        img.addEventListener('error', () => { img.hidden = true; });
        preview.dataset.localReplacement = 'true'; preview.replaceChildren(img);
        card.querySelector('[data-replacement-note]').textContent = 'Nueva — se guarda al guardar';
      });
    });
    window.addEventListener('pagehide', () => replacementUrls.forEach(url => URL.revokeObjectURL(url)), {once: true});
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('change', () => { dirty = true; });
    window.addEventListener('beforeunload', event => {
      if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
    });
    form.addEventListener('submit', event => {
      // A retry has its own fetch handler and must not lock the editing form.
      if (event.submitter?.hasAttribute('data-photo-retry')) return;
      const missing = Array.from(form.querySelectorAll('[required]')).find(el => el.willValidate && el.getClientRects().length && el.validity.valueMissing);
      if (missing) { event.preventDefault(); missing.focus(); missing.reportValidity(); return; }
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
      card.querySelectorAll('[data-photo-move]').forEach(button => button.addEventListener('click', () => {
        const order = cards(), target = order[order.indexOf(card) + Number(button.dataset.photoMove)];
        if (!target) return;
        if (Number(button.dataset.photoMove) < 0) cardsRoot.insertBefore(card, target);
        else cardsRoot.insertBefore(target, card);
        syncPositions(); dirty = true; button.focus();
      }));
    });
    if (cards().length) {
      syncPositions();
      const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'ca-text-action';
      clear.textContent = 'Quitar efecto al pasar el mouse';
      const clearSlot = document.createElement('div'); clearSlot.className = 'ca-hover-clear'; clearSlot.append(clear); cardsRoot.before(clearSlot);
      const updateClear = () => { clear.hidden = !cards().some(card => card.querySelector('[name$="-is_hover"]').checked); };
      clear.addEventListener('click', () => {
        cards().forEach(card => { card.querySelector('[name$="-is_hover"]').checked = false; card.querySelector('[name="visual-is_hover"]').checked = false; });
        dirty = true; updateClear();
        cards()[0]?.querySelector('[name="visual-is_hover"]')?.focus();
      });
      form.addEventListener('change', updateClear); updateClear();
    }
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
      categoryCheck();
      const button = form.querySelector('[data-publish-button]');
      if (button && !submitting) {
        button.disabled = !data.ready_to_publish;
        form.querySelector('[data-publish-reason]').textContent = data.ready_to_publish ? 'Todo listo para publicar.' : 'Completa lo que falta y guarda los cambios para publicar.';
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
