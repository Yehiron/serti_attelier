# CMS — Fase 2: integridad editorial

## Entrega y alcance

Trabajo sobre `fase-9-produccion`, base `54cbb9c`. Sin red, sin push y sin dependencias nuevas. Se evoluciona el CMS existente. No se modifican la API pública de la tienda, carrito, catálogo comercial, checkout, Wompi ni pedidos. El cambio del comando E2E, ubicado históricamente en payments, solo permite elegir el rol de una cuenta de prueba nueva.

La implementación incluye documentos versionados, conflictos de edición, revisión antes de publicar, publicación atómica e idempotente, restauraciones auditables y permisos separados. La integración PostgreSQL y la inspección visual **no están validadas en este entorno**; véanse los resultados y los comandos de verificación.

## Decisiones de modelo y transacción

- `ContentDocument` identifica `home` y `page:<kind>`. Inicio comparte una sola versión para todas sus secciones y diapositivas; cada página comparte una versión con sus pasos y FAQ. Se eligió un modelo separado para conservar un único mecanismo de bloqueo y evitar repartir la misma lógica entre Page y un singleton distinto del inicio. No es un registry de secciones.
- `draft_version` empieza en cero y tiene constraint de no negatividad. `updated_at` y `updated_by` permiten identificar el último guardado. `published_version` y los punteros tipados `home_publication`/`page_revision` registran la publicación asociada. Una publicación migrada no se considera automáticamente igual al borrador: el estado pendiente se calcula comparando snapshots.
- Las escrituras editoriales requieren responsable con `cms.edit_content` y `expected_version`. Se bloquea primero el documento con `select_for_update(of=("self",))`, se comprueba la versión y se guarda contenido, auditoría e incremento dentro de la misma transacción. El parámetro se recibe mediante el decorador `draft_mutation`; omitirlo nunca desactiva la comprobación.
- El admin valida el campo oculto antes de guardar. Un contexto limitado a ese envío comparte el bloqueo entre padre e inlines, de modo que guardar varios pasos, preguntas o fotos aumenta la versión una sola vez. Una validación fallida no aumenta la versión. Los contextos se restablecen incluso si ocurre una excepción.
- También se leen los formularios completos, sus inlines y el editor visual bajo el bloqueo del documento. Esto evita mostrar contenido antiguo acompañado de una versión nueva durante una carrera de lectura. Los bloqueos terminan al generar la respuesta; no se mantienen mientras la persona edita.
- La identidad `Page.kind` queda fija una vez creada. El servicio tampoco permite trasladar un paso o FAQ a otra página. Ordenar Inicio se conserva en el editor visual, el formulario de sección y la lista de Unfold. La lista envía `expected_version` por formulario, valida bajo el bloqueo del documento y guarda mediante `save_section` en un único lote: varias posiciones incrementan la versión una sola vez. El arrastre de inlines se conserva.
- Publicar exige `cms.publish_content` y la versión revisada. Snapshot, estado publicado de Page, puntero del documento y auditoría se guardan atómicamente. Una segunda solicitud con la misma versión y el mismo contenido devuelve la publicación existente, sin duplicarla ni cambiar su nota. Si falla crear el snapshot o actualizar el puntero, la transacción conserva la publicación anterior. Se mantienen los selectores públicos existentes y sus contratos.
- `DraftRevision` reutiliza la base inmutable y sus metadatos de autor/fecha, pero representa una revisión de **borrador** con `kind=restore`. Dos FK tipadas (`restored_from_home` o `restored_from_page`) y una propiedad `restored_from` identifican el origen sin una referencia genérica sin integridad referencial. Un constraint exige exactamente un origen; otro hace única la versión por documento. Restaurar conserva su snapshot, responsable, nombre y fecha, aumenta la versión y no mueve los punteros publicados. No modifica ni elimina publicaciones anteriores.

Las constraints añadidas no son diferibles. Los bloqueos de consultas con relaciones anulables usan expresamente `of=("self",)`.

## Comportamiento visible

