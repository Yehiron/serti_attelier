# Catálogo — Etapa 5: auditoría, rendimiento y regresión

Rama `fase-9-produccion`, base `d83c434`, con `7f69bd0`, `0fad218` y `22dc0f3`
en el historial. Trabajo local, sin red y sin push. Se leyeron los informes de
Etapas 1–4 y se contrastaron los pendientes indicados con el código. No se encontró
un informe separado de auditoría del catálogo en los archivos del repositorio;
`docs/auditoria-frontend.md` corresponde a la revisión anterior del frontend.
Se usaron `codebase-memory` y `surgical-patch`, con comprobación de cobertura y
lectura directa de los servicios, administrador y editor visual.

No se modificaron Next.js, los serializadores, vistas o rutas públicas del catálogo,
los permisos de los roles ni el esquema de datos. No hay migraciones. Se conserva
el diseño; Historial incorpora una tabla de eventos al acceso existente.

## Auditoría

Todos los cambios nuevos usan `apps.audit.services.record` dentro de la transacción
de la operación. Los puntos de entrada del dashboard transmiten actor y petición;
el registro conserva objeto, diferencias, IP y navegador. Los servicios internos
siguen aceptando actor/petición ausentes, como operaciones de sistema.

- `save_piece_relations`: piedras, materiales y piezas relacionadas, antes/después
  con nombres españoles. Bloquea la pieza; una validación fallida revierte relaciones
  y evento. Guardar las mismas relaciones no añade un evento.
- `save_collection_piece` y `delete_catalog_object`: incorporación, cambio y retiro
  de colecciones de la pieza; también registra el cambio de posición en la colección.
  Un cambio de vínculo y posición comparte evento.
- `apply_photo_changes`: extiende el evento existente `catalog.photos_updated` con
  descripciones en español/inglés y sustitución de archivos. Principal, hover, orden
  y borradas siguen en ese mismo evento, ahora con etiquetas de fotos legibles.
  Las subidas múltiples pasan la petición al servicio existente.
- `save_taxonomy`: creación/edición de categorías, piedras, materiales y colecciones;
  diferencias de nombres, traducciones, padre por nombre y otros campos editables.
  Altas, sustituciones y retirada de portadas quedan registradas. El endpoint
  `taxonomy-cover` utiliza este servicio con el contexto de la petición.
- Creación rápida: se retira su `record` independiente; reutiliza el evento
  `catalog.category_created` de `save_taxonomy`. Se prueba que sea uno solo.
- Borrado de taxonomías y de piezas en los servicios: evento con nombres, contexto
  y objeto conservado aunque la fila desaparezca. Una falla posterior en un lote
  revierte también sus eventos anteriores.
- Duplicar: el evento conserva nombre y SKU del origen, y ahora recibe petición.
  La referencia de categoría de los nuevos diffs de pieza usa el nombre.

**Historial:** piezas y taxonomías incorporan sus propios eventos de `AuditLog`,
con fecha, responsable y diferencias en español, además de los `LogEntry` de Django.
Por ejemplo: «Piedras: Esmeralda → Diamante, Esmeralda», «Foto principal cambiada»
y «Portada de Anillos: Portada anterior → Portada reemplazada». Las portadas se
consultan en Historial de su categoría/piedra/colección; no se atribuyen a una pieza
individual. Paginación de 50 eventos, permiso del objeto conservado, textos escapados,
sin mostrar IP ni navegador. Los eventos antiguos son inmutables y no se reescriben:
pueden conservar IDs. Las escrituras ORM ajenas a estos servicios no se convierten
en un mecanismo nuevo de auditoría por señales.

**Bug privado encontrado:** el administrador técnico de fotos guardaba/borraba
mediante servicios individuales, eludiendo el estado final del inline. Podía borrar
la principal publicada y no auditaba el cambio de descripción. Ahora pasa por
`apply_photo_changes`, bloquea mover fotos entre piezas y presenta los errores de
validación sin guardar. La prueba HTTP real usa superusuario, porque esa pantalla
es técnica y los roles del negocio no tienen acceso a ella. Esto conserva el
contrato público y extiende al acceso técnico la regla de fotos ya existente.

## Rendimiento: evidencia y presupuestos

Medición con `CaptureQueriesContext`, incluyendo middleware y renderización de las
respuestas. **Son mediciones auxiliares con SQLite; no mediciones verificadas en
PostgreSQL.** Se calientan las cachés ajenas al catálogo. El conjunto inicial tiene
5 o 25 piezas con seis fotos por pieza, asignadas a hijas de una raíz. El test final
agrega también 5/25 piedras y colecciones para comprobar las tres taxonomías.

