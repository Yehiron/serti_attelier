# sertiattelier.com — correo y DNS en Hostinger

Estado al 2026-11-18: dominio registrado en Hostinger, DNS de Hostinger (`*.dns-parking.com`), página de estacionamiento (`A @ → 2.57.91.91`, `www → @`). Sin MX, SPF, DKIM ni DMARC: no hay nada que conservar.

## 1. Resend (lo hace la dueña de la cuenta)

1. Crear cuenta en resend.com con el correo de SERTI.
2. **Domains → Add Domain** → `sertiattelier.com` (región por defecto).
3. Resend muestra 3 registros (los valores de DKIM son únicos de la cuenta; copiar exactamente los de Resend):

   | Tipo | Nombre en Hostinger | Valor | Prioridad |
   |---|---|---|---|
   | TXT | `resend._domainkey` | `p=MIGf...` (largo, de Resend) | — |
   | MX | `send` | `feedback-smtp.<región>.amazonses.com` (de Resend) | 10 |
   | TXT | `send` | `v=spf1 include:amazonses.com ~all` (de Resend) | — |

## 2. Hostinger → hPanel → Dominios → sertiattelier.com → DNS / Nameservers → Registros DNS

- En **Nombre** escribir solo la parte antes del dominio (`send`, `resend._domainkey`, `_dmarc`); Hostinger agrega `.sertiattelier.com`.
- TTL: dejar el predeterminado.
- Agregar los 3 registros de Resend y además DMARC:

  | Tipo | Nombre | Valor |
  |---|---|---|
  | TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:<correo de SERTI>` |

- **No tocar** los registros `A @` ni `www` todavía: se cambian al IP del servidor el día del despliegue.
- No crear un SPF en la raíz (`@`) salvo que se active correo de Hostinger; si se activa, Hostinger agrega su propio MX/SPF en la raíz y no choca con los de `send`.

## 3. Verificación

- En Resend, **Verify DNS records** hasta ver *Verified* (minutos a pocas horas).
- Desde el proyecto se puede comprobar la publicación:
  ```
  dig +short TXT resend._domainkey.sertiattelier.com @1.1.1.1
  dig +short MX send.sertiattelier.com @1.1.1.1
  dig +short TXT send.sertiattelier.com @1.1.1.1
  dig +short TXT _dmarc.sertiattelier.com @1.1.1.1
  ```

## 4. Llave y servidor

- Resend → **API Keys → Create**, permiso *Sending access*, dominio `sertiattelier.com`.
- La llave (`re_...`) va **solo** en `.env.production` del servidor como `EMAIL_HOST_PASSWORD`. No pegarla en chats ni correos.
- Valores (ya preparados en `.env.production.example`):
  ```
  EMAIL_HOST=smtp.resend.com
  EMAIL_PORT=587
  EMAIL_USE_TLS=true
  EMAIL_HOST_USER=resend
  DEFAULT_FROM_EMAIL=SERTI Atelier <pedidos@sertiattelier.com>
  SERTI_ORDERS_EMAIL=<buzón donde SERTI recibe copias>
  ```
- Dashboard → Datos del sitio → **Correo de atención**: buzón para las respuestas de los clientes (Reply-To).
- Verificar con `check_production` y `send_test_email` hacia mail-tester.com (≥ 9/10) y Gmail/Outlook (SPF, DKIM, DMARC: PASS). Detalle en [correo.md](correo.md).

## 5. Después (despliegue)

- `A @` → IP del VPS; `CNAME www` → `sertiattelier.com` (Caddy redirige `www` y emite HTTPS solo).
- Tras 2–4 semanas de envíos sin fallos, endurecer DMARC a `p=quarantine`.
