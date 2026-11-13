# Pruebas de carga básicas (2026-11-13)

Solo lectura: no crea carritos, pedidos ni datos. Script: `infra/scripts/load-read.py <origen>`; reparte peticiones entre portada ES/EN, catálogo, catálogo filtrado, ficha de pieza y Envíos durante 20 s por nivel.

Entorno: tienda con la imagen de producción (`next start`, un proceso), backend de desarrollo (`runserver`) en Docker Desktop sobre un portátil. Las cifras orientan; repetir en el VPS antes del lanzamiento.

| Usuarios simultáneos | Páginas/s | p50 | p95 | p99 | Errores |
|---|---|---|---|---|---|
| 1 | 15 | 65 ms | 79 ms | 108 ms | 0 |
| 10 | 63 | 142 ms | 250 ms | 801 ms | 0 |
| 25 | 84 | 292 ms | 408 ms | 503 ms | 0 |
| 50 | 88 | 578 ms | 723 ms | 799 ms | 0 |

- Cada página tarda ~55 ms en servirse sola (48–134 KB de HTML); todas salen de la caché de la fase 8.
- Durante la carga el backend solo recibe `cms/redirects` (consulta del proxy, con token interno, sin límite de peticiones).
- El techo (~88 páginas/s) es la CPU de un único proceso Node. Equivale a millones de visitas al día: muy por encima del tráfico esperado de una joyería de piezas únicas.
- No se midió el checkout ni el pago bajo carga: crearía pedidos y reservas. Se puede hacer en *staging* con datos desechables y la llave sandbox de Wompi.
