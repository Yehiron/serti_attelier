# CMS — Fase 5: biblioteca de fotos

Implementación sobre `fase-9-produccion`, base `7820b10`, sin red, push ni dependencias nuevas. Se leyeron las fases 1–4. `docs/capturas/` se conserva intacto. Cropper.js 1.6.2 y su licencia MIT se consumen desde los archivos vendorizados recibidos.

## Decisiones y comportamiento

`MediaAsset` pertenece a **cms**, porque sus permisos, responsables, borradores, publicaciones y limpieza pertenecen al ciclo editorial. No se crea otra aplicación ni otra fuente de contenido para Personaliza. No se modifican `PieceImage`, `apps/catalog/images.py`, carrito, checkout, pagos ni pedidos. Las portadas de categoría, colección y piedra actuales se administran en catálogo y se leen como contenido vivo; no pasan por el editor CMS y conservan ese flujo.

Cada foto conserva un original completo, orientado y sin metadatos, codificado como WebP con las utilidades actuales. Los recortes nunca sobrescriben este archivo. La huella SHA-256 se calcula sobre los bytes subidos para detectar cargas iguales; el peso almacenado corresponde al original normalizado. Los nombres nuevos son UUID, nunca el nombre recibido. El archivo normalizado es público conforme a la decisión aprobada. Se conserva la eliminación de EXIF/GPS del pipeline común `validated_image`; no se guardan los bytes originales con sus metadatos.

El modelo incluye dimensiones, tipo, peso, huella, alt ES/EN, título opcional, etiquetas separadas por coma, responsable, fechas, archivo, archivo anterior, estado, archivado/activo, punto focal y recortes relativos. Se eligieron etiquetas simples, sin tablas ni jerarquía de carpetas.

Las referencias son `{asset: número, crop: "16:9" | "4:5" | "1:1", version: número}`. La versión adicional evita que editar una foto cambie silenciosamente borradores o publicaciones que ya la eligieron. Columnas históricas y diapositivas guardan `image_reference`; los tipos nuevos guardan la referencia dentro del slot de `props`. Los lectores históricos de URLs siguen funcionando. El contrato público conserva `src/srcset/width/height/alt`; solo añade `focal: {x,y}` cuando está disponible, sin exponer identificadores de biblioteca ni nombres originales.

`versions` conserva generaciones de renditions y textos alternativos. Celery prepara WebP de cada proporción a 240, 480, 960, 1600 y 2400 px, sin ampliar imágenes pequeñas y respetando las utilidades de anchos existentes. La cuadrícula usa la versión más pequeña. Los estados son preparando/lista/error, con dos reintentos automáticos y reintento desde el panel. Los trabajos obsoletos no reemplazan versiones nuevas. Si la cola no acepta el trabajo, la foto queda en error recuperable. No se añade otro formato porque el pipeline CMS actual utiliza WebP.

Los formularios y endpoints anteriores mantienen sus salidas síncronas y renditions habituales. Sus nuevas cargas también conservan el original completo en la biblioteca y agregan una generación que representa exactamente la salida anterior. Cambiar un alt desde estos formularios genera otra referencia, sin reescribir la anterior. El editor de tres paneles utiliza directamente el selector nuevo.

Las subidas admiten únicamente JPEG, PNG y WebP decodificados realmente con Pillow, hasta 25 MB y 40 megapíxeles. Extensión y MIME no determinan la aceptación. SVG, HEIC y otros formatos se rechazan con mensaje claro. Se validan coordenadas finitas 0–1, límites de la imagen y proporción del recorte. Las dimensiones recomendadas del slot generan un aviso y permiten continuar. Para seleccionar una foto son obligatorios alt ES y EN de la generación elegida.

## Interfaz y publicación

«Página web → Biblioteca de fotos» ofrece cuadrícula, búsqueda por alt/título/etiqueta, filtros en uso/sin usar/archivadas, páginas de 40 fotos, arrastre o selección múltiple, progreso por archivo y detalle lateral. El detalle permite editar ambos idiomas, marcar el punto de interés con clic o controles de teclado, ajustar los tres recortes mediante Cropper.js y botones, consultar usos, archivar/recuperar y eliminar con confirmación integrada. Usa CSS propio, foco visible, diálogo nativo con retorno del foco y estilos claro/oscuro adaptables a pantallas estrechas.

