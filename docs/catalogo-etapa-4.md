# Catálogo — Etapa 4

Rama `fase-9-produccion`, base `22dc0f3` (Etapas 1–3).
Trabajo sin red ni push. Sin dependencias nuevas, migraciones, cambios en Next.js
ni en la API pública. Se aplicó la skill `frontend-design` manteniendo el estilo
del administrador y los permisos de las etapas anteriores.

## Categorías desde la pieza

En Clasificación aparece «Nueva categoría» con el icono `add` si la persona tiene
`catalog.add_category`. Con JavaScript se coloca junto al selector; sin JavaScript
abre Añadir categoría del administrador en otra pestaña.

El diálogo nativo es hermano del formulario de pieza: no anida formularios ni
abre otro modal. El navegador contiene el foco y permite cerrar con Esc; × también
cierra y el foco vuelve al enlace que lo abrió. La entrada se enfoca al abrir.
Los controles tienen al menos 44 px y el diálogo usa transform/opacity durante
180 ms ease-out, con alternativa sin animación para movimiento reducido.

`POST /dashboard/catalog/category/quick-add/` es una ruta privada del admin,
protegida por sesión, segundo factor, CSRF y permiso de creación. No modifica
el contrato público. Recibe `name` (español obligatorio) y `parent` opcional,
limitado a raíces activas. Usa `services.save_taxonomy`, que genera un slug libre,
valida el modelo y rechaza nombres repetidos dentro del mismo padre, incluyendo
las raíces. Un nombre igual bajo otro padre puede tener otro slug.

La respuesta es exclusivamente `{id, label}`; el label de una subcategoría es
«Padre → Hijo». Los errores son 400 con `errors` por campo; el diálogo los muestra
junto a su entrada y enfoca el primer campo inválido. Sin permiso devuelve 403.
La creación y `record("catalog.category_created", ...)` comparten transacción.

Al crear, se incorpora y selecciona la opción sin recargar ni tocar los demás
campos de la pieza. Los selectores conservan orden jerárquico por posición; la
opción nueva se añade al final de sus hermanos. Se actualiza Categoría en el
checklist y aparece el aviso discreto. Una raíz recién creada queda disponible
como padre en el mismo diálogo para crear después su subcategoría.
La publicación sigue validándose y guardándose por los servicios existentes.

## Lista y formulario de categorías

La lista muestra miniatura, nombre jerárquico (raíz en negrita, hijo con ↳), padre,
conteo de piezas publicadas asignadas directamente a esa categoría, badge de
actividad e iconos con `aria-label` y título. Ver en la tienda solo aparece si
está activa y usa la ruta existente `/es/joyeria/<slug>`.
El encabezado ofrece Nueva categoría según permiso.

El queryset utiliza `select_related("parent")`, `Count` filtrado por publicada y
orden jerárquico: posición de la raíz, identificador de raíz, nivel, posición e
identificador. `get_ordering` conserva ese orden también en el ChangeList de
Django. Las pruebas comparan la lista pequeña y 23 categorías: menos de 35
consultas en la página y como máximo dos adicionales al crecer.

**Decisión sobre arrastre:** se conserva `ordering_field="position"` de Unfold.
Arrastrar cambia posiciones, nunca el padre; al guardar y recargar, cada hija
vuelve a mostrarse bajo su padre y las posiciones ordenan entre hermanos.
No se ofrece cambiar la jerarquía mediante arrastre. `position` está declarado
explícitamente en `list_display`, aunque Unfold lo oculta, para mantener válidas
las comprobaciones de Django después de abrir la lista.

El formulario de categoría solo ofrece raíces como padre, excluye la propia
categoría y explica con ejemplos cuándo dejarlo vacío. `Category.clean` conserva
la última validación, incluido impedir convertir en hija una raíz con hijas.

## Celular y fotos

A 760 px o menos, CSS transforma las filas existentes de piezas y categorías en
tarjetas. No hay una segunda copia del contenido ni de los controles: se mantienen
los permisos, enlaces, selección y acciones renderizados por Django/Unfold.
Se respeta el `tbody` por registro que utiliza esta versión de Unfold, incluido
su arrastre. La foto ocupa 64 px a la izquierda; nombre y referencia, categoría,
precio según permiso y estados quedan a la derecha, con acciones abajo y selección
arriba a la derecha. Las reglas están limitadas a estas dos listas y al ancho
móvil; no cambian la tabla de escritorio.

El archivo original usa ahora un `FileInput` sencillo dentro del mismo formset.
Se retira el widget técnico con nombre de archivo, descarga y subida de Unfold.
El input conserva nombre, identificador, envío multipart y validación; queda
visualmente oculto y enfocable. Su label «Reemplazar foto» con `swap_horiz` abre
el selector incluso sin JavaScript y muestra foco visible.

Al elegir archivo se muestra su vista previa local y «Nueva — se guarda al
guardar». El seguimiento del worker no pisa esa vista previa. Se liberan las URL
temporales al sustituir el archivo o salir; si la selección se vacía se restaura
la vista anterior. El servicio de guardado de fotos y sus bloqueos
`select_for_update(of=("self",))` permanecen intactos.

Se reemplaza el botón grande de la primera tarjeta por una única acción pequeña
«Quitar efecto al pasar el mouse», fuera de las tarjetas y visible solo si hay una
foto con ese efecto. Su espacio está reservado para evitar que salte la cuadrícula.
La descripción española se etiqueta «Descripción de la foto (para accesibilidad
y Google)». El inglés queda junto a ella como «Descripción en inglés (opcional)»:
se conserva el renderizado traducido del inline y todos sus errores.

## Archivos

