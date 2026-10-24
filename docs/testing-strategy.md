# Estrategia de pruebas

## Pirámide

| Nivel | Herramienta | Qué cubre | Dónde corre |
|---|---|---|---|
| Unitarias | pytest | Servicios puros: `pricing`, máquinas de estado, firma de Wompi, validadores | CI en cada push |
| Integración | pytest + PostgreSQL real (contenedor) + Redis | Servicios con base de datos, transacciones, concurrencia, API (DRF `APIClient`), tareas Celery en modo *eager* | CI en cada push |
| Contrato | `drf-spectacular` + cliente TS generado | El esquema OpenAPI no cambia sin actualizar el frontend | CI |
| E2E | Playwright (Chromium, WebKit; móvil y escritorio) | Recorridos completos contra el stack en Docker | CI en PR a `main`; nocturno contra *staging* |
| Seguridad | Tests dirigidos + herramientas | Ver abajo | CI y antes del lanzamiento |
| Accesibilidad y rendimiento | `@axe-core/playwright`, Lighthouse CI | WCAG 2.2 AA y presupuestos de rendimiento | CI en PR |

Cobertura mínima: **90 % en `pricing`, `inventory`, `orders` y `payments`**; 80 % en el resto del backend. La cobertura no reemplaza los casos críticos de abajo.

## Casos críticos

### Piezas únicas (`inventory`)
- Dos compradores piden la misma pieza al mismo tiempo (dos hilos con `select_for_update`) → una reserva, un `409 piece_reserved`.
- Reserva online vencida → la pieza vuelve a `available`; el pedido pasa a `expired`.
- Reserva manual de 24 h vencida sin confirmación → mismo resultado (DC-14).
- Una pieza `sold` no puede volver a `available` ni reservarse.
- Pieza oculta (DC-16) → 404 en la API pública y fuera del sitemap.

### Precios (`pricing`) — tabla de casos
| Caso | Esperado |
|---|---|
| Pieza sin descuento | total = precio |
| Pieza con precio rebajado | total = precio rebajado |
| Cupón porcentaje sobre pieza sin rebaja | aplica |
| Cupón sobre pieza rebajada con `applies_to_sale_items=False` | no aplica a esa pieza (P-04) |
| Cupón por categoría con piezas mixtas | aplica solo a las de la categoría |
| Subtotal bajo el mínimo del cupón | `coupon_min_subtotal` |
| Cupón vencido / agotado / inactivo | error específico |
| Cupón fijo mayor que el subtotal | el descuento no supera el subtotal; total > 0 |
| Certificado con costo (P-21) | se suma al total |
| Envío a cualquier municipio de Colombia | $0 |

### Pedidos y pagos
- `POST /orders` dos veces con la misma `Idempotency-Key` → un pedido; con cuerpo distinto → `idempotency_conflict`.
- Firma de integridad igual a la de un vector calculado a mano.
- Webhook con checksum válido → aplica; inválido → `rejected_checksum`, sin efecto.
- Webhook con `properties` en otro orden o con otras propiedades → se valida leyendo las del evento.
- Monto o moneda distintos → `mismatch`.
- Evento duplicado → `duplicate`, sin efecto ni segundo correo.
- Dos eventos `APPROVED` distintos para el mismo pedido → el índice único impide la segunda aprobación.
- Conciliación encuentra `APPROVED` sin webhook → aplica una sola vez.
- Pago aprobado tras vencer la reserva con la pieza ya vendida → `needs_attention` y alerta.
- Confirmación de pago manual por rol Contenido → 403; por Operaciones → aprobado y auditado.
- `fulfillment_status = preparing` sin pago aprobado → rechazado.

### Notificaciones
- Pago aprobado → exactamente un correo al comprador, uno a SERTI y un WhatsApp a SERTI (idempotencia por clave).
- Proveedor caído → reintentos con *backoff*; el pedido sigue `approved`.
- El correo de confirmación no contiene la palabra "factura" (test de plantilla, ES y EN).

### Idiomas
- Comando de traducciones faltantes falla si una pieza publicada no tiene campos `_en`.
- `hreflang` y `canonical` correctos en home, listado y ficha.

## E2E (Playwright)

| Recorrido | Dispositivo |
|---|---|
| Home → piedra → ficha → carrito → checkout → Wompi sandbox aprobado → confirmación | Móvil y escritorio |
| Pago rechazado → reintento aprobado | Móvil |
| Pago manual → instrucciones → confirmación desde el dashboard → confirmación del pedido | Escritorio |
| Pieza vendida → CTA de pieza a medida con el mensaje correcto | Móvil |
| Pieza vendida mientras está en el carrito → aviso y CTA | Móvil |
| Lista de deseos: guardar, recargar, ver estado | Móvil |
| Cambio de idioma conserva la página | Escritorio |
| Dashboard: crear pieza con fotos → publicar → aparece en el sitio; ocultar → desaparece | Escritorio |
| Dashboard: editar hero → vista previa → publicar | Escritorio |
| Navegación completa solo con teclado en el checkout | Escritorio |

Los E2E usan Wompi **sandbox** y adaptadores simulados de correo (Mailpit) y WhatsApp. **Nunca dinero real.**

## Seguridad

- Tests dirigidos de [security-plan.md](security-plan.md) (T1–T18).
- `manage.py check --deploy` en CI con settings de producción.
- `gitleaks`, `pip-audit`, `npm audit`, Dependabot.
- Subida de archivos maliciosos (SVG con script, *polyglot*, imagen gigante) → rechazados.
- IDOR: token aleatorio en `/orders/{token}` → 404; sin enumeración por tiempos de respuesta apreciables.
- Antes del lanzamiento: OWASP ZAP *baseline* contra *staging* y revisión manual de los flujos de pago.

## Datos de prueba
- *Factories* (`factory_boy`) para piezas, pedidos y cupones; sin datos personales reales.
- *Seed* de desarrollo: 3 piedras, 5 categorías, 4 colecciones, ~30 piezas con imágenes de marcador (DC-07).
