# Contrato de API

Base: `https://<dominio>/api/v1`. JSON UTF-8. La especificación OpenAPI se genera con `drf-spectacular` en `/api/v1/schema/` (solo en `dev` y `staging`) y el cliente TypeScript del frontend se genera desde ella.

## Convenciones

| Tema | Regla |
|---|---|
| Idioma | `?locale=es|en` o cabecera `Accept-Language`; por defecto `es`. Las respuestas traen solo los campos del idioma pedido |
| Dinero | Enteros en centavos COP: `{"amount_cents": 250000000, "currency": "COP"}`. El frontend formatea |
| Fechas | ISO 8601 con zona (`2026-10-23T19:40:00-05:00`) |
| Paginación | `?page=&page_size=` (máx. 48); respuesta `{count, next, previous, results}` |
| Errores | `application/problem+json` con `type`, `title`, `status`, `code` estable y `detail` traducido |
| Autenticación pública | Ninguna. El carrito se identifica con la cookie `serti_cart` (`HttpOnly`, `Secure`, `SameSite=Lax`, firmada) |
| Autenticación admin | Sesión de Django Admin + CSRF; no hay endpoints admin en esta API en el MVP (ADR-002) |
| Idempotencia | `Idempotency-Key` (UUID) obligatoria en `POST /orders` y `POST /orders/{token}/payment-attempts` |
| Límite de peticiones | Ver tabla al final |

### Códigos de error de dominio

| `code` | HTTP | Cuándo |
|---|---|---|
| `piece_not_found` | 404 | Pieza inexistente, oculta o en borrador |
| `piece_reserved` | 409 | Otra persona está pagando la pieza |
| `piece_sold` | 409 | La pieza ya se vendió |
| `piece_preorder` | 409 | La pieza es de preventa (va por WhatsApp) |
| `cart_empty` | 422 | Checkout sin piezas |
| `coupon_invalid` / `coupon_expired` / `coupon_exhausted` / `coupon_not_applicable` / `coupon_min_subtotal` | 422 | Cupón no aplicable |
| `shipping_not_covered` | 422 | Dirección fuera de Colombia o municipio inválido |
| `consent_required` | 422 | Falta aceptar términos o política de privacidad |
| `idempotency_conflict` | 409 | Misma clave con un cuerpo distinto |
| `payment_not_retryable` | 409 | El pedido ya está pagado, expirado o es manual |
| `rate_limited` | 429 | Límite superado |

Ejemplo:

```json
{
  "type": "https://<dominio>/errors/piece_sold",
  "title": "Pieza vendida",
  "status": 409,
  "code": "piece_sold",
  "detail": "Esta pieza ya encontró su dueño. Podemos crear una pieza única para ti.",
  "piece": { "slug": "anillo-halo-esmeralda", "whatsapp_url": "https://wa.me/57XXXXXXXXXX?text=..." }
}
```

## Catálogo

### `GET /catalog/taxonomy`
Categorías (con subcategorías), colecciones, piedras y materiales activos, para menús y filtros.

### `GET /catalog/pieces`
Filtros: `category`, `collection`, `stone` (múltiple), `material`, `price_min`, `price_max` (centavos), `availability=available|all` (por defecto `available`), `is_new`, `q` (búsqueda), `sort=newest|price_asc|price_desc|featured`, `page`.

```json
{
  "count": 37, "next": "…?page=2", "previous": null,
  "results": [{
    "slug": "anillo-halo-esmeralda",
    "sku": "SRT-AN-0012",
    "name": "Anillo halo esmeralda",
    "category": { "slug": "anillos", "name": "Anillos" },
    "stones": [{ "slug": "esmeralda", "name": "Esmeralda" }],
    "price": { "amount_cents": 480000000, "currency": "COP" },
    "sale_price": null,
    "sale_state": "available",
    "is_new": true,
    "image": { "src": "/media/…/960.webp", "srcset": "…", "width": 1600, "height": 2000, "alt": "…" }
  }],
  "facets": { "stones": [{ "slug": "esmeralda", "count": 21 }], "price": { "min_cents": 90000000, "max_cents": 1200000000 } }
}
```

### `GET /catalog/pieces/{slug}`
Detalle completo: descripciones, historia, atributos, galería, piedras, materiales, colecciones, relacionadas, SEO (`title`, `description`, `alternates: {es, en}`) y `cta`:

```json
"cta": { "kind": "add_to_cart" }
"cta": { "kind": "whatsapp", "reason": "preorder|reserved|sold", "url": "https://wa.me/…?text=…" }
```

### `GET /catalog/pieces/status?skus=SRT-AN-0012,SRT-DJ-0004`
Estado actual de varias piezas (lista de deseos y carrito). Máximo 50 SKU. Respuesta: `{ "SRT-AN-0012": "sold", … }`.

## Contenido