- Los formularios conservan el texto enviado ante conflicto y muestran quién guardó y a qué hora de Bogotá, junto a «Ver versión actual» en una pestaña nueva. La versión oculta sigue siendo la original: reenviar sin revisar vuelve a producir conflicto. Los archivos locales pueden necesitar seleccionarse de nuevo por las restricciones del navegador sobre campos de archivo.
- Las acciones AJAX devuelven HTTP 409 con `error`, `conflict` y `current_url`. El JS muestra el aviso y un botón «Recargar versión actual»; no recarga automáticamente ante conflicto.
- Todos los accesos de publicación conducen a «Revisar y publicar». El botón heredado de guardar/publicar ya no publica directamente. La acción masiva de páginas exige seleccionar una sola página para revisarla.
- La revisión muestra resumen ES/EN, nota opcional de hasta 300 caracteres y «Publicar ahora». Sin diferencias muestra «No hay cambios pendientes» y deshabilita el botón. Un POST con versión desactualizada devuelve 409, conserva la nota y exige abrir de nuevo la revisión.
- El resumen del inicio compara también fuentes editables: incluye secciones ocultas, títulos/textos originales por idioma, visibilidad, orden, fotos/diapositivas y destinos de enlaces. El de páginas incluye títulos, direcciones, contenido, pasos y FAQ por idioma.
- `publishing.pending_changes(key)` devuelve `count`, `changes` y `snapshot`. Es el selector reutilizable por Fase 4. El encabezado del editor visual y el formulario de página muestran la cantidad de cambios sin publicar.
- El historial conserva la paginación de publicaciones y muestra además las últimas 20 restauraciones del documento: «Restaurado desde la publicación del …», responsable y fecha de guardado. La confirmación de restauración también lleva la versión; ante conflicto devuelve 409 sin restaurar.

Las portadas de categorías, piedras y colecciones siguen perteneciendo al catálogo vivo, como antes. La acción existente del editor conserva su servicio y permiso de catálogo, y ahora exige también acceso editorial. No convierte esas cargas en borradores del inicio ni altera su publicación comercial. Las cargas de secciones y diapositivas sí pertenecen al documento Inicio y se versionan. `PersonalizationService` conserva su funcionamiento heredado fuera de los snapshots de Page; su guardado exige permiso editorial.

## Permisos

| Capacidad | Propietario | Contenido | Operaciones | Superusuario activo |
|---|---|---|---|---|
| Editar | Sí | Sí | No | Sí |
| Previsualizar / emitir token | Sí | Sí | No | Sí |
| Consultar historial | Sí | Sí | No | Sí |
| Revisar y publicar | Sí | No | No | Sí |
| Restaurar | Sí | No | No | Sí |

Se añaden `cms.edit_content`, `cms.preview_content` y `cms.restore_content`; se conserva `cms.publish_content` para publicar. `sync_roles` reemplaza los permisos de los grupos: Contenido pierde publicación y Operaciones pierde todos los permisos del CMS. La migración activa la sincronización ya existente por `post_migrate`. Operaciones tampoco accede al editor mediante sus permisos de catálogo y desaparece su grupo de menú «Página web».

Los servicios verifican permisos además de las vistas. El token de preview exige `preview_content` al emitirse y vuelve a consultar al usuario activo y su permiso al verificarse, de modo que retirar el permiso revoca los tokens existentes. La UI de Contenido muestra «Cambios pendientes de publicar — la Propietaria puede publicarlos» y no ofrece publicar ni restaurar. No se implementó «Enviar a revisión». No se cambió 2FA.

## Archivos y rutas

- `backend/apps/cms/models.py`, `documents.py`: documento, revisión de restauración, permisos, control de versión y contexto de envío.
- `services.py`, `editor_services.py`: guardados, orden, visibilidad, fotos, publicación y restauración.
- `admin.py`, `forms.py`: versión oculta, conservación de formularios, inlines y enlaces a revisión.
- `publishing.py`, `history.py`: revisión, selector de pendientes, resúmenes e historial.
- `editor.py`, `preview.py`, `apps/core/static/core/editor.js`: permisos HTTP, lectura consistente, conflictos AJAX y revocación de preview.
- Plantillas en `backend/templates/admin/cms/` y `backend/apps/cms/templates/admin/cms/`: estado, revisión, botones e historial.
- `apps/accounts/roles.py`, `apps/core/dashboard.py`, `config/urls.py`: roles, navegación y rutas.
- `apps/cms/tests/test_phase2.py`: 25 casos recopilados. Se adaptan las regresiones anteriores al contrato explícito de actor/versión, publicación idempotente y revisión previa; `tests/helpers.py` prepara versiones actuales para esos escenarios anteriores. Las pruebas nuevas de conflictos envían versiones explícitas y no utilizan ese ayudante.
- `backend/conftest.py`: actor explícito para regresiones de imagen/validación; ajustes de expectativas de menú en `apps/core/tests/test_dashboard_client.py` y de llamadas editoriales en pruebas de catálogo/core.
- `apps/payments/management/commands/e2e_admin_session.py`, `frontend/tests/e2e/support.ts`: argumento `--role` (`Propietario`, `Contenido`, `Operaciones`); conserva DEBUG, cuenta nueva sin contraseña, sesión efímera y prohibición si 2FA está exigida.
- `frontend/tests/e2e/cms-phase2.spec.ts`; se adapta también el escenario Fase 1 a revisión y versiones.

