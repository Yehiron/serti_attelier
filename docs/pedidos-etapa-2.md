# Pedidos — etapa 2

Fecha: 2026-11-06. Rama: `fase-9-produccion`. Base: etapa 1, `d3b5538` y `docs/pedidos-etapa-1.md`. Trabajo local, sin red, sin push. No se modificaron Next.js ni las rutas, campos o formatos de la API pública.

## Cambios y decisiones

### Avisos durables (D2)

Los eventos crean `NotificationDelivery` dentro de la transacción de negocio. `on_commit` solo publica el ID mediante `dispatch`; no contiene la creación del aviso. Se conserva el estado pendiente existente, `queued`, sin agregar otro estado equivalente.

Se reutiliza la clave única existente de la entrega: pedido, evento, canal y audiencia. Los avisos de estados incorporan el ID de `OrderStatusChange`; los de incidencias, el ID de `OrderIncident` y, al resolver, el sufijo de resolución. Los eventos únicos conservan sus claves anteriores. Esto permite volver a abrir una incidencia sin perder su nuevo aviso y evita duplicados al repetir un webhook.

`enqueue` comprueba que existan las plantillas de correo. `events._notify` aísla la operación en un savepoint: ante un fallo, conserva el pago, registra únicamente ID de pedido, evento y clase de excepción, y abre una incidencia operativa no bloqueante para revisar el aviso. Esa incidencia de respaldo no vuelve a intentar notificar, evitando recursión. Si tampoco se puede persistir la incidencia, queda un log de error sin PII.

`retry_due` recoge tanto fallidas como pendientes, incluso pendientes nunca despachadas con fecha nula. Un broker caído deja las filas en la base; el beat existente (`retry_failed`) las vuelve a publicar. No se necesita otro scheduler ni otra tabla de outbox. Se conserva la semántica de envío existente: no se garantiza entrega exactamente una vez frente a una caída después de que el proveedor haya aceptado el correo.

Se aplicó a pago aprobado, instrucciones manuales, vencimiento, atención y cambios operativos. Se agregaron avisos internos de cancelación y resolución; se reutiliza la plantilla interna y se añadieron sus títulos. No se editaron las plantillas ni los textos estáticos de los correos existentes. El motivo dinámico de atención ahora identifica la incidencia abierta.

### Cancelación coordinada (D3)

`orders.services.cancel_order(order, *, actor, reason, notify, expected_status)` es la única operación de cancelación. Verifica `orders.cancel_order`, motivo de 5–2000 caracteres, estado esperado y origen sin preparar/en preparación; rechaza pedidos que ya registren envío. Bloquea el pedido y después las piezas en orden de ID, como la aprobación del pago.

- Libera todas las reservas activas del pedido con `release_reservation`.
- Si la pieza estaba vendida a este pedido, cambia `sold → reserved`, limpia `sold_at`, cierra sus reservas convertidas y registra `PieceStatusChange`. **No vuelve a disponible.** Se reutiliza `reserved`: queda fuera de venta, sin reserva activa que el vencimiento pueda liberar. No hace falta un estado ni una migración de inventario. Su revisión y eventual disponibilidad requieren una decisión posterior de la dueña; esta etapa no incorpora una acción para publicarla automáticamente.
- Pago aprobado: crea «Devolución de dinero pendiente». No hay reembolso automático.
- Guarda el motivo y responsable en `OrderStatusChange` y `AuditLog`.
- Aviso al cliente opcional; aviso interno de cancelación siempre registrado.
- Rechaza crear/reutilizar un intento Wompi y confirmar pago manual sobre cancelados. Tampoco ofrece checkout/reintento para esos pedidos. Se conserva el esquema público de errores.
- Una aprobación tardía de un pago pendiente conserva el dinero aprobado y `paid_at`, no vende ni reserva piezas y abre «Pago recibido en pedido cancelado». Webhook y conciliación pasan por el mismo servicio.
- La tarea de vencimiento excluye cancelados para no mandar después un correo contradictorio de reserva vencida.

La tarjeta llama al servicio. **Se quitó cancelar del lote**, incluida la acción de detalle que usa ese formulario: el motivo y la confirmación se realizan en la tarjeta individual. Un POST manipulado tampoco habilita cancelar desde el lote.

### Preparar y enviar (D4, D5, D22)

`transition_status` bloquea una copia actual del pedido y compara `expected_status` antes de validar la transición. Tarjeta y lote pasan ese valor. Si otro administrador ya cambió el estado, devuelve «El pedido cambió, recarga.».

