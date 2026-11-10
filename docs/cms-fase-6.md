# CMS — Fase 6: páginas, direcciones, menús, SEO y traducciones

Trabajo sobre `fase-9-produccion`, base `482709d`. Se leyeron `cms-fase-1.md` a `cms-fase-5.md`. No se añadieron dependencias ni campañas programadas. No se cambiaron carrito, checkout, Wompi, pedidos ni las rutas o direcciones de catálogo. `docs/capturas/` ya estaba sin seguimiento y se conserva intacto.

La integración con PostgreSQL y la ejecución del escenario E2E quedan pendientes de validación local: este sandbox no permite conectar a PostgreSQL. Los resultados de compilación y pruebas sin base de datos no sustituyen esa validación.

## Páginas y compatibilidad

Se mantiene la lista fija de ocho tipos de `Page`: terms, privacy, returns, shipping, cookies, manufacturer, contact y personalize. El admin tampoco permite crear ni borrar tipos. Cada página conserva `page:<kind>`, su versión de borrador y sus publicaciones inmutables.

El panel derecho del editor incorpora título, cuerpo Markdown y dirección en ES/EN. La barra mínima ofrece negrita, cursiva, enlace, lista y encabezado; el contenido pasa por el renderizador Markdown/nh3 existente. La vista previa usa el iframe autenticado habitual. Los parches por idioma conservan el texto del otro idioma. Las páginas legales muestran versión, última publicación y aviso de que publicar cambia la versión legal visible.

Personaliza sigue usando exclusivamente `ProcessStep`, `FaqItem` y `page_bindings`. No se crean secciones duplicadas. Hay una precaución de compatibilidad: su cuerpo general anterior estaba oculto por decisión de la clienta. `Page.body_enabled`, inicialmente falso, conserva esa composición; editar el cuerpo lo habilita en el borrador y la revisión explica que se mostrará antes de los pasos. Publicar solo SEO no habilita ese cuerpo. La restauración recupera también esa decisión. El campo público aditivo `body_visible` permite mantener el comportamiento de publicaciones antiguas sin reescribirlas.

## Direcciones y redirecciones

Las direcciones existentes permanecen intactas durante la migración, incluidas las legales con `/legal/`. Al elegir otra dirección se guarda un único segmento normalizado: minúsculas, sin acentos, con guiones. La dirección nueva es `/<idioma>/<segmento>`. `Page.slug_paths` conserva el camino completo elegido por idioma, y las publicaciones guardan `path`; un adaptador calcula los caminos de snapshots antiguos. Volver a escribir el mismo segmento con acentos o mayúsculas no cambia silenciosamente su prefijo antiguo.

La validación reserva los segmentos de `frontend/lib/routes.ts`, reflejados en `apps/core/routes.py`, sus prefijos de catálogo y palabras de sistema. Comprueba otras páginas en borrador, sus direcciones publicadas y las redirecciones manuales activas. Las constraints únicas de los segmentos continúan siendo inmediatas; un conflicto concurrente de unicidad devuelve una validación legible. Publicar vuelve a comprobar los caminos de destino.

`Redirect` conserva dirección anterior/destino, idioma, código 301/308, responsable y fechas, estado activo, origen automática/manual y campos de visitas. Las automáticas nacen únicamente dentro de la transacción de publicación. Guardar o restaurar un borrador no cambia las redirecciones. Publicar una restauración recalcula la transición desde la publicación actualmente visible, reactiva el camino restaurado como página y desactiva su redirección anterior. Las cadenas se aplanan, se rechazan ciclos y no se admiten redirecciones a sí mismas. Los cambios de páginas y las redirecciones manuales comparten un bloqueo de `home`; publicar toma primero ese bloqueo y luego el documento de página, siempre en el mismo orden. Solo se guardan las redirecciones automáticas que realmente cambian.

La pantalla «Página web → Redirecciones» permite buscar, crear, editar y desactivar. Contenido puede consultar; solo quien tiene `publish_content` puede escribir. El formulario usa CSRF y un documento interno `redirects` con `expected_version` y HTTP 409. No admite URLs externas, dobles barras, escapes porcentuales, parámetros, fragmentos ni segmentos reservados. Verifica el destino final existente, no solo que coincida con un prefijo de catálogo. Permite Inicio como destino. Una página vigente no puede quedar oculta por una redirección manual.

`frontend/proxy.ts` consulta la lista pública compacta antes de resolver/renderizar las rutas y responde con 301 o 308. El resolvedor comprueba de nuevo caminos, códigos y ciclos. Excluye `/api`, `/dashboard`, `/_next`, `/media`, `/static` y `/preview`, también en sus formas localizadas. Draft Mode omite las redirecciones para permitir editar/previsualizar un camino que volvió al borrador. El proxy tiene timeout de dos segundos; ante indisponibilidad continúa con la tienda. Se conservan parámetros de consulta del visitante.

