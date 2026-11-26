import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement as h } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { brandStyle, brandIcons, brandMetadata, brandLogoUrl, originalBrand } from './cms-brand.ts';

test('identidad inicial conserva exactamente tokens y HTML del layout', () => {
  for (const title of [90,100,110,120]) for (const text of [90,100,110,120]) {
    const prior = { '--title-scale': title/100, '--text-scale': text/100 };
    const current = brandStyle({ ...originalBrand, title_scale: title, text_scale: text });
    assert.deepEqual(current, prior);
    const layout=(style: object)=>renderToStaticMarkup(h('html',{lang:'es',className:'fuentes',style},h('body',{},'SERTI')));
    assert.equal(layout(current),layout(prior));
  }
});
test('CSS rechaza texto libre y solo emite hex de la lista', () => {
  assert.deepEqual(brandStyle({...originalBrand,wine:'#6A1F36'}), {'--title-scale':1,'--text-scale':1,'--color-wine':'#6a1f36'});
  for(const wine of ['red','#fff','#123456;display:none','</style><script>']) assert.deepEqual(brandStyle({...originalBrand,wine}),brandStyle(originalBrand));
  assert.equal(brandStyle({...originalBrand,title_font:'cormorant'})['--font-serif' as keyof React.CSSProperties], 'var(--font-cormorant), "Cormorant Garamond", Georgia, serif');
  assert.deepEqual(brandStyle({...originalBrand,title_scale:999,text_scale:NaN,title_font:'url(evil)' as 'ninna'}),brandStyle(originalBrand));
});
test('metadata e iconos originales conservan la misma salida y referencias', () => {
  const base={icons:{icon:'/favicon.svg'},title:'SERTI',description:'Joyas'};
  assert.strictEqual(brandMetadata(originalBrand,base),base);
  assert.strictEqual(brandIcons(originalBrand,base.icons),base.icons);
  assert.equal(brandLogoUrl(originalBrand,'https://serti.co'),'https://serti.co/brand/logo/wordmark-wine.png');
});
test('metadata usa rendiciones y foto de marca; JSON-LD usa URL absoluta', () => {
  const custom={...originalBrand,icon:{'32':'/32.png','180':'/180.png','192':'/192.png','512':'/512.png',ico:'/favicon-custom.ico'},logo_light:{src:'/media/logo.webp',width:800,height:300},sharing:{src:'/share.webp',srcset:'',width:1200,height:628,alt:'SERTI'}};
  const data=brandMetadata(custom,{title:'SERTI'});
  assert.deepEqual(data.icons, {icon:[32,192,512].map(size=>({url:`/${size}.png`,sizes:`${size}x${size}`,type:'image/png'})),shortcut:'/favicon-custom.ico',apple:'/180.png'});
  assert.deepEqual(data.openGraph?.images,[{url:'/share.webp',width:1200,height:628,alt:'SERTI'}]);
  assert.equal(brandLogoUrl(custom,'https://serti.co'),'https://serti.co/media/logo.webp');
});

test('editar SEO conserva la imagen de marca y una imagen propia tiene prioridad', async () => {
  const { applyCmsSeo } = await import('./cms-seo.ts');
  const branded=brandMetadata({...originalBrand,sharing:{src:'/brand-share.webp',srcset:'',width:1200,height:628,alt:'SERTI'}},{title:'Historia'});
  const changed=applyCmsSeo(branded,{title:'Nuestra historia',description:'',image:null,noindex:false},'https://serti.co');
  assert.deepEqual(changed.twitter && 'images' in changed.twitter ? changed.twitter.images : null,['/brand-share.webp']);
  assert.equal(changed.twitter && 'card' in changed.twitter ? changed.twitter.card : null,'summary_large_image');
  const custom=applyCmsSeo(branded,{title:'',description:'',image:{src:'/page.webp',srcset:'',width:1200,height:628,alt:'Página'},noindex:false},'https://serti.co');
  assert.deepEqual(custom.openGraph?.images,['https://serti.co/page.webp']);
});

test('layout real conserva todo el HTML con identidad inicial y escalas migradas', async () => {
  const { readFileSync } = await import('node:fs');
  const { createRequire } = await import('node:module');
  const ts = (await import('typescript')).default;
  const require=createRequire(import.meta.url);
  for(const title of [90,100,110,120]) {
    const identity={...originalBrand,title_scale:title,text_scale:90};
    const render=async(file:string,legacy:boolean)=>{
      const source=readFileSync(new URL(file,import.meta.url),'utf8')+'\nexport { SiteDocument };';
      const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
      const mod={exports:{} as {SiteDocument:(props:object)=>Promise<React.ReactElement>}};
      const stubs:Record<string,unknown>={
        'next/headers':{draftMode:async()=>({isEnabled:false})},
        'next/navigation':{notFound:()=>{throw Error('404');}},
        'next/root-params':{locale:async()=>'es'},
        'next/font/google':{Cormorant_Garamond:()=>({variable:'serif'}),Inter:()=>({variable:'sans'})},
        '@/components/route-scroll-reset':{RouteScrollReset:()=>null},
        '@/components/scroll-reveal':{ScrollReveal:()=>null},
        '@/components/site-shell':{Header:()=>h('header',{},'SERTI'),Footer:()=>h('footer',{},'SERTI'),PreviewBar:()=>null},
        '@/lib/api/server':{siteUrl:'https://serti.co',getBrand:async()=>identity,getSettings:async()=>{assert.ok(legacy,'El layout actual no debe leer las escalas antiguas');return {title_scale:title/100,text_scale:.9};},emptySettings:{}},
        '@/lib/cms-brand':{brandStyle,brandMetadata,originalBrand},
        '@/lib/i18n':{isLocale:()=>true,locales:['es','en']},
        './dictionaries':{getDictionary:async()=>({ui:{loading:'Cargando',skip:'Saltar'}})},
        '../globals.css':{},
      };
      Function('require','module','exports',js)((name:string)=>stubs[name]??require(name),mod,mod.exports);
      return renderToStaticMarkup(await mod.exports.SiteDocument({current:'es',dict:{nav:{skip:'Saltar'},ui:{loading:'Cargando'}},children:h('main',{},'Contenido')}));
    };
    assert.equal(await render('../app/[locale]/layout.tsx',false),(await render('../tests/fixtures/layout-before-phase7.tsx.txt',true)).replace('<html ', '<html data-scroll-behavior="smooth" '));
  }
});

test('los tokens iniciales coinciden con el CSS oficial sin emitir sobreescrituras', async () => {
  const { readFileSync } = await import('node:fs');
  const { brandColors } = await import('./cms-brand.ts');
  const css=readFileSync(new URL('../app/globals.css',import.meta.url),'utf8');
  for(const [key,value] of Object.entries(brandColors)) assert.ok(css.includes(`--color-${key}: ${value};`));
  assert.ok(css.includes('--color-emerald: #0b6e4f;'));
  assert.deepEqual(Object.keys(brandStyle(originalBrand)),['--title-scale','--text-scale']);
});
