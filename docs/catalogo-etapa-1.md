# Catálogo: seguridad y reglas de operación — Etapa 1

Rama: `fase-9-produccion`. Sin push, sin consultas externas y sin cambios en
la API pública, Next.js, el diseño ni las columnas de las piezas.

## Cambios por tarea

1. **Permisos.** Se incorpora `catalog.publish_piece` a Propietario y Operaciones.
   Contenido pierde `catalog.add_piece`. Las acciones comerciales requieren tanto
   cambio como el permiso comercial, con comprobación al mostrar y al ejecutar;
   duplicar exige además crear, y borrar exige además eliminar.
   Django combina los permisos declarados de acciones con OR: por eso
   `has_commercial_permission` exige ambos y `get_actions` filtra explícitamente.
   También hay protección en los servicios comerciales, incluida preventa.
   El POST de «Guardar y publicar» se rechaza antes de guardar si falta permiso.

   Se mantienen los permisos anteriores de colecciones, categorías, piedras y
   materiales: permiten administrar clasificación, textos y portadas, sin crear
   piezas ni cambiar su estado editorial. Contenido sigue sin borrar fotos.
   Los precios siguen visibles y de solo lectura.

   Los grupos existentes se actualizan mediante el mecanismo ya existente:
   `accounts.apps.sync_after_migrate` llama a `sync_roles`, crea los permisos de
   todas las aplicaciones y reemplaza los permisos de cada grupo gestionado.
   El comando `manage.py sync_roles` permite repetir esa sincronización.
   No hace falta otra migración de datos.

2. **Transiciones.** Matriz única en `catalog/services.py`, validada con la pieza
   bloqueada en la base. Detalle, lote y «Guardar y publicar» usan esos servicios.

   | Origen | Destinos permitidos |
   |---|---|
   | Borrador | Publicada, archivada |
   | Publicada | Oculta, archivada |
   | Oculta | Publicada, archivada |
   | Archivada | Ninguno |

   Archivada es terminal también para superusuarios. No se añade restauración.
   «Volver a publicar» exige que la pieza esté oculta; «Publicar» acepta borrador
   u oculta. No se permiten transiciones al mismo estado.
   Los servicios internos que ya usaban `actor=None` conservan esa vía de sistema;
   no se expone como autorización del administrador.

3. **Lotes.** Cada cambio comercial se ejecuta en una transacción por pieza.
   El mensaje resume cuántas cambiaron y enumera los SKU que fallaron con sus
   motivos. La publicación distingue una foto principal pendiente de procesar.

4. **Borrado.** Se bloquea y comprueba todo el lote antes de borrar la primera
   pieza. Un fallo impide borrar todas. Se exige borrador y ausencia de pedidos,
   reservas e historial de inventario. Vendida o reservada se rechaza
   explícitamente, incluso si su estado editorial es borrador.
   La acción estándar de borrado pasa primero por esa prevalidación.
   El detalle también comprueba si la pieza se puede eliminar.

5. **Duplicado.** Detalle y lista abren la nueva copia y muestran su nombre, SKU
   y la indicación de agregar fotos. En la lista se exige seleccionar una sola
   pieza para que el destino sea inequívoco. Las fotos siguen sin copiarse.

6. **Errores de formulario.** Los errores de validación o dominio durante
   `save_model`, `save_related` o `save_formset` revierten las escrituras y vuelven
   al formulario enviado. Se asignan al campo cuando existe o a los errores
   generales. La denegación de precio del servicio también se convierte en error
   del formulario. Se prueba la relación consigo misma y errores en los tres
   puntos de guardado.

7. **Guardar y publicar con fotos pendientes.** Guarda los datos y las fotos,
   conserva el borrador y muestra:
   «Se guardó como borrador. Las fotos se están procesando; podrás publicar en
   unos segundos.» Se cubre creación y edición. No se programa publicación futura.

8. **Confirmaciones.** Identifican la pieza por nombre y explican qué pasará al
   publicar, ocultar, volver a publicar, archivar, duplicar o cambiar la preventa.

## Archivos

- `backend/apps/accounts/roles.py`: permisos de los grupos.
- `backend/apps/catalog/models.py`: permiso comercial en Meta.
- `backend/apps/catalog/migrations/0008_piece_commercial_permission.py`:
  solo `AlterModelOptions`; no añade ni modifica columnas.
- `backend/apps/catalog/services.py`: matriz, autorización, publicación,
  prevalidación de borrado y duplicado.
- `backend/apps/catalog/admin.py`: permisos, lotes, formularios, mensajes y destinos.
- `backend/apps/inventory/services.py`: autorización y bloqueo de preventa archivada.
- `backend/templates/admin/catalog/confirm_action.html`: confirmaciones.
- `backend/apps/catalog/tests/test_operating_rules.py`: nuevas regresiones.
- `backend/apps/core/tests/test_dashboard_client.py`: Contenido ya no ve el acceso
  para agregar y recibe 403 en creación; conserva precios legibles.
- `backend/apps/core/tests/test_one_page_actions.py`: duplicar redirige a la copia.
- `backend/apps/orders/tests/test_operations.py`: Contenido ya no puede duplicar;
  prueba real de prevalidación de piezas con pedidos.

No se editaron `orders/metrics.py` ni `templates/admin/index.html`: ya
condicionaban «Agregar pieza» a `catalog.add_piece`; las pruebas verifican su efecto.

## Validación local

Se utilizó `backend/.venv/bin` porque Python y pytest no estaban en PATH.
Variables de prueba: `DJANGO_SECRET_KEY=local-test`,
`REDIS_URL=redis://localhost:6379/0` y la URL de base indicada abajo.

- Desde `backend`, `pytest --ds=config.settings.test -q`, usando
  `DATABASE_URL=postgresql:///serti?host=/tmp`: **73 pasaron, 600 errores de
  preparación de base**. El entorno devuelve «Operation not permitted» al
  conectar con el socket local de Postgres. Esta ejecución ocurrió antes de
  terminar de incorporar todas las regresiones.
- Misma suite con `DATABASE_URL=sqlite:////private/tmp/catalog-stage1.sqlite3`:
  **752 pasaron, 21 omitidas y 1 fallo**, en 51,01 segundos.
  El fallo es `test_ready_reports_dependencies`: Redis no está accesible y
  readiness responde 503. No se modificó ese test para ocultar la dependencia.
- Después de los últimos cambios de servicios y de las pruebas reales de
  reservas/pedidos, se ejecutaron catálogo completo, acciones y panel del
  administrador, operaciones de pedidos e inventario:
  **326 pasaron y 17 omitidas**, en 36,19 segundos.
  Doce omisiones corresponden a combinaciones sin ruta: «Guardar y publicar»
  solo tiene destino publicada; las restantes requieren Postgres.
- `manage.py check --settings=config.settings.test`: sin problemas.
- `manage.py makemigrations --check --dry-run --settings=config.settings.test`:
  sin cambios pendientes.
- Ruff sobre los archivos Python modificados y `git diff --check`: correctos.

Los logs de ejecución quedan en `/private/tmp/catalog-stage1-*.log`.

## Pendientes de entorno y entrega

- Ejecutar la suite final con Postgres y Redis accesibles; SQLite no prueba
  bloqueos ni concurrencia de Postgres.
- Aplicar la migración durante el despliegue para crear el permiso y sincronizar
  los grupos existentes.
- `.git` no es escribible en este entorno: cambios sin commit. No se crearon
  scripts de commit y no se hizo push.