Las proporciones están en `ImageSlot.ratios` y se exportan al registro. «Elegir de la biblioteca» y «Subir nueva» abren el mismo diálogo desde cada slot y desde ambos carruseles de Portada. Allí se pueden ajustar los recortes antes de usar la foto. Una selección de sección existente envía `media-select` por la API del documento; las secciones nuevas incluyen la referencia al crearse. Ambos caminos conservan `edit_document`, `expected_version`, 409, servicios versionados, revisión, publicación y restauración de las fases anteriores. Las ediciones de la biblioteca tienen su propia versión y también rechazan conflictos con 409; no publican cambios por sí solas.

Next aplica `focal` como `object-position`, también al cambiar entre fotos de computador/celular en `<picture>`. Sin focal conserva el centrado anterior. No se cambia la composición de la tienda.

## Migraciones y reversa

1. `0019_heroslide_image_reference_and_more`: modelo, referencias de columnas/diapositivas y constraints inmediatos para focal. Incluye guardia antes de retirar el esquema si hay fotos nuevas o referencias en historial.
2. `0020_import_cms_media`: importa las imágenes CMS del borrador, servicios históricos, props y fotos que solo aparecen en snapshots históricos. **No mueve, reescribe ni borra archivos ni publicaciones**. Solo importa rutas `cms/`, nunca fotografías de piezas. La generación cero conserva literalmente el payload antiguo; los lectores y la comparación semántica reconocen esa adaptación sin falsos pendientes. Los hashes reales se calculan cuando el archivo local está disponible; de lo contrario quedan nulos, sin inventar una huella de contenido. Un identificador separado de importación asegura idempotencia.

La reversa de datos repone URLs de props y retira las referencias de columnas, conservando archivos y filas importadas. Se niega antes de alterar contenido si existen fotos nuevas o referencias en publicaciones/restauraciones: eliminarlas rompería el historial. La reversa de esquema también está protegida. Las pruebas de migraciones vuelven a `loader.graph.leaf_nodes()` y usan modelos históricos en estados intermedios. Se adaptó esa lectura en la prueba de Fase 3 sin debilitar la comparación de bytes ES/EN.

## Uso, eliminación y limpieza

«Dónde se usa» recorre el borrador completo, publicaciones vigentes, publicaciones históricas y `DraftRevision`. Reconoce referencias nuevas, archivos y URLs antiguos. No se elimina una foto referenciada, incluido el historial; archivar la oculta del selector pero conserva todos sus usos y permite restaurar publicaciones anteriores. Los bloqueos de fotos serializan selección y eliminación. Se conserva `select_for_update(of=("self",))`.

`manage.py cleanup_cms_media` y `--dry-run` **simulan por defecto**. `--execute` elimina cargas abandonadas de más de 24 horas, sin descripción/etiquetas, sin archivar y sin referencias; conserva las fotos descritas intencionalmente aunque no estén en una página. Los archivos solo se retiran después de 24 horas y si no pertenecen a activos conservados ni a ninguna fuente histórica. Cada retirada de registro/archivo se audita. El recorrido está limitado a `MEDIA_ROOT/cms`, comprueba rutas resueltas y no sigue enlaces simbólicos. No elimina fuera del almacenamiento CMS.

La tarea `apps.cms.tasks.cleanup_media` no está en el calendario predeterminado y tampoco borra al invocarse sin `CMS_MEDIA_WEEKLY_CLEANUP=True`. Para activarla, configurar explícitamente esa opción y una entrada semanal en el Celery Beat existente.

## Endpoints y seguridad

Todos los endpoints de biblioteca requieren staff activo con `cms.edit_content`, CSRF en escritura y `never_cache`. Contenido y Propietaria pueden usarlos; Operaciones y anónimos reciben 403. Se conserva el middleware del dashboard, incluido el segundo factor. Publicar y restaurar siguen exigiendo sus permisos separados.

| Ruta relativa a ADMIN_URL | Método | Función |
|---|---|---|
| `biblioteca/` | GET | Pantalla Unfold |
| `biblioteca/api/` | GET | Buscar/filtrar/paginar (`q`, `filter`, `page`) |
| `biblioteca/api/` | POST multipart | De 1 a 10 archivos `file`; resultado individual y duplicados reutilizables |
| `biblioteca/api/<id>/` | GET | Detalle, generaciones actuales y usos |
| `biblioteca/api/<id>/` | POST JSON | `save`, `retry`, `archive`, `delete`, con `expected_version` |
| `editor/documento/?document=home` | POST JSON | Acción `media-select`, `id`, `slot`, `reference`, `expected_version`; `slide` opcional para reemplazar una diapositiva |