La lista tiene caché de Django de 60 segundos y cabeceras públicas del mismo plazo. Publicar o guardar redirecciones invalida esa caché al confirmar la transacción; la invalidación usa callback robusto. El proxy solicita también revalidación corta y no depende de variables globales compartidas. Esto es caché de redirecciones, no la invalidación por tags de CMS prevista para Fase 8.

**No se cuentan visitas redirigidas en esta fase.** `hits` y `last_hit_at` se reservan en el modelo, pero no se hace ninguna petición adicional por visita ni se presenta una estadística que sugiera lo contrario.

Los caminos nuevos se sirven mediante el catch-all editorial. Las páginas legales comprueban su camino canónico para no servir una segunda copia en `/legal/<dirección-nueva>`. Hreflang, `PageAlternates`, canonical y sitemap usan las publicaciones vigentes. El sitemap conserva el respaldo de las tres páginas editoriales fijas si todavía no tienen publicación y excluye páginas publicadas con `noindex`.

## Menús como documentos independientes

Se eligieron `menu:main` y `menu:footer` para que editar/publicar un enlace no publique cambios ajenos de Inicio. Reutilizan `ContentDocument.draft_version`, `expected_version`, revisión semántica, publicación idempotente, permisos e historial. `MenuPublication` es inmutable; su puntero es tipado. `DraftRevision.restored_from_menu` incorpora un tercer origen tipado y la constraint exige exactamente uno de los tres orígenes posibles.

Los enlaces se editan como lista ordenable, con visibilidad, etiqueta bilingüe de hasta 40 caracteres y destino tipado mediante el mismo control CTA. Hay hasta ocho enlaces principales o doce en el pie. Los desplegables Catálogo/Piedras/Colecciones se pueden ocultar y reordenar; sus hijos continúan viniendo de la taxonomía. Se permiten categorías, piedras, colecciones, páginas internas, catálogo, Inicio y los accesos editoriales existentes. Los externos HTTPS solo se admiten en el pie. Una página explícita debe estar publicada antes de publicar el menú que la enlaza. Los accesos históricos Personaliza/Historia/Contacto conservan sus respaldos cuando todavía no hay publicación.

El documento del pie controla su navegación legal/editorial. Se conservan como elementos globales separados la invitación superior a Personaliza, correo, redes, medios de pago, firma y textos de marca. No se convierten en enlaces de catálogo ni se altera su estructura.

La migración copia exactamente las seis etiquetas y destinos actuales ES/EN del principal, y los enlaces legales publicados del pie, con sus títulos publicados. No toma títulos de borradores ni publica páginas. Una publicación vacía no activa el respaldo histórico. El frontend lee menús en vivo mediante `cmsRead` y `connection()`, igual que páginas e Inicio; no se añadió invalidación por tags.

## SEO

Las opciones de Inicio y páginas pertenecen a su `ContentDocument`. Los títulos (60) y descripciones (155) son bilingües; la foto usa una referencia estable de la biblioteca con proporción `1.91:1` y alt ES/EN. `noindex` es común a ambos idiomas y solo puede cambiarlo quien publica. La advertencia explica que puede retirar la página de Google. El panel dibuja tarjetas de Google y WhatsApp/Facebook con HTML/CSS propio, sin servicios externos.

Inicio congela SEO en una columna de `HomePublication`, conservando la forma histórica del arreglo de secciones. Las páginas lo congelan en `_seo` dentro de su snapshot. Las restauraciones recuperan esas fuentes y las fotos siguen protegidas por el índice de usos, incluidos borradores, publicaciones anteriores y `DraftRevision`. No se modifica ninguna publicación antigua. Las generaciones anteriores de biblioteca se conservan: elegir una foto para compartir prepara una generación con el recorte nuevo.

`applyCmsSeo` aplica title, description, openGraph, twitter y robots sobre los metadatos existentes. Canonical y alternates conservan los caminos publicados. Sin opciones personalizadas devuelve exactamente el objeto de metadatos anterior, sin introducir twitter ni robots nuevos. Los vacíos mantienen título de página/diccionario y descripción del diccionario. Draft Mode lee SEO del borrador y conserva `noindex, nofollow`.

La API añade `seo: {title, description, image, noindex}` a Inicio y páginas. Se actualizaron serializers/OpenAPI, tipos TypeScript, contrato documentado y exportación JSON del registro (`seo_slot`). Las once secciones existentes conservan su contrato.

