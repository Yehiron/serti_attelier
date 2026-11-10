# CMS — Fase 3: registro tipado de secciones

## Alcance y resultado

Trabajo sobre `fase-9-produccion`, base `ac8fbe8`. Sin red, push ni dependencias nuevas. Se leyeron las entregas de las fases 1 y 2; el documento de auditoría CMS citado no está en el repositorio disponible. Se implementan los requisitos de esta solicitud sobre registro y compatibilidad. No se modifican carrito, catálogo comercial, checkout, Wompi ni pedidos. No se construyen el editor de tres paneles ni la biblioteca multimedia.

`apps/cms/registry.py` declara once tipos mediante dataclasses: metadatos, campos editoriales, traducciones, valores por defecto, límites, opciones con etiquetas, listas ordenables, slots y recomendaciones de imagen, reglas de composición, documentos y contrato público. Sus validadores rechazan tipos/versiones desconocidos, propiedades ajenas y destinos no admitidos. Los nuevos bloques se pueden guardar por servicio y renderizar públicamente; añadirlos desde la interfaz de la dueña corresponde a la Fase 4.

Los componentes históricos de la tienda conservan su composición. Los estilos añadidos solo afectan a los tres tipos nuevos. **La equivalencia visual en navegador y la integración PostgreSQL no quedaron verificadas en este entorno.**

## Modelo de instancias y compatibilidad

Se elige la opción (a): conservar `HomeSection` y añadir `schema_version` (1) y `props` (JSONB en PostgreSQL). Los ocho tipos históricos conservan sus columnas, archivos, FK y diapositivas. `props` se utiliza para `image_text`, `faq` y `process`; no se agrega una columna por campo nuevo. No hay traslado de contenido ni publicación automática.

`save_section` valida mediante el registro antes de procesar imágenes y guardar. Las propiedades de los tipos nuevos se normalizan con sus valores por defecto y se conservan como fuente editable en `draft_snapshot`. Se rechazan propiedades JSON ajenas. Las columnas irrelevantes tampoco admiten nuevos valores: si un registro histórico ya las tenía, puede conservarlas sin perder su fuente anterior. Los formularios ya no las presentan. El JSON no permite HTML ni CSS ejecutables: el texto normal se escapa al renderizar y las respuestas Markdown pasan por el mismo pipeline Markdown/nh3 de la Fase 1. Se conserva la fuente Markdown para editar/restaurar.

Las imágenes nuevas reciben un objeto tipado con `src`, `srcset`, `width`, `height` y `alt: {es, en}`. Se validan medidas positivas, direcciones relativas seguras o HTTPS y alt en ambos idiomas. La edición manual no admite `srcset` arbitrario: queda vacío; el contrato público sigue admitiendo los renditions generados del CMS histórico. Las diapositivas históricas mantienen su pipeline de carga y renditions. La integración de referencias y ciclo de vida con la biblioteca multimedia queda para la Fase 5; esta fase no implementa nuevas cargas de archivos para `props`.

Todos los guardados siguen dentro de `draft_mutation`, con responsable, permisos y `expected_version`. Publicar/restaurar mantiene el bloqueo de `ContentDocument`, comprobación de versión, auditoría, punteros publicados y `DraftRevision.restored_from`. No se cambian los permisos de Fase 2. Los bloqueos con relaciones anulables conservan `select_for_update(of=("self",))`. No se añaden constraints diferibles.

La comparación de publicación y pendientes adapta las fuentes antiguas con los defaults nuevos, evitando marcar cambios o crear otra publicación únicamente por la expansión del esquema. El resumen y la auditoría de `props` muestran etiquetas, idioma, orden y valores legibles; detectan también elementos retirados. No presentan el JSON a la dueña.

## Decisión para Personaliza

Se mantienen `Page.process_title`, `Page.faq_title`, `ProcessStep` y `FaqItem`, con sus inlines y snapshots. Son la única fuente del documento `page:personalize`. Crear otras instancias con una copia de esos datos produciría dos fuentes y exigiría una migración mayor sin beneficio para esta fase.

El registro describe los mismos subesquemas de pasos y preguntas. `save_page_item` reutiliza esos validadores; los máximos de nuevas filas y de los inlines se derivan del registro (8 pasos, 20 preguntas). La compatibilidad conserva el respaldo español de las traducciones de los modelos existentes y permite guardar borradores incompletos o restaurar cantidades históricas. El mínimo de dos pasos se exige a las **nuevas secciones JSON**; no se impone retroactivamente a los modelos de Fase 1. No se eliminan ni recortan filas antiguas.

