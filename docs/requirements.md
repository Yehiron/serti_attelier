# Requisitos

## Origen y etiquetas

| Etiqueta | Significado | Fuente |
|---|---|---|
| **C** | Confirmado por el cliente en la reunión | Notas manuscritas `Serti_261023_114242.pdf` |
| **DC-xx** | Decisión posterior del cliente | [decisions.md](decisions.md) |
| **D** | Documentado previamente | Brief "Proyecto SERTI — E-commerce premium" y prototipo editorial |
| **R** | Recomendación técnica del equipo | Este documento |
| **P-xx** | Pendiente | [decisions.md](decisions.md#asuntos-pendientes) |

Prioridad: **M** = MVP obligatorio · **S** = MVP si cabe · **L** = posterior.

### Transcripción de las notas de reunión

- **Página 1:** Filtro por gema ✓ · Filtro por stock · Filtro por precio ✓ · Imágenes 16:9 y divisiones por categoría y por piedra (boceto de 3 paneles) · "Ipso facto al pasar por las categorías" · Pasarela de pago Wompi · Stock ✓, preordenado, nuevo · Categorías: Anillos, Aretes, Cadenas, Dijes, Pulseras o Brazaletes · Regalos, Novedades y Destacados, Sets, Descuentos · Envíos gratis.
- **Página 2:** Envío de correos · WhatsApp Business · Compras como invitado · Carrito de compras · Privacidad y cookies · Mi lista de deseos · Descripción de la pieza y resumen de compra · Buscador · Devoluciones · Redes sociales y contacto · Paleta de colores · Dashboard para manipular imágenes (webp) · Cambio de idioma ES/EN.
- **Página 3:** Boceto de 3 paneles inclinados "Diamond · Esmeraldas · Zafiros" · e-commerce · Preordenado → remitir al WhatsApp · Botón flotante WhatsApp · Personaliza tus joyas · Tipo tarjeta con cambio de fondo (parallax) · Términos y condiciones · Info del fabricante.
- **Página 4:** en blanco.

## 1. Catálogo y navegación

| ID | Requisito | Origen | Prioridad | Criterios de aceptación |
|---|---|---|---|---|
| CAT-01 | Categorías: Anillos, Aretes, Cadenas, Dijes, Pulseras/Brazaletes | C | M | Existen, son administrables y tienen URL propia en ES y EN |
| CAT-02 | Colecciones: Regalos, Novedades y Destacados, Sets, Descuentos | C | M | Administrables; una pieza puede estar en varias; orden manual |
| CAT-03 | Navegación por piedra: Diamante, Esmeralda, Zafiro | C | M | Página por piedra; la piedra es un atributo filtrable; imagen de portada 16:9 |
| CAT-04 | Filtros por gema, precio y disponibilidad | C | M | Combinables, reflejados en la URL, funcionan en la primera carga sin JS; "Disponibles ahora" por defecto, "Ver también vendidas" opcional |
| CAT-05 | Buscador | C | M | Busca por nombre, categoría, piedra y material, en ambos idiomas, sin importar tildes ni mayúsculas; estado vacío con sugerencias |
| CAT-06 | Estados de la pieza: disponible, reservada, vendida, preventa + etiqueta "nuevo" | C + DC-08 | M | Cada estado muestra su CTA (ver PU-01…PU-06) |
| CAT-07 | Preventa → WhatsApp | C | M | Una pieza en preventa no entra al carrito; el CTA abre WhatsApp con mensaje prellenado (nombre, SKU y URL) |
| CAT-08 | Descripción de la pieza | C | M | Ficha con historia, materiales, piedra, medidas, peso, cuidados y galería |
| CAT-09 | Información del fabricante | C | M | Página y bloque en la ficha; contenido administrable (P-09) |
| CAT-10 | Imágenes 16:9 en portadas | C | M | Hero, paneles de piedra y portadas de categoría en 16:9; la galería de producto usa 4:5 (R) |
| CAT-11 | Subcategorías | D | S | Un nivel bajo cada categoría |
| CAT-12 | Atributos de la pieza única (talla, largo, metal, quilates, peso) | D → DC-08 | M | Se muestran como datos, no como selector; el ajuste de talla se consulta por WhatsApp (P-17) |
| CAT-13 | Piezas relacionadas | D | S | Selección manual con respaldo automático (misma piedra o categoría, disponibles primero) |
| CAT-14 | SEO por idioma | D | M | Title, description y slug en ES y EN; `hreflang`, `canonical`, `sitemap.xml` y datos estructurados `Product` |
| CAT-15 | No eliminar piezas con ventas | D | M | `on_delete=PROTECT` desde `OrderItem`; el admin solo permite archivar |
| CAT-16 | Piezas vendidas visibles y ocultables | DC-16 | M | Por defecto siguen publicadas con estado "Vendida"; acción "Ocultar del catálogo" individual y masiva en el dashboard; una pieza oculta responde 404 y sale del sitemap |

## 2. La pieza única (DC-08, DC-09)

| ID | Requisito | Origen | Prioridad | Criterios de aceptación |
|---|---|---|---|---|
| PU-01 | Distintivo "Pieza única · 1 de 1" | R | M | Visible en listado y ficha; sin contadores de urgencia falsos |
| PU-02 | Reserva al pagar, no al agregar al carrito | R | M | Solo `POST /orders` reserva; dos compradores simultáneos → uno obtiene la reserva y el otro recibe `piece_reserved` |
| PU-03 | Estado "Reservada" | R | M | Mensaje: "Alguien está completando la compra de esta pieza…"; botón "Avísame por WhatsApp" |
| PU-04 | Estado "Vendida" con CTA de pieza a medida | DC-09 | M | CTA "Creemos una pieza única para ti" abre WhatsApp con el mensaje prellenado que nombra la pieza y su SKU |
| PU-05 | Pieza vendida en carrito o lista de deseos | DC-09 | M | Se marca como vendida, se retira del carrito con aviso y se ofrece el mismo CTA |
| PU-06 | "Duplicar como nueva pieza" en el dashboard | R | S | Copia atributos y textos a un borrador nuevo con SKU vacío |

## 3. Compra

| ID | Requisito | Origen | Prioridad | Criterios de aceptación |
|---|---|---|---|---|
| BUY-01 | Compra como invitado | C | M | Ningún paso pide cuenta ni contraseña |
| BUY-02 | Carrito persistente | C + D | M | Cookie `HttpOnly` firmada, 30 días; una unidad por pieza |
| BUY-03 | Resumen de compra | C | M | Antes de pagar se ven las piezas, el descuento, el envío ($0) y el total, calculados por el backend |
| BUY-04 | Pago con Wompi y todos sus métodos | C + DC-10 | M | Sandbox de punta a punta con tarjeta, PSE, Nequi y efectivo en corresponsal (queda `PENDING` hasta el pago) |
| BUY-05 | Envío gratis solo en Colombia | C + DC-01 | M | Dirección con departamento y municipio DANE; otro país → bloqueo con mensaje |
| BUY-06 | Lista de deseos en el navegador | C + DC-03 | M | `localStorage`; muestra el estado actual de cada pieza; no requiere backend |
| BUY-07 | Descuentos desde el dashboard | D + DC-02 | M | Precio rebajado por pieza y cupones (porcentaje o fijo, fechas, límite de usos, por categoría o colección, subtotal mínimo); regla de acumulación según P-04 |
| BUY-08 | Prevención de compras duplicadas | D | M | `Idempotency-Key` en la creación del pedido; un solo pago aprobado por pedido |
| BUY-09 | Recuperación de carrito | D | L | Requiere correo previo y consentimiento |
| BUY-10 | Pago manual fuera de Wompi con reserva de 24 h | DC-11 + DC-14 | M | El comprador elige "Pagar por otro medio"; recibe instrucciones por correo; la pieza queda reservada 24 h (configurable); SERTI confirma el pago en el dashboard con referencia y soporte adjunto; si no se confirma a tiempo, el pedido expira y la pieza se libera |
| BUY-11 | Certificado de autenticidad a solicitud | DC-15 | M | Casilla opcional en el checkout; queda en el pedido, en el correo de confirmación y en el aviso a SERTI; costo según P-21 |

## 4. Comunicación

| ID | Requisito | Origen | Prioridad | Criterios de aceptación |
|---|---|---|---|---|
| COM-01 | Correo de confirmación al comprador | C + D | M | Solo tras pago aprobado (webhook, conciliación o confirmación manual); identidad SERTI; ES/EN según el idioma del pedido; nunca dice "factura" |
| COM-02 | Aviso a SERTI por correo | D | M | Pedido, comprador, piezas, total, entrega, certificado solicitado y enlace al admin |
| COM-03 | Aviso a SERTI por WhatsApp | C + DC-04 | M | Plantilla *utility* aprobada por Meta, enviada por la API oficial de WhatsApp Cloud |
| COM-04 | Botón flotante de WhatsApp | C | M | Número y mensaje editables; accesible por teclado; no tapa CTA fijos ni el paso de pago |
| COM-05 | Personaliza tus joyas | C + DC-05 | M | Página informativa administrable con CTA a WhatsApp por servicio; los servicios se activan cuando el cliente responda (P-07, DC-17) |
| COM-06 | Redes sociales y contacto | C | M | Enlaces administrables en el pie y en la página de contacto |
| COM-07 | Instrucciones de pago manual | DC-14 | M | Correo con datos de pago (P-16), monto, referencia del pedido y hora límite de la reserva |

## 5. Contenido, idioma y legal

| ID | Requisito | Origen | Prioridad | Criterios de aceptación |
|---|---|---|---|---|
| CMS-01 | Imágenes con conversión a WebP | C | M | JPG/PNG/WebP de entrada; salida WebP en varios anchos; sin EXIF; texto alternativo ES/EN obligatorio |
| CMS-02 | Home editable sin código | D | M | Borrador → vista previa → publicar; historial con restauración |
| CMS-03 | Paneles de piedra con cambio de fondo | C *(interpretación, P-22)* | M | Al pasar o enfocar un panel, el fondo cambia de inmediato a la foto de esa piedra; en móvil, tarjetas apiladas |
| CMS-04 | Idioma ES/EN | C | M | Rutas `/es/…` y `/en/…`; español por defecto; preferencia persistida en cookie |
| CMS-05 | Paleta del prototipo | C + DC-06 | M | Tokens de DC-06; contraste AA verificado en cada combinación de texto y fondo |
| LEG-01 | Privacidad y cookies | C | M | Política de tratamiento de datos (Ley 1581 de 2012); aviso de cookies; casilla de autorización no premarcada en el checkout, guardada con fecha y versión |
| LEG-02 | Devoluciones | C | M | Política que respeta el derecho de retracto (Ley 1480, art. 47) y la reversión del pago (art. 51); excepciones para piezas personalizadas sujetas a validación legal |
| LEG-03 | Términos y condiciones | C | M | Página versionada; el pedido guarda la versión aceptada |
| LEG-04 | Sin facturación electrónica en el MVP | D | M | Exclusión técnica documentada, no exención legal (P-14); interfaz `InvoicingProvider` sin implementación |

## 6. Administración

| ID | Requisito | Origen | Prioridad | Criterios de aceptación |
|---|---|---|---|---|
| ADM-01 | Login, roles y permisos | D | M | Roles Propietario, Operaciones y Contenido con permisos definidos en [security-plan.md](security-plan.md#roles) |
| ADM-02 | Gestión de pedidos | D | M | Búsqueda, filtros, historial; estado de pago separado del estado operativo; transiciones permitidas por rol |
| ADM-03 | Indicadores | D | S | Ventas confirmadas, pedidos por estado, piezas vendidas por categoría y piedra, descuentos usados; solo cuentan pagos aprobados |
| ADM-04 | Auditoría | D | M | Quién, qué, cuándo y diff (sin datos sensibles) en cambios de precio, estado, descuento, confirmación manual y usuarios |
| ADM-05 | 2FA | R | S | TOTP obligatorio para Propietario |
| ADM-06 | Confirmar pago manual | DC-14 | M | Acción solo para Operaciones y Propietario; exige referencia y soporte; queda auditada |

## Fuera del MVP

Recuperación de carrito (BUY-09), dashboard a medida en Next.js (ADR-002), facturación electrónica (LEG-04), cuentas de cliente, reseñas, programa de fidelidad y envíos internacionales (DC-01).
