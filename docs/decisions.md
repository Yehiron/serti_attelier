# Decisiones y asuntos pendientes

Registro vivo. Cada decisión tiene un ID estable que el resto de documentos cita.

- **DC** = decisión comercial confirmada por el cliente.
- **ADR** = decisión técnica del equipo (Architecture Decision Record).
- **P** = asunto pendiente.

## Decisiones del cliente

| ID | Fecha | Decisión | Efecto |
|---|---|---|---|
| DC-01 | 2026-10-23 | Envíos **solo dentro de Colombia**, gratis | Dirección con departamento y municipio (códigos DANE); cualquier otro país se rechaza |
| DC-02 | 2026-10-23 | Los descuentos los crea SERTI **desde el dashboard** | Precio rebajado por pieza y cupones administrables |
| DC-03 | 2026-10-23 | Lista de deseos **en el navegador** | `localStorage`; sin backend ni datos personales |
| DC-04 | 2026-10-23 | **Aceptan el costo por mensaje** de WhatsApp Business | El aviso de pedido a SERTI por WhatsApp entra en el MVP |
| DC-05 | 2026-10-23 | Personalización: **información + contacto directo por WhatsApp**, sin formulario | Página editorial con CTA por servicio |
| DC-06 | 2026-10-23 | **Se mantiene la paleta del prototipo** | Tokens: vino `#591e24`, crema `#e9e3d0`, papel `#dbd4b7`, oliva `#736b51`, tinta `#24241e`, mineral `#4e7366`, oro `#a9946f` |
| DC-07 | 2026-10-23 | Las **fotografías llegan después** | Desarrollo con marcadores; guía de fotografía para el cliente |
| DC-08 | 2026-10-23 | **Todas las piezas son únicas** (1 de 1) | Sin variantes ni inventario por cantidades; la pieza tiene estado de venta |
| DC-09 | 2026-10-23 | Pieza agotada → **ofrecer fabricar una pieza única** | CTA "Creemos una pieza única para ti" a WhatsApp |
| DC-10 | 2026-10-23 | Métodos de pago: **los que ofrece Wompi** | Todos los que habilite la cuenta del comercio |
| DC-11 | 2026-10-23 | **Pago fuera de Wompi** (Efecty u otra entidad) con la pieza reservada | Canal de pago manual (ver DC-14) |
| DC-12 | 2026-10-23 | El **cliente compra el dominio**; se aloja en **el VPS del equipo** | HTTPS automático con Caddy cuando el DNS apunte al VPS |
| DC-13 | 2026-10-23 | **Repositorio nuevo** para la plataforma | Este repositorio (`serti_attelier`); el prototipo Vite queda como referencia visual |
| DC-14 | 2026-10-23 | Con pago fuera de Wompi, **la pieza se reserva 24 horas** | Reserva `manual` de 24 h (configurable); SERTI confirma el pago en el dashboard; al vencer, la pieza vuelve a estar disponible |
| DC-15 | 2026-10-23 | **Certificado de autenticidad a solicitud** del cliente | Casilla opcional en el checkout; el pedido lo registra y el aviso a SERTI lo destaca |
| DC-16 | 2026-10-23 | Las **piezas vendidas quedan visibles** en el catálogo; **desde el dashboard se pueden ocultar** | Por defecto visibles con estado "Vendida"; acción "Ocultar" (individual y masiva) en el dashboard |
| DC-17 | 2026-10-23 | Decisiones de **personalización pendientes** mientras el cliente responde | La página se construye con contenido administrable; los servicios se activan cuando se confirmen (P-07) |

## Decisiones técnicas (ADR)

### ADR-001 — Monolito modular Django + frontend Next.js
- **Contexto:** e-commerce pequeño al inicio, con SEO, dos idiomas, pagos y un panel administrativo.
- **Decisión:** un backend Django (DRF) organizado por dominios y un frontend Next.js (App Router). Sin microservicios.
- **Consecuencias:** dos runtimes que mantener, compensados por SEO/SSR en el frontend y por el ecosistema maduro de Django para el admin, la seguridad y el ORM.

### ADR-002 — Panel administrativo sobre Django Admin + Unfold
- **Contexto:** el brief pide un dashboard completo (catálogo, CMS, descuentos, pedidos, indicadores, roles).
- **Decisión:** en el MVP, Django Admin con el tema `django-unfold`, más vistas propias dentro del admin para indicadores y vista previa del home.
- **Alternativa descartada:** dashboard a medida en Next.js. Duplica autenticación, permisos, formularios y validaciones; se reevalúa en la v2.
- **Consecuencias:** login, permisos por modelo, CSRF, sesiones, búsqueda y filtros resueltos desde el día uno.