## Traducciones pendientes

«Página web → Traducciones pendientes» recorre fuentes originales de secciones, páginas, listas y enlaces de menús, SEO y alt de biblioteca. Detecta ES no vacío con EN vacío o idéntico, agrupado por documento, y abre el editor en sección/campo e idioma EN; los enlaces de fotos abren su detalle. Las direcciones no se cuentan como textos de traducción.

El contador del panel usa la misma regla. En los campos que ya tienen el mismo texto puede marcarse «Es igual en ambos idiomas». La excepción pertenece al documento y conserva el texto español exacto: si cambia el texto o se vacía el inglés, vuelve a contarse. Las excepciones son una anotación editorial versionada, no cambian las publicaciones. Los alt de biblioteca se detectan y traducen en su pantalla; no tienen este marcado opcional.

## Migraciones y reversa

1. **0022_menupublication_redirect_and_more**: modelos de menús y redirecciones, punteros y origen de restauración, fuentes SEO, direcciones, compatibilidad del cuerpo de Personaliza y excepciones de traducción. Constraints inmediatas, no diferibles. La última operación protege la reversa antes de retirar columnas si existen menús, redirecciones, caminos, SEO, cuerpo habilitado o excepciones que se perderían.
2. **0023_initial_menus**: semilla idempotente con modelos históricos y alias de conexión. No sobrescribe documentos existentes. La reversa valida ambos menús antes de retirar la semilla: se niega si fueron editados, publicados de nuevo o restaurados. Retira únicamente documentos/publicaciones propios de la semilla intacta.
3. **0024_alter_page_slug_alter_page_slug_en_and_more**: etiquetas españolas «Dirección de la página», sin cambiar datos; reversible.

Las pruebas de migraciones vuelven a `loader.graph.leaf_nodes()` en `finally`. Las comparaciones de bytes de Fases 3 y 5 siguen ejerciendo las vistas públicas y comparando los bytes completos ES/EN: el helper selecciona modelos históricos durante el estado intermedio del esquema y proporciona únicamente defaults aditivos ausentes. No utiliza modelos runtime para consultar columnas todavía inexistentes, no reescribe snapshots y no retira aserciones de igualdad.

## Endpoints

| Ruta | Uso |
|---|---|
| `GET /api/v1/cms/redirects` | Solo activas, `{from_path,to_path,status_code}`, caché 60 s |
| `GET /api/v1/cms/menus/main` y `/footer` | Menú localizado publicado; token `preview` opcional |
| `GET /api/v1/cms/home` y `/cms/pages/*` | `seo` aditivo; páginas añaden `body_visible` |
| `GET/POST /<ADMIN_URL>/editor/documento/?document=menu:main\|menu:footer` | Mismo protocolo de versión y permisos del editor |
| `GET/POST /<ADMIN_URL>/revisar-publicacion/<documento>/` | Revisión/publicación de páginas, Inicio y menús |
| `GET/POST /<ADMIN_URL>/publicaciones/?document=menu:main\|menu:footer` | Historial y restauración confirmada |
| `GET/POST /<ADMIN_URL>/redirecciones/` | Búsqueda y gestión manual; Contenido solo consulta |
| `GET /<ADMIN_URL>/traducciones/` | Traducciones pendientes y enlaces al campo en inglés |

Las escrituras del editor, biblioteca y redirecciones conservan sesión/CSRF y 409. Propietaria publica y restaura; Contenido edita y previsualiza; Operaciones no accede. Las vistas públicas no exponen fuentes de borrador sin token, responsables ni referencias internas de biblioteca.

## Archivos

- Dominio: `backend/apps/cms/{models,page_options,menus,redirects,services,documents,selectors,review_changes,publishing,history}.py`; `documents.py` conserva su implementación.
- Editor: `visual_documents.py`, `editor_api.py`, `phase6_views.py`, `admin.py`, plantillas de historial/redirecciones/traducciones y `static/cms/{visual-editor.js,visual-editor.css,media-library.js}`.
- Biblioteca/contratos: `media.py`, `registry.py`, `api/{views,urls,serializers}.py`, migraciones 0022–0024 y `docs/api-contract.md`.
- Navegación del panel: `backend/apps/core/dashboard.py` y `backend/config/urls.py`.
- Tienda: proxy y resolvedor, `cms-seo.ts`, `api/{server,types,section-registry.json}`, navegación/pie, páginas editoriales, legales/catch-all, Inicio y sitemap.
- Pruebas: `backend/apps/cms/tests/test_phase6.py`, helper y ajustes de migraciones anteriores; `frontend/lib/{cms-phase6,cms-footer}.test.ts`; `frontend/tests/e2e/cms-phase6.spec.ts`.

