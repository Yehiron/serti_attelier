# CMS — Fase 4: editor con vista previa de la tienda

Trabajo sobre `fase-9-produccion`, base `073b760`. Sin red, sin push, sin nuevas dependencias ni migraciones. No se modifican carrito, catálogo comercial, checkout, Wompi ni pedidos. `docs/capturas/` ya estaba sin seguimiento y se conserva intacto.

## Arquitectura y decisiones

La URL existente `/<ADMIN_URL>/editor/` abre un editor de tres paneles: estructura, tienda real en iframe y propiedades. El selector incluye Inicio y todas las páginas existentes. Los campos y opciones de composición proceden del registro Python. Las páginas conservan sus campos propios; Personaliza añade los bindings de proceso y preguntas, sin otra colección JSON de esos contenidos. Las otras páginas mantienen su composición fija: no se inventan tipos de sección que el registro no permite.

`editor_api.py` es la frontera HTTP; `visual_documents.py` adapta valores editoriales a las columnas históricas, props o modelos de página. Las mutaciones adquieren `edit_document` **antes de leer el contenido**, comprueban `expected_version` y llaman a los servicios actuales. Los servicios anidados comparten la transacción y el incremento: cada petición válida sube una sola versión. Reordenar y ocultar reutilizan `editor_services`; duplicar guarda por `save_section` y copia las diapositivas mediante `save_hero_slide`; eliminar registra un evento dentro de la misma transacción. Las validaciones fallidas revierten la escritura y el incremento.

Los bindings conservan `Page.process_title`, `Page.faq_title`, `ProcessStep` y `FaqItem` como única fuente. Se actualizan las filas por posición y se agregan o retiran únicamente las necesarias. Se conserva la tolerancia histórica a traducciones incompletas y cantidades anteriores; los límites para nuevas filas siguen en `save_page_item`. No se crean `HomeSection` para Personaliza. No se cambian publicación, restauración, adaptadores ni snapshots inmutables.

El editor usa JavaScript propio, sin bibliotecas nuevas. La cola de guardados es serial y toma la versión devuelta por la petición anterior. El debounce es de 800 ms; también hay guardado explícito. Cada envío captura una copia de sus valores; una respuesta de guardado de texto no reemplaza los textos que la persona haya seguido escribiendo. Una nueva sección permanece deshabilitada durante su creación para evitar creaciones dobles. Los fallos conservan los valores locales, ofrecen reintento y mantienen el aviso al salir. Un 409 bloquea la cola, muestra el conflicto y permite recargar voluntariamente o copiar los textos con etiquetas legibles ES/EN. Nunca se reintenta un conflicto con la versión nueva sin revisión humana.

La barra inferior usa el conteo de `pending_changes`, no el número de pulsaciones. «Descartar cambios» exige `restore_content` y recupera el puntero publicado por los servicios de restauración existentes: conserva la publicación, crea `DraftRevision`, aumenta la versión y registra auditoría. No se añade otra restauración paralela. Contenido puede editar y ver la vista previa; no obtiene el enlace de publicación ni puede descartar/restaurar. Operaciones no tiene acceso. La API responde 403 al anónimo; se conserva el middleware de segundo factor del dashboard.

## Interfaz

- Lista con nombre e icono del registro, título, visibilidad y estados locales de cambio/error. Arrastre, botones subir/bajar y anuncios `aria-live`.
- Mostrar/ocultar, duplicar y eliminar; eliminación y descarte tienen confirmación integrada. La creación presenta los tipos de Inicio permitidos, incluidos Imagen con texto, Preguntas frecuentes y Proceso de encargo.
- Propiedades ES/EN: textos con contador, Markdown con ayuda, destinos CTA tipados, selectores de catálogo, opciones, booleanos, listas con mínimos/máximos y controles de orden, fotos y texto alternativo bilingüe. Los errores del backend se asocian con su campo. No hay editor de JSON ni campos de esquema o identificadores visibles.
- Vista previa real de Next en Draft Mode. Escritorio 1280, Tableta 820 y Celular 390, escalados al espacio disponible; idioma y recarga independientes. Cada guardado vuelve a entrar por el enlace firmado para renovar la autorización y refrescar la tienda sin recargar el editor.
- Por debajo de 1100 px, pestañas muestran estructura, propiedades o vista previa. Los textos siguen siendo editables sin mantener la vista previa visible. Estilos propios para claro/oscuro, foco, estados deshabilitados y movimiento reducido. La dirección visual sigue Unfold: bordes discretos, paneles compactos y acento vino, con transiciones de 120 ms.
- Historial y revisión comparten el CSS. Los resúmenes de columnas y props muestran campos ES/EN y valores anteriores/nuevos abreviados. Se conserva la publicación de la versión revisada, idempotencia, nota y permisos. Ambas pantallas enlazan al editor con su documento y vista previa.

