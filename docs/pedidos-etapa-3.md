# Pedidos — etapa 3

Fecha: 2026-11-06. Rama: `fase-9-produccion`. Base consultada: Etapas 1 (`d3b5538`) y 2 (`072af27`), especialmente `docs/pedidos-etapa-2.md`. Trabajo local, sin red externa y sin push. No se modificaron la API pública ni Next.js. La auditoría original de pedidos no aparece como archivo en este checkout; se implementaron los puntos D15–D18 descritos en la solicitud y las garantías documentadas de la Etapa 2.

## Correos y eventos

- Layout común HTML con tabla de hasta 600 px, estilos inline y alternativa de texto. Componentes compartidos para piezas, referencias, precios, totales en COP y dirección. Todos los importes aparecen, incluidos descuento, envío y certificado en cero; no se afirma que el envío sea gratis independientemente del valor guardado.
- Saludo con nombre, número, estado financiero y operativo en palabras, enlace de seguimiento con `public_token`, contacto configurado y pie legal breve. No se imprime el teléfono del cliente, tampoco en correos internos. Sin contacto configurado se omiten sus enlaces. El logo usa `/brand/monogram-email.png` bajo `PUBLIC_SITE_URL` absoluto HTTP(S); sin URL se muestra texto SERTI. La imagen ya existe en el sitio público; no se duplicó ni modificó Next.js.
- Variante interna sin saludo de cliente, identificada como comunicación del equipo y con botón al pedido del dashboard. Incidencias abiertas/resueltas reciben el tipo legible del incidente específico en metadatos, evitando inferirlo de otra incidencia abierta al enviar. Se conserva la opción existente de avisar a SERTI al resolver una incidencia.
- Asuntos `SERTI · Pedido SRT-000123 · <estado>` y equivalente inglés. Tanto cliente como equipo usan el idioma del pedido.
- Nuevo `order_received`: solo desde la aplicación de una respuesta canónica Wompi `PENDING`, con pedido Wompi aún pendiente y no cancelado. No se emite al crear pedido/intento ni para pago manual; clave única por pedido, sin aviso interno. Webhook y conciliación comparten el servicio y la deduplicación.
- `order_paid`: pago aprobado con `paid_at`, sin usar la fecha de creación ni afirmar que ya se prepara. Indica que avisaremos al comenzar. Preparación, envío, entrega, cancelación y vencimiento comparten el resumen completo. Envío muestra transportadora, guía y rastreo cuando existen. El correo manual describe instrucciones y confirmación futura del pago; su pie no dice «confirmación de compra».
- Nuevo `payment_issue`: se registra automáticamente, dentro de la transacción de apertura, solo para `no_piece` y `cancelled_payment`. Usa `incident:<id>` en la clave; repetir la apertura no duplica, reabrir después de resolver crea un aviso nuevo. Texto al cliente: «Recibimos tu pago y lo estamos revisando; te contactaremos en menos de 1 día hábil». Las demás incidencias solo avisan al equipo.
- Cancelación: la casilla «Incluir motivo en el correo de cancelación» comienza desmarcada. Solo el motivo expresamente autorizado se copia a metadatos del aviso al cliente; no se reconstruye desde notas internas. La decisión también queda en auditoría. Si había pago aprobado o `paid_at`, añade el mensaje de devolución, sin automatizar reembolsos.

Los avisos siguen persistiendo en la transacción de negocio. `on_commit` solo despacha, y el beat existente recupera pendientes/fallos. No se cambió ese mecanismo ni se añadieron colas nuevas.

## Historial, contenido guardado y acciones

Una columna JSON `NotificationDelivery.payload` conserva metadatos mínimos del evento, destinatario enmascarado y el contenido renderizado (asunto, HTML, texto, reply-to) al primer intento de correo. Los reintentos y copias reutilizan ese contenido. Cambiar después la dirección de entrega o la plantilla no altera la vista del mensaje enviado. Este contenido contiene nombre, dirección y token: debe recibir la misma protección y política de retención que los datos privados del pedido.

La sección «Comunicaciones» utiliza las clases actuales de la tarjeta, sin rediseño: cronología ascendente por fecha e ID, evento legible, canal, cliente/SERTI, correo enmascarado, estado, intentos, fecha de creación/aceptación y error resumido. Nunca muestra el texto crudo del último error; códigos desconocidos o antiguos se convierten a una explicación genérica.

