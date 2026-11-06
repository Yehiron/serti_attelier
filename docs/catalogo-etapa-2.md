# Catálogo — Etapa 2: integridad y procesamiento de fotos

Rama `fase-9-produccion`, base `7f69bd0`. Trabajo local, sin red y sin push.
No se modificaron la API pública, Next.js, el diseño de lista/ficha ni los permisos
comerciales de la Etapa 1. No hay migraciones nuevas ni publicación automática.

## Integridad del inline

`services.apply_photo_changes` recibe el conjunto final de fotos y el actor.
Dentro de `transaction.atomic` bloquea primero la pieza y después sus fotos con
`select_for_update(of=("self",))`. Recupera del registro bloqueado el estado,
error, versiones y dimensiones: guardar metadatos no pisa el resultado del worker.

Valida exactamente una principal cuando quedan fotos, como máximo un hover,
principal distinta de hover y posiciones solicitadas sin duplicados. Ordena por
la posición solicitada y normaliza a `0..n-1`. Las posiciones repetidas producen
un error de formulario; los huecos se normalizan.

El guardado tiene dos fases: libera ambas marcas y asigna a cada fila una posición
temporal única en un bloque libre fuera del rango final; después borra las filas
retiradas y escribe posiciones y marcas finales. Busca un bloque libre para
admitir también posiciones antiguas cercanas al límite del entero de PostgreSQL.
Las restricciones existentes siguen activas y no se vuelven diferibles.
Los archivos borrados siguen usando las señales existentes de limpieza tras commit.
Una reversión conserva tanto filas como archivos y deshace la auditoría.

El formset valida el estado final sin contrastar sus posiciones y marcas contra
las filas antiguas durante la validación individual. Esa excepción se limita a
los formularios del inline. Los errores de validación del servicio usan el manejo
de formularios incorporado en la Etapa 1, con reversión de la transacción.
Las subidas múltiples también pasan por el servicio y conservan el tratamiento
independiente de archivos inválidos.

En publicada, la principal final debe estar lista y conservar un archivo ya
procesado: se rechazan una principal pendiente/fallida, sustituir su archivo,
borrarla sin reemplazo listo y borrar la última foto. El mensaje es:

> Esta pieza está publicada: elige como principal una foto que ya esté lista, u oculta la pieza antes de cambiarla.

Se permite subir fotos secundarias y borrar la principal si se elige simultáneamente
otra foto lista. En borrador/oculta puede elegirse una principal pendiente/fallida,
o eliminar todas las fotos; si quedan fotos, debe elegirse una principal.
Contenido puede subir, editar, ordenar y elegir principal/hover, y sigue sin poder
borrar. El servicio comprueba también ese permiso, además del control del inline.

`catalog.photos_updated` registra actor y pieza, con diferencias de `principal`,
`hover`, `orden` y `borradas`, cuando corresponda. Incluye las subidas múltiples.
Se usa `apps.audit.services.record` dentro de la misma transacción.

## Estado, reintento y UI mínima

Rutas relativas al administrador de piezas:

- GET `<pk>/photos/status/`: exige `catalog.view_piece` y la autorización del
  administrador sobre la pieza. Devuelve `photos`, `ready_to_publish` y `missing`.
  Cada foto contiene exclusivamente `id`, `status`, `thumb_url`, `is_primary`,
  `is_hover` y `message`. La miniatura solo procede de versiones listas; nunca
  devuelve el original. Los mensajes usan `admin_presentation`, sin HTML ni el
  campo de error interno.
- POST `<pk>/photos/<image_id>/retry/`: exige CSRF y cambio sobre la pieza.
  Una imagen de otra pieza devuelve 404. Solo `failed` pasa a `pending`, limpia
  su error y encola `tasks.process_piece_image` después del commit, reutilizando
  el archivo guardado. Repetir sobre una pendiente/lista no crea otra tarea.

Ambas rutas están envueltas en `admin_site.admin_view` y respetan el queryset y las
comprobaciones por objeto del administrador. El catálogo actual utiliza permisos
globales; no se añadió un concepto de propietario de pieza o tenant.

El JavaScript vanilla se incluye únicamente desde `PieceAdmin.Media`.
Consulta si hay pendientes, comienza a los 3 segundos, aumenta el intervalo hasta
15 segundos y para al terminar, salir de la página o llegar a unos 3 minutos.
Actualiza miniatura y estado en la fila existente, ofrece «Reintentar» y usa
regiones `aria-live="polite"`. Si las fotos permiten publicar muestra
«Las fotos están listas. Ya puedes publicar.»; si faltan otros datos, solo informa
que las fotos están listas. Al agotar el plazo muestra el mensaje solicitado.

