# Pedidos — Etapa 7: pruebas integrales

Fecha: 2026-11-06. Rama `fase-9-produccion`. Base leída: `docs/pedidos-etapa-{1,2,3,4,5}.md` y commits indicados en la solicitud. Sin red externa, push ni dependencias nuevas. No se ejecutaron pruebas de base de datos en SQLite.

## Implementación y límites

`infra/wompi-fake/server.py` usa únicamente la biblioteca estándar de Python. El servicio dev `wompi-fake:8080` no publica puertos, no está en el compose de producción ni tiene ruta en Caddy. Estado en memoria, perdido al reiniciar. No se debe usar con datos reales.

- `GET /v1/transactions/{id}` devuelve `{data: transaction}` o 404.
- `GET /v1/transactions?reference=...` devuelve `{data: [transaction, ...]}`.
- `POST /control` admite `transaction`, `unavailable` y `emit`. Estados: PENDING, APPROVED, DECLINED, VOIDED, ERROR. `unavailable: true` hace que ambas consultas canónicas devuelvan 503; el control continúa disponible.
- Con `emit: true`, primero guarda la transacción y luego envía un webhook firmado al destino fijo `http://backend:8000/api/v1/payments/wompi/events`. No admite destinos elegidos por el solicitante. No registra cuerpos, referencias ni tokens. Una entrega fallida devuelve 502; el comando puede repetirse.
- El simulador ya no admite `--in-process` ni `--url`. Configura la transacción mediante el control y pide al fake emitir el evento; el backend verifica firma, consulta con `WompiClient`, compara la canónica y aplica el servicio real. `--unavailable` permite probar la recepción durable y la tarea de recuperación.

La excepción de configuración exige conjuntamente DEBUG y WOMPI_ALLOW_FAKE_API. Solo acepta `http://wompi-fake[:8080]/v1`, sin credenciales, query ni fragmento, y las cuatro llaves con prefijos de prueba y sufijo inicial `e2e`. El compose dev contiene valores ficticios; `.env.example` no recibe esas credenciales. Desarrollo muestra `payments.W002`. Producción rechaza la bandera y cualquier URL no oficial, incluso con todas las llaves vacías. La misma restricción se aplica en el límite de transporte de WompiClient para impedir que webhook/sync consulten un fake deshabilitado. Los tests no heredan la bandera del compose.

Los comandos `e2e_admin_session` y `e2e_order_status` exigen DEBUG. El primero crea su propia cuenta Propietario con contraseña inutilizable y sesión de una hora; devuelve cookie y ruta del panel, sin pedir ni escribir contraseñas. Rechaza segundo factor activado: requiere la configuración dev existente. El segundo solo permite preparar/enviar mediante el servicio real, con cuenta E2E, estado esperado y transportadora/guía ficticias. Las cuentas de prueba permanecen en la base local; usar una base dev desechable. No seleccionar cuentas reales con estos comandos.

## Matriz backend

Todas las pruebas de `apps/orders/tests/test_integration.py` usan PostgreSQL (`django_db(transaction=True)` y `postgres`), fixtures del checkout, endpoints reales de Django y un transporte `urlopen` en memoria. No se sustituye `WompiClient`, su parsing, la firma ni la lógica de negocio. Las entregas se dejan en cola y se procesan explícitamente para no depender del broker.

**Resultado de cada fila: pendiente de ejecución funcional; PostgreSQL está bloqueado por el sandbox.** Recolección correcta de 19 pruebas; no equivale a aprobarlas.

