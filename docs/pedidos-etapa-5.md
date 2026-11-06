# Pedidos — Etapa 5: centro de pedidos y avisos del panel

Fecha: 2026-11-06. Rama `fase-9-produccion`. Base: Etapas 1–4 (`d3b5538`, `072af27`, `7b736a6`, `ff3e920`) y lectura de `docs/pedidos-etapa-{1,2,3,4}.md`. La auditoría original de pedidos no está en el checkout; se aplicaron H, D10, D20 y D21 según esta solicitud. Trabajo local, sin red externa, sin push y sin nuevas dependencias.

## Resultado

### Centro y lista de pedidos

Encima de las pestañas aparecen cuatro enlaces: **Cobros aprobados**, **Por preparar**, **Pagos manuales por confirmar** e **Incidencias abiertas**. El período se elige entre Hoy, 7 días, 30 días y Mes actual. Son días de calendario de Bogotá, incluido el día actual, desde medianoche hasta ahora. Los cobros se suman por `paid_at`, exclusivamente con pago aprobado; cancelados y devueltos se identifican aparte dentro de ese importe. No se presentan como ventas ni como ingresos netos.

Los indicadores son globales, independientes de los filtros de la tabla. Cada enlace abre su filtro correspondiente. Incidencias cuenta incidencias, no pedidos; al abrir el enlace un pedido con varias incidencias aparece una sola vez. «Por preparar» exige pago aprobado, estado sin preparar y ninguna incidencia abierta bloqueante. El cálculo completo hace **tres consultas agregadas**, con prueba de presupuesto, sin recorrer pedidos individualmente.

Se conservó la regla real de `metrics.py`: puede ver los importes quien tiene `orders.view_order`. No existe hoy un permiso de finanzas que los limite a Propietario; Operaciones también ve precios y totales en el panel existente. Contenido no accede al centro de pedidos.

Las pestañas conservan filtros de pago activos, búsqueda y demás filtros ordinarios. Sus contadores usan esa misma combinación. «Por preparar» aplica sus condiciones sin sustituir el filtro de pago: por ejemplo, si se combina con pagos pendientes da cero. Cambiar de pestaña sustituye el filtro de etapa del centro y el estado operativo. Se conservan paginación de 20, filtros existentes, `actions_row=()` y «Ver pedido».

La búsqueda incluye referencia del intento `SRT-…-01` e identificador de transacción Wompi. La lista muestra la última tentativa rechazada solo cuando el pedido sigue pendiente, y una insignia de incidencia abierta con tipos en su descripción emergente. La última tentativa se obtiene por subconsulta y las incidencias mediante precarga por página. En celular (≤760 px), las filas usan tarjetas apiladas, siguiendo el patrón del catálogo.

### Tarjeta y piezas retenidas

El aviso superior enumera las incidencias abiertas con su nombre y si bloquean preparación. Se quitó el mensaje genérico adicional del admin. Las secciones siguen el orden Resumen · Cliente · Entrega · Piezas · Pagos · Incidencias · Estado · Comunicaciones · Historial · Notas, manteniendo el estilo y las dos columnas existentes.

Pagos muestra referencias, métodos permitidos en palabras, estados, importes y fechas de creación/actualización de los intentos. Los eventos muestran fecha, estado y resultado en palabras: no se renderizan datos completos recibidos, soportes, datos de tarjeta ni identificadores arbitrarios del proveedor.

«Imprimir / guardar PDF» reemplaza el nombre anterior. La página completa no muestra «Abrir en página completa», tampoco después de guardar por AJAX. Se conserva en el panel lateral.

Una pieza retenida por cancelación ofrece **Volver a poner a la venta** y **Mantener retenida**, con confirmación y permisos comerciales existentes (`catalog.publish_piece` + `catalog.change_piece`; Propietario y Operaciones por defecto). Ambas decisiones quedan en `AuditLog`; volver a disponible agrega además `PieceStatusChange`. El servicio vuelve a comprobar pedido, pertenencia, último cambio vendido → retenido, cancelación y ausencia de reserva activa, dentro de una transacción. Bloquea primero pedido y luego pieza, usando `select_for_update(of=("self",))`. No abre la pieza automáticamente al cancelar.