Sin JavaScript, «Reintentar» envía un POST con CSRF desde el formulario actual y
regresa a la pieza; recargar permite consultar el nuevo estado. Se conservó la
vista previa inicial existente del inline. El endpoint de seguimiento no utiliza
esa alternativa del original. No se rediseñaron las plantillas ni las columnas.

Guardar metadatos de una foto pendiente ya existente no vuelve a encolar su tarea.
Las subidas y sustituciones conservan la cola; los fallos tienen reintento explícito.

## Archivos

- `backend/apps/catalog/services.py`: estado final, guardado en dos fases,
  política de publicada, auditoría, subidas múltiples y reintento.
  Los bloqueos directos de `Piece` usan `of=("self",)` para evitar problemas
  de PostgreSQL con joins anulables.
- `backend/apps/catalog/forms.py`: validación final del inline y exclusión
  limitada de comprobaciones contra el estado anterior.
- `backend/apps/catalog/admin.py`: conexión del inline, rutas protegidas,
  estados, botones y carga del JavaScript.
- `backend/apps/catalog/static/catalog/photo-status.js`: seguimiento y reintento.
- `backend/templates/admin/catalog/piece_status.html`: región accesible y URL
  de seguimiento, dentro de la plantilla actual.
- `backend/apps/catalog/tests/test_photo_management.py`: 33 casos nuevos.
- `backend/apps/catalog/tests/test_hover.py`: la prueba de eliminación ahora
  elige principal entre las fotos restantes, conforme a la nueva regla.

Las regresiones cubren POST reales del admin: intercambio 0/1, inversión de tres,
principal anterior/posterior, intercambio con hover, estados finales inválidos,
publicada/borrador/oculta, permisos de Contenido, estado y privacidad, alcance por
pieza, CSRF, tarea tras commit, auditoría, rollback y limpieza de archivos.
El contrato público compara `image`, `hover_image` y `gallery` antes/después de
reordenar: las dos primeras conservan sus valores y la galería sigue el nuevo orden.

## Comandos y resultados

Se usó `backend/.venv/bin`, con `DJANGO_SECRET_KEY=local-test` y
`REDIS_URL=redis://localhost:6379/0`. No se consultaron servicios externos.

Desde `backend`, con `DATABASE_URL='postgresql:///serti?host=/tmp'`:

```sh
.venv/bin/pytest --ds=config.settings.test -q
```

**PostgreSQL no verificable desde este sandbox.** La ejecución final terminó con
73 pruebas pasadas y 734 errores de preparación en 78,69 s. La conexión al socket
`/tmp/.s.PGSQL.5432` falla con `Operation not permitted`. Las 73 pasadas no prueban
el comportamiento transaccional en PostgreSQL. Log:
`/private/tmp/catalog-stage2-postgres-final.log`.

Prueba auxiliar con `DATABASE_URL=sqlite:////private/tmp/catalog-stage2.sqlite3`:

```sh
.venv/bin/pytest --ds=config.settings.test -q
.venv/bin/pytest --ds=config.settings.test apps/catalog/tests/test_photo_management.py apps/catalog/tests/test_hover.py -q
.venv/bin/python manage.py check --settings=config.settings.test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

- Suite completa: **785 pasaron, 21 omitidas y 1 fallo**, en 54,94 s.
  El único fallo es `test_ready_reports_dependencies`: Redis no está accesible y
  readiness devuelve 503. No se alteró esa prueba ni se simuló la dependencia.
- Comprobación enfocada posterior a los últimos ajustes de formulario/presentación:
  **44 pasaron**, en 11,26 s. Incluye las 33 nuevas y las pruebas de hover existentes.
- `check`: sin problemas. `makemigrations`: sin cambios pendientes.
- Ruff sobre los cinco archivos Python modificados: correcto.
- `git diff --check`: correcto.
- `node --check backend/apps/catalog/static/catalog/photo-status.js`: correcto.
- Comprobación local con Node y DOM simulado: polling, backoff, parada a 180 s,
  miniatura, aviso, salida de página y reintento con CSRF correctos. No equivale
  a una verificación visual en navegador real. Script auxiliar en
  `/private/tmp/catalog-stage2-js-check.cjs`.

Logs auxiliares: `/private/tmp/catalog-stage2-sqlite-full.log` y
`/private/tmp/catalog-stage2-focused-final.log`.
SQLite no acredita bloqueos, concurrencia ni restricciones de PostgreSQL.

## Entrega y pendientes

- Ejecutar la suite completa con PostgreSQL y Redis accesibles antes de considerar
  verificada esta etapa en el entorno requerido. Revisar visualmente el inline
  durante un procesamiento real con worker y almacenamiento disponibles.
- Sin commit: `.git` no es escribible en este entorno. No se crearon scripts de
  commit ni se hizo push. La base sigue siendo `7f69bd0` y los cambios quedan en
  el árbol de trabajo. El commit posterior debe estar en español y terminar con:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