### Fotos, sin biblioteca multimedia

El formulario reutiliza **`PhotoInput` / `photo_input.html`** mediante una plantilla clonable. Las portadas llaman a `editor_services.upload_hero_photos`; el panel de propiedades permite administrar ambos carruseles y sus textos alternativos (véase «Ajustes tras revisión»). Las fotos históricas usan `replace_section_image`, que ahora acepta alt ES/EN explícito sin romper a sus llamadores anteriores. Los nuevos slots llaman a `upload_editor_image`, que reutiliza `services.process_image`: validación, eliminación de metadatos, WebP y renditions del pipeline existente. No se aceptan rutas de archivo escritas a mano en la interfaz.

Una foto para una sección aún no creada se carga con versión y auditoría y devuelve la referencia tipada, que se guarda al completar la sección. Esto permite crear Imagen con texto sin exigir antes una sección inválida. No hay modelo, buscador ni selector de biblioteca. Como en los flujos actuales, los archivos almacenados no son transaccionales: una carga abandonada o un error posterior puede dejar archivos sin referencia. Su limpieza y ciclo de vida corresponden a Fase 5. Los slots nuevos mantienen `srcset` vacío en el contenido editable, conforme al validador actual.

## Protocolo de selección

Next comprueba `draftMode().isEnabled` en el servidor antes de añadir atributos o montar `CmsDraftSelection`. Inicio identifica cada sección con `data-cms-section`; las páginas identifican cabecera/contenido como `page`, y Personaliza sus bindings como `process` y `faq`. Las marcas incluyen foco por teclado únicamente en draft. Fuera de draft no se añaden estas marcas ni se monta el puente.

El iframe acepta solo mensajes de `window.parent`, con `event.origin === location.origin`, tipo enumerado `cms:select` e id de texto acotado. La búsqueda compara `dataset` con el id, sin interpolarlo en selectores. No evalúa código, HTML, rutas ni funciones recibidas. El panel comprueba el mismo origen y que `event.source` sea su iframe. Solo acepta `cms:ready`, `cms:selected` con una sección local conocida y `cms:scroll` con coordenada finita. El clic o Enter/Espacio selecciona; el mensaje de vuelta resalta la sección. `reveal` permite mostrarla al seleccionarla desde la lista; las recargas restauran el desplazamiento comunicado mientras sea posible.

## Cabeceras y cookies

Se conserva `X_FRAME_OPTIONS = DENY` de Django. El editor y sus endpoints no necesitan ser enmarcados. Next niega el enmarcado público y, para respuestas con cookie de Draft Mode, retira X-Frame-Options y establece `frame-ancestors 'self'`, junto con las protecciones existentes de caché, robots y referrer.

Los dos Caddyfile restringen `@cms_draft` a cookie `__prerender_bypass=` y rutas localizadas `/es`, `/en`, `/es/*`, `/en/*`. Solo esas respuestas eliminan X-Frame-Options y reciben CSP con `frame-ancestors 'self'`. El matcher inverso `@cms_public` mantiene `'none'` para las demás respuestas públicas; API y dashboard conservan sus restricciones. Los ajustes diferidos evitan que las cabeceras de Next reemplacen las protecciones de Caddy. Una cookie draft no relaja las respuestas del admin o la API.

