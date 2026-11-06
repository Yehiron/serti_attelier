# Ronda: búsqueda, eliminación y selección opcional

Rama `fase-9-produccion`, base `257062f`. Trabajo sin red ni push. Se leyeron las
Etapas 1–5 y se aplicaron `frontend-design` y `codebase-memory`. No hay dependencias,
migraciones ni cambios del contrato público de la API. No se modificaron los datos
existentes de Gorras ni su posición.

## Buscador

La causa identificada en CSS es el monograma: estaba colocado a `right: -40px` y
`bottom: -30px` dentro de un diálogo con `overflow-y: auto`. Ese desbordamiento
decorativo podía crear scroll aun sin escribir. Además, `body:has(dialog[open])`
ya bloqueaba el fondo, pero no había una reserva estable para la barra del navegador;
retirarla podía cambiar el ancho del contenido.

Ahora el monograma queda dentro de la tarjeta; el diálogo y su contenedor no
se desplazan. El contenedor usa flex con altura máxima limitada al espacio disponible;
solo las sugerencias o los accesos a categorías/piedras pueden desplazarse si no caben.
La barra de esas listas es fina y el desplazamiento no se propaga al fondo.
`scrollbar-gutter: stable` reserva el ancho del navegador. Se conserva el bloqueo
del fondo y el comportamiento nativo de foco, Escape y retorno al disparador del diálogo.
Los controles tocados tienen al menos 44 px; la entrada anima opacity/transform durante
180 ms ease-out y respeta `prefers-reduced-motion`.

Playwright comprueba en escritorio y celular: diálogo sin desbordamiento vertical
vacío y con seis resultados, documento sin desbordamiento horizontal, ancho de `main`
idéntico antes/durante/después, fondo inmóvil con rueda y foco de entrada/retorno.
No se ejecutó el navegador; estas comprobaciones quedan preparadas para la dueña.

## Eliminar y seleccionar

- Piezas: icono Material Symbols `delete`, con nombre «Eliminar pieza», únicamente
  para quienes tienen permiso de eliminar y permiso comercial. Contenido no lo ve.
  La pieza protegida muestra el icono deshabilitado y explica todos los motivos
  del servicio: estado editorial, venta/reserva, reservas, historial o pedidos.
  Se sugiere archivarla. Se mantienen los bloqueos y la auditoría existentes.
- Categorías: sin selección ni borrado masivo. Icono individual con confirmación
  Django/Unfold y CSRF; se explica que la acción no puede deshacerse. Las categorías
  con piezas o hijas están protegidas por PROTECT y el icono explica el motivo.
- Piedras y colecciones: también tenían casillas únicamente para borrar; reciben
  icono individual y pierden esa selección. Antes borrar podía retirar sus vínculos
  con piezas (y los registros intermedios de colecciones). Ahora se bloquea mientras
  tengan piezas vinculadas: hay que retirarlas de esa clasificación primero. No
  se borran las piezas. La protección se aplica tanto en la confirmación como en
  el servicio, que vuelve a leer y bloquea la taxonomía antes de comprobarla.
- Materiales conserva sus acciones anteriores; no se amplió el cambio a esa lista.
- La auditoría sigue pasando por `delete_catalog_object`/`delete_piece`, dentro de
  la transacción; las pruebas comprueban el evento y responsable tras confirmar.

Piezas y pedidos comparten «Seleccionar» / «Cancelar selección» (icono `checklist`).
El botón aparece solo si existe el selector de acciones masivas. Con JavaScript,
las columnas y barras se ocultan por defecto mediante `selection-ready`; al activar
se muestran. Cancelar limpia las casillas, la selección de todo el conjunto y las
marcas de filas. El foco permanece en el botón. Sin JavaScript se conserva la lista
estándar con selección visible, para no impedir las acciones.

`?select=1` mantiene el modo al recargar; los enlaces de filtros/paginación y formularios
GET lo conservan mientras está activo. `SelectionChangeList` elimina ese parámetro
antes de construir filtros ORM y conserva el ChangeList de Unfold. Los cálculos del
centro de pedidos también lo excluyen. El CSS móvil de pedidos oculta por completo
la celda al cancelar, sin reservar su espacio ni agregar una fila a la tarjeta.

Los motivos de borrado usan anotaciones en las listas, evitando consultas por fila.
En piezas se usan subconsultas Exists, sin GROUP BY en el queryset que puede llegar
a un bloqueo de PostgreSQL. Se conserva `select_for_update(of=("self",))` y ninguna
restricción pasa a diferible. Pasa el presupuesto de consultas de la Etapa 5.

