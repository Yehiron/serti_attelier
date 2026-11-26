# Rendimiento

Mediciones iniciales facilitadas para el stack local con 958 piezas y 385 pedidos:

| Operación | Antes | Después |
| --- | --- | --- |
| Ajustes / taxonomía | 5 / 5 consultas | 5 / 5 consultas (una sola petición por página) |
| Listado | 8 consultas | 8 consultas, constante entre páginas |
| Búsqueda `esmeralda` | 8 consultas, 65–71 ms de BD | 8 consultas, ~70 ms de BD con 958 piezas antes de la última optimización; medición posterior pendiente |
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

## Búsqueda: mejora resuelta

Cada palabra se resuelve mediante una unión de consultas independientes para campos de pieza, categoría, piedras, materiales y colecciones, además de descripciones largas y similitud. Se intersectan los resultados por palabra y se materializan los identificadores una sola vez por petición; página, conteo y facetas los reutilizan. La relevancia se calcula con la misma fórmula anterior. Esta elección es adecuada para catálogos de miles de piezas, a costa de mantener los identificadores en memoria y transmitirlos en los filtros posteriores. Los campos de pieza indexados usan exactamente la expresión de la migración 0012; los nombres relacionados conservan la comparación anterior y disponen de índices propios. El plan y la latencia resultantes aún requieren medición real con `EXPLAIN ANALYZE`.

### Medición de la búsqueda tras la mejora (25/11/2026, 958 piezas, mediana de 5 llamadas)

| Búsqueda | Antes (BD) | Después (BD) |
|---|---|---|
| `esmeralda` | ~70 ms, filtro de texto en 4 consultas | ~10 ms, filtro en 1 consulta, índices `catalog_trgm_*` usados (Bitmap Index Scan) |
| `zafiro oro` | — | ~16 ms |
| `anillos` (790 resultados) / `diamante` (833) | — | ~28 ms (domina el orden por relevancia) |

El listado sin búsqueda bajó de 8 a 6 consultas, constante entre tamaños de página. Verificación: backend 1491 pruebas, E2E de filtros, buscador, SEO y categorías.

## Navegación entre páginas (2026-11-25)

Medido con Playwright en un build de producción local (`docker build --target runtime`, `next start`), clic → contenido listo:

| | Precargas al abrir `/es` | Inicio / Historia / Contacto | Listados (`/es/joyeria…`) | Promedio |
|---|---|---|---|---|
| `next dev` (referencia) | 0 | ~430 ms | ~470 ms | ~445 ms |
| Producción antes | 12 | ~330 ms | ~340 ms | ~295 ms |
| Producción después (caché caliente) | 15 | **40–80 ms** | ~320–480 ms | ~140–200 ms |

- Causa: `cachedRead()` llamaba `connection()` en toda lectura pública y volvía dinámicas todas las rutas; la precarga solo traía el shell. Ahora las lecturas públicas en `'use cache'` (con tags) entran en la precarga; preview y pedidos siguen en vivo.
- La sonda de existencia del proxy se omite en peticiones del router (RSC/prefetch); las cargas de documento la conservan.
- 404 real en producción: un shell PPR siempre confirma 200, así que el proxy renderiza la **misma URL** internamente (cabecera `x-serti-not-found-render`) y devuelve ese HTML con 404, sin las cabeceras `x-middleware-*` internas. Misma URL ⇒ la hidratación coincide.
- Pendiente: los listados dependen de `searchParams` (filtros) y siguen pidiendo al servidor al hacer clic. El build sin API registra avisos de *cache miss* en el prerender (las rutas quedan dinámicas en build y se llenan en la primera visita).
- En local (`next dev`) la navegación siempre será más lenta: no hay precarga, compila al vuelo y lee la API sin caché.