Antes de preparar **y nuevamente antes de enviar**, exige pago aprobado, ausencia de incidencias abiertas bloqueantes y piezas vendidas con reservas convertidas pertenecientes a este pedido. También rechaza pedidos sin piezas. Los errores distinguen pago anulado, falta de aprobación, incidencia (con su tipo) y piezas ajenas/no vendidas. Al enviar sigue exigiéndose transportadora; guía y enlace son opcionales. Los campos ya existían y se reutilizan, sin migración de envío.

VOIDED después del envío conserva el estado operativo, actualiza el financiero a anulado y abre «Pago anulado tras el envío». Antes del envío abre una incidencia financiera de evento sospechoso con detalle fijo sobre la anulación. Un pedido en preparación con VOIDED no puede enviarse.

### Incidencias (D9)

`OrderIncident` registra tipo, abierta/resuelta, bloqueo, detalle, creación, responsable y resolución con nota y responsable. Una restricción única parcial inmediata impide dos incidencias abiertas del mismo tipo para un pedido. Los servicios bloquean el pedido para coordinar creación/resolución y sincronizan `needs_attention` con la existencia de cualquier incidencia abierta, aunque no bloquee. La API, métricas y filtros siguen leyendo el campo compatible.

Todos los puntos de pagos que antes escribían `needs_attention=True` usan ahora el tipo correspondiente. Una discrepancia entre evento recibido y respuesta canónica también abre «Evento de pago sospechoso» cuando la referencia canónica identifica un intento. No se vende por esa discrepancia.

Permisos, independientes de nombres de grupo:

| Operación | Permiso | Asignación inicial |
| --- | --- | --- |
| Cancelar | `orders.cancel_order` | Propietario |
| Resolver cualquiera de los seis tipos financieros | `orders.resolve_payment_incident` | Propietario |
| Abrir una incidencia manual «Otra» | `orders.add_orderincident` | Propietario y Operaciones |
| Resolver «Otra» | `orders.resolve_operational_incident` | Propietario y Operaciones |

Se conserva el permiso general de cambiar pedido para las acciones HTTP de la tarjeta. La asignación inicial vive en `accounts.roles`; la autorización de los servicios usa `has_perm`. El mecanismo existente `sync_roles` también se ejecuta al migrar y aplica esos valores por defecto; ejecutarlo de nuevo restablece las asignaciones del catálogo de roles. Las concesiones directas a usuarios permiten configurar excepciones sin cambiar nombres de grupo.

La tarjeta incluye una lista simple de incidencias, fechas, responsables, detalle y resolución. Abrir exige detalle de 5–2000 caracteres; resolver exige nota de 5–2000 y una casilla de confirmación. El aviso interno de resolución es opcional. Los campos piden expresamente no incluir datos de tarjeta. Ambas operaciones quedan auditadas; no se agregaron formularios públicos ni otro panel.

### Lote (D8)

Cada pedido pasa por la misma transacción y validaciones del servicio usado por la tarjeta. La página intermedia conserva un estado esperado por ID y agrega «Avisar al cliente», inicialmente desmarcado. El resultado muestra cuántos se actualizaron y los números y motivos de los fallidos, sin revertir los pedidos correctos. El lote no permite cancelar.

## Archivos

- `backend/apps/orders/{models,services,events,forms,admin,card_admin}.py`: modelo, reglas, cancelación, avisos y acciones existentes.
- Nuevo `backend/apps/orders/incidents.py`: creación, resolución, permisos, auditoría y sincronización del indicador.
- `backend/apps/payments/services.py`: incidencias, rechazo de pagos nuevos y aprobación tardía sobre cancelados.
- `backend/apps/notifications/{models,services,rendering}.py`: evento interno, claves por evento de dominio, validación de plantillas, recuperación de pendientes y títulos internos. `tasks.py` mantiene el beat existente.
- `backend/apps/accounts/roles.py`: permisos por defecto.
- `backend/templates/admin/orders/{card,fulfillment}.html` y `backend/apps/orders/static/orders/order-card.js`: controles mínimos con las clases actuales y envío del formulario de incidencias dentro de la tarjeta.
- Nuevos `backend/apps/orders/tests/{test_stage2,helpers}.py`, ampliación de `test_concurrency.py` y adaptación de los tests anteriores de tarjeta, estados, operaciones y eventos canónicos a las nuevas precondiciones. No se debilitaron las reglas para conservar fixtures que daban por preparado un pedido sin piezas vendidas.

## Migraciones mínimas

1. `orders/0006_alter_order_options_orderincident.py`: permisos del pedido, tabla de incidencias y restricción parcial única **no diferible**. Importa cada pedido existente con `needs_attention=True` como «Otra» abierta y bloqueante, con el detalle exacto «Incidencia previa a la actualización». La importación es idempotente. La operación inversa de datos es `noop`; revertir el esquema elimina la tabla y no conserva su historial, por lo que no debe usarse como procedimiento de devolución de dinero.
2. `notifications/0005_alter_notificationdelivery_event.py`: incorpora `incident_resolved` a las opciones del evento; no agrega columnas ni cambia filas previas.

