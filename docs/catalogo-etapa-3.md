# Catálogo — Etapa 3: lista y ficha de piezas

Rama: `fase-9-produccion`. Base local: Etapas 1 y 2, incluido `0fad218`.
Trabajo sin red y sin push. Sin cambios en Next.js, en `backend/apps/catalog/api`
ni en el esquema de la base de datos. No se necesitan migraciones.

## Qué cambia para la dueña

- **Piezas:** encabezado con acceso a «Nueva pieza» según permiso, 25 piezas por
  página y pestañas Todas, Borradores, Publicadas, Ocultas y Archivadas.
  Los contadores conservan la búsqueda y los demás filtros; cambiar de pestaña
  empieza en la primera página. Se conservan los filtros anteriores.
- Cada fila muestra la foto principal de 48 px, nombre y referencia, categoría
  completa, precio y estados separados. Los iconos visibles abren Editar,
  Ver en la tienda, Duplicar y Publicar u Ocultar según corresponda.
  Tienen nombre accesible y ayuda al pasar el mouse. No hay menú de tres puntos.
  Duplicar y cambiar la publicación pasan por las confirmaciones existentes:
  abrirlas no cambia datos; su confirmación sigue siendo un POST protegido.
- **Ficha completa:** secciones apiladas de información, clasificación, detalles
  y fotos. En escritorio, estado, checklist, precio y guardado están a la derecha;
  en celular aparecen arriba. Inglés, SEO, Video, Colecciones y Avanzado quedan
  plegados; los bloques con errores se abren mediante las reglas de Django.
- El checklist «Lista para publicar» usa `publication_missing`, la misma función
  del servicio de publicación. Incluye también la dirección en la web, porque
  ya era un requisito real. Publicar queda deshabilitado con explicación cuando
  falta algo, y no aparece para Contenido ni en estados sin transición permitida.
  Para una pieza nueva, primero se guarda el borrador; después puede publicarse
  cuando los datos y la foto principal estén listos.
- Los campos obligatorios conservan el asterisco de Unfold. Los necesarios para
  publicar llevan una indicación escrita distinta. Se avisa antes de salir con
  cambios sin guardar y se bloquea el doble envío mientras se guarda.

## Referencias automáticas

Al crear, la referencia se puede dejar vacía. Antes de `full_clean`, el servicio
asigna `SRT-<PREFIJO>-<NNNN>`: tres letras sin tildes de la categoría raíz, o GEN
si no existe categoría, y el siguiente número después del mayor existente.
Las referencias manuales se respetan. Al editar, la referencia sigue siendo
obligatoria. Duplicar conserva su sufijo anterior `-COPIA-…`.

En PostgreSQL se toma un bloqueo asesor por prefijo durante la transacción,
que funciona incluso cuando todavía no hay referencias de ese tipo. Se conserva
la restricción única y se permiten hasta cinco intentos ante colisiones de SKU,
con savepoint para recuperar la transacción tras un error de unicidad.
Los errores de otros campos o restricciones no se ocultan ni se reintentan.
Se añade una prueba concurrente para las dos primeras referencias del prefijo;
solo puede ejecutarse con PostgreSQL.

## Detalles de joyería

El formulario presenta Metal, Pureza, Talla de anillo, Largo, Dimensiones, Peso y
Quilates como campos normales, con los widgets de Unfold y las unidades visibles.
Todos son opcionales. Largo, peso y quilates admiten números positivos con límite
superior de 10 000; las tallas numéricas admiten valores mayores que cero hasta
100. La talla admite texto para conservar las notaciones ya permitidas.

Se guardan las mismas claves del JSON: `metal`, `metal_purity`, `ring_size`,
`length_mm`, `dimensions_mm`, `weight_g` y `carats`. Los valores numéricos siguen
siendo números, y una talla numérica histórica conserva su tipo si no cambia.
Vaciar un campo retira esa clave. Las claves desconocidas históricas se conservan;
el servicio comprueba que no se introduzcan ni modifiquen otras nuevas.
El validador público conserva sus reglas y los serializers no se modifican.