- `backend/apps/catalog/admin.py`: CategoryAdmin, endpoint, contexto de la ficha.
- `backend/apps/catalog/forms.py`: formularios, selector jerárquico y archivo simple.
- `backend/apps/catalog/services.py`: nombre duplicado y slug de categorías.
- `backend/apps/catalog/static/catalog/catalog-admin.{css,js}`: diálogo, checklist,
  tarjetas móviles, selección de archivos y acción de quitar hover.
- `backend/apps/catalog/static/catalog/photo-status.js`: conserva la preview local.
- `backend/templates/admin/catalog/category/change_list.html`: encabezado.
- `backend/templates/admin/catalog/piece/{change_form,category_link,category_dialog}.html`:
  incorporación del diálogo y alternativa sin JavaScript.
- `backend/templates/admin/catalog/photo_grid.html`: reemplazo accesible de archivo.
- `backend/apps/catalog/tests/test_stage4.py`: regresiones de esta etapa.

## Comandos y resultados

Se usó `backend/.venv/bin`, con `DJANGO_SECRET_KEY=local-test` y
`REDIS_URL=redis://localhost:6379/0`. Desde `backend`:

```sh
DATABASE_URL='postgresql:///serti?host=/tmp' .venv/bin/pytest --ds=config.settings.test -q
DATABASE_URL=sqlite:////private/tmp/stage4.sqlite3 .venv/bin/pytest --ds=config.settings.test -q
DATABASE_URL=sqlite:////private/tmp/stage4-focused.sqlite3 .venv/bin/pytest --ds=config.settings.test apps/catalog/tests/test_stage4.py -q
.venv/bin/python manage.py check --settings=config.settings.test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

**PostgreSQL no está accesible desde este sandbox.** Conectar al socket
`/tmp/.s.PGSQL.5432` devuelve `Operation not permitted`. No se considera
verificado el comportamiento en PostgreSQL, incluidos bloqueos y concurrencia.

- Suite completa auxiliar con SQLite: **804 pasaron, 22 omitidas y 1 fallo**,
  en 57,90 s. El fallo es `test_ready_reports_dependencies`, porque Redis no está
  accesible y readiness devuelve 503. No se modificó esa prueba.
- Las cinco pruebas nuevas: **5 pasaron**, en 5,09 s. Cubren raíz, subcategoría,
  tercer nivel, duplicado, nombre vacío, permiso, CSRF real, auditoría, botón,
  orden, conteo, crecimiento de consultas, padre e intercambio de archivo vía POST.
- `check`: sin problemas. `makemigrations --check --dry-run`: sin cambios.
- Ruff, `git diff --check` y `node --check` de ambos JS: correctos.
- DOM simulado con Node: diálogo (errores, selección, checklist, devolución de foco
  y nueva raíz disponible); conservación de cambios y doble envío; seguimiento,
  espera progresiva, parada y reintento con CSRF: correctos. No sustituye navegador.

Logs: `/private/tmp/catalog-stage4-sqlite-final.log`,
`/private/tmp/stage4-final-focused.log` y
`/private/tmp/catalog-stage4-postgres-final.log`.
Scripts de comprobación auxiliar en `/private/tmp/catalog-stage4-dialog-check.cjs`,
`/private/tmp/catalog-stage4-status-check.cjs` y
`/private/tmp/catalog-stage3-form-check.cjs`.

La ejecución final completa con PostgreSQL terminó con **73 pruebas pasadas y
754 errores de preparación**, en 83,17 s. Las 73 pasadas no prueban operaciones
de base de datos del catálogo. SQLite solo es una comprobación auxiliar.

## Revisión visual y entrega

El navegador integrado devuelve `The browser access host is unavailable`; no se
considera realizada la revisión visual real. El HTML se verificó con las respuestas
del administrador en las pruebas. Revisar en escritorio (1440 px), tableta (768 px)
y celular (390 px), con tema claro y oscuro:

1. Crear raíz y subcategoría sin perder texto, precios ni fotos seleccionadas;
   comprobar errores, Esc/×, recorrido del foco y retorno al enlace.
2. Reabrir el diálogo y crear una hija de la raíz recién creada; comprobar aviso
   y marca de Categoría. Confirmar que sin permiso no aparece el acceso.
3. Revisar categorías juntas, contador, iconos y arrastre entre hermanos;
   recargar para comprobar que las hijas siguen bajo su padre.
4. Revisar tarjetas móviles sin scroll horizontal, foto de 64 px, referencia,
   precio según rol, estados, acciones y selección. Confirmar escritorio intacto.
5. Reemplazar una foto, revisar etiqueta y vista previa, guardar y comprobar
   procesamiento real con worker; el seguimiento no debe pisar la selección local.
6. Quitar el efecto al pasar el mouse; comprobar las descripciones española e
   inglesa, teclado, foco visible y alternativa con JavaScript deshabilitado.

Ejecutar de nuevo la suite completa con PostgreSQL y Redis accesibles antes de
considerar verificada esta etapa en el entorno requerido.

`.git` no es escribible (`test -w .git` devuelve falso). Los cambios quedan sin
commit. No se crearon scripts de commit ni se hizo push. El commit posterior debe
estar en español e incluir:

```text
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

Comprobación enfocada final tras los ajustes de orden y formulario:

```sh
DATABASE_URL=sqlite:////private/tmp/stage4-check.sqlite3 .venv/bin/pytest --ds=config.settings.test apps/catalog/tests/test_stage4.py apps/catalog/tests/test_stage3.py apps/catalog/tests/test_photo_management.py apps/orders/tests/test_card.py::test_list_pagination_tabs_search_and_check -q
```

**53 pasaron y 1 omitida**, en 12,66 s. La omisión requiere PostgreSQL.
Incluye la comprobación de Django después de utilizar la lista de categorías.
Log: `/private/tmp/catalog-stage4-focused-final.log`.