La exportación incluye `page_bindings`: relación, modelo, encabezado y clave de lista. En Personaliza hay una composición fija de proceso y FAQ, sin ocultar, reordenar bloques ni duplicarlos; sus elementos internos siguen ordenables. En Inicio se permiten varias instancias de cada tipo, ocultarlas y reordenarlas. El renderer de Personaliza permanece intacto.

## Registro de tipos y campos

Todos tienen `schema_version=1`, nombre y descripción en español e icono Material Symbols. Los textos editoriales son bilingües. Los ocho tipos heredados conservan la posibilidad de textos vacíos y el respaldo español ya existentes; las nuevas secciones exigen ES/EN en los campos obligatorios. No se trunca contenido histórico durante la migración.

| Tipo | Nombre | Campos editoriales | Documento / almacenamiento |
|---|---|---|---|
| `hero` | Portada | Título, subtítulo, imagen de respaldo, CTA, diapositivas ordenadas por dispositivo con alt ES/EN | Inicio / columnas + HeroSlide |
| `statement` | Manifiesto | Título, texto | Inicio / columnas |
| `stone_panels` | Piedras | Título, subtítulo; piedras del catálogo vivo | Inicio / columnas |
| `collection_rail` | Colección | Título, subtítulo, colección obligatoria; hasta ocho piezas del catálogo vivo, como antes | Inicio / columnas + FK |
| `story` | Historia | Título, texto, imagen, CTA opcional | Inicio / columnas |
| `personalize` | Personalización | Título, texto, imagen, CTA opcional | Inicio / columnas |
| `banner` | Banner | Título, texto, imagen, CTA opcional | Inicio / columnas |
| `category_grid` | Categorías | Título y **subtítulo**; categorías del catálogo vivo | Inicio / columnas |
| `image_text` | Imagen con texto | Antetítulo opcional (120), título obligatorio (300), texto obligatorio (10000), imagen desktop obligatoria, imagen móvil opcional, CTA opcional, posición izquierda/derecha | Inicio / props |
| `faq` | Preguntas frecuentes | Título obligatorio (120), lista de 1–20 preguntas: pregunta obligatoria (160), respuesta Markdown obligatoria (1500) | Inicio / props; Personaliza / modelos existentes |
| `process` | Proceso de encargo | Título obligatorio (120), lista de 2–8 pasos: título obligatorio (60), descripción opcional (240) | Inicio / props; Personaliza / modelos existentes |

Los límites de texto se cuentan por idioma. Los campos de título históricos admiten 300 caracteres; subtítulo 2000 y texto 10000 en el validador editorial. La migración no valida/regraba los borradores ni modifica publicaciones existentes. Contenido histórico que exceda esos límites conserva su fuente; una edición posterior debe ajustarse al contrato al guardar.

CTA: texto ES/EN y destino discriminado. Se admiten catálogo, Personaliza, historia, contacto y referencias existentes a categoría, piedra, colección, pieza o página legal. Las referencias deben existir; una página no legal se rechaza. Los externos requieren URL HTTPS. No se aceptan rutas arbitrarias como CTA interno, protocolos relativos, JavaScript ni HTTP.

Slots: portada desktop/repuesto recomienda 16:9 y 2400 x 1350; portada móvil y fotos editoriales recomiendan 4:5 y 1080 x 1350 para móvil; imagen editorial desktop recomienda 1600 x 2000. Cada slot exige alt ES/EN cuando hay imagen. Las recomendaciones no recortan las diapositivas históricas ni cambian sus archivos.

## Exportación y contrato

- `GET /<ADMIN_URL>/section-registry/`, normalmente `/dashboard/section-registry/`: protegido por el admin (sesión/2FA habitual) y `cms.edit_content`. Solo GET; respuesta `private, no-store`.
- `python manage.py export_section_registry`: JSON UTF-8 con los once tipos, traducciones, slots, bindings y destinos CTA.
- `python manage.py export_section_registry --typescript`: genera el contrato público. Desde la raíz, con el entorno Django habitual:

```sh
backend/.venv/bin/python backend/manage.py export_section_registry --typescript > frontend/lib/api/sections.generated.ts
```