La categoría muestra «Anillos → Solitarios». No se implementaron creación rápida,
optgroups ni sugerencia dinámica de referencia: las dos últimas eran opcionales.
La talla permanece siempre visible.

## Fotos y permisos conservados

La tabla se sustituye por tarjetas, conservando management form, identificadores,
prefijos, originales, textos alternativos, errores y campos del formset.
Los radios visuales escriben las mismas casillas `is_primary` e `is_hover`;
los botones Mover antes/después actualizan `position`. Sin JavaScript quedan
las casillas y posiciones editables como alternativa. La selección de hover puede
quitarse. El borrado solo aparece con permiso y el servicio vuelve a comprobarlo.
Las vistas de solo lectura no muestran controles de edición.

El guardado continúa en `apply_photo_changes`, con su bloqueo, validación final,
normalización, dos fases y auditoría. No se cambiaron las restricciones ni se
hicieron diferibles. Se conserva `select_for_update(of=("self",))`.
Las transiciones editoriales y los permisos comerciales de la Etapa 1 siguen
vigentes: Contenido no crea, borra ni decide publicación, y ve el precio sin editarlo.

`photo-status.js` conserva sus endpoints, reintento con CSRF, espera progresiva y
límite de tiempo. Ahora emite `catalog:photo-status` después de recibir el estado;
el nuevo editor usa `ready_to_publish` y `missing` para refrescar el checklist y
el botón Publicar. No se publica automáticamente.

Las fotos nuevas muestran vistas previas locales con `URL.createObjectURL`,
contador y botón Quitar (mediante `DataTransfer` cuando el navegador lo permite).
Las URL temporales se liberan. En formatos que el navegador no puede mostrar,
como algunos HEIC, se conserva el nombre del archivo sin una imagen rota.
El selector acepta los formatos admitidos por el procesador y explica el límite
de 25 MB por foto. Si el formulario falla con archivos enviados, se pide volver
a elegirlos: el navegador no conserva esa selección tras la respuesta de error.

## Archivos principales

- `backend/apps/catalog/admin.py`: lista, acciones, consultas, secciones y checklist.
- `backend/apps/catalog/forms.py`: referencia opcional al crear, atributos y categorías.
- `backend/apps/catalog/services.py`: generación de SKU y conservación de atributos
  históricos; checklist de una pieza todavía sin guardar.
- `backend/apps/catalog/validators.py`: nombres compartidos de las claves existentes;
  el validador no cambia su contrato.
- `backend/templates/admin/catalog/piece/change_list.html` y `change_form.html`:
  nuevas pantallas completas.
- `backend/templates/admin/catalog/photo_grid.html`, `new_photos.html` y
  `piece_status.html`: tarjetas, subidas y seguimiento.
- `backend/apps/catalog/static/catalog/catalog-admin.css` y `catalog-admin.js`:
  distribución adaptable, modos claro/oscuro, controles, selección y guardado.
- `backend/apps/catalog/static/catalog/photo-status.js`: evento para el checklist.
- `backend/apps/catalog/tests/test_stage3.py`: regresiones nuevas. Se actualizan
  expectativas de presentación en `test_admin_sections.py`, `test_catalog.py`
  y `apps/core/tests/test_one_page_actions.py`, conservando las reglas operativas.

Las animaciones nuevas usan únicamente transform/opacity, 180 ms ease-out,
respuesta al pulsar de escala .97 y respeto de `prefers-reduced-motion`.
Los controles nuevos tienen áreas de al menos 44 px; las cifras usan
`tabular-nums`. La cuadrícula reserva espacio para las fotos mientras se procesan.
La lista usa un Prefetch limitado a la principal y `select_related` de categoría
con su raíz. La prueba compara una y 25 filas, exige menos de 35 consultas,
como máximo dos adicionales al crecer, y una sola consulta de fotos principales.