No se agregaron campos a inventario, pagos ni envío. Los bloqueos nuevos y los del servicio de transición usan `select_for_update(of=("self",))`, evitando bloquear relaciones anulables. No se introdujeron constraints diferibles.

## Verificación

Se usaron los ejecutables de `backend/.venv/bin` con `DJANGO_SECRET_KEY=local-tests`, `REDIS_URL=redis://localhost:6379/0` y una URL local de base de datos. No se cargaron secretos ni se hicieron consultas a Wompi. Los tests existentes bloquean la red de Wompi y usan mocks.

- Comando solicitado: `cd backend && pytest --ds=config.settings.test -q`, con `DATABASE_URL=postgres://serti:serti@localhost:5432/serti`: **81 passed, 833 errors** (88,15 s). Todos los errores de base se deben a PostgreSQL inaccesible: `Operation not permitted` contra localhost IPv4/IPv6. **No se verificó la suite en PostgreSQL**, ni concurrencia, bloqueos o aplicación real de las migraciones allí.
- Suite completa complementaria SQLite, con `DATABASE_URL=sqlite:////tmp/pedidos2.sqlite` y el mismo comando: **890 passed, 23 skipped, 1 failed** (61,47 s). El único fallo es `apps/core/tests/test_health.py::test_ready_reports_dependencies`: devuelve 503 porque Redis no es accesible, igual que en la etapa 1. Las omitidas incluyen las que requieren PostgreSQL. SQLite no sustituye la prueba requerida en PostgreSQL.
- `python manage.py makemigrations --check --dry-run --settings=config.settings.test`: **No changes detected** con SQLite. Generar las migraciones con PostgreSQL también informó la imposibilidad de comprobar su historial por el acceso bloqueado.
- `python manage.py check --settings=config.settings.test`: **System check identified no issues**.
- Ruff sobre pedidos, pagos, notificaciones y roles: **All checks passed**. Formato aplicado a los Python editados.
- `git diff --check`: sin errores.

Las pruebas nuevas incluyen persistencia del aviso dentro de la transacción sin ejecutar hooks, repetición del webhook sin duplicar avisos, broker caído recuperado por beat, plantilla inexistente sin revertir el pago, cancelación con/sin permiso y motivo, reservas liberadas, pieza vendida retenida, pagos nuevos bloqueados, devolución pendiente, aprobación tardía, reglas de preparar/enviar, VOIDED tras envío, deduplicación y resolución de incidencias, sincronización del indicador, función de migración usando modelos históricos, confirmación HTTP, resultado parcial y estado esperado en lote. La nueva prueba PostgreSQL enfrenta dos administradores con una barrera: debe quedar un solo cambio y el otro recibir «El pedido cambió, recarga.».

## Pendientes y revisión visual

1. En un entorno con PostgreSQL y Redis accesibles, ejecutar `python manage.py migrate` y **`cd backend && pytest --ds=config.settings.test -q`**. Revisar especialmente `test_two_admins_one_status_winner`, las demás pruebas `postgres` y la migración sobre una copia de datos previos con pedidos marcados para atención.
2. Confirmar worker y beat activos. Simular broker caído y comprobar que, al recuperarse, el beat publica las entregas pendientes; usar proveedores simulados.
3. Con Propietario, cancelar un pedido pendiente y uno pagado: motivo obligatorio, confirmación, opción de correo, historial, incidencia de devolución y pieza pagada que queda reservada. Con Operaciones, verificar que cancelar y resolver incidencias financieras no se ofrecen y que un POST directo devuelve 403.
4. Abrir y resolver «Otra» desde la tarjeta lateral y la página completa; revisar fechas, responsables, nota, casilla de confirmación y aviso interno opcional. Comprobar que desaparece el indicador solo al resolver la última incidencia abierta.
5. Intentar preparar con pago anulado/incidencia bloqueante y enviar sin transportadora. Comprobar guía opcional y errores legibles. Abrir el mismo pedido en dos ventanas y confirmar que la segunda recibe el aviso de recarga.
6. Probar un lote mixto con y sin «Avisar al cliente», revisar el resumen y que cancelar no esté en las opciones. Comprobar que las nuevas secciones no introduzcan formularios ni botones en impresión. No se realizó una comprobación visual en navegador durante esta etapa; sí se probaron las respuestas HTML y permisos mediante Django.

## Commits

Sin commit: `.git` no es escribible desde este sandbox (`test -w .git` devuelve falso). Se dejaron los cambios locales, sin scripts de commit y sin push. Mensaje propuesto: `Implementa reglas de pedidos, cancelación coordinada e incidencias durables`, con el trailer solicitado:

`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
