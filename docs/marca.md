# Marca SERTI: uso en el sitio

Fuente: carpeta `Marca` entregada por el cliente (octubre 2026): 12 logos PNG de 800×800 px con fondo transparente, 5 muestras de color y la tipografía Ninna. Sustituye la paleta y el monograma del prototipo (DC-06).

## Logos

Son 5 piezas, cada una en 2 o 3 colores. En el sitio están en `frontend/public/brand/logo/`, recortadas a su contenido y en WebP (17–43 KB).

| Pieza | Archivos originales | Archivo web | Uso |
|---|---|---|---|
| **Logotipo** «serti Jewelry Atelier» | 1 vino · 2 dorado · 9 oliva | `wordmark-*.webp` | Firma principal: cabecera en escritorio, menú móvil, correo, redes, schema.org |
| **Monograma con lema** «Timeless and Sophisticated» | 3 vino · 4 dorado | `monogram-tagline-*.webp` | Cierre de marca: pie de página, empaques, certificados |
| **Monograma** | 5 dorado · 6 vino | `monogram-*.webp` | Espacios pequeños: cabecera en móvil, favicon, ícono de iOS, avatar de redes y WhatsApp |
| **Ornamento** (arco con hojas) | 7 vino · 8 dorado | `ornament-*.webp` | Separador editorial bajo títulos y en secciones de historia |
| **Monograma floral** | 10 vino · 11 dorado · 12 oliva | `floral-*.webp` | Pieza especial: **certificado de autenticidad** (en uso); a futuro, empaque, tarjeta de agradecimiento y portada de colección |

**Dónde está aplicado:**
- **Cabecera:**
  - En escritorio, el logotipo: vino sobre crema y dorado sobre el hero vino.
  - En móvil, solo el monograma, porque el logotipo no cabe junto a los 5 íconos.
- **Menú móvil:** logotipo dorado.
- **Pie de página:** monograma con lema, en dorado.
- **Separadores:** ornamento vino en fondos claros y dorado en fondos vino.
- **Favicon e ícono de iOS:** monograma vino sobre crema.
- **Correos:** monograma vino.
- **Certificado de autenticidad:** monograma floral vino como encabezado (ver abajo).
- **Marca de agua:** monograma sin texto (`monogram-mark.webp`, coloreado con máscara CSS) al 8 % en los desplegables del menú, que son translúcidos con desenfoque, y al 6 % en crema detrás del menú del celular.
- **Favoritos:** corazón simétrico propio, sin logo. Vacío: contorno vino. Guardado: relleno **esmeralda `#0b6e4f`** y un pulso breve al agregarlo (sin animación con «reducir movimiento»). El corazón del encabezado se pone esmeralda cuando hay favoritos. El esmeralda es un acento funcional, no un color de la paleta, y tiene contraste 4,5:1 sobre crema.

### Reglas