## Validación y límites del entorno

Se usó `backend/.venv/bin` y las variables:

```sh
export DJANGO_SECRET_KEY=local-test
export REDIS_URL=redis://localhost:6379/0
cd backend
DATABASE_URL='postgresql:///serti?host=/tmp' .venv/bin/pytest --ds=config.settings.test -q
```

**PostgreSQL no está accesible desde el sandbox:** la conexión a
`/tmp/.s.PGSQL.5432` devuelve `Operation not permitted`. La ejecución final terminó con **73 pruebas pasadas y 749 errores de preparación**
en 80,64 s. Esas 73 pruebas no acreditan los bloqueos ni el guardado del catálogo.
La suite no queda verificada en PostgreSQL. La prueba concurrente y los bloqueos deben comprobarse
fuera de este entorno. El log final está en
`/private/tmp/catalog-stage3-postgres-final.log`.

Comprobaciones auxiliares, sin sustituir PostgreSQL:

```sh
DATABASE_URL=sqlite:////private/tmp/catalog-stage3-final.sqlite3 .venv/bin/pytest --ds=config.settings.test -q
DATABASE_URL=sqlite:////private/tmp/catalog-stage3-focused.sqlite3 .venv/bin/pytest --ds=config.settings.test apps/catalog/tests/test_stage3.py apps/catalog/tests/test_admin_sections.py apps/catalog/tests/test_photo_management.py -q
.venv/bin/python manage.py check --settings=config.settings.test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

- Pruebas enfocadas después de los últimos ajustes: **54 pasaron y 1 omitida**,
  en 12,20 s. La omisión corresponde a concurrencia de SKU, que requiere PostgreSQL.
- `check`: sin problemas. `makemigrations`: sin cambios pendientes.
- Logs auxiliares: `/private/tmp/catalog-stage3-sqlite-final.log` y
  `/private/tmp/catalog-stage3-focused-final.log`.
- Suite completa auxiliar con SQLite: **799 pasaron, 22 omitidas y 1 fallo**,
  en 56,16 s. El único fallo es `test_ready_reports_dependencies`: Redis no está
  accesible y readiness responde 503. No se alteró ni se simuló esa dependencia.
  SQLite no verifica bloqueos, concurrencia ni restricciones de PostgreSQL.

Ruff de los Python modificados, `git diff --check` y `node --check` de ambos JS:
correctos. Pruebas locales con Node y DOM simulado: seguimiento, evento de estado,
checklist, aviso solo con cambios, conservación del botón enviado y bloqueo del
segundo envío correctos. Scripts auxiliares en
`/private/tmp/catalog-stage3-status-check.cjs` y
`/private/tmp/catalog-stage3-form-check.cjs`. No equivalen a una revisión visual.

## Revisión visual pendiente

No fue posible abrir un navegador real: Chromium se cierra al arrancar dentro del
sandbox y el host del navegador integrado está indisponible. Se comprobó el HTML
renderizado con Django; no se consideran verificadas las pantallas visualmente.

Revisar en escritorio, tableta y celular, con temas claro y oscuro:

1. Etiquetas y selectores sin recortes, tarjeta lateral y estado arriba en celular.
2. Iconos por rol, confirmaciones y enlace a la tienda solo en publicadas.
3. Fotos reales, principal/hover, movimiento con teclado, eliminación autorizada,
   miniaturas locales y quitar archivos de una selección.
4. Procesamiento real con worker: pendiente → lista, checklist y reintento de fallo.
5. Campos ingleses plegados, errores visibles, unidades y precios legibles.
6. Aviso al salir con cambios, guardado único y foco visible.

Ejecutar la suite completa con PostgreSQL y Redis disponibles antes de dar esta
etapa por verificada.

## Commits

`.git` no es escribible en este entorno (`test -w .git` devuelve falso).
Los cambios quedan sin commit. No se crearon scripts de commit ni se hizo push.
El commit posterior debe tener mensaje en español y el pie solicitado:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