Se reutiliza el throttling de DRF: 30 peticiones de subida por minuto y persona, además del máximo de 10 archivos por petición. Los errores públicos del panel no incluyen rutas del servidor ni excepciones del worker. La biblioteca hace un conjunto fijo de consultas para usos, sin consultas por miniatura; la prueba fija un presupuesto de 18 consultas para una página de 40 fotos.

## Archivos principales

- Modelo/ciclo de vida: `models.py`, `media.py`, `media_views.py`, `tasks.py`, migraciones 0019/0020 y `management/commands/cleanup_cms_media.py`.
- Integración editorial: `services.py`, `editor_services.py`, `visual_documents.py`, `selectors.py`, `section_adapters.py`, `section_validation.py`, `review_changes.py`, `registry.py`, serializer CMS y `config/urls.py`.
- Panel: navegación de `apps/core/dashboard.py`, plantilla `admin/cms/media.html`, integración en `editor.html`, `media-library.js/css`, `visual-editor.js` y Cropper vendorizado.
- Tienda/contrato: `cms-focal.ts`, componentes Media, RegistrySection y HeroCarousel, CSS responsive de focal, `types.ts`, contrato TS y JSON regenerados y test de contrato.
- Pruebas: `test_phase5.py`, ajuste de lectura histórica en `test_phase3.py`, `cms-focal.test.ts`, nuevo E2E `cms-phase5.spec.ts` y adaptación del carrusel de `cms-phase4.spec.ts`.

## Verificación

- Frontend: lint, typecheck y **60 pruebas correctas**, incluido render real de Imagen con texto con focal por dispositivo y contrato regenerado.
- Backend sin BD: **78 pruebas correctas**, incluidas las etiquetas españolas, rutas/permisos de anónimo, contrato de referencia, focal y recortes.
- `manage.py check`, plantillas, Ruff de Python modificado, sintaxis de ambos JS, `makemigrations --check --dry-run` y `git diff --check`: correctos. La comprobación de migraciones avisa de PostgreSQL inaccesible; no se aplicaron migraciones a una BD existente.
- Suite completa PostgreSQL: ver resultado final debajo. No se usó SQLite. Las credenciales de prueba son ficticias locales; `127.0.0.1:5432` devuelve `Operation not permitted`.
- Playwright recopila los escenarios de Fases 4/5, con escritorio ejecutable y móvil omitido expresamente. El flujo de Fase 5 sube un fixture local, edita ES/EN, recorta 4:5, mueve focal, elige en el carrusel celular, comprueba preview, revisa/publica y verifica la tienda sin draft. En `finally` restaura/publica el estado inicial y archiva la foto de prueba; conserva el historial inmutable. Requiere stack migrado, Celery y una publicación inicial sin borrador pendiente.
- **E2E e inspección visual pendientes:** Chromium aborta al arrancar en este sandbox. No se declara verificada la apariencia, el teclado real ni la integración del stack por haber pasado compilación o pruebas puras.

Las pruebas PostgreSQL preparadas cubren subida falsa/SVG/tamaño/píxeles, EXIF, duplicados, permisos, CSRF, alt requerido, versiones/409, recortes/renditions, reintentos, selección/publicación/restauración, usos históricos, rechazo de eliminación, limpieza/auditoría y migración idempotente con comparación de bytes públicos ES/EN.

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
npx playwright test tests/e2e/cms-phase5.spec.ts --project=desktop
```

## Riesgos y pendientes para Fase 6

Antes de producción deben ejecutarse PostgreSQL y Playwright y revisar 1440/768/390 px, claro/oscuro, teclado, arrastre/recortes y worker detenido. Las fotografías históricas cuyos originales ya estaban recortados conservan ese archivo: esta fase no puede recuperar píxeles anteriores. Los archivos históricos ausentes no se recrean ni se oculta su falta mediante hashes ficticios.

El almacenamiento de archivos no es transaccional; un rollback puede dejar archivos que recogerá la limpieza posterior. La consulta de usos construye un índice en memoria una vez por petición: si crece mucho el historial, Fase 6 puede persistir ese índice sin omitir snapshots históricos. Las generaciones de fotos descritas se conservan deliberadamente; no se implementa eliminación de generaciones antiguas ni políticas de retención que puedan romper restauraciones.

### Resultado de la suite completa

Última ejecución desde `backend`, con `pytest --ds=config.settings.test -q`: **191 correctas, 1095 errores de preparación, 6 avisos, ninguna prueba fallida**, 11,69 s. Los 1095 errores proceden de PostgreSQL inaccesible; no prueban ni refutan la integración. Registro local: `/private/tmp/cms5-backend-final.txt`. Las pruebas puras finales pasan; no se declara verde la suite PostgreSQL.

### Registro de cambios

No se pudo crear el commit: `git add` fue rechazado al crear `.git/index.lock` con `Operation not permitted`. Los cambios quedan sin stage ni commit. No se crearon scripts de commit ni se hizo push. Al registrar fuera del sandbox, utilizar un mensaje en español y el tráiler solicitado:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```