Se eligió un archivo generado porque mantener otra unión a mano crearía divergencia. `frontend/lib/api/types.ts` lo importa y reexporta. La unión discrimina cada tipo por separado y exige `schema_version: 1`. El test compara el archivo completo con la generación actual. `sectionKinds` también se genera y se usa para filtrar respuestas futuras en el servidor Next. La frontera de lectura tolera una respuesta antigua sin versión durante un despliegue mixto.

Los serializers OpenAPI de secciones se construyen a partir de `public_fields` del registro, usando tipos compartidos para imagen, CTA, piezas y listas. Los nombres históricos necesarios siguen disponibles. Se comprueba que las claves de serializers y registro coincidan. Las pruebas de respuesta real validan enums, discriminador, tipos, claves y obligatorios contra el esquema OpenAPI generado de ambos endpoints.

La forma de `cms/home` y `cms/pages/*` se conserva. La adición es `schema_version` en cada sección del Inicio y dentro de los bloques `process`/`faq` ya existentes en páginas; no se añade un segundo arreglo de secciones en Personaliza.

## Lectores y migraciones

`section_adapters.py` copia antes de adaptar. Añade la versión implícita 1 a snapshots antiguos sin reescribirlos. Conserva el formato público de diapositivas emparejadas y separadas, el hero sin `slides`, el subtítulo de categorías y los snapshots de páginas anteriores a proceso/FAQ. No inventa hijos que una revisión antigua no tenía: el frontend conserva su respaldo anterior. Restaurar mantiene la compatibilidad histórica de fuentes emparejadas.

Un tipo o versión de Inicio desconocidos se omiten con un aviso en el logger del backend. Next aplica la misma defensa antes de renderizar y tiene además un caso desconocido en el dispatcher: devuelve `null` y escribe `console.warn` de servidor. Guardar o restaurar fuentes de tipos/versiones desconocidos se rechaza; una restauración inválida no llega a borrar el borrador.

1. `0017_homesection_props_homesection_schema_version_and_more`: expansión con defaults deterministas `{}` y `1`, y las tres opciones nuevas. No mueve ni publica contenido. La primera operación de su reversa comprueba que no haya props, tipos o versiones nuevos que se perderían. Si los hay, lanza `IrreversibleError` antes de retirar columnas y pide exportar/adaptar ese contenido.
2. `0018_registry_defaults`: normalización idempotente mediante modelos históricos y alias de conexión. Los defaults de 0017 ya cubren la base existente; la normalización de nulos resulta normalmente vacía. La reversa de datos es deliberadamente no destructiva. No toca `HomePublication`, `PageRevision`, punteros o versiones editoriales.

Los fixtures se reconstruyen de textos y formas de las migraciones, sin información personal. Su procedencia y limitación figuran en `backend/apps/cms/tests/fixtures/README.md`. **No fue posible obtener un volcado real de desarrollo.** La prueba PostgreSQL compara literalmente los bytes de ambos endpoints ES/EN antes/después de expandir y normalizar el esquema; comprueba además la identidad del contenido congelado excluyendo solo `schema_version`, la adición pedida. Repite la normalización y comprueba reversa y fuentes. Vuelve en `finally` a `loader.graph.leaf_nodes()`. También se ajustó la prueba histórica de split de diapositivas para acabar la expansión antes de usar lectores runtime con las columnas nuevas.

## Archivos

- Registro, adaptación y validación: `backend/apps/cms/{registry,section_adapters,section_validation}.py`.
- Integración: `models.py`, `services.py`, `selectors.py`, `publishing.py`, `history.py`, `forms.py`, `admin.py`, `editor.py` y `backend/templates/admin/cms/editor.html`. Unfold deriva los campos por tipo; el editor actual puede mostrar los nuevos bloques y conserva sus acciones versionadas.
- Exportación: `registry_view.py`, `management/commands/export_section_registry.py`, `backend/config/urls.py`.
- OpenAPI: `backend/apps/cms/api/serializers.py`.
- Migraciones 0017 y 0018; tests `test_registry.py`, `test_phase3.py`, fixtures; ajustes de expectativas de los once tipos en `test_cms.py` y del lector runtime en `test_slide_migration.py`.
- Frontend: `lib/api/{types,sections.generated}.ts`, `lib/section-compat.ts`, `components/{home-sections.tsx,registry-section.ts}`, `app/[locale]/page.tsx`, estilos acotados a `.cms-*` en `globals.css`, `lib/sections.test.ts` y `tests/e2e/cms-phase3.spec.ts`.