### ADR-003 — Mismo dominio para sitio y API
- **Decisión:** Caddy enruta `/api/*` y el admin a Django, y `/` a Next.js, bajo un único dominio.
- **Consecuencias:** sin CORS; la cookie del carrito es `HttpOnly` + `SameSite=Lax`.

### ADR-004 — CMS con modelos propios (sin Wagtail)
- **Decisión:** secciones del home, banners y páginas como modelos con estado borrador/publicado y tabla de revisiones; vista previa con *Draft Mode* de Next.js y token firmado.
- **Alternativa descartada:** Wagtail (segundo modelo de contenido y complejidad headless).

### ADR-005 — Traducción de contenido con `django-modeltranslation`
- **Decisión:** campos `_es` / `_en` en los modelos traducibles; un comando de gestión detecta traducciones faltantes.
- **Consecuencias:** simple para dos idiomas; agregar un tercer idioma requiere una migración.

### ADR-006 — Dinero en enteros de centavos COP
- **Decisión:** `BigIntegerField` en centavos (igual que `amount_in_cents` de Wompi); nunca `float` ni `Decimal` en cálculos de pago.

### ADR-007 — Pieza única como modelo de inventario
- **Decisión (derivada de DC-08):** el producto es la pieza. Su `sale_state` es `available | reserved | sold | preorder`. Un índice único parcial garantiza **una sola reserva activa por pieza**; la reserva se toma con `select_for_update()`.
- **Consecuencias:** sin variantes ni cantidades. Si en el futuro hay producción repetible, se introduce `Variant` en una migración aparte.

### ADR-008 — Canales de pago como adaptadores
- **Decisión:** `PaymentChannel` con dos implementaciones: `WompiChannel` y `ManualChannel` (DC-14). El pedido y la reserva no dependen del canal.

### ADR-009 — Notificaciones asíncronas con Celery
- **Decisión:** las notificaciones se encolan con `transaction.on_commit`; nunca dentro de la transacción del pago. Reintentos con *backoff* e idempotencia por `idempotency_key`.
- **Consecuencias:** el fallo de un proveedor no revierte un pago aprobado.

### ADR-010 — Imágenes procesadas en el backend
- **Decisión:** al subir, Pillow re-codifica la imagen (elimina EXIF y payloads) y genera versiones WebP en varios anchos. Next/Image usa un *loader* que apunta a esas versiones.
- **Almacenamiento:** `django-storages` con interfaz S3; en el MVP, volumen local.

## Asuntos pendientes

| ID | Pregunta | Responsable | Bloquea |
|---|---|---|---|
| P-01 | Transportadora, tiempos de entrega y si el envío va asegurado | Cliente | Textos de envío; Fase 5 (no bloquea el desarrollo) |
| P-04 | Aprobar la regla de acumulación de descuentos recomendada (un cupón por pedido; no sobre piezas ya rebajadas salvo que el cupón lo permita) | Cliente | Fase 5 |
| P-06 | Número de WhatsApp dedicado y verificación del negocio en Meta | Cliente | Fase 7 |
| P-07 | Servicios de personalización que ofrece SERTI y tiempos aproximados | Cliente | Contenido de la página (no bloquea el desarrollo) |
| P-09 | Qué información del fabricante se publica | Cliente | Contenido |
| P-10 | Fecha de entrega de la fotografía real | Cliente | Lanzamiento |
| P-11 | Estado de la cuenta Wompi (sandbox / producción) y métodos habilitados | Cliente | Fase 6 en producción |
| P-12 | Plazo de reserva en pagos en línea. **Propuesta:** 30 min para tarjeta, PSE y billeteras | Equipo + cliente | Fase 5 |
| P-13 | Nombre del dominio y proveedor de correo transaccional | Cliente | Fase 7 y 9 |
| P-14 | Validación tributaria de la exclusión de facturación electrónica | Contador del cliente | Lanzamiento |
| P-16 | Pago manual: **qué entidades** (Efecty, transferencia Bancolombia…), datos de pago que se muestran y **quién confirma** | Cliente | Fase 6 |
| P-17 | Ajuste de talla de anillos: ¿se ofrece? ¿costo? | Cliente | Contenido |
| P-18 | Plazo que da Wompi para pagar en efectivo en corresponsal Bancolombia | Equipo (soporte Wompi) | Fase 6 |
| P-21 | Certificado de autenticidad: ¿tiene costo? ¿se entrega físico, digital o ambos? | Cliente | Fase 5 |
| P-22 | Interpretación de dos notas manuscritas: "ipso facto al pasar por las categorías" y "(parallax)" | Cliente | Diseño del home |

Resueltos: P-02, P-03 (DC-08) · P-05 (DC-03) · P-08 (DC-06) · P-15 (DC-13) · P-19 (DC-16) · P-20 (DC-15).