La entrada `/preview` sigue verificando el token y el permiso actual en el backend. Tras habilitar Draft Mode, establece la cookie bypass y `serti_preview` con HttpOnly, Path `/`, SameSite Lax y Secure según HTTPS. El iframe comparte origen con el panel; no depende de cookies de terceros. El cambio de Secure permite también el stack HTTP local en `localhost:8090`.

**Caddy no está instalado en este entorno. No se declara validada su configuración.** Antes de desplegar, ejecutar con las variables reales:

```sh
SITE_DOMAIN=tienda.example ACME_EMAIL=equipo@example.com DJANGO_ADMIN_URL=dashboard/ caddy validate --config infra/Caddyfile --adapter caddyfile
```

Comprobar además en DevTools o con curl: público sin cookie → DENY/`'none'`; documento localizado con cookie draft → sin XFO y `'self'`; admin y API con esa misma cookie → DENY/`'none'`. Verificar que las respuestas solo contengan una CSP efectiva y que el iframe cargue en HTTPS.

## Endpoints

Todos se encuentran bajo `/<ADMIN_URL>/editor/` y usan sesión, CSRF y permisos editoriales. Las URLs anteriores de acciones permanecen por compatibilidad.

| Ruta | Método | Función |
|---|---|---|
| `documento/?document=home` o `page:<kind>` | GET | Documento, secciones/valores, registro aplicable, documentos, opciones de destinos, versión, pendientes y enlaces de preview |
| `documento/?document=…` | POST JSON | `action`: `create`, `update`, `visibility`, `reorder`, `duplicate`, `delete` o `discard` |
| `foto/` | POST multipart | Foto histórica, portada por dispositivo o slot tipado; también admite slot de una sección nueva |

Todos los POST requieren `expected_version`. Los JSON usan `id` para una sección, `values` para contenido, `kind` al crear, `visible` booleano al ocultar/mostrar o `ids` al ordenar. Respuesta válida: estado actualizado y nueva `version`; crear/duplicar devuelve `selected`. Conflicto: 409 y `conflict: true`; validación: 400 y errores `fields`; falta de permiso: 403. Leer y cargar fotos mantienen respuestas sin caché.

## Archivos principales

- Backend: `apps/cms/editor_api.py`, `visual_documents.py`, `editor_services.py`, `section_validation.py`, `history.py`, `publishing.py` y `config/urls.py`.
- Panel: `backend/templates/admin/cms/editor.html`, `apps/cms/static/cms/visual-editor.{js,css}` y plantillas de revisión/historial.
- Next: `components/cms-draft-selection.tsx`, `lib/cms-selection.ts`, páginas de Inicio/editoriales y `personalize-content.ts`, `lib/cms-preview.ts`, entrada `/preview` y ajuste de los selectores de portada en `app/globals.css` para conservar su cabecera dentro de las marcas de draft.
- Infraestructura: `infra/Caddyfile`, `infra/Caddyfile.dev`.
- Pruebas: `backend/apps/cms/tests/test_phase4.py`, adaptación de `test_visual_editor.py` a la vista previa real, `frontend/lib/cms-selection.test.ts`, `frontend/tests/e2e/cms-phase4.spec.ts`.

## Pruebas y resultados

| Comprobación | Resultado |
|---|---|
| Frontend `npm run typecheck`, `npm run lint` | Correctas |
| Frontend `npm test` | **58 correctas** |
| Registro backend + cabeceras/configuración sin BD | **63 correctas** |
| `manage.py check --settings=config.settings.test` | Correcto |
| Plantillas editor/revisión/historial y render de `PhotoInput` | Correctos |
| `makemigrations --check --dry-run` | Sin cambios; aviso de conexión PostgreSQL bloqueada |
| Ruff de Python modificado, sintaxis del JS y `git diff --check` | Correctos |
| Suite completa `cd backend && pytest --ds=config.settings.test -q` | **177 correctas, 1072 errores de preparación, 6 avisos**, 124,20 s; registro `/private/tmp/cms4-backend.txt` |
| Playwright Fase 4 | Escenarios listados en ambos proyectos; escritorio ejecutable, móvil omitido expresamente |
| Inspección visual | Pendiente: Chromium aborta al arrancar por `bootstrap_check_in … Permission denied (1100)` |
| `caddy validate` | Pendiente: no existe binario local y no se usa red |

