# Plan de seguridad

Referencias: OWASP ASVS 4.0 (nivel 2 como objetivo), *checklist* de despliegue de Django, Ley 1581 de 2012 (protección de datos personales) y Ley 1480 de 2011 (Estatuto del Consumidor).

## Activos

| Activo | Por qué importa |
|---|---|
| Dinero y estado de los pagos | Un pago falso marcado como aprobado = pieza única entregada sin cobrar |
| Piezas únicas | Una venta doble no se puede reponer |
| Datos personales de compradores | Ley 1581; reputación |
| Cuentas del dashboard | Control total del catálogo, precios y pedidos |
| Secretos (Wompi, correo, WhatsApp, Django) | Permiten suplantar al comercio |

## Amenazas y controles

| # | Amenaza | Control | Verificación |
|---|---|---|---|
| T1 | Manipular precio o total desde el navegador | `pricing` recalcula todo; el cliente solo envía SKU, cupón y municipio | Test: total enviado por el cliente se ignora |
| T2 | Webhook falso que aprueba un pago | Checksum SHA-256 (propiedades del evento + `timestamp` + secreto de eventos) con comparación en tiempo constante; verificación de referencia, monto en centavos y moneda contra el intento guardado; conciliación consulta a Wompi con la llave privada | Tests con checksum inválido, monto alterado y referencia desconocida |
| T3 | Estado de pago informado solo por el frontend | La página de retorno solo lee la base de datos | Test E2E: manipular la URL de retorno no cambia el estado |
| T4 | Venta doble de una pieza | `select_for_update()` + índice único de reserva activa + índice único de pago aprobado por pedido | Test concurrente con dos hilos |
| T5 | Pago manual confirmado sin pago real | Solo roles Operaciones y Propietario; exige referencia y soporte; auditoría; aviso al Propietario | Test de permisos; registro en `AuditLog` |
| T6 | IDOR en pedidos | URLs con `public_token` de 256 bits; nunca ID ni número secuencial; la vista pública oculta correo, teléfono y dirección completa | Test: token aleatorio → 404 |
| T7 | Fuerza bruta en el dashboard | `django-axes` (bloqueo por usuario + IP), 2FA TOTP, ruta del admin configurable, *rate limit* en Caddy | Test de bloqueo tras N intentos |
| T8 | Abuso de cupones | *Throttling* por carrito e IP; límites por correo (hash con *pepper*); redención solo con pago aprobado | Tests de límites |
| T9 | XSS | React escapa por defecto; contenido del CMS en bloques estructurados; texto enriquecido sanitizado con `nh3`; CSP estricta | Test de payloads en campos del CMS |
| T10 | CSRF | Mismo dominio; CSRF de Django en el admin y en mutaciones con cookie; `SameSite=Lax` | Test sin token → 403 |
| T11 | Archivos maliciosos | Lista blanca por contenido (Pillow abre y re-codifica); límite de 15 MB y 40 MP; nombres aleatorios; medios servidos sin ejecución y con `Content-Type` fijo | Tests con SVG, polyglot y archivo gigante |
| T12 | Inyección SQL | Solo ORM y consultas parametrizadas; prohibido `raw()` con interpolación (regla de Ruff y revisión) | Revisión de código |
| T13 | Fuga de secretos | Variables de entorno; `.env` fuera del repo; `gitleaks` en CI; llaves de sandbox y producción separadas | CI |
| T14 | Fuga de datos en logs | Filtro que enmascara correo, teléfono, dirección, documento y payloads; Sentry con `send_default_pii=False` | Test del filtro |
| T15 | Secuestro de sesión | Cookies `HttpOnly`, `Secure`, `SameSite`; rotación al iniciar sesión; expiración por inactividad (30 min) en el admin | Configuración verificada por `manage.py check --deploy` |
| T16 | Dependencias vulnerables | Dependabot, `pip-audit`, `npm audit` en CI; imágenes base con versión fija | CI |
| T17 | Pérdida de datos | `pg_dump` diario cifrado a almacenamiento externo; retención 30 días; **prueba de restauración mensual** | Registro de la prueba |
| T18 | Denegación de servicio simple | Límites por endpoint (ver [api-contract.md](api-contract.md#límites-de-peticiones)); tamaño máximo de cuerpo; *timeouts* | Prueba de carga básica |

## Roles

| Permiso | Propietario | Operaciones | Contenido |
|---|---|---|---|
| Usuarios y roles | ✅ | — | — |
| Piezas: crear, editar, publicar, ocultar | ✅ | ✅ | ✅ |
| Precios y precio rebajado | ✅ | ✅ | — |
| Cupones | ✅ | ✅ | — |
| Home, páginas, banners | ✅ | — | ✅ |
| Pedidos: ver | ✅ | ✅ | — |
| Pedidos: cambiar estado operativo | ✅ | ✅ | — |
| **Confirmar pago manual** | ✅ | ✅ | — |
| Configuración del sitio (WhatsApp, plazos, instrucciones de pago) | ✅ | — | — |
| Indicadores | ✅ | ✅ | — |
| Auditoría (lectura) | ✅ | — | — |

2FA obligatorio para Propietario; recomendado para todos.

## Configuración

- Django: `DEBUG=False`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS=31536000`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER`, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` explícitos, `PASSWORD_HASHERS` con Argon2 primero, validadores de contraseña con longitud mínima 12.
- Caddy: HSTS, `Content-Security-Policy` (scripts propios + `checkout.wompi.co`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` restrictiva, `X-Frame-Options: DENY` (excepto lo que Wompi requiera).
- CORS: deshabilitado (mismo dominio, ADR-003).
- Contenedores: usuario no root, sistema de archivos de solo lectura donde se pueda, solo Caddy expone puertos (80/443).
- VPS: SSH solo con llave, firewall (80/443/SSH), actualizaciones automáticas de seguridad, `fail2ban`.

## Datos personales (Ley 1581 de 2012)

- **Mínimos:** nombre, correo, celular, dirección y, solo si Wompi o la transportadora lo exigen, documento.
- **Autorización:** casilla no premarcada en el checkout, guardada con fecha y versión de la política.
- **Política de tratamiento** publicada: responsable, finalidades (venta, entrega, comunicaciones del pedido), derechos del titular, canal de consultas y reclamos, encargados (Wompi, proveedor de correo, Meta/WhatsApp, VPS).
- **Cookies:** solo las necesarias (carrito, idioma, sesión del admin). Si se agrega analítica, aviso con opción de rechazar.
- **Retención:** ver [database-design.md](database-design.md#retención-ley-1581).
- **Lista de deseos:** solo en el navegador; no se recolectan datos (DC-03).

## Consumidor (Ley 1480 de 2011)

En ventas a distancia aplican el **derecho de retracto** (5 días hábiles, art. 47) y la **reversión del pago** (art. 51). Las piezas personalizadas pueden estar exceptuadas. La política de devoluciones debe revisarla un abogado antes del lanzamiento.

## Facturación

La ausencia de facturación electrónica es una **exclusión técnica del MVP, no una exención legal**. El correo de confirmación nunca se llama "factura". La obligación tributaria del comercio la valida su contador (P-14).

## Pruebas de seguridad

Ver [testing-strategy.md](testing-strategy.md#seguridad). Antes del lanzamiento: `manage.py check --deploy` sin advertencias, escaneo con OWASP ZAP (*baseline*) contra *staging*, revisión manual de los flujos de pago y de confirmación manual.