| Método y ruta | Descripción |
|---|---|
| `GET /cms/home` | Secciones publicadas en orden. Con `?preview=<token firmado>` devuelve el borrador (token de 10 min emitido desde el admin) |
| `GET /cms/pages/{slug}` | Página publicada (legales, fabricante, personaliza, contacto) |
| `GET /site/settings` | Público y cacheable: WhatsApp (número y mensajes), redes, correo de soporte, costo del certificado, versiones vigentes de términos y privacidad |
| `GET /locations/departments` | Departamentos DANE |
| `GET /locations/departments/{code}/municipalities` | Municipios del departamento |

## Carrito

| Método y ruta | Cuerpo | Respuesta |
|---|---|---|
| `GET /cart` | — | Carrito con piezas, estado de cada una y subtotal. Si alguna dejó de estar disponible, viene con `removed: [{sku, reason}]` |
| `POST /cart/items` | `{ "sku": "SRT-AN-0012" }` | 201 con el carrito. Crea la cookie si no existe. 409 `piece_sold` / `piece_preorder`. `piece_reserved` **no** impide agregar (se informa en el estado) |
| `DELETE /cart/items/{sku}` | — | 200 con el carrito |

## Checkout y pedidos

### `POST /checkout/quote`
Calcula totales sin crear nada.

```json
// petición
{ "coupon_code": "BIENVENIDA", "shipping": { "municipality_code": "05001" }, "wants_certificate": true }
// respuesta
{
  "items": [{ "sku": "SRT-AN-0012", "name": "Anillo halo esmeralda", "unit_price_cents": 480000000, "discount_cents": 48000000 }],
  "subtotal_cents": 480000000,
  "discount_cents": 48000000,
  "shipping_cents": 0,
  "certificate_cents": 0,
  "total_cents": 432000000,
  "currency": "COP",
  "coupon": { "code": "BIENVENIDA", "applied": true },
  "payment_channels": ["wompi", "manual"]
}
```

### `POST /orders` — requiere `Idempotency-Key`

```json
{
  "contact": { "name": "…", "email": "…", "phone": "+57…" },
  "shipping": { "municipality_code": "05001", "address_line": "…", "address_extra": "…", "notes": "…" },
  "coupon_code": "BIENVENIDA",
  "wants_certificate": true,
  "payment_channel": "wompi",
  "accepted_terms_version": "2026-10",
  "accepted_privacy_version": "2026-10",
  "locale": "es"
}
```

Efecto (una transacción): recalcula totales, bloquea las piezas, crea el pedido, el snapshot de ítems y la reserva (30 min online · 24 h manual), y el primer intento de pago.

Respuesta `201` para Wompi:

```json
{
  "number": "SRT-000123",
  "public_token": "q8…",
  "total_cents": 432000000,
  "payment_status": "pending",
  "reservation_expires_at": "2026-10-23T20:10:00-05:00",
  "wompi": {
    "public_key": "pub_test_…",
    "reference": "SRT-000123-01",
    "amount_in_cents": 432000000,
    "currency": "COP",
    "signature_integrity": "<sha256>",
    "redirect_url": "https://<dominio>/es/pedido/q8…",
    "customer_email": "…"
  }
}
```

Respuesta `201` para el canal manual: igual, sin `wompi`, con `payment_status: "awaiting_manual_payment"` y `manual_instructions` (texto administrable, P-16).

Errores: `piece_reserved`, `piece_sold`, `coupon_*`, `shipping_not_covered`, `consent_required`, `idempotency_conflict`. Repetir la petición con la misma clave y el mismo cuerpo devuelve el mismo pedido.

### `GET /orders/{public_token}`
Estado para la página de confirmación: número, piezas, totales, estados, `reservation_expires_at`, `wants_certificate` y datos de entrega **parciales** (municipio, sin dirección completa). Sin correo ni teléfono completos.

### `POST /orders/{public_token}/payment-attempts` — requiere `Idempotency-Key`
Nuevo intento Wompi tras un rechazo o error, si la reserva sigue vigente. Devuelve un bloque `wompi` con referencia nueva. `409 payment_not_retryable` si no aplica.

## Webhook de Wompi

### `POST /payments/wompi/events`
- Sin autenticación de sesión; **la autenticidad se valida con el checksum** (ver [integrations.md](integrations.md#wompi)).
- Responde **200** siempre que el evento se haya registrado, incluso si es duplicado o no aplica, para que Wompi no reintente sin sentido. Responde 400 solo si el cuerpo no es JSON válido.
- No expone detalles de validación en la respuesta.

## Salud

| Ruta | Uso |
|---|---|
| `GET /health/live` | El proceso responde |
| `GET /health/ready` | Base de datos y Redis disponibles (para Docker y monitoreo) |

## Límites de peticiones

| Endpoint | Límite |
|---|---|
| `GET /catalog/*`, `/cms/*`, `/site/*` | 120/min por IP (cacheable en el borde) |
| `POST /cart/items` | 30/min por IP |
| `POST /checkout/quote` | 20/min por carrito |
| `POST /orders`, `POST …/payment-attempts` | 5/min por carrito y 20/h por IP |
| Validación de cupón (dentro de `quote`) | 10 cupones distintos/h por carrito |
| `POST /payments/wompi/events` | Sin límite por IP; protegido por checksum y tamaño máximo de cuerpo (64 KB) |
