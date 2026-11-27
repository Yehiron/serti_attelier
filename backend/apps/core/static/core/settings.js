(() => {
  const init = () => {
    const form = document.querySelector('#sitesettings_form');
    if (!form) return;
    const example = JSON.parse(document.getElementById('set-example').textContent);
    const fields = [...form.querySelectorAll('.set-field')];
    const input = name => form.querySelector(`[name="${name}"]`);
    const phone = input('whatsapp_number');
    const phoneInfo = form.querySelector('[data-whatsapp-info]');
    const phoneLink = form.querySelector('[data-whatsapp-link]');
    const updatePhone = () => {
      if (!phone) return;
      const value = phone.value.trim();
      phoneInfo.textContent = value ? (value.startsWith('57') && value.length === 12 ? `+57 ${value.slice(2, 5)} ${value.slice(5, 8)} ${value.slice(8)}` : `+${value}`) : 'Falta WhatsApp';
      phoneLink.hidden = !/^[1-9][0-9]{1,14}$/.test(value);
      if (!phoneLink.hidden) phoneLink.href = `https://wa.me/${value}`;
    };
    phone?.addEventListener('input', updatePhone); updatePhone();
    const appointment = input('appointment_only');
    const chip = form.querySelector('[data-appointment]');
    const updateAppointment = () => { if (appointment && chip) chip.hidden = !appointment.checked; };
    appointment?.addEventListener('change', updateAppointment); updateAppointment();
    fields.forEach(field => {
      const control = field.querySelector('input, textarea');
      const warning = field.querySelector('[data-social-warning]');
      if (warning && control) {
        const update = () => { const value = control.value.trim(); const suspicious = /qa\.|test|prueba|example/i.test(value); warning.textContent = !value ? 'Sin configurar' : suspicious ? '¿Es la cuenta real? Parece de pruebas' : ''; warning.classList.toggle('set-warning', suspicious); };
        control.addEventListener('input', update); update();
      }
      const preview = field.querySelector('[data-preview]');
      if (preview && control) {
        const error = field.querySelector('.set-live-error');
        const update = () => {
          const value = control.value;
          // Formatter accepts doubled braces as literals and forbids format specs/conversions.
          let rendered = '', invalid = false;
          for (let i = 0; i < value.length; i++) {
            const char = value[i];
            if ((char === '{' || char === '}') && value[i + 1] === char) { rendered += char; i++; continue; }
            if (char === '{') {
              const end = value.indexOf('}', i + 1);
              const key = end < 0 ? '' : value.slice(i + 1, end);
              if (!['name', 'sku', 'url'].includes(key)) { invalid = true; rendered += char; continue; }
              rendered += example[key]; i = end;
            } else { if (char === '}') invalid = true; rendered += char; }
          }
          error.textContent = invalid ? 'Solo se permiten {name}, {sku} y {url}.' : '';
          preview.textContent = rendered;
        };
        field.querySelectorAll('[data-variable]').forEach(button => button.addEventListener('click', () => {
          control.setRangeText(`{${button.dataset.variable}}`, control.selectionStart, control.selectionEnd, 'end'); control.focus(); control.dispatchEvent(new Event('input', {bubbles: true}));
        }));
        control.addEventListener('input', update); update();
      }
      const counter = field.querySelector('.set-counter');
      if (counter && control) { const limit = control.name.includes('description') ? 160 : 60; const update = () => { counter.textContent = `${control.value.length} / ${limit} recomendado`; counter.classList.toggle('set-over', control.value.length > limit); }; control.addEventListener('input', update); update(); }
    });
    // Pair translated fields while preserving both form controls in the submission.
    fields.filter(field => /_(es)$/.test(field.dataset.field)).forEach(es => {
      const en = fields.find(field => field.dataset.field === es.dataset.field.replace(/_es$/, '_en'));
      if (!en || !es.querySelector('input, textarea') || !en.querySelector('input, textarea')) return;
      const tabs = document.createElement('div'); tabs.className = 'set-tabs'; tabs.setAttribute('aria-label', 'Idioma');
      const show = lang => { es.hidden = lang !== 'es'; en.hidden = lang !== 'en'; [...tabs.children].forEach(button => button.setAttribute('aria-pressed', String(button.dataset.lang === lang))); };
      ['es', 'en'].forEach(lang => { const button = document.createElement('button'); button.type = 'button'; button.dataset.lang = lang; button.textContent = lang.toUpperCase(); button.addEventListener('click', () => show(lang)); tabs.append(button); });
      es.before(tabs); en.querySelector('.errorlist') ? show('en') : show('es');
    });
    const googleTitle = form.querySelector('[data-google-title]');
    const googleDesc = form.querySelector('[data-google-description]');
    const updateGoogle = () => { if (googleTitle) googleTitle.textContent = input('seo_home_title_es')?.value || ''; if (googleDesc) googleDesc.textContent = input('seo_home_description_es')?.value || ''; };
    form.addEventListener('input', updateGoogle); updateGoogle();
    const links = [...form.querySelectorAll('.set-nav a')];
    if ('IntersectionObserver' in window) { const observer = new IntersectionObserver(entries => { entries.forEach(entry => { if (entry.isIntersecting) links.forEach(link => link.classList.toggle('set-active', link.hash === `#${entry.target.id}`)); }); }, {rootMargin: '-10% 0px -65% 0px'}); form.querySelectorAll('.set-card').forEach(section => observer.observe(section)); }
    const firstError = form.querySelector('.set-field-error');
    form.querySelectorAll('.set-field-error').forEach(field => field.closest('.set-card').classList.add('set-has-error'));
    if (firstError) firstError.scrollIntoView({block: 'center'});
    // Dirty means "differs from what was loaded": undoing an edit clears the warning.
    const snapshot = () => JSON.stringify([...new FormData(form)].filter(([key]) => key !== 'csrfmiddlewaretoken'));
    const initial = snapshot();
    let dirty = false; const dirtyLabel = form.querySelector('[data-dirty]');
    const track = () => { dirty = snapshot() !== initial; if (dirtyLabel) dirtyLabel.hidden = !dirty; };
    form.addEventListener('input', track);
    form.addEventListener('change', track);
    form.addEventListener('submit', () => { dirty = false; });
    window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