## Gorras: reglas y corrección

Con los datos aportados (activa, raíz y cero piezas), **Gorras debe aparecer**. No
hay una regla que oculte categorías vacías. No hay menú hardcodeado, lista curada,
límite de tarjetas ni foto obligatoria. El inglés vacío usa el respaldo español.

El defecto comprobable en el código era la lectura compartida de Next: tanto
`getTaxonomy` como el inicio conservaban datos con `stale: 60`, `revalidate: 60`,
`expire: 300`. Había etiquetas, pero no existía ningún mecanismo que las invalidara
al guardar una taxonomía desde Django. Eso permite que una categoría ya presente
en la API siga ausente temporalmente en la tienda. Sin acceso a la tienda ni a
sus datos en ejecución no se puede atribuir con certeza la observación concreta
solo a esa caché; sí se confirmó y corrigió esta fuente de retraso.

Ahora taxonomía e inicio se leen de la API en cada petición de servidor. React
`cache` evita duplicados dentro de la misma renderización; no comparte esos datos
entre peticiones. Se conserva la caché temporal del catálogo de piezas, fichas y
otras páginas. No se añadió un endpoint de revalidación ni se modificó la API.
El coste es una lectura actual de taxonomía y de inicio por petición correspondiente.
Después de guardar una categoría hay que recargar o volver a entrar a la tienda;
una página ya abierta no se actualiza sola. Las piezas recién publicadas conservan
su caché habitual.

| Lugar | Regla real |
| --- | --- |
| Joyería, escritorio y celular | Todas las raíces activas y sus hijas activas; sin exigir piezas o foto. Una hija de raíz inactiva no entra en ese árbol. |
| Comprar por categoría | Todas las raíces activas, si la sección `category_grid` está en el inicio publicado. Las hijas no tienen tarjeta propia. Cuenta piezas publicadas directas y de hijas activas. No exige foto ni mínimo de piezas. |
| Filtros del catálogo y accesos del buscador | Se alimentan de la misma taxonomía activa; vacías incluidas. |
| Página de categoría | La ruta pública es `/es/joyeria/gorras`, no `/es/categorias/gorras`. Usa la taxonomía para identificarla y la API para filtrar piezas publicadas; una categoría vacía muestra el estado vacío. La raíz incluye piezas de sus hijas. Vendidas se excluyen por defecto, salvo disponibilidad «Todas». |
| Inglés | Nombre y slug españoles como respaldo si falta traducción; no se oculta por ello. |

La lista del panel distingue «Visible en la tienda · sin piezas publicadas» de
«No visible en la tienda: inactiva». El formulario explica las condiciones del menú,
el inicio y la recarga. No se añadió la insignia «No visible: sin piezas», porque
sería falsa para Gorras. El contador de la lista es de piezas directas, como antes;
las tarjetas del inicio también cuentan las hijas activas.

El servicio de alta asigna `max(position) + 1` entre hermanos. La creación rápida
ya lo hacía; ahora la regla vive en el servicio y también cubre el formulario
completo. No cambia posiciones al editar ni reordena categorías existentes.

## Archivos

- `frontend/app/globals.css`: contención del buscador, listas, gutter y movimiento.
- `frontend/lib/api/server.ts`: lecturas actuales de taxonomía e inicio.
- `frontend/tests/e2e/quick-search.spec.ts`: geometría, scroll y foco en ambos tamaños.
- `frontend/tests/e2e/category-visibility.spec.ts`: calienta el inicio, crea una raíz
  vacía, verifica que aparece, le asigna una pieza publicada y comprueba menú,
  página y tarjeta del inicio. Usa datos temporales y retira la categoría al terminar.
- `backend/apps/core/admin_selection.py` y `static/core/selection.{css,js}`:
  modo opcional compartido y alternativa sin JavaScript.
- `backend/apps/catalog/admin.py`, `forms.py`, `services.py` y
  `static/catalog/catalog-admin.css`: iconos, permisos, motivos, ayuda, posición,
  protección y consultas sin crecimiento por fila.
- `backend/templates/admin/catalog/delete_confirmation.html`: texto claro sobre
  la confirmación existente de Unfold.
- `backend/apps/orders/admin.py`, `card_admin.py`, `static/orders/order-card.css`:
  modo selección y compatibilidad con centro de pedidos/tarjeta móvil.
