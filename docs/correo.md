# Correo de pedidos sin spam (Resend)

## Qué ya hace la tienda

El cliente recibe un correo en cada etapa, en su idioma (ES/EN), con versión HTML y texto plano y un botón a la página de su pedido:

| Momento | Correo al cliente | Copia a SERTI |
|---|---|---|
| Pedido creado (pago en proceso) | Pedido recibido | — |
| Pago aprobado (Wompi o manual confirmado) | Pago aprobado | Sí (+ WhatsApp interno) |
| Pago en revisión / incidencia | Pago en revisión | Sí |
| Pago manual elegido | Instrucciones de pago | — |
| Reserva vencida sin pago | Reserva vencida | — |
| Dashboard → En preparación | En preparación | — |
| Dashboard → Enviado (transportadora obligatoria; guía y enlace opcionales) | Pedido enviado, con transportadora, guía y enlace de rastreo | — |
| Dashboard → Entregado | Pedido entregado | — |
| Dashboard → Cancelado | Pedido cancelado (motivo opcional) | — |

Los envíos se reintentan solos si el proveedor falla y quedan visibles en el pedido del dashboard.

## Por qué llegan a spam y cómo se evita

Gmail y Outlook solo confían en un correo si el dominio del remitente lo **autentica**:

- **SPF**: qué servidores pueden enviar por el dominio.
- **DKIM**: firma criptográfica de cada correo.
- **DMARC**: política que une las dos y le dice al receptor qué hacer si fallan.

Por eso el remitente debe ser del **dominio de la tienda** (p. ej. `pedidos@serti.co`), nunca una cuenta de Gmail. `check_production` bloquea el lanzamiento si el remitente no usa el dominio de la tienda, si falta TLS o si faltan las credenciales.

## Pasos

Para `sertiattelier.com` en Hostinger: [dominio-sertiattelier.md](dominio-sertiattelier.md).

1. **Cuenta en Resend** (resend.com, plan gratis: 3.000 correos/mes, 100/día). La crea el cliente con su correo.
2. **Domains → Add domain** → el dominio de la tienda. Resend muestra los registros exactos: normalmente un TXT de DKIM (`resend._domainkey`), y un MX y un TXT de SPF en un subdominio de envío. **Copiarlos tal cual** en el panel DNS del dominio.
3. **DMARC** (lo agrega uno mismo en el DNS): TXT en `_dmarc` con `v=DMARC1; p=none; rua=mailto:<correo-del-cliente>`. Tras 2–4 semanas sin problemas, cambiar a `p=quarantine`.
4. Esperar a que Resend marque el dominio como **Verified** (minutos a pocas horas).
5. **API Keys → Create** con permiso *Sending access* solo para ese dominio.
6. En `.env.production` **del servidor** (nunca en el repositorio ni en el chat):
   ```
   EMAIL_HOST=smtp.resend.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=true
   EMAIL_USE_SSL=false
   EMAIL_HOST_USER=resend
   EMAIL_HOST_PASSWORD=re_...
   DEFAULT_FROM_EMAIL=SERTI <pedidos@DOMINIO>
   SERTI_ORDERS_EMAIL=<correo donde SERTI recibe las copias>
   ```
7. En el dashboard → **Datos del sitio → Correo de atención**: el correo donde el cliente quiere recibir respuestas. Se usa como *Reply-To*: si un comprador responde, le llega ahí (puede ser Gmail).
8. Reiniciar backend y worker, y verificar:
   ```
   docker compose -f infra/docker-compose.yml exec backend python manage.py check_production
   docker compose -f infra/docker-compose.yml exec backend python manage.py send_test_email <dirección de mail-tester.com>
   ```
   En mail-tester.com apuntar a **9/10 o más**; en Gmail, «Mostrar original» debe decir `SPF: PASS`, `DKIM: PASS` y `DMARC: PASS`. Probar también con una cuenta de Outlook/Hotmail.

## Buenas prácticas que ya cumple el código

- Remitente estable `pedidos@` (no `no-reply@`), con Reply-To a una persona.
- HTML sencillo con alternativa de texto plano; imágenes con URL absoluta del propio dominio; sin píxeles de rastreo ni acortadores de enlaces.
- `Message-ID` con el dominio de la tienda.
- Solo correos transaccionales (no publicidad): no requieren enlace de baja. Si en el futuro se envían campañas, deben salir por otro remitente/subdominio y con baja en un clic.

## Opcional

Para **recibir** correo en `pedidos@DOMINIO` (Resend solo envía), usar el reenvío del registrador del dominio o un buzón (Zoho Mail gratis, Google Workspace de pago). No es necesario si el Reply-To apunta a un buzón existente.