- `sent` se presenta como **Aceptado por el proveedor** en la tarjeta y en el administrador de notificaciones. Significa aceptación SMTP/Meta, no entrega al buzón o al teléfono. No se integraron recibos de entrega; pueden añadirse después con eventos verificados del proveedor y estados separados.
- WhatsApp `log` termina en `skipped` con `whatsapp_simulation`, visible como **Omitido · Simulación**, sin llamada al proveedor ni `sent_at`. Se reutiliza el estado existente porque no hubo envío real; no hace falta otro estado de base de datos.
- Reenviar admite `failed`, `gave_up` y omitidos por falta/configuración/simulación cuando el canal ya está disponible. La reconfiguración explícita actualiza huella y etiqueta del destinatario, con auditoría del estado, intentos previos y decisión de reconfigurar. `recipient_changed` sigue requiriendo revisión y no permite redirigir automáticamente un aviso.
- Reenviar y copiar exigen `notifications.resend_notificationdelivery` en el servicio y la vista; la tarjeta exige además poder ver el pedido. La confirmación es obligatoria en el POST. Se conserva CSRF del admin y solo se muta mediante POST. Ambas acciones quedan auditadas como `notifications.resent` y `notifications.copied`.
- «Enviar copia al cliente» solo admite correos al cliente aceptados. Crea una entrega nueva y una clave de evento derivada `...:copy:1..3`; el máximo se aplica a toda la familia, incluso copiando una copia. Bloquea el pedido con `select_for_update(of=("self",))` antes de contar, para serializar peticiones concurrentes. No agrega otro permiso.
- «Ver correo» abre HTML en ventana nueva y exige permiso de ver pedidos; la entrega debe pertenecer a ese pedido y ser correo. Devuelve el contenido guardado o el que se enviaría, con CSP sandbox, sin scripts, sin caché y sin referer.

**Límite histórico:** las entregas anteriores a esta etapa no almacenaban HTML. No es posible recuperar el contenido exacto que enviaron. La tarjeta lo advierte expresamente y su vista se reconstruye con las plantillas/datos actuales. Las copias de esos mensajes también usan esa reconstrucción. No se fabricaron snapshots retrospectivos. Para destinatarios antiguos sin etiqueta, solo se muestra el correo actual si su huella coincide; si cambió, se indica que el destinatario anterior no es recuperable.

## Archivos y migración

- `backend/apps/notifications/{models,services,rendering,adapters}.py`: eventos, estados legibles, contenido guardado, simulación, reenvío y copias. `tasks.py` y `admin.py` se revisaron; conservan el dispatch/beat y consumen las nuevas etiquetas y reglas compartidas.
- Nuevo `backend/apps/notifications/presentation.py`: etiquetas, máscara y resumen de errores para la tarjeta.
- `backend/apps/orders/{events,incidents,services,forms,card_admin,admin}.py`: metadatos durables, avisos de incidencias, motivo optativo de cancelación y vistas privadas de comunicaciones.
- `backend/apps/payments/services.py`: punto canónico de aviso PENDING.
- `backend/templates/emails/`: bases HTML/texto, variante interna, includes y todas las plantillas ES/EN; nuevos `order_received` y `payment_issue`.
- `backend/templates/admin/orders/card.html` y `backend/apps/orders/static/orders/order-card.js`: sección y formularios con el comportamiento AJAX existente, incluida confirmación; casilla de motivo.
- Nuevo `backend/apps/notifications/tests/test_stage3.py`; adaptación de expectativas de textos en `test_notifications.py` y `orders/tests/test_operations.py`.

Única migración: `notifications/0006_notificationdelivery_payload_and_more.py`. Añade JSON vacío por defecto; actualiza choices sin modificar los códigos existentes; corrige WhatsApp histórico `sent` con ID `log-*` a omitido por simulación, quitando la falsa fecha de aceptación. Usa modelos históricos y el alias de la conexión. La corrección de datos tiene reversa `noop`: no restituye afirmaciones falsas de envío al bajar de versión. Revertir la columna elimina los snapshots, por lo que no es un procedimiento para conservar historial. No se requieren migraciones de pedidos ni inventario.

## Verificación

Se usaron los ejecutables de `backend/.venv/bin`, `DJANGO_SECRET_KEY=local-tests`, `REDIS_URL=redis://localhost:6379/0` y URLs de base locales, sin cargar secretos ni consultar Wompi/Meta.