## Ajustes tras revisión

- **Slide vaciada:** `save_hero_slide` reconoce que se retiró el archivo de una carga existente y retira también su referencia automática antes de validar. Sigue rechazando «Agrega una imagen»; una slide elegida únicamente por referencia continúa siendo válida. No se debilitó `test_pipeline_and_clearing`.
- **Restauración y versiones congeladas:** la prueba ahora localiza por ID la sección que eligió la foto, en vez de suponer que ocupa la última posición del orden editorial (los datos iniciales contienen otras posiciones). Comprueba el payload completo restaurado contra la publicación y la referencia exacta de generación. Los lectores y el servicio de restauración conservan su comportamiento.
- **Consultas y coste de usos:** se reutilizan los listados de publicaciones y revisiones para identificar las vigentes, eliminando dos consultas redundantes. El límite sigue siendo **18**. `UsageIndex` recorre cada snapshot una vez por petición e indexa IDs, rutas y URLs/srcset; cada foto consulta el índice sin volver a recorrer todo el historial. Una prueba sin BD cubre referencias, archivos antiguos, srcset y separación entre URLs parecidas. No se afirma una nueva latencia ni un presupuesto medido sin ejecutar PostgreSQL.
- **Etiquetas españolas:** `MediaAsset.Meta` declara «foto de biblioteca» / «Fotos de biblioteca»; los campos ya tienen nombres españoles. Se añade **0021_media_spanish_labels**, solo de opciones del modelo, para no modificar 0019/0020 ya aplicadas. Ejecutar `python manage.py migrate` en desarrollo.
- **Migración aislada:** la prueba crea su propia página Personaliza si no existe tras un flush; utiliza los modelos históricos del estado correspondiente para la importación idempotente, conteos y lecturas. La primera transición de esquema también queda dentro del `try`; el `finally` restaura siempre `loader.graph.leaf_nodes()`, incluida 0021.
- **Carrusel celular:** se corrigió una regresión real en los nombres accesibles. El botón nuevo «Ajustar foto y recorte» desplazaba un índice compartido: «Eliminar foto 1» señalaba «Bajar», deshabilitado con una sola foto. Subir/Bajar/Eliminar reciben ahora su etiqueta directamente. El E2E espera la carga y el estado listo antes de rellenar los alt, verifica miniatura/vista previa y elimina por UI. Las peticiones de limpieza tienen timeout propio de **5 s**, obtienen CSRF de la cookie y la restauración inicial se ejecuta en un `finally` interior aunque falle la limpieza por API.
- **Detalle:** título interno → alt ES → número. «Dónde se usa» muestra Borrador y Publicado y resume el historial como «Y en N publicaciones anteriores»; el bloqueo de eliminación sigue contando todos los usos históricos.

Validación de esta ronda:

- Frontend: `npm run lint`, `npm run typecheck` y `npm test`: **60 correctas**.
- Backend sin BD: **11 correctas** de Fase 5, incluida la regresión del índice de usos; Ruff de los Python ajustados, `manage.py check`, sintaxis de ambos JS y `git diff --check`: correctos.
- `makemigrations --check --dry-run`: sin cambios pendientes. PostgreSQL sigue inaccesible desde este sandbox (`Operation not permitted`); no se ejecutaron aquí los cinco casos de integración ni se aplicó 0021.
- Playwright recopila los **4 escenarios de escritorio** de Fases 4/5. No se ejecutó el stack E2E en esta ronda. La revisión del usuario previa a estos ajustes confirmó biblioteca, Cropper, selector, E2E Fase 5 y bytes públicos ES/EN tras 0019/0020. Su suite PostgreSQL informó 1269 correctas y los 5 fallos descritos; falta repetirla con estos ajustes.
- Sin dependencias nuevas, sin cambios en carrito/pagos/pedidos/fotos de piezas. `.git` no es escribible desde este entorno; entrega sin stage, commit, scripts de commit ni push.