| Pantalla / endpoint | Antes: 5 | Antes: 25 | Después: 5 | Después: 25 | Presupuesto final |
|---|---:|---:|---:|---:|---:|
| Lista de piezas | 22 | 22 | 22 | 22 | 25 |
| Ficha con seis fotos | 48 | 48 | 29 | 29 | 35 |
| Lista de categorías | 13 | 13 | 13 | 13 | 18 |
| `photos/status` | 15 | 15 | 12 | 12 | 15 |
| Editor visual, pestaña taxonomía | 32 | 72 | 20 | 20 | 25 |
| Creación rápida, padre existente | 28 primera petición | — | 27 caché caliente | 27 caché caliente | 35 |

La primera creación rápida incluye una consulta de `ContentType`; con esa caché
caliente son 27 consultas tanto antes como después. No se atribuye esa diferencia
a una optimización del endpoint. El test calienta esa caché y exige igualdad de los
dos POST. Para las otras cinco rutas también exige **igualdad exacta** entre 5 y 25,
además de los presupuestos. La lista renderiza 25 piezas; su precarga de solo la
principal y la precarga/conteo de categorías de las Etapas 3–4 ya eran suficientes.

Optimizaciones justificadas:

1. Unfold consulta el objeto una vez por acción de detalle. `PieceAdmin.get_object`
   comparte la lectura durante un mismo GET; no la comparte entre peticiones ni
   en POST. Los servicios siguen releyendo y bloqueando antes de escribir.
2. `publication_missing` reutiliza las fotos precargadas, evitando tres consultas
   adicionales para saber si existe una principal pendiente/lista.
3. El editor agrega los conteos publicados mediante `Count` filtrado y precarga
   hijas; elimina `count()` y `children.all()` por tarjeta. Reutiliza las tarjetas
   de piedras en vez de consultarlas dos veces.

Logs de medición: `/private/tmp/catalog-stage5-baseline.log` y
`/private/tmp/catalog-stage5-finalfocused.log`.

### Limpieza de archivos

El código anterior recorría todos los objetos con imágenes y las publicaciones una
vez por callback de archivo/foto. Ya agrupaba los caminos de una foto, pero un lote
de seis fotos generaba seis recorridos completos.

`batch_file_cleanup` agrupa las rutas por operación y base mediante `ContextVar`.
Se aplica a cambios finales de fotos, subidas múltiples y borrado de piezas. Los
ámbitos anidados solo se unen si terminan correctamente. Al salir se programa un
único `on_commit`; Django lo descarta al revertir la transacción. Antes de borrar se
mantiene íntegra la revisión de todos los modelos y de `snapshot`/`draft_snapshot`.
Fuera de estas operaciones agrupadas, las señales conservan su comportamiento.

Prueba medida: borrar seis fotos pasó de **54 consultas de revisión a 9**, seis
recorridos a uno. Contar 1 o 30 caminos sin referencias exige las mismas 9 consultas.
El coste sigue siendo lineal en las referencias del catálogo por operación; no se
añade un índice de archivos ni se cambia su formato. Las instantáneas JSON se siguen
recorriendo para no perder referencias anidadas o en `srcset`.

Regresiones: archivo compartido por una piedra, referencia en publicación y en
borrador mediante URL/srcset, eliminación de archivo obsoleto, rollback de base y
archivos, ámbito anidado fallido y número de recorridos. Se conservan además las
pruebas previas de sustitución, portadas y borrado en cascada. La comprobación de
referencias se hace al ejecutar la limpieza; no se introduce un protocolo nuevo
para escrituras externas concurrentes sobre los mismos caminos de almacenamiento.

## Regresión pública

`test_stage5_contract.py` fija las respuestas HTTP reales en español e inglés:

- Claves exactas de lista y detalle; objetos de imagen con `src`, `srcset`, ancho,
  alto y alt; principal, hover opcional y galería ordenada, excluyendo pendientes/fallidas.
- Precio y rebaja en centavos COP, con rebaja nula cuando corresponde.
- Los cuatro `sale_state`; solo `published` visible. Vendidas disponibles por detalle
  y por `availability=all`, excluidas de la lista predeterminada como antes.
- Filtro por raíz que incluye hijas, filtro por hija, piedra, material, colección
  y búsqueda; `categories.children`, hijas activas y forma de las portadas.
- Todas las claves conocidas de `attributes`, conservando tipos; talla entera,
  decimal o texto; objeto vacío. La prueba previa de Etapa 3 conserva además claves
  históricas desconocidas al editar.
- Publicada con imagen no nula después de cambiar principal, retirar hover,
  ordenar y borrar secundarias; se rechaza retirar todas.