Los nuevos renderers conservan las tipografías, paleta y ritmo editorial de la marca. Imagen con texto usa `<picture>` y composición lateral que se apila en móvil. FAQ usa `<details>/<summary>` nativos, foco visible y controles táctiles; proceso usa lista ordenada y cuadrícula adaptable. No añaden JavaScript de interacción ni animaciones; conservan el soporte de movimiento reducido de los estilos existentes.

## Pruebas y resultados

| Comprobación | Resultado |
|---|---|
| Registro puro, validación de modelos sin BD, renderer backend y OpenAPI, contrato TS, Markdown, CTA, alt, versiones, propiedades ajenas, auditoría bilingüe | **54 pruebas correctas** (`test_registry.py`) |
| Registro + etiquetas españolas | **56 correctas** en la última ejecución enfocada |
| `manage.py check --settings=config.settings.test` | Correcto |
| `makemigrations --check --dry-run --settings=config.settings.test` | Sin cambios pendientes; aviso al consultar historial por PostgreSQL bloqueado |
| Generación `manage.py spectacular` | Correcta, sin errores de esquema |
| Ruff del CMS y URLs | Correcto |
| `npm run lint`, `npm run typecheck` | Correctos |
| `npm test` | **54 correctas**, incluye los tres renderers ES/EN y tipos/versiones futuros |
| Suite completa PostgreSQL solicitada | **168 pasadas, 1063 errores de preparación, 6 avisos, sin pruebas fallidas**, 113,50 s; registro en `/private/tmp/cms3-backend-final.txt` |
| Playwright | Listados los dos proyectos, escritorio y celular; preparado, sin ejecutar contra stack |
| Inspección visual local | Bloqueada: Next no puede escuchar `127.0.0.1:3100` (`listen EPERM`) |

La suite completa se lanzó con `pytest --ds=config.settings.test -q` y `PYTEST_ADDOPTS=--tb=short` para abreviar los errores repetidos. Usa PostgreSQL con credenciales locales ficticias de prueba y nunca SQLite. Los 1063 errores proceden de la preparación de BD: localhost:5432 devuelve `Operation not permitted`. No prueban ni refutan los casos de integración. Después de esa ejecución se completaron los ajustes de auditoría y se repitió la suite enfocada de 56 pruebas. No se aplicaron migraciones a una base existente.