La suite completa usó PostgreSQL, sin sustituirlo por SQLite, con variables locales ficticias de prueba. `127.0.0.1:5432` devuelve **Operation not permitted**. Sus errores no validan ni refutan las pruebas de integración. Las pruebas nuevas cubren roles/anónimo, CSRF, versión obsoleta y omitida, errores por campo, tipos rechazados, operaciones estructurales auditadas, bindings sin copia, descarte con `DraftRevision` y negación de enmarcado del admin aunque exista una cookie draft. Se recopilan para ejecutarlas localmente.

Las pruebas antiguas del editor conservan sus verificaciones de servicios/cargas y ahora consultan el documento JSON y el renderer real en lugar de buscar una maqueta de la tienda en el HTML del admin.

```sh
cd backend
pytest --ds=config.settings.test -q
```

```sh
cd frontend
npm run lint
npm run typecheck
npm test
npx playwright test tests/e2e/cms-phase4.spec.ts
```

El E2E exige el stack de desarrollo migrado, PostgreSQL, Docker y una publicación de Inicio sin borrador pendiente. Usa `e2e_admin_session --role Propietario|Contenido` con cookie `sessionid` en `http://localhost:8090`. Cubre selección desde lista/iframe, texto/autosave/preview, ancho Celular, conflicto por segunda petición, copia de textos, Contenido sin publicar, revisión/publicación y comprobación en un contexto público sin draft. En `finally` restaura y vuelve a publicar la publicación inicial; conserva el historial inmutable. Solo debe ejecutarse en desarrollo y sin trabajo editorial simultáneo. El segundo escenario verifica los cajones a 820 px. Prepara capturas del editor y conflicto en `test-results`; todavía no se han generado.

## Pendientes de verificación y Fase 5

Antes de producción: ejecutar PostgreSQL y Playwright; validar Caddy; comprobar cookies/iframe y cabeceras reales en HTTPS; revisar escritorio, 820 y 390 px, teclado, claro/oscuro, carga de imágenes y errores de consola. La compilación y las pruebas puras no sustituyen estas comprobaciones. No se declara visualmente verificado el editor ni verde la suite de integración.

Para Fase 5: referencias estables y ciclo de vida de imágenes, limpieza de cargas abandonadas, renditions de slots nuevos y biblioteca multimedia. Los carruseles de portada ya se administran desde el panel de propiedades; el formulario existente conserva su compatibilidad. No se incorporan campañas programadas.