La ficha del catálogo incorpora «Volver a poner a la venta» usando su página de confirmación existente y el mismo servicio. «Mantener retenida» deja el estado intacto y guarda la decisión; la pieza puede reconsiderarse después.

### Avisos privados del panel

Se agregaron `AdminNotification` y `AdminNotificationReceipt`. La primera representa el evento con clave única; la segunda registra destinatario y fecha de lectura por usuario, con unicidad usuario/aviso. Los destinatarios se fijan al crear el evento: usuarios activos del panel con permiso de ver pedidos. Las incidencias financieras se entregan únicamente a quienes pueden resolverlas. No se generan avisos retrospectivos al migrar ni se reparten avisos antiguos a nuevos usuarios.

Se publican dentro de la transacción de pago aprobado, creación de pedido manual, apertura de incidencia y agotamiento de una entrega de correo/WhatsApp. Los avisos de incidencias también se crean cuando se desactiva el correo externo. Las claves únicas evitan duplicar por reintento del mismo evento. Si la transacción se revierte, desaparecen tanto aviso como destinatarios. Se mantienen los correos y tareas existentes; la campana no depende de su envío ni requiere Channels.

La campana aparece en la barra superior de Unfold y hay enlace «Avisos de pedidos» en la navegación. El panel muestra los últimos 20, contador de no leídos, enlaces a pedidos y «Marcar todo como leído». La página completa pagina de 20 en 20. Leer o marcar avisos de una cuenta no cambia los de otra. Retirar permisos también bloquea el acceso a avisos previamente asignados.

Rutas privadas, relativas al prefijo admin configurado:

- `GET notifications/unread/?since=<id>`: contador, últimos 20 y nuevos entre esos últimos 20.
- `POST notifications/read/`: sesión y CSRF; marca solo hasta el ID máximo ya mostrado, evitando consumir avisos que llegaron después.
- `GET notifications/`: página completa.

La vista JSON hace **tres consultas** para un usuario ordinario: permisos actuales, contador y últimos 20 con sus relaciones. El test mide la vista con un usuario autenticado mediante RequestFactory, sin calentar permisos. Este presupuesto **no incluye** las consultas previas de sesión, autenticación y segundo factor del middleware existente. El JSON solo contiene mensaje fijo, número de pedido, importe cuando corresponde, fecha, estado de lectura, ID del aviso y enlace privado. No contiene nombres, teléfonos, correos, tokens públicos ni datos recibidos de Wompi. La lectura de filas selecciona únicamente las columnas necesarias.

Polling a 45 segundos con documento visible; al ocultarlo se retira el temporizador y al volver se programa el siguiente intervalo. Los fallos aumentan la espera hasta seis minutos; una respuesta de sesión vencida o redirección detiene las consultas. No hay WebSockets ni SSE. La primera carga no dispara toasts históricos. Las siguientes muestran un aviso discreto accesible (`role="status"`); ante varias novedades juntas se muestra la más reciente, mientras el contador incluye todas. Sonido apagado por defecto, con preferencia en localStorage y activación explícita del navegador. El panel gestiona foco, Tab y Esc. Controles de al menos 44 px, números tabulares, modo claro/oscuro y animaciones de transform/opacidad de 180 ms ease-out, desactivadas con movimiento reducido.

### Seguimiento público: HTTP 404

El proxy de Next comprueba el detalle antes de que se inicie la respuesta de React. Un 404 o 410 de la API devuelve directamente un documento HTML localizado con **HTTP 404**, sin token ni datos del pedido y con `no-store, private`, `no-referrer` y noindex. Se evita depender de `notFound()` bajo el Suspense del layout con `cacheComponents`. La respuesta de enlace inválido es una página breve de SERTI con explicación y enlace de vuelta; no carga el catálogo ni el CMS. El seguimiento válido conserva su página y comportamiento existentes. Los alias mantienen su redirección canónica.