Las pruebas PostgreSQL preparadas cubren guardado de los once tipos, versiones/permisos, publicación/restauración e idempotencia ES/EN de los tres nuevos, procedencia de restauración, FK/CTA legales, exportación protegida, Unfold, payload real/OpenAPI, versiones y tipos desconocidos, fixtures antiguos, comparación de bytes y reversas. Deben ejecutarse localmente antes de producción.

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
npx playwright test tests/e2e/cms-phase3.spec.ts
```

El E2E usa el stack Docker de desarrollo habitual y el helper `e2e_admin_session`. Exige una publicación inicial de Inicio sin borrador pendiente. Crea por `save_section` una Imagen con texto, publica mediante el servicio versionado, comprueba textos y CTA ES/EN, foto desktop/móvil, carga real, ausencia de desbordamiento y guarda capturas. En `finally` restaura la publicación inicial y la vuelve a publicar; las publicaciones históricas inmutables permanecen. Ejecutar solo en DEBUG, sin otro trabajo editorial simultáneo. No se limpia el historial de publicaciones.

## Pendientes y límites

Antes de producción: correr PostgreSQL y E2E; revisar capturas en escritorio/celular y Unfold claro/oscuro; añadir fixtures anonimizados de publicaciones reales. No se declara la tienda visualmente verificada ni la suite backend verde.

Fase 4 debe consumir el registro y `page_bindings`, conservar `expected_version` y permisos, y sustituir el formulario técnico de props por controles de contenido. No debe crear otra copia de pasos/FAQ de Personaliza. Las reglas de composición por documento y la detección de tipos futuros ya están disponibles. Fase 5 debe resolver referencias, renditions y ciclo de vida de los archivos de las imágenes nuevas sin cambiar el contrato público ni introducir HTML/CSS libres.

No hay commit: `git add` fue rechazado al crear `.git/index.lock` con `Operation not permitted`. No se crearon scripts de commit ni se hizo push. Para registrar fuera del sandbox, usar un mensaje en español y el tráiler solicitado:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

`docs/capturas/` ya estaba sin seguimiento al comenzar y no se modificó.

## Correcciones tras la ejecución PostgreSQL de Claude (2026-11-09)

Se leyó completa `fase3-fallos.txt`: el resumen recibido indica 1216 correctas y
4 fallidas; el detalle de la repetición enfocada contiene **3 fallidas y 1 correcta**.
La migración de preservación de bytes pasa en ese detalle. No se cambió ni debilitó
esa prueba: no contiene acceso al frontend y sigue comprobando bytes, idempotencia
y reversa segura independientemente de que el frontend esté presente.

1. **Auditoría de fotos:** `editorial_values` fusionaba etiquetas de `props` con las
   columnas históricas. El slot vacío del registro sobrescribía `Imagen: Foto cargada`
   con `Imagen: Sin foto`, ocultando el segundo reemplazo. Ahora las etiquetas de props
   que colisionan se guardan con prefijo `Contenido · `; ambos valores se conservan y
   la detección de reemplazo vuelve a producir `Foto anterior → Foto reemplazada`.
   Archivos: `backend/apps/cms/services.py`, `tests/test_phase1.py` (reemplazos sucesivos
   en story/personalize/banner), `tests/test_registry.py` (regresión pura para hero,
   story, personalize, banner e image_text). Se mantienen también las pruebas de slides.
2. **Publicación legada:** la expectativa en `test_client_changes.py` excluye únicamente
   `schema_version` de las secciones públicas. Es la adición aprobada del adaptador;
   el snapshot persistido sigue comparándose íntegro y todos los demás campos públicos
   se comparan sin cambios. No se modifica el comportamiento de publicación.
3. **Contrato en backend aislado:** el ancla backend de `infra/docker-compose.dev.yml`
   monta `../frontend/lib/api:/frontend/lib/api:ro`. `test_registry.py` comprueba la
   presencia de TS, JSON y types; si faltan, omite con motivo explícito, o falla con
   ese mensaje cuando `REQUIRE_FRONTEND_CONTRACT=1`. Ambas ramas tienen prueba pura.
   El test compara además el JSON versionado con `export_registry()`; un archivo
   presente pero desactualizado siempre falla. No se omiten pruebas de migración.
4. **Contrato en frontend:** `frontend/lib/section-contract.test.ts`, incluido en
   `npm test`, reconstruye el contrato completo (campos, tipos, orden y kinds) desde
   `frontend/lib/api/section-registry.json` y exige igualdad exacta con el TS generado.
   También exige la reexportación de Section en types.ts. Así un CI sin backend puede
   comprobar el par JSON/TS. Para detectar cambios del registro Python se ejecuta el
   gate backend con el montaje y `REQUIRE_FRONTEND_CONTRACT=1`; frontend solo no puede
   detectar que ambos archivos exportados hayan quedado obsoletos respecto de Python.

Regeneración desde la raíz (entorno Django configurado):

```sh
cd backend
python manage.py export_section_registry > ../frontend/lib/api/section-registry.json
python manage.py export_section_registry --typescript > ../frontend/lib/api/sections.generated.ts
```

Validación local sin descargas: **61 pruebas de registro correctas**, **55 pruebas
frontend correctas**, Ruff enfocado, `npm run typecheck`, `npm run lint` y
`git diff --check` correctos. Se intentaron las pruebas PostgreSQL enfocadas: los cinco
casos (incluye las tres variantes de fotos) quedaron en error de preparación por
`127.0.0.1:5432: Operation not permitted`; salida en
`/private/tmp/cms3-correcciones-postgres.txt`. Docker también rechaza acceso al socket.
No se declara verificada la integración PostgreSQL tras esta corrección. No hubo
acceso a servicios externos ni push.

Se intentó registrar la entrega con `git add backend frontend
infra/docker-compose.dev.yml docs/cms-fase-3.md`: Git rechazó crear `.git/index.lock`
con `Operation not permitted`. Los cambios permanecen en el árbol, sin commit,
sin scripts de commit y sin push. `docs/capturas/` permanece intacto.
