/* No dependencies. The server registry owns validation and document composition. */
(() => {
  'use strict';
  const root = document.querySelector('#cms-editor');
  if (!root) return;
  const $ = id => document.getElementById(`cms-${id}`);
  const clone = value => structuredClone(value);
  let state, selected, language = 'es', timer, busy = false, uploadBusy = false, blocked = false, dirty = false;
  let queue = [], failed, confirmation, dragId, slideFocus, scrollY = 0, allowUnload = false;
  const local = new Map();
  const slideEdits = new Map();
  const csrf = root.querySelector('[name=csrfmiddlewaretoken]').value;
  const spec = row => state.registry.find(s => s.kind === row.kind);
  const row = () => local.get(selected);
  const status = text => { $('save-status').textContent = text; };
  const announce = text => { $('announcement').textContent = text; };
  function element(tag, text, attrs = {}) {
    const el = document.createElement(tag);
    if (text) el.textContent = text;
    Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
    return el;
  }
  function button(text, action, disabled = false) {
    const el = element('button', text, { type: 'button' });
    el.disabled = disabled; el.onclick = action; return el;
  }
  function pickMedia(slot, set, slide) {
    if (busy || blocked || queue.length || uploadBusy) { announce('Espera a que se guarden los cambios.'); return; }
    if (dirty && selected !== 'new') { flush(); announce('Espera a que se guarden los textos y vuelve a elegir la foto.'); return; }
    if(failed && selected!=='new'){announce('Corrige y guarda los textos antes de elegir la foto.');return;}
    clearTimeout(timer);
    const imageSlot=spec(row()).slots?.find(s=>s.key===slot);
    const recommendation=(slot.includes('mobile')?imageSlot?.mobile:imageSlot?.desktop)||'4:5 · 1600 x 2000 px';
    window.CmsMediaLibrary.open({api:root.dataset.media,csrf,recommendation,crop:slot==='slides.desktop'||row().kind==='hero'&&slot==='image'?'16:9':'4:5',onChoose:reference=>{
      if(selected==='new'){set(reference);properties();}
      else {if(!slot.startsWith('slides.'))row().values[slot]=reference;enqueue({action:'media-select',id:selected,slot,reference,slide});}
    }});
  }
  let photoSequence = 0;
  function photoControl(label, onFile, multiple = false) {
    const control = $('photo-widget').content.firstElementChild.cloneNode(true);
    const input = control.querySelector('input[type=file]');
    const id = `cms-photo-${++photoSequence}`;
    input.id = id; input.setAttribute('aria-label', label);
    control.querySelectorAll('label').forEach(el => el.htmlFor = id);
    input.multiple = multiple;
    input.onchange = () => onFile(multiple ? [...input.files] : input.files[0]);
    return control;
  }
  function pending() { return slideEdits.size || dirty || uploadBusy || busy || queue.length || failed || [...local.values()].some(r=>r.changed); }
  function refreshPreview() {
    if (!state.preview[$('preview-language').value]) { $('preview-status').textContent = 'No tienes permiso de vista previa'; return; }
    $('preview-status').textContent = 'Cargando…';
    $('frame').src = state.preview[$('preview-language').value] + `&refresh=${Date.now()}`;
  }
  function sizePreview() {
    const width = Number($('device').value), space = $('preview-space');
    const scale = Math.min(1, space.clientWidth / width);
    $('frame').style.width = `${width}px`;
    $('frame').style.transform = `scale(${scale})`;
    $('frame').style.height = `${Math.max(900, space.clientHeight / scale)}px`;
  }
  function highlight(reveal = false) {
    $('frame').contentWindow?.postMessage({type:'cms:select', id:selected, scrollY, reveal}, location.origin);
  }
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== $('frame').contentWindow) return;
    if (event.data?.type === 'cms:ready') highlight();
    if (event.data?.type === 'cms:scroll' && Number.isFinite(event.data.y)) scrollY = Math.max(0, event.data.y);
    if (event.data?.type === 'cms:selected' && typeof event.data.id === 'string' && local.has(event.data.id)) select(event.data.id);
  });
  $('frame').onload = () => { $('preview-status').textContent = 'Vista previa'; sizePreview(); highlight(); };
  new ResizeObserver(sizePreview).observe($('preview-space'));
  $('device').onchange = sizePreview;
  $('preview-language').onchange = () => { scrollY = 0; refreshPreview(); };
  $('refresh').onclick = async () => { try {const response=await fetch(`${root.dataset.api}?document=${encodeURIComponent(state.key)}`);if(!response.ok)throw Error();const result=await response.json();state.preview=result.preview;refreshPreview();}catch{$('preview-status').textContent='No se pudo recargar. Inténtalo de nuevo.';} }; 
  function updateBar() {
    $('pending').textContent = `${state.pending} cambios sin publicar`;
    if ($('review')) $('review').href = state.review_url;
    $('discard').hidden = !state.can_discard;
    $('discard').disabled = !!pending();
  }
  async function load(key = 'home') {
    const response = await fetch(`${root.dataset.api}?document=${encodeURIComponent(key)}`);
    if (!response.ok) throw Error('No se pudo abrir la página.');
    state = await response.json(); root.dataset.version=state.version; local.clear(); slideEdits.clear();
    state.sections.forEach(s => local.set(s.id, clone(s)));
    $('document').replaceChildren(...state.documents.map(d => element('option', d.name, {value:d.key})));
    $('document').value = state.key;
    const available = state.key === 'home' ? state.registry : [];
    $('kind').replaceChildren(...available.map(s => element('option', s.name, {value:s.kind})));
    $('add').disabled = !available.length;
    selected = state.sections[0]?.id; dirty = false; blocked = false; failed = null;
    $('conflict').hidden = true; $('retry').hidden = true;
    structure(); properties(); updateBar(); refreshPreview(); status('Guardado');
  }
  async function drain() {
    if (busy || blocked || failed || !queue.length) return;
    busy = true; status('Guardando…');
    const job = queue.shift();
    if(job.payload.action==='create' || job.payload.action.startsWith('hero-'))$('properties-form').inert=true;
    try {
      const response = await fetch(`${root.dataset.api}?document=${encodeURIComponent(state.key)}`, {
        method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':csrf},
        body:JSON.stringify({...job.payload, expected_version:state.version})
      });
      const result = await response.json();
      if (response.status === 409) {
        blocked = true; failed = job; $('conflict').hidden = false; status('Error'); return;
      }
      if (!response.ok) {
        failed = job; status('Error'); $('retry').hidden = false;
        showErrors(result.fields || {'__all__':[result.error]},job.payload.id); return;
      }
      state.version = result.version; root.dataset.version=state.version; state.pending = result.pending; state.preview = result.preview; state.can_discard = result.can_discard;
      if (job.payload.action === 'update') {
        const latest = local.get(job.payload.id);
        if (latest && Object.entries(job.payload.values).every(([key,value])=>JSON.stringify(latest.values[key])===JSON.stringify(value))) {latest.changed = false;latest.errors=false;}
        state.sections = result.sections;
      } else {
        // Structural actions flush text writes first; preserve any edits made while waiting.
        const changed = [...local.values()].filter(r => r.changed && r.id !== 'new');
        local.clear(); result.sections.forEach(s => local.set(s.id, s));
        changed.forEach(r => { if (local.has(r.id)) local.set(r.id, r); });
        if (result.selected) selected = result.selected;
        if (!local.has(selected)) selected = local.keys().next().value;
        properties();
        if(job.payload.action==='hero-reorder' && slideFocus){
          [...$('fields').querySelectorAll('[data-slide]')].find(el=>el.dataset.slide===slideFocus)?.querySelector('button:not(:disabled)')?.focus();
          slideFocus=null;
        }
      }
      structure(); refreshPreview(); status('Guardado'); announce('Cambios guardados');
    } catch { failed = job; status('Error de conexión'); $('retry').hidden = false; }
    finally { busy = false; $('properties-form').inert=false; updateBar(); if (!failed && !blocked) void drain(); }
  }
  function enqueue(payload) { queue.push({payload:clone(payload)}); void drain(); }
  function flush() {
    flushText();
    const edits = [...slideEdits.values()];
    slideEdits.clear();
    if(edits.length && !blocked && failed?.payload.action==='hero-alt'){
      failed=null;$('retry').hidden=true;
    }
    edits.forEach(enqueue);
  }
  function flushText() {
    clearTimeout(timer);
    if (!dirty || !row()) return;
    if(row().id==='new' && (busy || queue.some(j=>j.payload.action==='create'))) return;
    dirty = false;
    const current = row();
    if (failed && !blocked) { failed = null; $('retry').hidden = true; }
    const previous = state.sections.find(s=>s.id===current.id)?.values || {};
    const values = Object.fromEntries(Object.entries(current.values).filter(([key,value])=>key!=='slides' && !(key==='image' && !previous[key] && !value?.asset && !value?.src && !value?.alt?.es && !value?.alt?.en) && (current.id==='new' || JSON.stringify(value)!==JSON.stringify(previous[key]))));
    if(!Object.keys(values).length && current.id!=='new'){current.changed=false;status('Guardado');updateBar();return;}
    enqueue({action:current.id === 'new' ? 'create':'update', id:current.id, kind:current.kind, values});
  }
  function changed() {
    dirty = true; row().changed = true; status('Cambios pendientes');
    clearTimeout(timer); timer = setTimeout(flush, 800); structure(); updateBar(); missing();
  }
  function select(id) { if(uploadBusy){announce('Espera a que termine la carga de la foto.');return;} if(busy&&row()?.id==='new'){announce('Espera a que se guarde la nueva sección.');return;} flush(); selected = id; properties(); structure(); highlight(true); }
  function structure() {
    const active=document.activeElement;const oldRow=active?.closest('#cms-sections li');const focusId=oldRow?.dataset.section;const focusIndex=oldRow?[...oldRow.querySelectorAll('button')].indexOf(active):-1;
    $('sections').replaceChildren(...[...local.values()].map((section, index, rows) => {
      const li = element('li', '', {'aria-current':String(section.id === selected),'data-section':section.id});
      const title = spec(section);
      const pick = button('', () => { select(section.id); if (innerWidth < 1100) document.querySelector('.cms-panels').dataset.panel='properties'; });
      pick.className = 'cms-section-select';
      const icon = element('span', title.icon, {class:'material-symbols-outlined','aria-hidden':'true'});
      pick.append(icon, document.createTextNode(` ${title.name}${section.values.title?.es ? ' · '+section.values.title.es.slice(0,45):''}${!section.visible ? ' · Oculta':''}${section.changed ? ' · Con cambios':''}${section.errors ? ' · Con errores':''}`));
      li.append(pick);
      if (title.can_reorder && section.id !== 'new') {
        li.draggable = true;
        li.ondragstart = () => { dragId = section.id; };
        li.ondragover = e => e.preventDefault();
        li.ondrop = e => { e.preventDefault(); move(dragId, index); };
        const tools = element('div', '', {class:'cms-row-tools'});
        tools.append(button('↑', () => move(section.id, index - 1), index === 0), button('↓', () => move(section.id, index + 1), index === rows.length - 1));
        tools.children[0].setAttribute('aria-label', `Subir ${title.name}`); tools.children[1].setAttribute('aria-label', `Bajar ${title.name}`);
        li.append(tools);
      }
      return li;
    }));
    if(focusId){const target=[...$('sections').children].find(el=>el.dataset.section===focusId);target?.querySelectorAll('button')[focusIndex]?.focus();}
  }
  function move(id, index) {
    flush(); if (local.has('new')) return;
    const rows = [...local.values()], start = rows.findIndex(r => r.id === id);
    if (start < 0 || index < 0 || index >= rows.length) return;
    rows.splice(index,0,rows.splice(start,1)[0]); local.clear(); rows.forEach(r => local.set(r.id,r));
    structure(); enqueue({action:'reorder',ids:rows.map(r => r.id)}); announce(`Sección en la posición ${index + 1}`);$('sections').children[index]?.querySelector('button')?.focus();
  }
  function missing() {
    const count = JSON.stringify(row()?.values || {}).match(/"en":""/g)?.length || 0;
    $('missing').textContent = count ? `${count} textos sin traducir` : '';
  }
  function showErrors(errors, id = selected) {
    document.querySelectorAll('.cms-field-error').forEach(el => el.remove());
    const current=local.get(id);if(current)current.errors=errors;
    if(id!==selected){structure();return;}
    for (const [path, messages] of Object.entries(errors)) {
      const target = [...document.querySelectorAll('[data-path]')].filter(el => el.dataset.path === path || path.startsWith(el.dataset.path + '.')).sort((a,b)=>b.dataset.path.length-a.dataset.path.length)[0] || $('fields');
      target.append(element('p', (/\.(es|en)$/.test(path) ? path.slice(-2).toUpperCase()+': ' : '') + (Array.isArray(messages) ? messages.join(' ') : String(messages)), {class:'cms-field-error',role:'alert'}));
    }
    structure();
  }
  function focusList(path,index){const wrap=[...$('fields').querySelectorAll('[data-path]')].find(el=>el.dataset.path===path);const group=wrap?.querySelectorAll('fieldset')[index];(group?.querySelector('input,textarea,button') || wrap?.querySelector('button'))?.focus();}
  function fields(fields_, values, container, prefix = '') {
    fields_.forEach(field => {
      if (field.key === 'slides' && spec(row()).storage === 'columns') { heroPhotos(container); return; }
      const path = prefix + field.key;
      const wrap = element('div','',{class:'cms-field','data-path':path});
      const label = element('span', row().kind==='hero' && field.key==='image' ? 'Foto de respaldo (si no hay carrusel)' : field.label); wrap.append(label); container.append(wrap);
      const set = value => { values[field.key] = value; changed(); };
      let value = values[field.key] ?? clone(field.default ?? null);
      if (field.translated) {
        value ||= {es:'',en:''};
        const input = element(field.type === 'short_text' ? 'input':'textarea','',{'aria-label':`${field.label} (${language.toUpperCase()})`});
        input.value = value[language] || ''; input.setAttribute('aria-required',String(!!field.required)); if (field.max) input.maxLength = field.max;
        const count = element('small',`${input.value.length} / ${field.max || '—'}`,{class:'cms-help'});
        input.oninput = () => { values[field.key] = value; value[language] = input.value; count.textContent = `${input.value.length} / ${field.max || '—'}`; changed(); };
        wrap.append(input,count); if (field.type === 'markdown') wrap.append(element('p','Puedes usar **negrita**, listas y enlaces [texto](https://…). El contenido se limpia al mostrarlo.',{class:'cms-help'}));
      } else if (field.type === 'list') {
        value ||= []; values[field.key] = value;
        value.forEach((item,index) => {
          const group = element('fieldset'); group.append(element('legend',`${field.label} ${index+1}`));
          fields(field.fields,item,group,`${path}.${index}.`);
          const shift = delta => { const next = index+delta; [value[index],value[next]]=[value[next],value[index]]; changed(); properties(); focusList(path,next); };
          group.append(button('Subir',()=>shift(-1),index===0),button('Bajar',()=>shift(1),index===value.length-1),button('Quitar',()=>{value.splice(index,1);changed();properties();focusList(path,Math.max(0,index-1));},value.length <= (field.min || 0)));
          wrap.append(group);
        });
        wrap.append(button('Añadir',()=>{value.push(Object.fromEntries(field.fields.map(f=>[f.key,clone(f.default)])));changed();properties();focusList(path,value.length-1);},field.max && value.length>=field.max));
      } else if (field.type === 'select' || ['category','collection','piece'].includes(field.type)) {
        const input = element('select','',{'aria-label':field.label});
        const options = field.type === 'select' ? field.options.map(v=>({id:v,name:Object.fromEntries(field.option_labels || [])[v] || v})) : state.choices[field.type];
        input.append(element('option','Selecciona…',{value:''}),...options.map(o=>element('option',o.name,{value:o.id})));
        input.value = value ?? ''; input.onchange=()=>set(field.type==='select'?input.value:Number(input.value)); wrap.append(input);
      } else if (field.type === 'boolean') {
        const input=element('input','',{type:'checkbox','aria-label':field.label}); input.checked=!!value; input.onchange=()=>set(input.checked); wrap.append(input);
      } else if (field.type === 'cta') {
        const kinds = {none:'Sin enlace',catalog:'Catálogo',personalize:'Personaliza',story:'Historia',contact:'Contacto',category:'Categoría',collection:'Colección',piece:'Pieza',stone:'Piedra',page:'Página legal',external:'Enlace externo HTTPS'};
        const input=element('select','',{'aria-label':'Destino del enlace'});
        input.append(...Object.entries(kinds).map(([id,name])=>element('option',name,{value:id}))); input.value=value?.kind || 'none';
        input.onchange=()=>{set(input.value==='none'?null:{kind:input.value,label:value?.label || {es:'',en:''},...(['category','collection','piece','stone','page'].includes(input.value)?{target:null}:input.value==='external'?{url:''}:{})});properties();}; wrap.append(input);
        if(value) {
          fields([{key:'label',type:'short_text',label:'Texto del enlace',translated:true,max:150}],value,wrap,path+'.');
          if(value.kind==='external') { const url=element('input','',{type:'url',placeholder:'https://…','aria-label':'Dirección HTTPS'});url.value=value.url||'';url.oninput=()=>{value.url=url.value;changed();};wrap.append(url); }
          if(state.choices[value.kind]) {const target=element('select','',{'aria-label':'Destino'});target.append(element('option','Selecciona…',{value:''}),...state.choices[value.kind].map(o=>element('option',o.name,{value:o.id})));target.value=value.target||'';target.onchange=()=>{value.target=Number(target.value);changed();};wrap.append(target);}
        }
      } else if (field.type === 'image') {
        wrap.append(button('Elegir de la biblioteca',()=>pickMedia(field.key,set)),button('Subir nueva',()=>pickMedia(field.key,set)));
        if(value?.asset){
          const image=element('img','',{alt:'Foto elegida de la biblioteca',width:'160'});wrap.append(image,element('p',`Foto de biblioteca · recorte ${value.crop}`,{class:'cms-help'}));
          fetch(`${root.dataset.media}${value.asset}/`).then(r=>r.json()).then(a=>{if(a.thumbnail)image.src=a.thumbnail;}).catch(()=>{});
          wrap.append(button('Ajustar foto y recorte',()=>pickMedia(field.key,set)));return;
        }
        const slot = spec(row()).slots?.find(s=>s.key===field.key);wrap.append(element('p',`Recomendación: ${slot?.desktop || '4:5 · 1600 × 2000 px'}. Celular: ${slot?.mobile || '4:5 · 1080 × 1350 px'}. Texto alternativo obligatorio en ES y EN.`,{class:'cms-help'}));
        if(value?.src) wrap.append(element('img','',{src:value.src,alt:'Foto elegida',width:'160'}));
        if (spec(row()).storage === 'columns') {
          if(!value){value={alt:{es:'',en:''}};values[field.key]=value;} fields([{key:'alt',type:'short_text',label:'Texto alternativo',translated:true,max:300}],value,wrap,path+'.');

        } else {
          if(!value) { wrap.append(button('Elegir una foto',()=>{set({src:'',srcset:'',width:1600,height:2000,alt:{es:'',en:''}});properties();})); return; }
          fields([{key:'alt',type:'short_text',label:'Texto alternativo',translated:true,max:300}],value,wrap,path+'.');

          if(!field.required) wrap.append(button('Quitar imagen',()=>{set(null);properties();}));
        }
      }
    });
  }
  function heroPhotos(container) {
    if(selected==='new') {container.append(element('p','Guarda la portada antes de añadir fotos.'));return;}
    for(const device of ['desktop','mobile']) {
      const slot=spec(row()).slots.find(s=>s.key===`slides.${device}`);
      if(!slot) continue;
      const group=element('fieldset','',{'data-carousel':device,class:'cms-carousel'});
      group.append(element('legend',slot.label),element('p',`Recomendación: ${device==='mobile'?slot.mobile:slot.desktop}.`,{class:'cms-help'}));
      const slides=(row().values.slides || []).filter(s=>s.device===device);
      const moveSlide=(id,index)=>{
        if(index<0 || index>=slides.length)return;
        const ids=slides.map(s=>s.id),start=ids.indexOf(id);if(start<0)return;
        ids.splice(index,0,ids.splice(start,1)[0]);slideFocus=id;flush();enqueue({action:'hero-reorder',id:selected,device,ids});
        announce(`Foto en la posición ${index+1}`);
      };
      slides.forEach((slide,index)=>{
        const card=element('div','',{class:'cms-slide','data-slide':slide.id,draggable:'true'});
        card.ondragstart=e=>{e.dataTransfer.setData('text/plain',slide.id);};
        card.ondragover=e=>e.preventDefault();card.ondrop=e=>{e.preventDefault();moveSlide(e.dataTransfer.getData('text/plain'),index);};
        if(slide.thumbnail)card.append(element('img','',{src:slide.thumbnail,alt:slide.alt[language] || 'Foto de portada',width:'160',loading:'lazy'}));
        card.append(element('p',`Foto ${index+1}`));
        if(slide.reference?.asset)card.append(button('Ajustar foto y recorte',()=>pickMedia(`slides.${device}`,null,slide.id)));
        for(const [lang,label] of (slide.reference?.asset ? [] : [['es','ES'],['en','EN']])) {
          const input=element('input','',{'aria-label':`Texto alternativo foto ${index+1} (${label})`,maxlength:'300'});input.value=slide.alt[lang] || '';
          input.oninput=()=>{
            slide.alt[lang]=input.value;
            slideEdits.set(slide.id,{action:'hero-alt',id:selected,device,slide:slide.id,alt:slide.alt});
            status('Cambios pendientes');clearTimeout(timer);timer=setTimeout(flush,800);updateBar();
          };
          input.onchange=flush;
          card.append(element('label',`Texto alternativo (${label})`),input);
        }
        const up=button('Subir',()=>moveSlide(slide.id,index-1),index===0);
        const down=button('Bajar',()=>moveSlide(slide.id,index+1),index===slides.length-1);
        const remove=button('Eliminar foto',()=>confirmAction('¿Eliminar esta foto del carrusel?',()=>{flush();enqueue({action:'hero-delete',id:selected,device,slide:slide.id});}));
        for(const [control,label] of [[up,'Subir'],[down,'Bajar'],[remove,'Eliminar']])control.setAttribute('aria-label',`${label} foto ${index+1}`);
        card.append(up,down,remove);
        group.append(card);
      });
      group.append(button('Elegir de la biblioteca',()=>pickMedia(`slides.${device}`)),button('Subir nueva',()=>pickMedia(`slides.${device}`)));

      container.append(group);
    }
  }
  async function uploadPhoto(file, slot, device) {
    if (!file || busy || blocked || queue.length) { announce('Guarda primero los textos antes de subir la foto.'); return; }
    if((dirty || slideEdits.size) && selected!=='new'){flush();announce('Espera a que se guarden los textos y vuelve a elegir la foto.');return;}
    if(failed && !slot){announce('Corrige y guarda los textos antes de subir la foto.');return;}
    clearTimeout(timer); dirty=false; failed=null;$('retry').hidden=true; if (busy) { announce('Espera a que termine el guardado y vuelve a elegir la foto.'); return; }
    const data=new FormData(); data.append('expected_version',state.version);data.append('section',selected);data.append('kind',row().kind);for(const item of (Array.isArray(file)?file:[file]))data.append('file',item);
    if(slot)data.append('slot',slot);if(device)data.append('device',device);
    data.append('alt_es',row().values[slot || 'image']?.alt?.es || ''); data.append('alt_en',row().values[slot || 'image']?.alt?.en || '');
    busy=true;uploadBusy=true;$('properties-form').inert=true;status('Guardando…');
    try {const response=await fetch(root.dataset.api.replace('documento/','foto/'),{method:'POST',headers:{'X-CSRFToken':csrf},body:data});const result=await response.json();
      if(response.status===409){blocked=true;$('conflict').hidden=false;status('Error');return;}
      if(!response.ok){showErrors(result.fields || {'image':[result.error]});status('Error');return;}
      state.version=result.version;root.dataset.version=state.version;state.pending=result.pending;state.preview=result.preview;state.can_discard=result.can_discard;state.sections=result.sections;if(result.image&&slot)row().values[slot]=result.image;else result.sections.forEach(s=>{if(s.id===selected)local.set(s.id,s);});properties();updateBar();refreshPreview();status('Guardado');if(slot && selected==='new')changed();
    }catch{status('Error de conexión');}finally{busy=false;uploadBusy=false;$('properties-form').inert=false;updateBar();void drain();}
  }
  function properties() {
    $('fields').replaceChildren(); $('section-actions').replaceChildren();
    if(!row()) return;
    const current=row(),type=spec(current); $('section-title').textContent=type.name;
    fields(type.fields,current.values,$('fields'));missing();if(current.errors)showErrors(current.errors);
    if(state.key==='home' && current.id!=='new') {
      $('section-actions').append(button(current.visible?'Ocultar sección':'Mostrar sección',()=>{flush();enqueue({action:'visibility',id:current.id,visible:!current.visible});}));
      if(type.multiple)$('section-actions').append(button('Duplicar sección',()=>{flush();enqueue({action:'duplicate',id:current.id});}));
      $('section-actions').append(button('Eliminar sección',()=>confirmAction('¿Eliminar esta sección del borrador?',()=>{flush();enqueue({action:'delete',id:current.id});})));

    }
  }
  function confirmAction(message, action) { confirmation=action;$('confirm-message').textContent=message;$('confirm').hidden=false;$('confirm-no').focus(); }
  $('confirm-no').onclick=()=>{$('confirm').hidden=true;confirmation=null;};
  $('confirm-yes').onclick=()=>{$('confirm').hidden=true;confirmation?.();confirmation=null;};
  $('discard').onclick=()=>confirmAction('¿Volver a la última publicación? Los cambios del borrador se reemplazarán.',()=>enqueue({action:'discard'}));
  $('properties-form').onsubmit=e=>{e.preventDefault();dirty=true;flush();};
  $('retry').onclick=()=>{if(failed&&!blocked){if(row()?.id===failed.payload.id && failed.payload.action==='update')failed.payload.values=Object.fromEntries(Object.keys(failed.payload.values).map(key=>[key,clone(row().values[key])]));
    if(failed.payload.action==='hero-alt'){const slide=row()?.values.slides?.find(s=>s.id===failed.payload.slide);if(slide)failed.payload.alt=clone(slide.alt);}queue.unshift(failed);failed=null;$('retry').hidden=true;void drain();}};
  $('reload').onclick=()=>{allowUnload=true;location.reload();};
  if($('review'))$('review').onclick=e=>{if(pending()){e.preventDefault();flush();announce('Espera a que se guarden los cambios antes de revisar la publicación.');}};
  $('copy').onclick=async()=>{const lines=[];const visit=(fields,values,prefix='')=>fields.forEach(f=>{const v=values?.[f.key];if(f.translated){for(const lang of ['es','en'])if(v?.[lang])lines.push(`${prefix}${f.label} (${lang.toUpperCase()}): ${v[lang]}`);}else if(f.key==='slides'&&Array.isArray(v))v.forEach((slide,i)=>{for(const lang of ['es','en'])if(slide.alt?.[lang])lines.push(`Foto ${i+1} (${slide.device==='mobile'?'celular':'computador'}) · Texto alternativo (${lang.toUpperCase()}): ${slide.alt[lang]}`);});else if(f.type==='list'&&Array.isArray(v))v.forEach((item,i)=>visit(f.fields,item,`${f.label} ${i+1} · `));else if(f.type==='cta'&&v)for(const lang of ['es','en'])if(v.label?.[lang])lines.push(`Enlace (${lang.toUpperCase()}): ${v.label[lang]}`);});for(const r of local.values()){lines.push(spec(r).name);visit(spec(r).fields,r.values);}const texts=lines.join('\n\n');const area=$('copy-text');area.hidden=false;area.value=texts;area.focus();area.select();try{await navigator.clipboard.writeText(texts);}catch{/* Text remains selected for manual copying. */}};
  $('document').onchange=()=>{const key=$('document').value;if(pending()){ $('document').value=state.key;announce('Espera a que se guarden los cambios antes de cambiar de página.');return;}void load(key).catch(e=>status(e.message));};
  $('add').onclick=()=>{if(uploadBusy)return;flush();if(local.has('new'))return;const kind=$('kind').value;const type=state.registry.find(s=>s.kind===kind);local.set('new',{id:'new',kind,visible:true,changed:true,values:Object.fromEntries(type.fields.map(f=>[f.key,clone(f.default)]))});selected='new';structure();properties();document.querySelector('.cms-panels').dataset.panel='properties';};
  document.querySelectorAll('[data-language]').forEach(el=>el.onclick=()=>{language=el.dataset.language;document.querySelectorAll('[data-language]').forEach(b=>b.setAttribute('aria-pressed',String(b===el)));properties();});
  document.querySelectorAll('[data-panel]').forEach(el=>{if(el.tagName==='BUTTON')el.onclick=()=>{document.querySelector('.cms-panels').dataset.panel=el.dataset.panel;sizePreview();};});
  window.addEventListener('beforeunload',e=>{if(!allowUnload && pending()){e.preventDefault();e.returnValue='';}});
  void load(new URLSearchParams(location.search).get('document') || 'home').catch(e=>status(e.message));
})();