- PostgreSQL, comando solicitado: `cd backend && pytest --ds=config.settings.test -q` con `DATABASE_URL=postgres://serti:serti@localhost:5432/serti`: **81 passed, 890 errors**, 94,41 s. Error de conexión: `Operation not permitted` en localhost IPv4/IPv6. **PostgreSQL no es accesible desde este sandbox; no queda verificada la suite, las migraciones ni la concurrencia en PostgreSQL.** Una primera ejecución antes de incorporar las pruebas nuevas dio 81 passed y 833 errores por la misma causa.
- Suite completa SQLite final, mismo comando con `DATABASE_URL=sqlite:////tmp/pedidos3.sqlite`: **946 passed, 24 skipped, 1 failed**, 63,34 s. Único fallo: `apps/core/tests/test_health.py::test_ready_reports_dependencies`, 503 porque Redis no es accesible. Las omitidas incluyen pruebas PostgreSQL. Es comprobación complementaria, no sustituye PostgreSQL.
- Pruebas enfocadas finales: `pytest --ds=config.settings.test apps/notifications/tests apps/orders/tests/test_card.py apps/orders/tests/test_stage2.py apps/orders/tests/test_operations.py -q`: **182 passed, 1 skipped**, 13,63 s, en SQLite. La omitida es la nueva prueba concurrente PostgreSQL. Una ejecución enfocada anterior dio 146 passed. La primera suite SQLite completa identificó tres expectativas antiguas del asunto/texto de envío y una prueba de migración que intentaba abrir un schema editor SQLite dentro de una transacción; se corrigieron los tests. El fallo adicional de salud corresponde a Redis no accesible, como en Etapa 2.
- `python manage.py check --settings=config.settings.test`: **sin problemas**.
- `python manage.py makemigrations --check --dry-run --settings=config.settings.test`: **No changes detected**, comprobado con SQLite.
- Ruff sobre los módulos y pruebas modificados: **sin errores**. `git diff --check`: **sin errores**.

Las pruebas nuevas cubren todas las plantillas de cliente ES/EN con piezas, importes no nulos, dirección, token, contacto y ausencia de teléfono/variables sin resolver; fallback de logo/contacto; fecha de pago; PENDING canónico deduplicado; aviso por los dos tipos de incidencia; motivo y devolución al cancelar; WhatsApp simulado; reconfiguración de correo/WhatsApp y auditoría; límites, copias de copias y persistencia del HTML; 403 y confirmaciones HTTP; máscara y etiquetas; pertenencia y permisos de vista previa; errores antiguos sin PII; idiomas y tipos de incidencia internos; normalización histórica de simulados. Se añade una prueba PostgreSQL concurrente para el límite de copias, omitida en SQLite.

## Pendientes y revisión visual

1. En el entorno con PostgreSQL/Redis accesibles, ejecutar migraciones y **`cd backend && pytest --ds=config.settings.test -q`**. Verificar especialmente la prueba concurrente de copias y las existentes de bloqueo/concurrencia; aquí no se validaron en PostgreSQL. Todos los bloqueos añadidos usan `of=("self",)` para evitar FKs anulables.
2. En Mailpit, revisar ES y EN para pago recibido/PENDING, aprobado con fecha distinta de creación, manual, preparación, envío con/sin guía, entregado, vencido, incidencia y cancelación. Comprobar encabezado, ancho móvil, referencias, todos los importes, dirección sin teléfono y contacto. Probar sin `PUBLIC_SITE_URL` (texto SERTI) y con URL pública válida (logo existente).
3. Confirmar el botón con token y que los internos abren el pedido del dashboard; revisar tipos de incidencias y resolución con «Avisar a SERTI». Comprobar cancelación con casilla desmarcada/marcada y frase de devolución solo cuando corresponda.
4. En tarjeta lateral y página completa, revisar cronología, máscara, «Aceptado por el proveedor», «Omitido · Simulación», errores y ventana de vista previa. Cambiar la dirección después del envío y comprobar que la vista guardada conserva el mensaje original.
5. Reenviar un fallo y un omitido tras configurar el canal. Crear tres copias y comprobar rechazo de la cuarta; verificar auditoría y denegación con usuario sin permiso. Los formularios de comunicaciones no aparecen en impresión.
6. Comprobar worker y beat activos. Las pruebas no envían a proveedores reales; la aceptación no garantiza entrega y una caída entre aceptación del proveedor y commit todavía puede provocar un duplicado, como antes. No se realizó revisión visual real en Mailpit/navegador durante esta etapa.

## Commit

Sin commit: `.git` no es escribible desde el sandbox (`test -w .git` devuelve falso). No se crearon scripts de commit ni se hizo push. Mensaje propuesto:

```text
Completa correos de pedidos e incorpora historial, reenvíos y copias auditadas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
