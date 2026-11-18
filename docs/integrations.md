# Integraciones

Todas detrás de adaptadores con una interfaz propia, para poder simularlas en pruebas y cambiarlas sin tocar los dominios.

## Wompi

Documentación revisada el 2026-10-23: https://docs.wompi.co/docs/colombia/ (eventos, métodos de pago). **Volver a revisarla al iniciar la Fase 6.**

### Ambientes y llaves

| Variable | Uso | Dónde vive |
|---|---|---|
| `WOMPI_PUBLIC_KEY` | Widget / Web Checkout (`pub_test_…` en sandbox) | Backend; se envía al navegador en la respuesta de `POST /orders` |
| `WOMPI_PRIVATE_KEY` | Consultas de transacciones (conciliación) | Solo backend |
| `WOMPI_INTEGRITY_SECRET` | Firma de integridad | Solo backend |
| `WOMPI_EVENTS_SECRET` | Validar webhooks | Solo backend |
| `WOMPI_API_URL` | `https://sandbox.wompi.co/v1` o `https://production.wompi.co/v1` | Backend |

Wompi exige **una URL de eventos distinta por ambiente** (sandbox y producción).

### Flujo

1. `POST /orders` crea el pedido, la reserva y un `PaymentAttempt` con `reference` única (`SRT-000123-01`).
2. El backend calcula la **firma de integridad**: SHA-256 de `reference + amount_in_cents + currency + WOMPI_INTEGRITY_SECRET` (con `expiration_time` en medio si se usa).
3. El frontend abre el Widget o el Web Checkout con `public_key`, `reference`, `amount_in_cents`, `currency`, `signature:integrity`, `redirect_url` y el correo del cliente.
4. Wompi redirige a `redirect_url?id=<transaction_id>`. El frontend **solo muestra** lo que dice el backend.
5. Wompi envía `transaction.updated` a `/api/v1/payments/wompi/events`.

### Vencimiento del pago = vencimiento de la reserva (ADR-015)
La firma de integridad incluye `expiration-time` igual a `reservation_expires_at` del pedido. Wompi rechaza pagos después de esa hora, así que un cliente no puede pagar una pieza cuya reserva ya se liberó. El caso residual (aprobación que llega tarde por un medio asíncrono) se marca `needs_attention` para reembolso manual.

Usamos **Web Checkout** (redirección con un formulario GET a `https://checkout.wompi.co/p/`) en lugar del widget: ningún script de terceros corre en nuestras páginas. La redirección de vuelta **no** prueba el pago; el sitio pide al backend sincronizar la transacción (consulta con la llave privada) y, en paralelo, llegan el webhook y la conciliación.

### Validación del webhook

Según la documentación de eventos:

1. Leer `signature.properties` **del evento** (la lista puede cambiar; no se asume fija).
2. Concatenar los valores de esas propiedades (rutas dentro de `data`), luego `timestamp` y luego `WOMPI_EVENTS_SECRET`.
3. SHA-256 de la cadena; comparar en tiempo constante con `signature.checksum` (también viene en la cabecera `X-Event-Checksum`).
4. Si coincide: buscar el intento por `reference`; verificar `amount_in_cents` y `currency = COP`; registrar el `PaymentEvent` (idempotente por `transaction_id + status`); aplicar el cambio con bloqueo de fila.
5. Responder **200**. Cualquier otro código hace que Wompi reintente.

### Conciliación (obligatoria)

Wompi reintenta un webhook fallido **solo 3 veces en 24 horas** (30 min, 3 h y 24 h). Por eso:

- `reconcile_pending_wompi` corre cada 5 min y consulta `GET /v1/transactions/{id}` (o por referencia) para cada intento `PENDING` con más de 10 min.
- El resultado pasa por el **mismo servicio** que el webhook: misma validación y misma idempotencia.

### Métodos y pagos asíncronos (DC-10)

Tipos documentados: `CARD`, `PSE`, `NEQUI`, `DAVIPLATA`, `BANCOLOMBIA_TRANSFER`, `BANCOLOMBIA_QR`, `BANCOLOMBIA_COLLECT` (efectivo en corresponsal), `BANCOLOMBIA_BNPL` (desde $100.000), `PCOL` (Puntos Colombia), `SU_PLUS` (entre $35.000 y $5.000.000). Se habilitan los que active la cuenta del comercio (P-11).