| Caso | Prueba en `test_integration.py` | Comprobación |
| --- | --- | --- |
| 1 Compra completa | `test_purchase` | Carrito, cotización, pedido/intento, firma/canónica, venta, aviso y dos correos en cola; API aprobada. Texto «Pago aprobado» en E2E. |
| 2 PSE pendiente | `test_pending_then_paid_once` | PENDING repetido genera un recibido; APPROVED repetido mantiene dos correos de pago y un aviso. |
| 3 Rechazo/reintento | `test_declined_retry` | HTTP de nuevo intento, referencia -02, aprobación. |
| 4 Duplicados | `test_duplicate_webhook` | Tres eventos, una transición a vendida, un aviso y una entrega por destinatario/canal. |
| 5 Firma/referencia | `test_signatures_and_manipulated_reference` | Firma inválida no consulta API ni paga; referencia manipulada firmada crea mismatch/incidencia, sin venta. |
| 6 API caída | `test_api_down_persists_queues_and_recovers`, `test_receipt_or_queue_failure_returns_503` | 503 del transporte, recibo durable antes de delay, recuperación real del task; fallo de persistencia/broker responde 503. |
| 7 SMTP | `test_smtp_failure_and_card_resend` | Excepción en envío real del adaptador; failed y fecha de reintento; POST de reenvío de tarjeta y entrega posterior; pago intacto. |
| 8 WhatsApp | `test_whatsapp_failure_isolated` | Adaptador falla, pago conserva venta y correos se envían. |
| 9 Permisos/estados | `test_unauthorized_and_invalid_transition` | Contenido HTTP 403, anónimo denegado por servicio y redirigido al login HTTP; unfulfilled→delivered rechazado en servicio y tarjeta. |
| 10 Dos administradores | `test_two_administrators` | Dos cuentas, conexiones por hilo y barrera; una transición y un «El pedido cambió, recarga.». |
| 11 Invitado | `test_guest_tracking_privacy_expiry_and_throttle` | Token válido sin PII/notas, incorrecto y caducado 404, throttle 429. |
| 12 Inventario | `test_two_buyers_only_one_reservation`, `test_late_payment_piece_already_sold` | HTTP concurrente 201/409, una reserva; liberación/vencimiento, otra compra aprobada y pago tardío con no_piece, una sola venta. |
| 13 Cancelación | `test_cancel_and_late_payment[True/False]` | Devolución pendiente para pagado; pago posterior a cancelar abre cancelled_payment y no vende. |
| 14 Rollback | `test_apply_failure_rolls_back_then_retry` | Excepción después de aprobación y avisos; revierte venta, reserva, intento, estado, fecha y avisos; reintento aplica. |
| 15 Confirmación manual | `test_no_manual_confirmation_for_wompi` | Servicio y POST del admin rechazan Wompi; no crean intento manual. |
| Auxiliar | `test_e2e_session_authenticates_without_password` | Cookie autentica en el panel, permisos y contraseña inutilizable. |

La expectativa solicitada de 403 anónimo difiere del comportamiento existente de Django admin: un navegador anónimo recibe **302 al login**, sin ejecutar cambios. Se preservó esa conducta y se comprueba además `PermissionDenied` en el servicio; no se alteró producción para hacer coincidir una expectativa de test.

## Matriz E2E

| Caso | Prueba | Resultado |
| --- | --- | --- |
| Manual y correo | `purchase.spec.ts`: manual payment | Preparada; asunto actualizado a plantilla Etapa 3. No ejecutada en navegador. |
| Rechazado → -02 → aprobado | `purchase.spec.ts`: online payment | Preparada con canónica del fake y asunto «SERTI · Pedido SRT-… · Pago aprobado». No ejecutada. |
| PSE y polling | `orders.spec.ts`: pending PSE… | Comprueba mensaje existente de confirmación PSE, aprobación y cero navegaciones completas; espera polling ≤20 s. No ejecutada. |
| Cronología | Mismo test | Prepara/envía mediante comando; muestra estados, transportadora y guía. No ejecutada. |
| Campana y toast | Mismo test | Cuenta nueva, inicialización sin históricos; un pago produce contador 1/toast; espera ≤50 s por polling existente de 45 s. No se modifica polling de producción. No ejecutada. |
| Axe | Mismo test y enlace inválido | WCAG 2/2.1/2.2 A/AA, cero infracciones serious/critical en pedido, tarjeta y 404. No ejecutada. |
| Enlace inexistente | `orders.spec.ts`: nonexistent tracking… | HTTP 404 real y no-store. No ejecutada. |

