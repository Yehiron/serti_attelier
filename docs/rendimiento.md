# Rendimiento

Mediciones iniciales facilitadas para el stack local con 958 piezas y 385 pedidos:

| Operación | Antes | Después |
| --- | --- | --- |
| Ajustes / taxonomía | 5 / 5 consultas | 5 / 5 consultas (una sola petición por página) |
| Listado | 8 consultas | 8 consultas, constante entre páginas |
| Búsqueda `esmeralda` | 8 consultas, 65–71 ms de BD | 8 consultas, ~70 ms de BD con 958 piezas (el filtro se reevalúa en conteo, página y facetas; ver pendiente) |
| Ficha de pieza | 17 consultas | 8 consultas, constante |
| Inicio CMS / menú | 9 / 3 consultas | 9 / 3 consultas |
| Edición de pieza | 35 consultas, 7 comprobaciones repetidas de reservas | 29 consultas, sin repetidas |
| Historial de publicaciones | 13 consultas, 60 ms BD, 160–220 ms total | 16 consultas, 12 ms BD, 45 ms total |

Las tarjetas pedían una ficha completa para obtener los slugs de ambos idiomas. El serializador de tarjetas entrega ahora `alternates` y el componente los utiliza directamente; esto incluye destacadas y relacionadas que usen ese serializador. Las relacionadas solo precargan las relaciones utilizadas por las tarjetas. `getPiece` y `getSettings` emplean `React.cache` para reutilizar llamadas con los mismos argumentos durante el render, sin modificar los tiempos de `cacheLife`.

La sonda del proxy usa `catalog/exists` con una consulta `exists()` y caché de 60 segundos; las páginas editoriales reutilizan su endpoint publicado, también con revalidación de 60 segundos. Esta ventana puede conservar temporalmente un 404 o una existencia tras publicar o retirar contenido. La taxonomía incluye los slugs de ambos idiomas, por lo que los alternates no necesitan una segunda descarga. Marca, menús, ajustes, taxonomía y ficha usan `React.cache` con sus argumentos de idioma y recurso.

La ficha carga la categoría y su padre junto con el video; comparte las precargas de imágenes y piedras entre la pieza y sus relacionadas, y carga materiales y colecciones en consultas independientes. Reutiliza la configuración de WhatsApp durante la serialización. Se añadieron pruebas de límite y estabilidad de consultas, pendientes de ejecución y medición real.

La búsqueda usa subconsultas `EXISTS` para relaciones multivaluadas, evitando multiplicar filas y el `DISTINCT` sobre la pieza completa. La relevancia por trigramas se mantiene; el conteo ya no necesita desduplicar filas anchas. En PostgreSQL se indexan con GIN los nombres ES/EN, SKU y descripciones cortas mediante `catalog_immutable_unaccent(lower(campo))`. La función fija el diccionario `public.unaccent` y se declara inmutable para permitir índices: si cambian sus reglas hay que reconstruir esos índices con `REINDEX`. El plan depende de los términos y de la selectividad; la similitud y los textos relacionados pueden seguir requiriendo trabajo adicional. La migración es reversible y omite el SQL específico fuera de PostgreSQL.

El historial pagina una unión de claves por fecha, id y tipo, y carga únicamente las entradas de la página y sus predecesores en bloque. Las comprobaciones de reserva activa se comparten por pieza dentro del GET de edición; las acciones POST vuelven a consultar el estado.

Índices aditivos: `piece_public_order_idx` ayuda a filtrar estado y disponibilidad y ordenar por fecha de publicación/id; la clave foránea de categoría ya tiene índice y existe además `(category, status)`. `order_fulfill_created_idx` ayuda al filtro operativo y orden cronológico; ya existe `(payment_status, -created_at)`. Auditoría ya tenía índice por fecha y `audit_action_at_idx` añade filtro por acción con fecha. `reservation_piece_state_idx` cubre pieza, estado y vencimiento; el índice existente por estado y vencimiento sigue sirviendo al vencimiento global. La utilidad efectiva debe confirmarse con `EXPLAIN ANALYZE` sobre datos reales.

## Peticiones de la tienda a la API por página (caché vacía, medido en el log del backend)

| Página | Antes | Después |
|---|---|---|
| Categoría (`/es/joyeria/anillos`) | 37 (24 detalles, uno por tarjeta; taxonomía ×3; settings ×2) | 8, cada recurso una vez |
| Ficha (`/es/piezas/<slug>`) | 16 (la misma ficha ×3; una por relacionada; settings ×3) | 8 |
| Inicio (`/es`) | 14 (una ficha por destacada; settings ×3) | 8 |

Verificación (24/11/2026): backend 1488 pruebas, frontend 97 unitarias, Playwright 91 (desktop y mobile).

## Pendiente opcional

La búsqueda reevalúa el filtro de texto en el conteo, la página y las facetas (precio y piedras); como el filtro combina con OR columnas de otras tablas (categoría, piedras), PostgreSQL no puede usar el índice trigram. Mejora propuesta: calcular una vez los ids coincidentes y reutilizarlos en las facetas, y separar la coincidencia por nombre de pieza (indexable) de la coincidencia por relaciones.