Decisión y coste: un seguimiento válido hace una lectura adicional de la API antes del render de la página. Ambas cuentan para el límite existente por IP; no se desactiva el throttle ni se agrega una excepción pública. Un 429 o fallo del servicio no se convierte en 404. Se mantienen las rutas y formas de la API pública. No se almacenan tokens ni se agregan logs de estas comprobaciones.

## Archivos

- Pedidos: `backend/apps/orders/{admin,card_admin,metrics,filters,models,events,incidents}.py`; plantillas `backend/templates/admin/orders/{change_list,card,card_page}.html`; CSS/JS `backend/apps/orders/static/orders/order-card.*`.
- Inventario/catálogo: `backend/apps/inventory/services.py`, `backend/apps/catalog/admin.py`.
- Avisos: `backend/apps/notifications/{models,panel,views,services}.py`, `static/notifications/panel.{css,js}`, `backend/templates/admin/notifications/page.html`, `backend/templates/unfold/helpers/userlinks.html`, `backend/config/urls.py`, `backend/apps/core/dashboard.py`. La configuración Unfold ya consume la navegación de `dashboard.py`; no necesitó cambiar settings.
- Frontend: `frontend/proxy.ts`, `frontend/lib/order-http.ts` y su test.
- Pruebas: `backend/apps/orders/tests/test_stage5.py` y `test_stage5_concurrency.py`.

## Migraciones mínimas

1. `notifications/0007_adminnotification_adminnotificationreceipt.py`: dos tablas nuevas, clave de evento única, relación por usuario, unicidad de lectura y un índice `(user, read_at, notification)` para contador y últimas filas. No modifica correos ni datos históricos.
2. `orders/0007_order_order_payment_paid_at_idx_and_more.py`: índice `(payment_status, paid_at)` para los cobros del período, y un índice parcial de incidencias abiertas por tipo. No agrega estados ni transforma pedidos/piezas.

La reversión de la primera elimina el historial de avisos del panel; respaldarlo si se necesita conservar. Revertir los índices no modifica datos. Las migraciones se verificaron como esquema en SQLite, **no se aplicaron ni comprobaron en PostgreSQL desde este sandbox**.

## Comandos y resultados

Ejecutables de `backend/.venv/bin`, con `DJANGO_SECRET_KEY=local-tests`, `REDIS_URL=redis://localhost:6379/0` y URLs locales de base. No se cargaron secretos del `.env` ni se llamaron proveedores reales.