- Portadas no nulas y nombres traducidos; proporción original de categorías/piedras
  y 16:9 para colecciones.

Se leyó `frontend/lib/api/types.ts`: `Image`, `Money`, `SaleState`, `PieceCard`,
`PieceDetail`, `Category` y `Taxonomy` son coherentes con estas respuestas. La API
conserva sus tipos anulables para imágenes de datos históricos; no se cambia ese
contrato. No se modificó ni se ejecutó el frontend.

## Archivos

- `backend/apps/catalog/services.py`: auditoría y contexto; reutilización de fotos;
  agrupación de limpieza en las operaciones indicadas. Se conservan bloqueos
  `select_for_update(of=("self",))` y restricciones inmediatas.
- `backend/apps/catalog/admin.py`: transmite petición/actor, lectura compartida
  durante GET, historial y reglas del administrador técnico de fotos.
- `backend/apps/catalog/audit_history.py` y
  `backend/templates/admin/catalog/piece/object_history.html`: presentación y paginación.
- `backend/apps/catalog/image_cleanup.py`: agrupación segura de callbacks.
- `backend/apps/cms/editor.py`: conteos/precarga y auditoría de portadas.
- `backend/apps/catalog/tests/test_stage5_{audit,performance,cleanup,contract}.py`:
  **35 casos añadidos** contando parametrizaciones.
- `docs/requirements.md`, `docs/security-plan.md`, `docs/api-contract.md`:
  comportamiento y permisos reales; corrección de referencias antiguas a SKU
  vacío en copias, permisos de Contenido y portadas 16:9 universales.
- `docs/catalogo-guia-uso.md`: guía corta para la dueña y su equipo.
- Este informe.

## Comandos y resultados finales

Variables locales, sin servicios externos:

```sh
export DJANGO_SECRET_KEY=local-test
export REDIS_URL=redis://localhost:6379/0
cd backend
DATABASE_URL='postgresql:///serti?host=/tmp' .venv/bin/pytest --ds=config.settings.test -q
DATABASE_URL=sqlite:////private/tmp/stage5-finalfull.sqlite3 .venv/bin/pytest --ds=config.settings.test -q
DATABASE_URL=sqlite:////private/tmp/stage5-checks.sqlite3 .venv/bin/python manage.py check --settings=config.settings.test
DATABASE_URL=sqlite:////private/tmp/stage5-checks.sqlite3 .venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

- **PostgreSQL no accesible desde el sandbox.** La conexión al socket
  `/tmp/.s.PGSQL.5432` devuelve `Operation not permitted`. Suite final: **73 pasadas,
  789 errores de preparación**, en 88,15 s. Las 73 pasadas no acreditan las operaciones
  del catálogo. No se da PostgreSQL por verificado.
- Suite completa auxiliar con SQLite: **839 pasadas, 22 omitidas y 1 fallo**, en
  60,71 s. El fallo existente es `test_ready_reports_dependencies`: Redis no es
  accesible y readiness responde 503. No se alteró ni se simuló esa prueba.
  Las 35 pruebas nuevas están entre las pasadas. SQLite no prueba bloqueos,
  concurrencia ni restricciones específicas de PostgreSQL.
- Enfocada de auditoría/rendimiento/limpieza: **19 pasadas**, en 6,19 s,
  antes de las últimas ampliaciones del contrato incluidas en la suite completa.
- `manage.py check`: sin problemas. `makemigrations --check --dry-run`: sin cambios.
- Ruff en todos los Python modificados/nuevos y `git diff --check`: correctos.

Logs finales: `/private/tmp/catalog-stage5-postgres-final.log`,
`/private/tmp/catalog-stage5-sqlite-final.log` y
`/private/tmp/catalog-stage5-finalfocused.log`. Las pruebas están listas para
usarse con PostgreSQL; no incorporan sustituciones de bloqueos ni constraints
diferibles para hacerlas pasar en SQLite.

## Entrega y pendientes

1. Ejecutar `cd backend && pytest --ds=config.settings.test -q` con PostgreSQL
   y Redis accesibles. Confirmar también los presupuestos en PostgreSQL antes de
   considerar verificada la etapa en la base requerida.
2. Verificar visualmente Historial con datos reales y los cambios de fotos con worker
   y almacenamiento reales. Esta etapa comprueba HTML renderizado, sin revisión
   de navegador ni rediseño de UI.
3. `.git` no es escribible (`test -w .git` devuelve falso): cambios **sin commit**.
   No se crearon scripts de commit ni se hizo push. Cuando se pueda escribir,
   el commit debe tener mensaje en español y el pie solicitado:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

No queda una propuesta de cambio de contrato público pendiente de confirmación:
el comportamiento existente se conservó y se documentó.