Rutas del panel (prefijo configurable `ADMIN_URL`, normalmente `/dashboard/`):

- `GET|POST revisar-publicacion/home/` y `revisar-publicacion/page:<kind>/`: revisión y publicación. POST requiere CSRF y `expected_version`; nota opcional.
- `editor/<acción>/`: acciones existentes; las de borrador requieren `expected_version`.
- `publicaciones/?document=home|<id>`: historial; `&restore=<id>` confirma/restaura mediante POST, `confirm=yes`, CSRF y `expected_version`.
- Las rutas heredadas de publicación redirigen a revisión y no publican contenido directamente.
- Preview conserva sus rutas y formato firmado; cambia la autorización, sin ampliar acceso público.

## Migraciones

1. `0014_alter_homesection_options_contentdocument_and_more`: capacidades editoriales, tablas ContentDocument/DraftRevision y constraints.
2. `0015_content_documents`: crea `home` y un documento por página existente, con su último snapshot publicado si existe. Usa la conexión de la migración y `get_or_create`, por lo que no duplica documentos ni sobrescribe versiones/punteros existentes al repetirse. No crea publicaciones.

La reversa **de datos** de 0015 conserva los documentos: eliminar un contador o un puntero que ya se utilizó perdería información editorial. Es una reversa deliberadamente no destructiva y puede repetirse. Revertir también el esquema 0014 elimina esas tablas y sus nuevas revisiones: exportarlas antes si ya se usaron, y revertir el código junto con el esquema. La prueba que retrocede migraciones vuelve en `finally` a `loader.graph.leaf_nodes()`.

## Pruebas y resultados

- `manage.py check --settings=config.settings.test`: correcto.
- `manage.py makemigrations --check --dry-run --settings=config.settings.test`: sin cambios pendientes; aviso de conexión bloqueada al verificar el historial de migraciones.
- Ruff de todos los Python modificados/nuevos: correcto. `git diff --check`: correcto.
- Construcción de formularios Home/Page con versión y compilación de las plantillas editoriales: correctas; se comprobaron sin usar una base alternativa. Resumen bilingüe, fotos y visibilidad: comprobación directa correcta.
- Pruebas de etiquetas españolas: 2/2 correctas. La primera ejecución completa detectó una etiqueta sin traducir en los modelos nuevos; se corrigió y la última suite ya no reporta fallos de pruebas ejecutadas.
- Última suite completa solicitada: `cd backend && pytest --ds=config.settings.test -q`, con backend PostgreSQL: **115 pasadas, 1030 errores de preparación, 6 avisos, 122,28 s**. PostgreSQL en localhost:5432 devuelve `Operation not permitted` desde el sandbox. Los errores de preparación impiden ejecutar las pruebas que dependen de base de datos; no son validación de integración. No se sustituyó PostgreSQL por SQLite ni se aplicaron migraciones a una base existente.
- Recopilación de la suite: 1145 pruebas; Fase 2: 25 casos. Incluyen conflicto admin/AJAX y texto conservado; padre e inlines con un incremento; permisos en servicios y HTTP; revocación de preview; resumen bilingüe y fuentes ocultas; publicación exacta, sin cambios y doble clic; fallos de snapshot/puntero; restauración auditable y conflicto; migración idempotente y reversa segura; hilos/barrera y conexiones separadas para guardar/publicar Inicio y Page en PostgreSQL. **Están preparados, pero bloqueados por la conexión en este entorno.**
- Frontend: `npm run lint`, `npm run typecheck`, `npm test`: correctos; 51 pruebas unitarias pasan.
- Playwright: listado del escenario nuevo correcto (desktop y mobile; mobile se omite expresamente para el flujo del panel). No se ejecutó contra un stack. Preparado para ejecución local por la clienta.