## Pruebas y resultados

- Frontend: lint, typecheck y **72 pruebas correctas**. Incluyen resolvedor del middleware (exclusiones, códigos, cadenas, ciclos y destinos inseguros), metadata vacía idéntica y SEO personalizado/draft, HTML real del principal y pie idéntico al respaldo anterior en ES/EN, publicación vacía y enlaces externos.
- Backend sin base de datos: **99 pruebas correctas** del CMS y etiquetas españolas. Incluyen normalización, caminos inseguros, cadenas/ciclos, límites SEO, detección de traducciones, proporción y contrato del registro.
- Fase 6: **59 casos recopilados**, incluidos los que requieren PostgreSQL para permisos, publicación/restauración/409, slugs y colisiones, redirecciones manuales/automáticas, caché, presupuestos, menús/migración, SEO, referencias y compatibilidad del cuerpo de Personaliza.
- `manage.py check`, `makemigrations --check --dry-run`, Ruff de Python modificado, sintaxis de JS y `git diff --check`: correctos. La comprobación de migraciones avisa de PostgreSQL inaccesible; no se aplicaron migraciones a una base existente.
- OpenAPI generado y validado sin errores en `/private/tmp/phase6-openapi-final.yaml`.
- Suite completa solicitada, `cd backend && pytest --ds=config.settings.test -q`: última ejecución **212 correctas, 1132 errores de preparación, 6 avisos**, en 121,02 s; registro `/private/tmp/phase6-backend-final.txt`. PostgreSQL en `127.0.0.1:5432` devuelve `Operation not permitted`. Nunca se utilizó SQLite. No se declara verde la integración. Las pruebas adicionales del cuerpo de Personaliza y de una dirección inglesa sin traducción restaurada se añadieron después de esa recopilación y están incluidas en los 59 casos finales; su ejecución también requiere PostgreSQL.
- Presupuestos preparados: redirecciones una consulta en caché fría y cero en caliente; menú público como máximo seis. La biblioteca conserva su límite existente de 18; los presupuestos de integración no se han medido aquí.
- Playwright recopila **un escenario de escritorio**. Está listo y no se ejecutó contra el stack. Cambia dirección ES de Envíos, publica y comprueba 301; publica una etiqueta del principal; publica SEO y verifica title/og; traduce desde la lista de pendientes y comprueba que desaparezca. `finally` restaura/publica las páginas y ambos menús iniciales y repone exactamente las redirecciones iniciales, incluidos sus metadatos. El historial inmutable permanece.

```sh
cd backend
python manage.py migrate
pytest --ds=config.settings.test -q
```

```sh
cd frontend
npm run lint
npm run typecheck
npm test
./node_modules/.bin/playwright test tests/e2e/cms-phase6.spec.ts --project=desktop
```

El E2E requiere el stack local migrado, PostgreSQL, DEBUG y el helper habitual de sesión, sin otro trabajo editorial simultáneo. Exige borradores iniciales sin pendientes y conserva el historial, por lo que aumenta versiones y guarda publicaciones de prueba aunque reponga el contenido inicial. Usar una base de desarrollo.

## Riesgos y Fases 7–8

Antes de producción: ejecutar PostgreSQL y el E2E, probar las reversas con una copia de desarrollo y revisar escritorio/tableta/celular, claro/oscuro y teclado en navegador. No se declara verificada la apariencia por haber pasado compilación o render estático.

Las redirecciones pueden tardar hasta un minuto en renovarse en la capa de proxy; los clientes que ya almacenaron una respuesta permanente pueden conservarla más tiempo. Una indisponibilidad del endpoint hace que continúe el render normal, por lo que un camino retirado puede responder temporalmente 404. Se omite el conteo de visitas deliberadamente. La invalidez o desaparición posterior de un destino del catálogo vivo puede omitir su enlace del menú; no se cambiaron los ciclos de vida del catálogo.

Las excepciones de traducción se aplican por campo y texto exacto. No se añadió traducción automática, envío a revisión, campañas ni publicación programada. Fase 7 puede ampliar las herramientas editoriales dentro de los mismos permisos. Fase 8 debe sustituir las lecturas vivas por invalidación de tags al publicar y considerar el coste del historial y las políticas de retención sin romper referencias/restauraciones.

## Registro de cambios

No se pudo crear el commit: `git add` fue rechazado al crear `.git/index.lock` con `Operation not permitted`. Los cambios quedan sin stage ni commit. No se crearon scripts de commit ni se hizo push. Al registrar fuera de este sandbox, usar un mensaje en español, por ejemplo «CMS fase 6: páginas, direcciones, menús, SEO y traducciones», y el tráiler:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