**Efectivo en corresponsal Bancolombia:** la transacción queda `PENDING` hasta que el cliente paga; los datos para pagar (`business_agreement_code`, `payment_intention_identifier`) se obtienen consultando la transacción. La documentación **no indica el plazo** para pagar (P-18). Hasta confirmarlo, la reserva de la pieza para este método se alarga a 24 h (igual que el canal manual) y se ajusta cuando Wompi responda.

### Casos borde

| Caso | Comportamiento |
|---|---|
| Pago aprobado después de vencer la reserva y la pieza sigue libre | Se aprueba y la pieza pasa a vendida |
| Pago aprobado después de vencer la reserva y la pieza ya se vendió a otra persona | Pedido `needs_attention`, aviso inmediato a SERTI, reembolso manual |
| Evento duplicado | Registrado como `duplicate`, sin efecto |
| Monto o moneda distintos | Registrado como `mismatch`, sin efecto, alerta |
| Referencia desconocida | Registrado como `unknown_reference`, sin efecto |
| `VOIDED` sobre un pedido aprobado | Estado de pago `voided`, alerta; el estado operativo lo decide SERTI |

### Pruebas
Sandbox con los datos de prueba de Wompi (tarjetas aprobada y rechazada, Nequi, PSE). **Nunca dinero real** en desarrollo ni en *staging*.

## Pago manual (DC-11, DC-14)

- Canal `ManualChannel`. El comprador elige "Pagar por otro medio" en el checkout.
- La pieza se reserva **24 horas** (`SiteSettings.manual_hours`, configurable).
- Se envía un correo (y, si el cliente lo decide, un WhatsApp) con las **instrucciones de pago** administrables: entidades (Efecty, transferencia…), datos, monto, referencia del pedido y hora límite (P-16).
- SERTI confirma en el dashboard con la acción **"Confirmar pago manual"**: exige referencia y soporte (imagen o PDF), queda en la auditoría y dispara las mismas notificaciones que un pago aprobado por Wompi.
- Si no se confirma a tiempo: `release_expired_reservations` expira el pedido y libera la pieza; se avisa al comprador.

## Correo transaccional