Verificación local con las variables habituales del proyecto y PostgreSQL accesible:

```sh
cd backend
python manage.py migrate
python manage.py sync_roles
pytest --ds=config.settings.test -q
```

```sh
cd frontend
npm run lint
npm run typecheck
npm test
npx playwright test tests/e2e/cms-phase2.spec.ts --project=desktop
```

El E2E requiere el stack de desarrollo migrado, Docker accesible, DEBUG y la configuración local de E2E que ya usaba `e2e_admin_session`. Crea cuentas sin contraseña, usa dos contextos de navegador independientes, comprueba que Contenido guarda sin publicar, conserva el texto de Propietaria ante conflicto y publica desde el resumen. Al terminar restaura y publica el snapshot inicial como nuevas revisiones; ejecutarlo en una base de desarrollo sin borradores que deban conservarse. No desactivar 2FA en producción.

## Riesgos y pendientes

- Antes de utilizar en producción, ejecutar la suite PostgreSQL y el E2E. La revisión estática y las pruebas frontend no demuestran el comportamiento de los bloqueos, de las migraciones o de Unfold con datos reales.
- Los formularios y el editor toman brevemente el bloqueo al leer/renderizar para garantizar coherencia entre versión y contenido. Conviene comprobar la respuesta con el volumen real de fotos; no hay bloqueo durante el tiempo humano de edición.
- Los servicios ahora rechazan escrituras editoriales sin actor o versión. Las llamadas externas o scripts locales que usen esos servicios deben obtener primero el documento, conservar la versión que revisaron y pasar ambos datos; no reintentar automáticamente con la versión nueva ante conflicto.
- La auditoría de restauraciones no depende de retener al usuario: conserva su nombre aunque posteriormente se elimine su cuenta.
- Fase 3: registry y composición de secciones siguen pendientes. Fase 4 puede consumir `pending_changes` y el documento/versionado ya implementados. El editor de tres paneles y la biblioteca multimedia no se crearon.

`.git` no es escribible: `git add -u` falló al crear `.git/index.lock` con `Operation not permitted`. Entrega **sin commits**; no se crearon scripts de commit. Al registrar el trabajo fuera del sandbox, usar un mensaje en español y el tráiler requerido:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

`docs/capturas/` ya estaba sin seguimiento al comenzar y no se modificó.

## Qué verificar visualmente

1. Como Contenido, editar textos ES/EN, pasos, FAQ y fotos: guardar conserva el borrador; hay preview, estado pendiente e historial, sin botones para publicar/restaurar.
2. Como Propietaria, abrir dos pestañas del mismo documento, guardar la primera y enviar la segunda: el texto de la segunda permanece, aparece nombre/hora y el enlace abre la versión actual en otra pestaña. Repetir con Página y con una portada con ambos inlines.
3. En dos pestañas del editor visual, cambiar visibilidad u orden: la pestaña antigua debe mostrar el aviso 409 y ofrecer recargar, sin recarga automática.
4. Revisar el resumen del Inicio (incluidas secciones ocultas y fotos reordenadas) y de Personaliza (ES/EN, pasos, FAQ). Verificar nota, botón deshabilitado sin cambios y que no se publica desde un formulario de sección.
5. Dejar abierta la revisión, guardar un cambio en otra pestaña e intentar publicar: debe avisar que el borrador cambió. Revisar otra vez y publicar; un doble clic no duplica el historial.
6. Restaurar una publicación anterior: confirmar que aparece una nueva restauración con autor/fecha, el borrador recupera el contenido y la tienda sigue sirviendo la publicación anterior.
7. Como Operaciones, verificar ausencia completa de «Página web» y rechazo por URL directa. Retirar preview a una cuenta de Contenido y comprobar que un token ya emitido deja de funcionar.
8. Revisar Unfold claro/oscuro, foco y mensajes en 390, 768 y 1440 px; enlace a versión actual, campos ocultos, formularios con errores e inlines deben seguir siendo utilizables.


## Corrección de los diez fallos PostgreSQL (9 de noviembre de 2026)