`docs/capturas/` se conserva sin seguimiento e intacto.

## Ajustes tras revisión

Se leyó completo `.codex-review/fase6-pytest.txt`; se conserva el archivo. Esta ronda sigue sin commit ni push, sin dependencias nuevas y sin cambios en carrito, pagos o pedidos. `.git` tiene acceso de solo lectura en este sandbox; no se intentó crear un commit ni se prepararon scripts para ello.

- **Pendientes falsos:** revisión, historial y publicación idempotente usan la misma comparación por tipo de página. Proceso, FAQ y sus títulos solo participan para Personaliza. El adaptador de lectura recupera los títulos de las secciones de revisiones antiguas que no tienen esos campos en `source`. SEO ausente equivale a las opciones vacías. No se reescriben revisiones ni se publican borradores para eliminar los avisos.
- **Cuerpo legal:** `_body_enabled: false` no oculta Envíos ni ninguna otra página legal: `body_visible` es verdadero para todo tipo distinto de Personaliza. El indicador pertenece exclusivamente a Personaliza y ahora tampoco produce diferencias editoriales en otros tipos. Se conserva el comportamiento público existente.
- **Rutas propias:** Historia, Contacto y Personaliza admiten sus segmentos fijos por idioma; un slug vacío conserva la resolución de la ruta fija. Las reservas de otras rutas siguen vigentes.
- **Redirecciones:** se asigna `created_by` antes de `full_clean()`, manteniendo toda la validación del modelo, destinos, cadenas y versiones.
- **Consultas:** la vista previa de Inicio reúne SEO de borrador y fecha de publicación en una consulta mediante subconsulta. La biblioteca reúne las fuentes SEO de borrador y las restauraciones con `UNION ALL`, sin omitir referencias del historial. Los límites permanecen en **4** para Inicio en preview y **18** para biblioteca; requieren volver a medirse en PostgreSQL.

Se corrigieron pruebas cuyo supuesto había quedado desactualizado, conservando sus comprobaciones originales:

- Inicio vacío y contrato de Fase 1 incluyen la clave aditiva `seo`; siguen comparando exactamente el contenido y las claves esperadas.
- La comprobación de proporciones de Fase 5 usa números decimales para incluir `1.91:1`, conservando tolerancia, metadata, duplicados y rendiciones.
- La prueba del orden de secciones compara todas las secciones de contenido, excluyendo únicamente el panel SEO independiente; mantiene las comprobaciones de visibilidad y rendiciones por dispositivo.
- La prueba CSRF reutiliza la sesión con 2FA de la fixture y comprueba acceso GET antes de exigir 403 en el POST sin token. Antes recibía una redirección a 2FA y no alcanzaba la protección CSRF.

Se añadieron ocho casos puros que ejercen `pending_changes` con revisiones antiguas sin títulos de proceso/FAQ ni SEO: los ocho tipos dan cero y conservan los snapshots originales. También verifican que editar cuerpo sigue detectándose y que los títulos del proceso solo cuentan en Personaliza. Otros ocho casos con BD construyen revisiones antiguas a partir de páginas reales y verifican cero pendientes y cuerpo legal visible.

El E2E guarda además los slugs, caminos, indicador del cuerpo y SEO iniciales. Tras restaurar/publicar Envíos y ambos menús, repone las redirecciones completas, invalida su caché y verifica slugs/caminos, SEO, contenido de menús, cero pendientes y todos los campos de cada redirección. Las aserciones finales se ejecutan después de confirmar la restauración, para que un fallo de verificación no revierta la limpieza.

Validación de esta ronda:

- Frontend: lint y typecheck correctos; **72 pruebas correctas**. Playwright recopila el escenario de escritorio.
- Backend sin BD: **105 pruebas correctas**, 77 deseleccionadas, con `test_registry.py`, `test_phase4.py`, `test_phase5.py` y `test_phase6.py`, usando `-m 'not django_db'`.
- `manage.py check`: sin errores; avisos por credenciales Wompi ausentes en el entorno de comprobación. `makemigrations --check --dry-run`: sin cambios; avisa de que no puede comprobar el historial en PostgreSQL.
- PostgreSQL continúa inaccesible (`Operation not permitted` en `127.0.0.1:5432`); el intento de ejecutar los nuevos casos con BD se detuvo en preparación. Docker también deniega acceso al socket. No se declara ejecutada ni verde la suite PostgreSQL ni el E2E; quedan pendientes en el stack de desarrollo autorizado.