**Implementación (Fase 7):** SMTP estándar de Django, configurado por variables de entorno (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`/`EMAIL_USE_SSL`). Funciona con cualquiera de los proveedores candidatos (SES, Postmark y Resend ofrecen SMTP), así que P-13 se decide sin cambiar código. Envíos asíncronos, idempotentes, con hasta 5 intentos (1, 5, 15 y 60 min); si fallan, el pedido y el pago no cambian. Se guarda solo el *hash* del destinatario y el tipo de error.

- Proveedor por decidir (P-13): **Amazon SES** (más económico), **Postmark** (mejor entregabilidad transaccional) o **Resend** (API simple). Recomendación: Postmark o SES.
- Dominio del cliente con **SPF, DKIM y DMARC** configurados antes del lanzamiento.
- Plantillas HTML + texto plano, ES/EN, con identidad SERTI (paleta DC-06), probadas en Gmail, Outlook y Apple Mail.
- Variables: `EMAIL_PROVIDER`, `EMAIL_API_KEY`, `EMAIL_FROM`, `EMAIL_REPLY_TO`, `SERTI_ORDERS_EMAIL`.

| Correo | Destinatario | Disparador |
|---|---|---|
| Confirmación de compra | Comprador | Pago aprobado (Wompi o manual) |
| Instrucciones de pago manual | Comprador | Pedido manual creado |
| Reserva vencida | Comprador | Pedido manual o pendiente expirado |
| Nuevo pedido | SERTI | Pago aprobado |
| Pedido requiere atención | SERTI | `needs_attention`, `mismatch` |

El correo de confirmación incluye: número de pedido, piezas, precios, descuentos, envío ($0), total pagado, dirección, estado, certificado solicitado (DC-15) y datos de contacto. **No se llama factura.**

## WhatsApp

### Notificaciones automáticas a SERTI (DC-04)
- **WhatsApp Cloud API** oficial de Meta, sin intermediarios (menor costo).
- Requisitos: cuenta de Meta Business **verificada**, un **número dedicado** que no esté en uso en la app de WhatsApp (P-06), y **plantillas aprobadas** por Meta.
- Plantilla `nuevo_pedido` (categoría *utility*): número de pedido, comprador, piezas, total, municipio, certificado sí/no y enlace al admin.
- Meta cobra **por mensaje de plantilla entregado**, con tarifa por categoría y país. Verificar la tarifa vigente para Colombia al configurar la cuenta.
- Variables: `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN` (token de sistema, no personal), `WHATSAPP_ORDERS_RECIPIENT`, `WHATSAPP_TEMPLATE_NEW_ORDER`.
- Si WhatsApp falla, el correo a SERTI sigue saliendo; reintentos con *backoff*; el pago no se toca (ADR-009).

### Plantillas a registrar en Meta (categoría *utility*, idioma `es`)
Implementado en la Fase 7 (`backend/apps/notifications/adapters.py`). Mientras no estén el número dedicado y la verificación (P-06), `WHATSAPP_PROVIDER=log` simula el envío sin red.

`nuevo_pedido`:
```text
Nuevo pedido {{1}}. Cliente: {{2}}. Piezas: {{3}}. Total: {{4}}.
Destino: {{5}}. Certificado: {{6}}. Revisar pedido: {{7}}
```

`pedido_requiere_atencion`:
```text
URGENTE: el pedido {{1}} requiere atención. Cliente: {{2}}. Piezas: {{3}}.
Total: {{4}}. Destino: {{5}}. Certificado: {{6}}. Revisar pedido: {{7}}.
Motivo: {{8}}. Requiere reembolso o contacto con el cliente.
```

API: `POST https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages` (versión por defecto `v26.0`, verificada en la documentación de Meta en octubre de 2026).

### Botón flotante y CTA (COM-04, CAT-07, DC-09)
- Enlaces `https://wa.me/<número>?text=<mensaje URL-encoded>`; **no** usan la API ni tienen costo.
- Número y mensajes administrables en `SiteSettings`. Es un módulo **separado** de las notificaciones automáticas.

## Almacenamiento de medios

- `django-storages` con backend S3-compatible; en el MVP, `FileSystemStorage` sobre un volumen Docker con copia de seguridad.
- Migrar a S3 compatible (Cloudflare R2, Backblaze B2, DigitalOcean Spaces) solo cambia variables: `STORAGE_BACKEND`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `MEDIA_PUBLIC_URL`.
- Procesamiento (ADR-010): validación por contenido, re-codificación, eliminación de EXIF, versiones WebP de 480, 960, 1600 y 2400 px. Corre en Celery; la imagen queda "procesando" hasta terminar.

## Facturación electrónica (excluida del MVP)

Interfaz `InvoicingProvider` con `issue(order) -> InvoiceRef` y una implementación `NoopInvoicingProvider`. Los datos del pedido ya guardan lo necesario para integrar un proveedor autorizado por la DIAN más adelante (P-14).

### Wompi sandbox real en local

Por defecto el entorno de desarrollo usa el simulador `wompi-fake` (las pruebas E2E dependen de él). Para probar con el sandbox real de Wompi:

1. Poner las cuatro llaves **de pruebas** (`pub_test_`, `prv_test_`, `test_integrity_`, `test_events_`) y `WOMPI_API_URL=https://sandbox.wompi.co/v1` en el `.env` raíz (no versionado).
2. Levantar con la capa opcional: `docker compose -f infra/docker-compose.dev.yml -f infra/docker-compose.sandbox.yml up -d`.
3. Para volver al simulador (y correr Playwright), levantar sin `docker-compose.sandbox.yml`.

Los eventos de Wompi no llegan a `localhost`: el estado se obtiene al volver del checkout (`payment-sync`) y con la conciliación periódica. El webhook se prueba en *staging* con una URL pública. Las llaves de producción solo van en `.env.production` del servidor.
