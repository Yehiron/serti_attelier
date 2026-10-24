# Plan UX/UI

## Principios

1. **Cada pieza es única (DC-08).** El diseño trata la pieza como una obra: una foto grande, su historia, su número. Sin urgencia falsa.
2. **La marca cuenta, el catálogo vende.** Narrativa editorial en el home, la historia y la personalización; claridad máxima en listado, ficha y checkout.
3. **Móvil primero.** La mayoría del tráfico de joyería llega desde redes sociales en el celular.
4. **WhatsApp como puente, no como escape.** Preventa, piezas vendidas y personalización terminan en una conversación con contexto (mensaje prellenado).
5. **Accesible y rápido.** WCAG 2.2 AA y Core Web Vitals en verde.

## Referente: Qirat — "Made for you"

Revisado el 2026-10-23 en https://www.qiratjewels.com/pages/made-for-you (tienda Shopify).

| Funciona | Oportunidad para SERTI |
|---|---|
| Promesa en una frase ("Made Only For You") y un único CTA | La página es solo hero + 4 fotos + botón: no explica proceso, tiempos, precios ni qué preparar |
| El CTA va **directo a WhatsApp** | Sin mensaje prellenado: la conversación empieza en frío |
| Paleta cálida vino/crema, muy cercana a la de SERTI | Diferenciarse con tipografía editorial y la historia de la pieza única |
| Menú por tipo, **por piedra** (Emerald, Ruby, Sapphire, Diamond) y por colección; **Pre-Order** en el menú | Mezcla idiomas (contenido en inglés, políticas en español) |
| Botón flotante de WhatsApp y políticas en el pie | Plantilla genérica; poca identidad propia |

## Arquitectura de navegación

```
Inicio
├── Joyería ▸ Anillos · Aretes · Cadenas · Dijes · Pulseras
├── Piedras ▸ Diamante · Esmeralda · Zafiro
├── Colecciones ▸ Novedades y Destacados · Sets · Regalos · Descuentos
├── Personaliza tus joyas
├── Nuestra historia (marca + fabricante)
└── Contacto
Utilidades: Buscar · Lista de deseos · Carrito · ES/EN
Pie: redes · términos · privacidad y cookies · devoluciones · envíos · fabricante
```

Rutas: `/es/joyeria/anillos`, `/en/jewelry/rings`, `/es/piedras/esmeralda`, `/es/piezas/{slug}`, `/es/colecciones/{slug}`, `/es/personaliza`, `/es/pedido/{token}`.

## Pantallas

### Home
1. Hero 16:9 administrable.
2. Statement de marca (del prototipo).
3. **Paneles de piedra** (CMS-03): tres paneles inclinados — Diamante, Esmeralda, Zafiro. Al pasar el cursor o enfocar con teclado, el fondo de la sección cambia **al instante** a la foto de esa piedra *(interpretación de "ipso facto", P-22)*. En móvil: tres tarjetas apiladas, cada una con su foto.
4. Novedades (carrusel).
5. Colecciones destacadas.
6. Historia y fabricante.
7. Bloque "Personaliza tus joyas".
8. Pie.

```
┌──────────────────────────────────────────────┐
│  [Fondo: foto de la piedra en foco]          │
│   ╱ Diamante ╱ ╱ Esmeralda ╱ ╱ Zafiro ╱       │
│   ver piezas →                               │
└──────────────────────────────────────────────┘
```

### Listado (PLP)
- Móvil: grilla de 2 columnas; filtros en un *bottom sheet*; chips de filtros activos; contador de resultados.
- Escritorio: 3–4 columnas; filtros en barra lateral.
- Filtros: piedra, precio (rango), disponibilidad ("Disponibles ahora" por defecto / "Ver también vendidas"), categoría, colección, material.
- Tarjeta: foto 4:5, nombre, precio (y precio rebajado), distintivo de estado, corazón de lista de deseos.

### Ficha (PDP)