`fixtures.ts` bloquea solicitudes de navegador fuera del origen local en todas las specs. El stub de checkout se registra en la página y responde antes de la regla del contexto; no visita Wompi. Los contextos adicionales también usan la restricción. Se reutilizan piezas nuevas y Mailpit. Los comandos de soporte no imprimen stderr con datos del stack.

## Bugs y cambios de producción

1. **Simulador obsoleto:** enviaba solo el evento y dependía de una canónica inexistente. Se reemplaza por control + transacción canónica + emisión firmada desde el fake. Pruebas de contrato verifican las cinco respuestas, búsqueda, caída/recuperación y firma con el algoritmo real; test del comando comprueba el control usado.
2. **Asuntos E2E obsoletos:** manual y aprobado seguían esperando textos previos a Etapa 3. Corregidos contra `EVENT_LABELS` y `render_email`; no cambian plantillas.
3. **Cierre de configuración en producción:** antes se validaba URL solo si había alguna llave. Ahora URL no oficial o bandera fake producen `ImproperlyConfigured` aun sin llaves. Pruebas explícitas de ambos casos. Es el único endurecimiento de comportamiento de producción solicitado; no se cambian pagos, inventario, estados, correos, permisos ni UI.

No se afirma haber encontrado otros bugs de negocio: sin PostgreSQL y navegador no pueden darse por demostrados los flujos nuevos.

## Activar, desactivar y ejecutar

Fake activado por defecto **solo en el compose dev**. Necesita imágenes, paquetes y navegador ya disponibles localmente para trabajar sin red. No ejecutar pulls ni instalar navegadores durante esta comprobación offline.

```sh
# Desde la raíz, con .env local ya configurado para PostgreSQL/Redis/Mailpit:
docker compose -f infra/docker-compose.dev.yml up -d --no-build --pull never
docker compose -f infra/docker-compose.dev.yml exec backend python manage.py check
docker compose -f infra/docker-compose.dev.yml exec backend python manage.py simulate_wompi_event --reference SRT-000001-01 --status PENDING
docker compose -f infra/docker-compose.dev.yml exec backend python manage.py simulate_wompi_event --reference SRT-000001-01 --status APPROVED
# Para probar caída: añadir --unavailable. Repetir sin la opción recupera el fake.
```

Usar una referencia creada por el propio checkout local. El estado canónico queda disponible también para sync/conciliación; no hay atajos. Worker/beat deben estar activos para las entregas y recuperación tras caída. Si se necesita recuperar sin emitir otro evento: POST interno a `/control` con `{"unavailable": false}`; `verify_wompi_event` reintentará según el backoff existente.

Para desactivar el fake, un override de compose debe reemplazar **en backend, worker y beat** `WOMPI_ALLOW_FAKE_API` por `false`, `WOMPI_API_URL` por `https://sandbox.wompi.co/v1` y las cuatro llaves ficticias por las llaves de prueba reales (o todas vacías para deshabilitar pagos online). El bloque environment de compose tiene precedencia sobre `.env`: editar solo `.env` no basta. Recrear esos servicios. El fake puede detenerse después; los comandos de simulación lo rechazarán. No usar este compose para producción.

```sh
# Pruebas obligatorias con PostgreSQL, usando el entorno del contenedor:
docker compose -f infra/docker-compose.dev.yml exec backend pytest --ds=config.settings.test -q
# Equivalente local, con DATABASE_URL PostgreSQL y Redis accesibles:
cd backend && pytest --ds=config.settings.test -q
# Frontend, desde raíz en otra terminal:
cd frontend && npm run lint && npm run typecheck && npm test
# Stack ya levantado, navegador instalado:
cd frontend && npx playwright test
```

En los comandos separados, volver a la raíz antes del siguiente `cd`. No hace falta introducir contraseñas del panel; las sesiones E2E las crea el comando local.