- `backend/apps/catalog/tests/test_search_delete_round.py`: 13 casos nuevos,
  incluidas parametrizaciones. Permisos, iconos protegidos, CSRF real, auditoría,
  confirmación, taxonomías sin casillas, `select=1`, altas al final y visibilidad.

## Comandos y resultados

Variables backend: `DJANGO_SECRET_KEY=local-test`,
`REDIS_URL=redis://localhost:6379/0`. Se utilizó `.venv/bin/pytest` desde `backend`.

```sh
DATABASE_URL='postgresql:///serti?host=/tmp' .venv/bin/pytest --ds=config.settings.test -q
```

**PostgreSQL no accesible desde este sandbox**: conexión a `/tmp/.s.PGSQL.5432`
rechazada con `Operation not permitted`. Última suite completa: **97 pasadas y
978 errores de preparación**, 119,98 s. Las pasadas no acreditan las operaciones
con base de datos. No se sustituyeron bloqueos ni constraints para hacerlas pasar.
Log: `/private/tmp/ronda-postgres-final.log`.

Comprobaciones auxiliares, que no sustituyen PostgreSQL:

```sh
DATABASE_URL=sqlite:////private/tmp/ronda-aux.sqlite3 .venv/bin/pytest --ds=config.settings.test apps/catalog/tests/test_search_delete_round.py apps/catalog/tests/test_stage5_performance.py -q
DATABASE_URL=sqlite:////private/tmp/ronda-full-final.sqlite3 .venv/bin/pytest --ds=config.settings.test -q
```

- Enfocada final: **14 pasadas**, incluido el presupuesto de consultas.
- Suite completa auxiliar final: **1029 pasadas, 45 omitidas y 1 fallo**, en
  71,68 s. Falla `apps/core/tests/test_health.py::test_ready_reports_dependencies`:
  Redis no es accesible y readiness responde 503. No se alteró esa prueba.
  SQLite no acredita bloqueos, concurrencia ni restricciones de PostgreSQL.
- Etapas 3, 4 y 5/auditoría/rendimiento y tarjetas de pedidos durante la ronda:
  **73 pasadas y 1 omitida** (requiere PostgreSQL).
- Ruff sobre Python tocado, `node --check` del selector y `git diff --check`: correctos.
- Frontend: `npm run lint`, `npm run typecheck` y `npm test`: correctos;
  **47 pruebas unitarias pasadas**.
- `playwright test quick-search.spec.ts category-visibility.spec.ts --list`:
  **4 pruebas descubiertas** entre escritorio y celular. No ejecutadas, según la
  indicación de dejarlas listas. Requieren la pila local y sus comandos E2E existentes.

Logs locales: `/private/tmp/ronda-{new-final,full-final,lint,types,unit,playwright-list}.log`.

## Verificación visual pendiente y entrega

Con la pila local levantada, desde `frontend`:

```sh
./node_modules/.bin/playwright test quick-search.spec.ts category-visibility.spec.ts
```

Revisar a 1440, 768 y 390 px, claro y oscuro de Unfold:

1. Buscador vacío y con sugerencias: sin barra propia, sin salto lateral, lista
   desplazable cuando haga falta, cierre por Escape y foco de retorno.
2. Propietario y Contenido: iconos de borrar según permiso, motivos al pasar el
   mouse y confirmación con el nombre correcto; piezas vendidas o con pedidos.
3. Seleccionar, marcar filas, cancelar y volver a seleccionar: nada queda marcado.
   Repetir con todos los resultados, filtros, paginación y JavaScript desactivado.
4. Pedidos móviles: checkbox solo al seleccionar, tarjeta sin nueva fila y altura
   de hasta 190 px con los datos usados para la comprobación compacta previa.
5. Categorías, piedras y colecciones: sin casillas; borrar vacío y comprobar
   Historial; vínculo o hija impide borrar. Alta nueva al final de sus hermanos.
6. Gorras: recargar, abrir Joyería en ambos tamaños y confirmar el inicio publicado.
   Si aún falta con esta versión, comprobar el origen API usado por Next y si el
   inicio publicado contiene `category_grid`: el código no justifica ocultarla
   por sus cero piezas. No se modificaron datos reales para simular una solución.

`.git` no es escribible (`test -w .git` devuelve 1): cambios **sin commit**.
No se crearon scripts de commit ni se hizo push. El commit posterior debe ser en
español e incluir:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