No hay commit: `git add backend/apps/cms/editor_api.py` fue rechazado al crear `.git/index.lock` con **Operation not permitted**. No se crearon scripts de commit. Para registrar fuera del sandbox, usar un mensaje en español, por ejemplo `CMS fase 4: editor de tres paneles y vista previa segura`, con el tráiler solicitado:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```


## Ajustes tras revisión

Ronda sobre `fase-9-produccion`, base `4eec13c`. Sin push, dependencias nuevas ni migraciones; sin cambios en carrito, pagos o pedidos. `docs/capturas/` se conserva intacto.

### Carrusel de portada

El panel de propiedades muestra «Fotos para computador» y «Fotos para celular», con recomendaciones de los slots del registro, carga múltiple, miniaturas tomadas exclusivamente de renditions, orden mediante arrastre o botones, anuncios `aria-live`, textos alternativos ES/EN y eliminación con confirmación integrada. La imagen individual se etiqueta «Foto de respaldo (si no hay carrusel)». La administración no depende del enlace al formulario anterior.

La API del documento incorpora `hero-reorder`, `hero-alt` y `hero-delete`, con sección, dispositivo e identificador de foto cuando corresponde. Reutiliza `reorder_hero_slides`, `save_hero_slide` y `delete_hero_slide`; la carga múltiple conserva `upload_hero_photos`. Todas las acciones comparten la comprobación de `expected_version`, permisos, auditoría y una sola subida de versión por petición. Se rechazan fotos de otra sección/dispositivo y órdenes inválidos. Cada guardado refresca la autorización y la vista previa. Los alt usan la cola de autosave y se incluyen al copiar textos ante un conflicto.

### Cambios reales y revisión

El editor envía únicamente las propiedades distintas de su última lectura/guardado y excluye `slides` del guardado de texto. Los servicios conservan las traducciones vacías históricas al recibir su equivalente vacío; las actualizaciones parciales de páginas y bindings mantienen los demás campos y filas. No se reescriben publicaciones ni se cambia el contrato JSON público.

`review_changes.py` compara valores editoriales tratando `null`, cadena vacía y ausencia como equivalentes. Revisión, historial y `pending_changes` comparten las filas semánticas: una edición de título produce una fila, sin repetir las traducciones derivadas, el HTML renderizado ni los textos vacíos. Las pruebas de Manifiesto y Piedras comprueban exactamente un cambio y la conservación de las otras claves del payload público.

Revisión e historial usan CSS propio de `visual-editor.css`, con superficies claras/oscuras, acento vino, enlaces secundarios visibles al editor y a la vista previa, grupos con nombre e icono del registro, columnas Antes/Después y textos largos desplegables mediante «Ver más». La revisión conserva nota, versión revisada y publicación idempotente; el botón primario explica su estado deshabilitado. El historial presenta tarjetas con fecha de Bogotá, autor, nota, cambios y restauración con confirmación integrada, limitada a `restore_content`. Las URLs y servicios de publicación/restauración se conservan.

### Verificación de esta ronda

- Frontend: `npm run lint`, `npm run typecheck` y `npm test` correctos (**58 pruebas**).
- Backend sin base de datos: `pytest -q backend/apps/cms/tests -m 'not django_db'` correcto (**66 pruebas; 218 excluidas por requerir BD**), con configuración PostgreSQL y variables ficticias locales. No se usa SQLite.
- Ruff de los archivos Python modificados, sintaxis del JavaScript, `manage.py check --settings=config.settings.test` y `git diff --check`: correctos. Revisión e historial renderizados con Django sin BD.
- `test_phase4.py`: **19 casos recopilados**. Se añaden permisos de Propietaria/Contenido/Operaciones, carga múltiple, renditions, versión omitida/obsoleta, orden, alt, eliminación, rechazo por dispositivo, auditoría, rollback de validación y conservación de campos vacíos. Las pruebas con BD quedan para ejecución con PostgreSQL por la persona responsable, según el encargo.
- E2E extendido con una imagen PNG determinista de prueba: Contenido crea una portada temporal, sube al carrusel de celular, comprueba la imagen WebP cargada dentro de la vista previa en Celular y la elimina. La limpieza de respaldo elimina fotos mediante la API versionada y restaura/publica la publicación inicial en `finally`. Playwright recopila los **6 casos** (3 de escritorio; sus equivalentes móviles se omiten explícitamente).
- **E2E e inspección visual pendientes**: el stack `localhost:8090` no responde en este entorno. También se intentó inspeccionar las plantillas renderizadas en 1440/768/390 y claro/oscuro, pero Chromium aborta al arrancar por `bootstrap_check_in … Permission denied (1100)`. El render de plantillas y las pruebas puras no prueban la apariencia en navegador ni la integración con PostgreSQL.

Para verificar fuera del sandbox, con PostgreSQL y el stack de desarrollo:

```sh
cd backend
pytest apps/cms/tests/test_phase4.py apps/cms/tests/test_phase2.py apps/cms/tests/test_visual_editor.py --ds=config.settings.test -q
```

```sh
cd frontend
npx playwright test tests/e2e/cms-phase4.spec.ts --project=desktop
```

Registro de esta ronda: no se pudo crear el commit. `git add` fue rechazado al crear `.git/index.lock` con `Operation not permitted`. Los cambios quedan sin stage; no se crearon scripts de commit ni se hizo push.
