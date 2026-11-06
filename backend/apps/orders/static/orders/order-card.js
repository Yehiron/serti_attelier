(() => {
  'use strict';
  const root = document.querySelector('[data-drawer-root]');
  const dialog = root?.querySelector('[role=dialog]');
  const body = root?.querySelector('[data-card-body]');
  let opener, controller, serial = 0, closeTimer, oldOverflow, inertNodes = [];
  const skeleton = '<div class="oc-skeleton" aria-busy="true"><h2 id="order-card-title" tabindex="-1">Cargando pedido…</h2><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>';
  function prepare(scope) {
    scope.querySelectorAll('[data-status-form]').forEach(form => {
      const sync = () => {
        const shipped = form.elements.target.value === 'shipped';
        form.querySelector('[data-shipping-fields]').hidden = !shipped;
        form.elements.carrier.required = shipped;
        const returned = form.elements.target.value === 'returned';
        form.querySelector('[data-return-notice]').hidden = !returned;
        const emailMissing = !form.closest('[data-card-content]').querySelector('a[href^="mailto:"]')?.getAttribute('href').slice(7);
        form.elements.notify.disabled = returned || emailMissing;
        const card = form.closest('[data-card-content]');
        const label = form.elements.target.selectedOptions[0]?.textContent || '';
        form.querySelector('[data-confirm-question]').textContent = `¿Cambiar el pedido ${card.dataset.orderNumber} de «${card.dataset.status}» a «${label}»?`;
      };
      form.elements.target.addEventListener('change', sync);
      sync();
    });
  }
  function isolate() {
    let current = root;
    while (current && current !== document.body) {
      for (const node of current.parentElement.children) {
        if (node !== current && !node.inert) { node.inert = true; inertNodes.push(node); }
      }
      current = current.parentElement;
    }
  }
  function close() {
    if (!root || root.hidden) return;
    serial++; controller?.abort();
    root.classList.add('is-closing'); root.classList.remove('is-open');
    inertNodes.forEach(node => node.inert = false); inertNodes = [];
    document.body.style.overflow = oldOverflow;
    const url = new URL(location.href); url.searchParams.delete('pedido'); history.replaceState(null, '', url);
    if (opener?.isConnected) opener.focus();
    else document.querySelector("#searchbar")?.focus();
    closeTimer = setTimeout(() => { root.hidden = true; body.innerHTML = ''; }, 240);
  }
  async function open(link, keyboard = false) {
    if (!root) return;
    clearTimeout(closeTimer); controller?.abort(); controller = new AbortController();
    const ticket = ++serial;
    const wasHidden = root.hidden;
    opener = link;
    root.hidden = false; root.classList.remove('is-closing');
    root.classList.toggle('oc-keyboard', keyboard);
    body.innerHTML = skeleton;
    if (wasHidden) { oldOverflow = document.body.style.overflow; isolate(); }
    document.body.style.overflow = 'hidden';
    const url = new URL(location.href);
    const endpoint = new URL(link.dataset.orderCard, location.origin);
    url.searchParams.set('pedido', endpoint.pathname.split('/').filter(Boolean).at(-2));
    history.replaceState(null, '', url);
    root.getBoundingClientRect(); root.classList.add('is-open');
    body.querySelector('h2').focus();
    try {
      const response = await fetch(endpoint, { signal: controller.signal, headers: { 'X-Order-Card': '1' } });
      if (!response.ok || response.redirected) throw new Error('load');
      const html = await response.text();
      if (ticket !== serial) return;
      body.innerHTML = html; prepare(body); body.querySelector('#order-card-title').focus();
    } catch (error) {
      if (error.name === 'AbortError' || ticket !== serial) return;
      window.location.assign(link.href);
    }
  }
  async function refreshList() {
    const url = new URL(location.href); url.searchParams.delete('pedido');
    const response = await fetch(url);
    if (!response.ok || response.redirected) return;
    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
    for (const selector of ['#result_list', '.oc-tabs', '.oc-pagination']) {
      const next = doc.querySelector(selector), current = document.querySelector(selector);
      if (next && current) current.replaceWith(next);
    }
    // The previous opener may have been replaced with its updated row.
    const cardUrl = body.querySelector('[data-card-url]')?.dataset.cardUrl;
    opener = [...document.querySelectorAll('[data-order-card]')].find(link => link.dataset.orderCard === cardUrl) || opener;
  }
  document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest('[data-close-card]')) { close(); return; }
    const choice = event.target.closest('[data-choose-state]');
    if (choice) {
      const section = choice.closest('section'), form = section.querySelector('form');
      form.classList.toggle('oc-no-motion', event.detail === 0);
      form.hidden = false; section.querySelector('[data-state-choices]').hidden = true;
      form.elements.target.value = choice.dataset.chooseState;
      form.elements.target.dispatchEvent(new Event('change'));
      form.elements.target.focus(); return;
    }
    const cancel = event.target.closest('[data-cancel-state]');
    if (cancel) {
      const section = cancel.closest('section'); section.querySelector('form').hidden = true;
      section.querySelector('[data-state-choices]').hidden = false;
      section.querySelector('[data-choose-state]:not(:disabled)')?.focus(); return;
    }
    if (!root || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    let link = event.target.closest('[data-order-card]');
    if (!link && !event.target.closest('a,button,input,select,textarea,label,[role=button]') && !window.getSelection()?.toString()) {
      link = event.target.closest('tr')?.querySelector('[data-order-card]');
    }
    if (link) { event.preventDefault(); open(link, event.detail === 0); }
  });
  document.addEventListener('keydown', event => {
    if (!root || root.hidden) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key === 'Tab') {
      const nodes = [...dialog.querySelectorAll('a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(node => node.getClientRects().length);
      const first = nodes[0], last = nodes.at(-1);
      if (event.shiftKey && (!nodes.includes(document.activeElement) || document.activeElement === first)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (!nodes.includes(document.activeElement) || document.activeElement === last)) { event.preventDefault(); first?.focus(); }
    }
  });
  document.addEventListener('submit', async event => {
    const form = event.target.closest('[data-status-form], [data-note-form], [data-incident-form]'); if (!form) return;
    event.preventDefault(); if (form.dataset.sending) return;
    form.dataset.sending = '1';
    const data = new FormData(form), submit = form.querySelector('[type=submit]');
    const originalLabel = submit.textContent;
    submit.disabled = true; submit.textContent = 'Guardando…'; form.setAttribute('aria-busy', 'true');
    const container = form.closest('[data-card-content]');
    try {
      const response = await fetch(form.action, { method: 'POST', body: data, headers: { 'X-Order-Card': '1' } });
      if (response.redirected || (!response.ok && response.status !== 422)) throw new Error('save');
      const html = await response.text();
      if (!container.isConnected) return;
      container.outerHTML = html;
      const scope = root && !root.hidden ? body : document;
      prepare(scope);
      const focus = scope.querySelector('[role=alert], [data-update-success], #order-card-title');
      focus?.setAttribute('tabindex', '-1'); focus?.focus();
      if (response.headers.get('X-Order-Updated') && root && !root.hidden) {
        try { await refreshList(); } catch (_) { /* The card retains the saved state. */ }
      }
    } catch (_) {
      let error = form.querySelector('[data-network-error]');
      if (!error) { error = document.createElement('p'); error.dataset.networkError = ''; error.setAttribute('role', 'alert'); form.prepend(error); }
      error.textContent = 'No pudimos confirmar el resultado. Revisa el estado del pedido antes de volver a intentarlo.';
      submit.disabled = false; submit.textContent = originalLabel; delete form.dataset.sending; form.removeAttribute('aria-busy');
    }
  });
  prepare(document);
  if (root) {
    const id = new URL(location.href).searchParams.get('pedido');
    if (id && /^\d+$/.test(id)) {
      const link = document.createElement('a');
      link.dataset.orderCard = `${location.pathname}${id}/card/`; link.href = `${link.dataset.orderCard}?full=1`;
      const existing = [...document.querySelectorAll('[data-order-card]')].find(node => node.dataset.orderCard === link.dataset.orderCard);
      open(existing || link, true);
    }
  }
})();