Se leyó completa la salida `fase2-fallos.txt` suministrada (10 fallos, 60 aciertos en esa ejecución enfocada). El resultado completo de 1123 aciertos fue comunicado por la usuaria; no es una ejecución realizada aquí.

| Punto | Causa comprobada y corrección | Archivo (bajo backend salvo indicación) |
|---|---|---|
| 1 | HomeSection se guardaba sin actor/versión. La prueba de reemplazo/borrado de imágenes ahora envía `cms_actor` y la versión actual en cada guardado. Se conservan todas las aserciones de tamaño y limpieza. Expectativa de llamada obsoleta por el contrato explícito de Fase 2. | apps/catalog/tests/test_image_pipeline.py |
| 2 | PersonalizationService también se guardaba sin actor. Ahora recibe `cms_actor`; conserva el permiso editorial, pero no exige versión de documento porque sigue fuera de sus snapshots. No se retira autorización del servicio. | apps/catalog/tests/test_image_pipeline.py |
| 3 | `publication_context` consultaba la última HomePublication y `pending_changes` repetía exactamente esa consulta. El selector acepta reutilizar el resultado, incluido None; el encabezado lo pasa. Se elimina una consulta del editor medido, sin cambiar ningún presupuesto. Pendiente confirmar 26 → 25 en PostgreSQL. | apps/cms/admin.py, apps/cms/publishing.py |
| 4 | El formulario inválido no enviaba el nuevo campo requerido. Se envía `expected_version` y se conserva la aserción del error de colección. Expectativa de entrada obsoleta por Fase 2. | apps/cms/tests/test_cms.py |
| 5 | `save_model` accedía a `form.cleaned_data` con form=None. HomeSection y Page solo extraen/pasan versión cuando existe formulario. No se consulta una versión nueva para eludir conflictos: una llamada real al servicio sin versión continúa rechazada. | apps/cms/admin.py |
| 6 | La salida demuestra que Contenido NO veía Publicar inicio; fallaba la expectativa que lo exigía. Se corrige únicamente esa expectativa obsoleta, comprobando su ausencia. El permiso de UI ya era correcto. | apps/core/tests/test_dashboard_client.py |
| 7 | La salida suministrada verifica fotos, estados e inlines y después falla porque `ordering_field` era None; no demuestra una regresión de renderizado de fotos. Se conserva toda esa cobertura y se restaura el ordenamiento. El error de management_form corresponde al caso 8. | apps/cms/admin.py; cobertura existente en apps/core/tests/test_dashboard_client.py |
| 8 | Se había eliminado el arrastre Unfold. Se restaura `ordering_field=position`, con formularios de lista versionados, bloqueo/transacción y `admin_batch`, usando `save_section`. La prueba envía el campo oculto nuevo. Se añaden casos de lote con incremento único, conflicto y versión ausente. | apps/cms/admin.py, apps/core/tests/test_dashboard_client.py, apps/cms/tests/test_phase2.py |
| 9 | El indicador había cambiado a una cantidad con «cambio(s) sin publicar», perdiendo el texto acordado. Se fija «Cambios sin publicar: N». Además el resto del test esperaba publicación directa por Contenido: expectativa obsoleta. Ahora Propietario abre revisión, se comprueba que abrirla no publica y después publica con versión explícita. | templates/admin/cms/page_status.html, apps/core/tests/test_one_page_actions.py |
| 10 | ContentDocument y DraftRevision carecían de etiquetas propias en español. Se añaden singular/plural y migración de opciones 0016, sin alterar datos. | apps/cms/models.py, apps/cms/migrations/0016_alter_contentdocument_options_and_more.py |

Validación de esta corrección: `manage.py check` correcto; migración 0016 generada; Ruff y diff revisados. La ejecución enfocada de los diez casos se detuvo al preparar el primero: PostgreSQL localhost:5432 está bloqueado con `Operation not permitted` (registro `/private/tmp/fase2-retest.txt`). No se usó SQLite ni se declara la suite verde. La eliminación de la consulta duplicada está comprobada por el código; su presupuesto y las pruebas de concurrencia/Unfold requieren repetir la suite con PostgreSQL accesible. Sin acceso externo ni push.

Se intentó `git add -u`: rechazado al crear `.git/index.lock` con `Operation not permitted`. No hay commit de esta corrección ni scripts de commit; los cambios quedan en el árbol junto con la entrega anterior.