- **Vino** (#651c32) sobre fondos claros y **dorado** sobre vino o ciruela. Los dorados son un degradado metálico: sobre crema desaparecen (contraste 1,05:1), así que nunca deben ir sobre crema. El vino sobre ciruela tampoco funciona (1,5:1).
- Las versiones **oliva** (9 y 12) son secundarias: sellos discretos en papelería o fondos crema donde el vino sea demasiado fuerte. No sirven para texto ni para piezas pequeñas.
- **Tamaño mínimo en pantalla:**
  - Logotipo: 32 px de alto. Por debajo, «Jewelry Atelier» deja de leerse; en ese caso se usa el monograma.
  - Monograma: 24 px.
- **Espacio libre:** como mínimo, la altura de la «s» del logotipo alrededor de cualquier versión.
- No deformar, rotar, recolorear ni poner sombras. No poner el logotipo sobre fotos con mucho detalle sin un velo de color de la paleta.

### Pendiente con el cliente

1. **Archivos vectoriales** (SVG, AI o PDF) de las 5 piezas. Los PNG de 800 px sirven para la web, pero no para impresión, gran formato ni bordado.
2. **Ortografía:** el logotipo dice «Jewelry **Attelier**» (doble t). En inglés y en francés la palabra es «Atelier». Hay que confirmar si es intencional, porque ya está en el logo y en el nombre del repositorio.
3. El lema y el descriptor están en inglés («Timeless and Sophisticated», «Jewelry Atelier»), mientras que el sitio es principalmente en español. Si se quiere una versión en español, la debe hacer el diseñador.

## Paleta

| Color | Hex | Rol en el sitio |
|---|---|---|
| Vino | `#651c32` | Color principal: títulos, botones, cabecera sobre el hero, pie de página, secciones destacadas |
| Carmesí | `#8a1538` | Acento: estado *hover* de botones, escala del dashboard |
| Crema | `#ead9cb` | Fondo principal y texto sobre vino |
| Ciruela | `#330414` | Texto de cuerpo y fondos oscuros (escenario de piedras) |
| Oliva | `#7a7256` | Líneas finas, separadores y bordes. **No para texto pequeño** (3,5:1) |

Tonos derivados (no son colores nuevos de marca):
- **Papel** `#dfc9b8`: crema un poco más oscura, para superficies como el fondo de fotos y avisos.
- **Oliva profunda** `#58513d`: texto secundario pequeño, como etiquetas, *placeholders* y precio tachado (5,75:1 sobre crema).

Contraste (WCAG 2.2):

| Combinación | Contraste | Resultado |
|---|---|---|
| Vino / crema | 8,7:1 | Apta para texto |
| Carmesí / crema | 6,8:1 | Apta para texto |
| Ciruela / crema | 13,1:1 | Apta para texto |
| Dorado de logo / vino | 9,1:1 | Apta para texto |
| Oliva / crema | 3,5:1 | Solo texto grande o decoración |
| Vino / ciruela, vino / carmesí, crema / dorado | Menos de 1,6:1 | Nunca juntos |

Están definidos como variables en `frontend/app/globals.css` (`--color-*`), en la escala `primary` del dashboard (`UNFOLD.COLORS`: carmesí 600, vino 800, ciruela 950) y en las plantillas de correo.

## Tipografía

| Uso | Fuente | Detalle |
|---|---|---|
| Títulos y textos de display | **Ninna**, de Margot Lévêque | Regular para títulos; Italic y Book Italic para la segunda línea de los títulos editoriales (por ejemplo «*Un poco de eternidad.*») |
| Texto de cuerpo, menús, botones y formularios | **Inter** (sin cambios) | Ninna es una romana de *display* y no está pensada para texto pequeño. La marca no entregó una fuente de texto |
| Respaldo de títulos | Cormorant Garamond | Se usa si Ninna no está instalada |

La fuente cubre todo el español: tildes, ñ, ü, ¿ ¡, números y $.

### ⚠️ Licencia de Ninna: obligatoria antes del lanzamiento

Los archivos entregados son **«Ninna Trial»**. Las versiones de prueba de esta fundidora son para evaluación y **no permiten uso comercial ni publicación en un sitio web**. Por eso:

- Los archivos **no se suben al repositorio**: `frontend/public/fonts/` está en `.gitignore`. En este equipo están instalados solo para la vista previa local.
- Sin los archivos, el sitio funciona igual y los títulos se muestran en Cormorant Garamond.
- **Antes de salir en vivo**, el cliente debe comprar la **licencia web** en https://margotleveque.com/pages/licenses, idealmente con los archivos WOFF2, que pesan menos.
- Los archivos con licencia se copian en el servidor como se indica en `docs/deployment.md` («Fuentes con licencia»).
- Si la licencia también cubrirá impresión o redes sociales, conviene confirmar los usos con la fundidora.

## Certificado de autenticidad

Se genera desde el dashboard: *Pedidos › (pedido) › Certificado de autenticidad › Abrir certificado para imprimir* (o con la acción «Imprimir certificado de autenticidad» de la lista).

- Solo se emite si el cliente lo pidió en el checkout y el pago está aprobado.
- Es una hoja A4 horizontal por pieza, en el idioma del pedido.
- Lleva el monograma floral vino, el título en Ninna, el texto de autenticidad y los datos de la pieza: nombre, número de pieza, SKU, piedras y materiales.
- También incluye el nombre del titular, la fecha de pago, el número de pedido, un código único (`pedido-SKU`) y una línea para la firma y el sello.
- Para entregarlo impreso, se usa papel de buen gramaje. Para el formato digital se elige «Guardar como PDF» en la ventana de impresión.

Pendiente con el cliente (P-21):
- Aprobar el texto: «diseñada y hecha a mano en Colombia».
- Definir si el certificado va firmado a mano o con firma digital.
- Decidir si se quiere una página pública de verificación por código.