- **Obligatoria PostgreSQL:** `cd backend && pytest --ds=config.settings.test -q`, `DATABASE_URL=postgres://serti:serti@localhost:5432/serti`: **81 passed, 938 errors**, 103,16 s. PostgreSQL rechaza la conexión con `Operation not permitted` (IPv4/IPv6). **Suite PostgreSQL NO validada**, tampoco bloqueos, concurrencia ni migraciones. Una ejecución anterior dio 80 aprobadas, 928 errores de conexión y un fallo de etiquetas, ya corregido.
- **Completa SQLite, complemento:** mismo comando con `DATABASE_URL=sqlite:////tmp/pedidos5.sqlite`: **992 passed, 26 skipped, 1 failed**, 69,74 s. Único fallo: `apps/core/tests/test_health.py::test_ready_reports_dependencies`, 503 por Redis inaccesible. Las omitidas incluyen las dos nuevas pruebas de concurrencia PostgreSQL: mismo evento simultáneo y dos decisiones simultáneas sobre la pieza. No sustituye PostgreSQL.
- Tras el último ajuste para conservar el modo de página completa al guardar por AJAX y su prueba adicional: `pytest --ds=config.settings.test apps/orders/tests/test_stage5.py -q`: **26 passed**, 6,64 s, SQLite. La suite completa anterior incluía los otros 25 casos de este archivo. Pruebas enfocadas previas de etapa 5, tarjeta y etiquetas: **66 passed**. Las primeras comprobaciones completas detectaron y permitieron corregir etiquetas de modelos y pestaña activa; se conserva únicamente el fallo de salud ajeno a esta etapa.
- `python manage.py check --settings=config.settings.test`: sin problemas.
- `python manage.py makemigrations --check --dry-run --settings=config.settings.test`: **No changes detected** después de generar ambas migraciones.
- Ruff en Python modificado y pruebas nuevas: aprobado. `node --check` de ambos JS: aprobado. `git diff --check`: aprobado.
- Frontend: `npm run lint`, `npm run typecheck` y `npm test`: **aprobados, 44/44 tests**. Incluye mapeo 404/410, exclusión de 429/errores, rutas ES/EN/alias y documento localizado.
- `npm run dev -- --hostname 127.0.0.1 --port 3105`: **bloqueado** por `listen EPERM`. No se pudo revisar la UI en navegador ni probar el HTTP efectivo de Next/Caddy. No se ejecutó build con fuentes remotas porque el trabajo es sin red; la limitación de `next/font` ya está documentada en la Etapa 4. No se ejecutaron los tests de navegador que requieren el stack local.

## Pendientes y revisión visual

1. Con PostgreSQL y Redis accesibles, aplicar migraciones y ejecutar **`cd backend && pytest --ds=config.settings.test -q`**. Revisar las pruebas concurrentes nuevas y los bloqueos con FKs anulables. Confirmar planes de consultas con datos representativos.
2. Probar Propietario, Operaciones, Contenido y concesiones directas. Verificar que Contenido no ve campana/pedidos, Operaciones no recibe incidencias financieras y retirar un permiso corta el acceso histórico. Confirmar lectura independiente con dos cuentas.
3. Escritorio (~1440 px), tablet (~768 px) y celular (~390 px), claro y oscuro: tarjetas de indicadores, período, combinaciones de pestañas/pago/búsqueda, fila como tarjeta sin desplazamiento horizontal, «Ver pedido», lateral, página completa y PDF. Revisar referencias largas e incidencias múltiples, orden de secciones y ausencia del botón redundante incluso después de guardar.
4. Cancelar un pedido vendido, mantener la pieza retenida y luego volver a venderla desde pedido/catálogo; confirmar auditoría, confirmaciones y rechazo si existe reserva activa o la pieza ya cambió. Confirmar que no se libera una pieza por un simple refresco.
5. Abrir campana con teclado, Tab/Shift-Tab/Esc y lector de pantalla. Crear eventos en otra cuenta: esperar 45 s, comprobar contador/toast, sonido apagado/activado, localStorage bloqueado, movimiento reducido y modo oscuro. Ocultar la pestaña y comprobar en herramientas de navegador que deja de programar consultas; simular fallos y sesión vencida. Ante ráfagas de más de 20, consultar la página completa: el desplegable se limita deliberadamente a las últimas 20.
6. Con Next y backend disponibles, consultar con una petición **GET** `/es/pedido/<token-inexistente>` y un token caducado: verificar **HTTP 404**, contenido español, noindex/no-store/no-referrer; repetir en inglés y siguiendo la redirección de alias. Revisar también un token válido (200) y un 429 (no convertido a 404). No registrar ni pegar tokens reales en logs o capturas. Repetir tanto directo a Next como a través de Caddy, y una navegación desde la tienda. Los tests unitarios no prueban la integración real de streaming/proxy.

## Commit

Sin commit: `test -w .git` devuelve falso; `.git` no es escribible desde el sandbox. No se crearon scripts de commit ni se hizo push. Mensaje propuesto para cuando sea escribible:

```text
Completa el centro de pedidos y los avisos privados del panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