## Resultados de este entorno

- **Suite completa PostgreSQL**, `cd backend && pytest --ds=config.settings.test -q`, con ejecutables de `.venv/bin`, `DJANGO_SECRET_KEY=local-tests`, `DATABASE_URL=postgres://serti:serti@localhost:5432/serti`, `REDIS_URL=redis://localhost:6379/0`: **97 passed, 958 errors, 102,77 s**. Los errores ocurren al preparar la base: psycopg informa `Operation not permitted` para localhost IPv4/IPv6. **PostgreSQL no es accesible desde el sandbox. Suite, concurrencia e integración NO validadas.** Los 97 aprobados no requieren base. Después se reforzó el guard del transporte y los avisos de configuración; la repetición enfocada de sus 30 pruebas también aprobó. Una ejecución anterior dio 88 passed/956 errores antes de incorporar los últimos auxiliares.
- **Configuración + contrato fake sin base**, `pytest --ds=config.settings.test apps/payments/tests/test_configuration.py apps/payments/tests/test_fake_api.py -q`: **30 passed**. No abren sockets ni sustituyen la firma; comprueban configuración, rechazo prod y comandos, contrato y emisión del servidor fake.
- **Colección integración:** `pytest ... apps/orders/tests/test_integration.py --collect-only -q`: **19 tests collected**. No prueba comportamiento SQL.
- **Frontend:** `npm run lint`, `npm run typecheck` y `npm test`: **aprobados, 44/44 tests**. Incluye tipado de los E2E.
- **Playwright:** solo descubrimiento con el binario instalado `playwright test --list`: **50 tests in 6 files**, contando escritorio y móvil. **No se ejecutaron navegadores ni E2E**: requieren stack y navegador operativos; las conexiones locales están restringidas. No se descargó navegador ni se levantó el stack mediante pulls.
- **Ruff** en los Python modificados, **`git diff --check`** y **`docker compose -f infra/docker-compose.dev.yml config --quiet`**: aprobados. Validar compose no ejecuta servicios.
- No se corrió SQLite, build que descargue fuentes, sandbox Wompi ni proveedores reales. No hay migraciones nuevas.

## Checklist exclusivo del sandbox real Wompi

Requiere autorización de red en ese entorno y las cuatro llaves **test** coherentes, incluida `WOMPI_PRIVATE_KEY`; no basta la llave pública. Desactivar fake como arriba y comprobar que `payments.W002` desaparece.

- Crear pedido de prueba desde checkout real; verificar firma de integridad, importe COP, referencia y expiración. No usar `simulate_wompi_event`, `stubWompi` ni el control fake.
- Completar tarjeta de prueba aprobada/rechazada y PSE pendiente según las instrucciones oficiales del sandbox disponibles para la cuenta. Comprobar -02 tras rechazo y webhook recibido por HTTPS accesible al proveedor.
- Verificar que GET canónico autenticado por llave privada identifica exactamente la transacción; retorno con `?id=` sincroniza y limpia el identificador de la URL. Confirmar PENDING→APPROVED, idempotencia, venta única, correos Mailpit y campana.
- Probar reintentos reales del proveedor y una indisponibilidad temporal de consulta; comprobar recibos persistidos, tareas y conciliación. Revisar sin publicar secretos ni datos del cliente.
- Verificar eventos VOIDED y los métodos/estados que la cuenta permita simular. Confirmar incidencias y que no se libera automáticamente una venta.
- Confirmar credenciales, HTTPS y contrato efectivo de la API con el sandbox real. El fake no certifica autenticación del proveedor, aceptación del checkout, disponibilidad, latencia, semántica específica de PSE ni entrega de SMTP/Meta externos. No valida pagos de producción ni reembolsos reales.

## Commit

`.git` no es escribible desde el sandbox. Cambios locales sin commit, sin scripts de commit y sin push. Mensaje previsto:

```text
Añade Wompi local y pruebas integrales de pedidos

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