```
Móvil                                   Escritorio
┌──────────────────┐                    ┌─────────────────┬───────────────┐
│ Galería 4:5 (swipe)│                  │ Galería         │ Pieza única   │
│ ● ○ ○            │                    │ (miniaturas)    │ · 1 de 1      │
├──────────────────┤                    │                 │ Nombre        │
│ Pieza única·1 de 1│                   │                 │ $ Precio      │
│ Nombre    ♡      │                    │                 │ Talla 6 · Oro │
│ $ Precio         │                    │                 │ 18k · 4,2 g   │
│ Talla · metal    │                    │                 │ [ CTA ]       │
│ ▸ Historia       │                    │                 │ ▸ Historia    │
│ ▸ Materiales     │                    │                 │ ▸ Materiales  │
│ ▸ Envío y devol. │                    │                 │ ▸ Envío…      │
├──────────────────┤                    └─────────────────┴───────────────┘
│ [ CTA fijo ]     │
└──────────────────┘
```

CTA según el estado:

| Estado | CTA |
|---|---|
| `available` | "Agregar al carrito" |
| `reserved` | "Alguien está completando la compra…" + "Avísame por WhatsApp" |
| `sold` | "Vendida — encontró su dueño" + **"Creemos una pieza única para ti"** (DC-09) |
| `preorder` | "Preordenar por WhatsApp" |

### Carrito
*Drawer* lateral. Piezas sin selector de cantidad, botón de quitar, aviso si alguna se vendió, subtotal del servidor, "Envío gratis en Colombia".

### Checkout (una página, tres bloques)
1. **Contacto:** nombre, correo, celular.
2. **Entrega:** departamento → municipio (DANE), dirección, indicaciones.
3. **Resumen y pago:** piezas, cupón (plegado), casilla "Quiero certificado de autenticidad" (DC-15), total, casillas de términos y privacidad (no premarcadas), medio de pago:
   - **Pagar en línea con Wompi** (tarjeta, PSE, Nequi, Daviplata, Bancolombia, efectivo en corresponsal…)
   - **Pagar por otro medio** (DC-14): "Te reservamos la pieza 24 horas mientras pagas. Te enviaremos las instrucciones por correo."

Atributos `autocomplete` correctos, validación en línea, errores asociados al campo, total siempre visible (barra fija en móvil). El botón de WhatsApp flotante se oculta en el checkout.

### Confirmación (`/pedido/{token}`)
- Wompi aprobado: "Esta pieza es solo tuya." Resumen, número de pedido, certificado (si se pidió).
- Pendiente: "Estamos confirmando tu pago…", con consulta automática cada pocos segundos.
- Rechazado: motivo genérico y "Intentar de nuevo" mientras la reserva siga vigente.
- Manual: instrucciones de pago, cuenta regresiva de 24 h y enlace a WhatsApp.

### Lista de deseos
Página `/es/deseos` con las piezas guardadas en el navegador (DC-03), su estado actual y el CTA correspondiente.

### Estados transversales
Vacío (carrito, búsqueda, lista de deseos, colección sin piezas) · carga (*skeletons* con la proporción real de la imagen) · error (red, pago, pieza no disponible) · éxito. Todos con texto en ES y EN.

## Personaliza tus joyas (DC-05; servicios pendientes, DC-17)

### Investigación: qué ofrece el sector

| Servicio | Práctica habitual | Fuente |
|---|---|---|
| Grabado | Iniciales, nombres, fechas, frases cortas y símbolos; en argollas, letra manuscrita o huella dactilar en la cara interior; límite de caracteres | Tiffany, Pandora, joyeros independientes |
| Láser vs. a mano | Láser: preciso y económico. A mano o con punta de diamante: artesanal, mayor valor percibido; monogramas y sellos | Pandora; casas *bespoke* |
| Marcado de autenticidad | Marca de ley (750 en oro de 18 k, 925 en plata) y sello de la casa | Práctica del oficio *(confirmar qué usa SERTI)* |
| Diseño a medida | Consulta → piedra y metal → boceto o render 3D con revisiones → fabricación → control de calidad y entrega; 3 a 7 semanas | Larsen, Rox, Agua de Oro, Royal Mint, Jarrett |
| Selección de piedra | Mostrar piedras sueltas y explicar su calidad | Joyeros *bespoke* |
| Compromiso y matrimonio | Anillos de compromiso, argollas, anillos de familia | Qirat |
| Rediseño de joyas heredadas | Reutilizar oro y piedras de una joya familiar | Práctica habitual *(confirmar)* |
| Política | Las piezas grabadas o personalizadas no admiten devolución | Tiffany, Pandora |

### Estructura propuesta (contenido administrable)
1. **Apertura:** "Una pieza que solo puede ser tuya."
2. **Qué podemos crear:** tarjetas por servicio, cada una con su CTA a WhatsApp y su mensaje prellenado. Los servicios se activan o desactivan desde el dashboard cuando SERTI confirme cuáles ofrece (P-07).
3. **El proceso en 4 pasos:** conversación → piedra y metal → boceto para aprobar → taller y entrega.
4. **Antes de escribirnos, ten a mano:** ocasión, fecha, piedra y metal, talla o largo, presupuesto aproximado y fotos de referencia.
5. **Inspiración:** piezas vendidas ("Esta ya encontró su dueño; la tuya está por hacerse").
6. **Preguntas frecuentes:** precio, tiempos, devoluciones (sujeto a validación legal), certificado.
7. **CTA final.**

Mensaje prellenado (editable): "Hola SERTI, vengo de la página de personalización. Me interesa: *{servicio}*. Ocasión: ___. Fecha: ___."

Fuentes: [Tiffany — grabado](https://www.tiffany.com/faq/engraving-faq/) · [Tiffany — estilos de grabado](https://www.tiffany.ie/faq/engraving-faq/what-are-the-different-engraving-styles-and-prices/) · [Pandora — cómo grabar](https://uk.pandora.net/en/engraving/how-to-engrave-jewellery/) · [Larsen Jewellery](https://larsenjewellery.com.au/services/our-bespoke-process) · [Rox](https://Rox.co.uk/engagement-rings/bespoke) · [Agua de Oro](https://aguadeoro.com/pages/creations-and-services) · [Royal Mint](https://886.royalmint.com/pages/our-bespoke-services) · [Jarrett](https://jarrettjewellery.com.au/pages/custom-design) · [My Jewellery Shop](https://myjewelleryshop.com.au/pages/custom-designs) · [Qirat](https://www.qiratjewels.com/pages/made-for-you)

## Direcciones visuales (paleta fija, DC-06)

| | A. Editorial Vino | B. Galería Crema | C. Vitrina Nocturna |
|---|---|---|---|
| Idea | El prototipo tal cual: revista de lujo | La pieza sobre crema y papel; vino solo en acentos | Tinta y vino de fondo; las piedras brillan |
| Fortaleza | Identidad fuerte, ya validada | Legibilidad y conversión | Dramatismo |
| Riesgo | El fondo compite con las fotos | Menos impacto de marca | Fatiga visual y contraste en textos largos |

**Recomendación: A + B.** Vino en home, historia y personalización; crema en catálogo, ficha y checkout.

Tipografía: Cormorant Garamond (titulares) + Inter (texto e interfaz), como en el prototipo.

## WhatsApp flotante (COM-04)
- Esquina inferior derecha, 56 px, con etiqueta accesible "Escríbenos por WhatsApp".
- Se oculta en el checkout y se desplaza hacia arriba cuando aparece el CTA fijo de la ficha en móvil.
- Enlace oficial `https://wa.me/<número>?text=<mensaje codificado>`; mensaje distinto según la página (general, ficha, personalización).

## Accesibilidad y rendimiento

| Objetivo | Medida |
|---|---|
| LCP < 2,5 s (4G) | Hero con `priority`, WebP, tamaños correctos, fuentes con `display=swap` y *preload* |
| CLS < 0,1 | Dimensiones reservadas en todas las imágenes; *skeletons* con proporción real |
| INP < 200 ms | Componentes de servidor por defecto; JS solo donde hay interacción |
| WCAG 2.2 AA | Contraste verificado sobre la paleta; foco visible; objetivos ≥ 24 px; `prefers-reduced-motion`; formularios con etiquetas y errores asociados; *skip link* |
| SEO | `hreflang`, `canonical`, `sitemap.xml` por idioma, datos estructurados `Product` y `Organization` |

## Guía de fotografía para el cliente (DC-07)
- Portadas (hero, piedras, categorías): 16:9, mínimo 2400 px de ancho.
- Producto: 4:5, mínimo 2000 px de alto; fondo y luz consistentes; 3–6 fotos por pieza (frente, perfil, detalle de la piedra, en uso).
- Formato de entrega: JPG o PNG de alta calidad; el sistema genera WebP.
