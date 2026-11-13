# CMS — Fase 8: invalidación, regresión de comercio y copias

Rama `fase-9-produccion`, base verificada `abeb070`. Sin red externa, dependencias nuevas, push ni deploy. Se revisaron fases 1–7, arquitectura, despliegue, seguridad y estrategia de pruebas. `docs/capturas/` estaba sin seguimiento y se conserva intacto. No se cambiaron servicios, vistas, componentes ni plantillas de carrito, checkout, Wompi, pedidos o correos; se añadió una prueba de regresión comercial. Los hooks de catálogo solo programan invalidación de presentación.

## Caché y mapa de tags

Se verificó el estado inicial en `frontend/lib/api/server.ts`: Inicio, páginas, menús y marca vivos; settings/personalization/sitemap con tag agregado y TTL corto; preview privado y vivo. Ahora `cmsRead` publicado pasa por `cachedResult` con `use cache`, tag agregado `cms` y tag fino. `cacheLife`: stale de cliente 0, revalidación a 3600 s, expiración a 14400 s. El respaldo ante errores sigue siendo corto. Catálogo conserva sus TTL anteriores y tags `catalog`/`piece:<slug>`; taxonomía del encabezado sigue en vivo. Locale forma parte de los argumentos de caché; invalidar un tag cubre ambos idiomas sin duplicar tareas.

| Lectura | Tag fino | Origen de invalidación |
|---|---|---|
| Inicio | `cms:home` | HomePublication nueva y cambios de catálogo |
| Página por tipo | `cms:page:<kind>` | PageRevision nueva |
| Página por slug / sitemap | `cms:pages`, y tag del tipo al resolver respuesta | PageRevision nueva; incluye 404 y cambios de dirección |
| Menú principal / pie | `cms:menu:main`, `cms:menu:footer` | MenuPublication nueva; destinos de páginas/catálogo |
| Identidad | `cms:brand` | BrandPublication nueva |
| Ajustes | `cms:settings` | SiteSettings guardado/eliminado; enlaces legales al publicar página |
| Personalización histórica | `cms:personalization` | PersonalizationService guardado/eliminado |
| Redirecciones | `cms:redirects` | Servicio manual y transiciones automáticas al publicar página; límite abajo |
| Catálogo / ficha | `catalog`, `piece:<slug>` | Cambios de catálogo invalidan `catalog`, compartido por ambas lecturas |

Publicar una página invalida además Inicio, ambos menús, settings y redirecciones: pueden contener destinos derivados de esa publicación. El agregado `cms` permite invalidación global interna; no se envía indiscriminadamente en cada guardado. Inicio se invalida por altas/guardados/bajas de Category, Collection, Stone, Piece, PieceImage, CollectionPiece y cambios M2M de colecciones/piedras/materiales. Esto incluye portadas, categorías que adquieren su primera pieza publicada, carruseles, precios y estado de presentación. No se añade caché independiente a reservas o datos de compradores. Las escrituras masivas SQL/`QuerySet.update` externas a los servicios no emiten señales: un importador futuro debe emitir invalidación explícita.

Preview continúa antes de la frontera de caché: Draft Mode + token → `request` no-store, sin tags. Se mantienen protección de cabeceras, autorización vigente y privacidad existentes. Lecturas para sitemap nunca consultan cookies. No se modificaron el contrato público ni snapshots/versiones/revisión exacta/409/restauraciones tipadas/permisos.

## Publicar → invalidar y recuperación

1. Una publicación nueva dispara la señal del modelo inmutable. Dentro de la transacción se crea `CacheInvalidation` con tags deduplicados, documento, fechas, estado e intentos. Una publicación idempotente reutilizada no crea otra fila. Restaurar solo borrador tampoco invalida; restaurar y publicar usa el mismo flujo normal.
2. `transaction.on_commit(..., robust=True)` encola `revalidate_tags(tags, invalidation_id=...)`. Rollback descarta fila y callback. Si el broker falla, se conserva pendiente y se registra solamente su ID.
3. Worker bloquea la fila para serializar entregas duplicadas; POST al frontend privado con timeout 5 s, sin redirecciones HTTP. Solo acepta 200 y `{ok:true}`. Una fila enviada no vuelve a enviar.
4. Ante fallo guarda pendiente y reintenta con backoff 30/60/120/240/480 s (inicial + cinco reintentos). Guarda fallida al sexto intento; no lanza errores de transporte hacia la publicación. Excepciones de retry/logs están saneadas y nunca incluyen secreto, URL, cabeceras ni cuerpo remoto.
5. Beat revisa cada minuto pendientes de más de 15 min, recuperando fallos de broker o procesos interrumpidos. Agotados requieren intervención técnica; véase deployment. Una entrega duplicada tras caída del worker puede volver a expirar tags: operación idempotente.

El historial de Propietaria consulta el último estado por documento y muestra discretamente «La tienda se actualizará en unos minutos» si hay pendientes/fallos. Un envío posterior correcto del mismo documento retira su aviso anterior. La fila persistente conserva evidencia pendiente/fallida/enviada; no se reescribe auditoría editorial. El mensaje de éxito ya no promete que una tarea asíncrona se haya completado.

Migración **0027_cacheinvalidation**: solo esquema, sin copia de contenido. Django registra su aplicación; ejecutarla de nuevo no duplica filas. La reversa se permite vacía y se niega antes de retirar la tabla si contiene registro de invalidaciones; exportar y resolver conscientemente ese registro antes de revertir. No se toca historial CMS, medios ni publicaciones existentes. Modelos/campos nuevos llevan etiquetas españolas.

Las lecturas públicas mantienen sus presupuestos de consultas. No se elevaron límites existentes (Inicio preview 4, biblioteca 18, marca 1/2). El nuevo aviso del historial requiere una consulta PostgreSQL que obtiene el último estado por documento, sin N+1. Cada escritura observada añade una inserción de outbox y un callback; cada envío tiene su lectura/bloqueo y actualización. Falta medir ese coste bajo PostgreSQL real.

## Seguridad de Next y Caddy

`app/api/internal/revalidate/route.ts` exporta POST, runtime Node. La comparación SHA-256 de longitud fija usa `timingSafeEqual`; un secreto ausente devuelve 503 y log fijo, nunca abre el endpoint. Se exige `X-Revalidate-Secret`, cuerpo JSON con exactamente `tags`, 1–50 tags y máximo 8192 bytes leídos incluso sin Content-Length. Se valida la lista entera antes de invalidar. Regex cerrada admite solo tags CMS conocidos, `cms:page:<identificador>`, `catalog` y `piece:<slug>` acotados; rechaza órdenes, comodines, rutas y menús desconocidos. Métodos no implementados reciben 405 de Next (OPTIONS automático del framework).

Se consultaron **documentación y tipos instalados** en `node_modules/next/dist`, sin web: Next 16.4.3 exige segundo argumento. Se usa `revalidateTag(tag, { expire: 0 })`; el perfil `max` serviría primero contenido anterior y no cumple la siguiente visita fresca.

Caddy dev/prod bloquea `/api/internal/*` con 404, antes de cualquier proxy. Frontend no publica puerto en ninguno de los compose. Django llama directamente a `FRONTEND_INTERNAL_URL=http://frontend:3000`, nunca por Caddy. No se cambió la exposición de servicios de producción.

**Redirecciones:** el proxy conserva su consulta corta existente (`next.revalidate:60`) y el caché Django de 60 s, borrado tras commit. No se introdujo `use cache` en proxy ni se promete propagación de tags a esa capa: la documentación instalada recomienda no depender de caché compartida allí. `cms:redirects` se acepta/envía para coherencia de eventos; no hay una entrada Next cacheada con ese tag. El límite operativo de frescura sigue siendo hasta ~60 s en condiciones normales, más indisponibilidad; una redirección permanente ya guardada por navegador puede persistir más. Validar comportamiento real del proxy antes del lanzamiento.

## Medición antes/después

**No se obtuvo una medición real de visitas en este entorno.** PostgreSQL devuelve `Operation not permitted` y no se arrancaron servidores ni contenedores. No se presentan estimaciones como resultados medidos.

Por inspección de lectores, una visita repetida de `/es` o de una página publicada elimina las cuatro lecturas CMS vivas anteriores: documento, marca y dos menús pasan de **4 peticiones a 0** cuando la caché está caliente. Esto es una expectativa estructural; no es el total medido de la visita. Quedan la taxonomía viva del encabezado y la consulta de redirecciones del proxy; settings/catalog pueden añadir peticiones al vencer o con caché fría. La primera visita tras invalidar vuelve a cargar las entradas afectadas.

Se entrega `infra/scripts/cms-cache-measure.py`: cuenta líneas reales de acceso Django para primera visita y repetición de ambas rutas, sin navegador/prefetch ni cambios de datos. Ejecutarlo contra un stack dev sin otro tráfico, con las mismas publicaciones, primero en la base y luego en Fase 8. No cambia revisión ni arranca procesos:

```sh
python3 infra/scripts/cms-cache-measure.py --label antes --page /es/legal/envios > /tmp/cms8-antes.json
python3 infra/scripts/cms-cache-measure.py --label despues --page /es/legal/envios > /tmp/cms8-despues.json
```

Ajustar el camino al Envíos publicado. Guardar ambos JSON con endpoints/conteos y repetir la medición de producción local (`next start`) si se quiere evaluar rendimiento real: dev/HMR puede alterar la caché. La medición real es un pendiente de aceptación.

## Regresión de comercio

| Área | Cobertura que existía |
|---|---|
| Carrito | `cart/tests/test_cart.py`: cookie, limpieza, límites, estados, cotización |
| Reservas | `inventory/tests/test_inventory.py`, suites concurrentes orders/payments: unicidad, vencimiento, venta doble |
| Checkout manual/Wompi | `orders/tests/test_checkout.py`, `payments/tests/test_payments.py`: totales, idempotencia, reintento, aprobación/rechazo |
| Fake Wompi | `payments/tests/test_fake_api.py` + `infra/wompi-fake`: estados canónicos y evento firmado al backend fijo; `purchase.spec.ts` cubre rechazado→reintento→aprobado |
| Webhooks | Firma inválida, vector oficial, propiedades dinámicas, monto/moneda, duplicados, aprobación tardía y conciliación en payments |
| Pedidos/seguimiento | `orders/tests/test_stage*.py`, `test_card.py`, `test_dev_tracking.py`; `orders.spec.ts` |
| Correo/notificaciones | Idempotencia por destinatario, doble webhook, proveedor caído, reintentos, plantillas ES/EN, ausencia de «factura» en notifications; Mailpit en purchase E2E |

Se añadió `orders/tests/test_cms_regression.py`: conserva un pedido/reserva existentes y otro carrito, publica identidad, menú, SEO de Inicio y página, compara filas comerciales completas, carrito y cotización exactos, y termina el checkout del carrito con el mismo total. No se cambia código de dominio comercial. No se detectó ni corrigió un fallo funcional de comercio; **la integración comercial no se declara validada sin ejecutar PostgreSQL**.

`cms-phase8.spec.ts` añade:

- Escritorio: calienta home/página, guarda textos de borrador y comprueba que siguen ocultos, publica ambos, espera únicamente entrega de invalidación (máximo 30 s, inferior al TTL) y comprueba el texto en una sola visita posterior.
- Móvil y escritorio: publica temporalmente identidad distinta (color, fuente, escala), menú y SEO; compara HTML completo del formulario de checkout antes/después, rellena contacto/envío/consentimientos, comprueba botón habilitado, carrito y ausencia de desbordamiento horizontal. No crea pedidos persistentes; las suites existentes prueban el envío/pago completo.
- Limpieza en `afterEach` y respaldo `afterAll` tras desmontar contextos: restaura/publica home/página/marca/menú originales, comprueba cero pendientes y referencias originales de marca/menú. No modifica direcciones. Retira el carrito aislado de prueba y la pieza E2E propia por servicio conservador tras comprobar que no tiene pedidos ni reservas; solo la fixture DEBUG revierte su estado editorial para poder eliminarla. Conserva publicaciones/restauraciones/auditoría inmutables.

Requiere base dev migrada y sembrada, sin borradores pendientes ni edición simultánea, propietario de prueba, secreto igual en backend/frontend y worker activo. El escenario rechaza invalidaciones pendientes/fallidas previas: repararlas conscientemente antes de probar. No se ocultan borradores ni se eliminan pedidos reales para preparar el escenario.

## Copias y restauración

La copia ya incluía BD, `media` y `private_media`, cifrado age, checksums y rotación configurable (14 días por defecto), con cron diario a las 3 de Bogotá. Eso conserva originales/renditions, logos/íconos, fuentes históricas CMS y comprobantes privados. Fuentes con licencia, secretos y código se custodian aparte. Continúa siendo necesaria copia cifrada fuera del VPS.

Se corrigió un riesgo de los scripts de copia: una tubería POSIX podía ocultar un fallo de pg_dump/tar cuando age terminaba correctamente. Ahora se valida cada paso mediante archivos temporales con permisos privados y limpieza por trap; manifest completo se publica por renombrado. La restauración tampoco usa una tubería que oculte fallos de descifrado. `restore.sh` exige **`--confirm-replace-real-data`**, antes de tocar datos.

`backup-verify.sh --confirm-temporary-restore /ruta/absoluta/llave dev|prod` usa última pareja completa, verifica checksum/cifrado, rechaza rutas/enlaces peligrosos del tar y restaura en BD/volumen temporales exclusivos. `verify_backup` comprueba migraciones, recuentos CMS/MediaAsset/pedidos, referencias/generaciones y archivos públicos/privados en transacción PostgreSQL READ ONLY. El trap elimina solo esos recursos temporales. No ejecuta migraciones, no limpia volúmenes reales y no reutiliza el nombre de la BD real. Dev tiene un perfil optativo `backup` con medios fuente de solo lectura.

Deployment contiene comandos, espacio temporal necesario, custodia de llave, copias externas, simulacro mensual y recuperación real paso a paso. Restaurar BD restaura también borradores, publicaciones, punteros, `DraftRevision`, auditoría e invalidaciones a esa fecha; se pierde lo posterior. BD y medios no forman una única transacción: mantener mantenimiento si falla cualquier paso y verificar el conjunto antes de abrir tráfico. No se ejecutó ninguna restauración real ni temporal aquí.

## Variables

- `REVALIDATE_SECRET`: vacío en ejemplos; mismo valor aleatorio privado para Django/worker/Next.
- `FRONTEND_INTERNAL_URL`: privado, `http://frontend:3000`.
- Variables BACKUP existentes añadidas también al ejemplo dev: `BACKUP_AGE_RECIPIENT`, `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`, `BACKUP_HOUR`. Ninguna llave privada se configura por entorno ni se incluye en imágenes.

## Pruebas y resultados

- Frontend: **83/83** unitarias correctas; lint y typecheck correctos. Lectores reales ejecutados con stubs de Next: tags, TTL y bypass de preview. Handler: método, secreto ausente/incorrecto, allowlist, deduplicación, JSON y límite de cuerpo.
- Backend CMS sin BD: **127 correctas**, 313 excluidas por requerir BD en la ejecución registrada, cuatro avisos existentes de URLField; `REQUIRE_FRONTEND_CONTRACT=1`. Incluye guardas de restauración y reversa sin pérdida de registro.
- Nuevos casos: **23 recopilados** entre Fase 8, seguridad de copias y regresión comercial. Cubren on_commit/rollback, tags, idempotencia, restauración, reintentos saneados, agotamiento/broker, recuperación beat, catálogo, redirecciones y migración/reversa. Los de BD están preparados para PostgreSQL; no se ejecutaron con SQLite.
- `manage.py check`: sin errores. `makemigrations --check --dry-run`: sin cambios pendientes, con aviso de que no puede consultar PostgreSQL. No se aplicaron migraciones a una BD existente.
- Ruff sobre Python modificado/nuevo, sintaxis shell y `git diff --check`: correctos.
- Playwright: cuatro escenarios recopilados en ambos proyectos; el editorial móvil se omite expresamente (tres ejecutables). No se arrancó navegador ni stack, no se declara verde E2E ni apariencia visual.
- Caddy, restauración de una copia y medición HTTP: pendientes de ejecución en entorno autorizado. Compilar no sustituye esas verificaciones.

```sh
cd backend
python manage.py migrate
REQUIRE_FRONTEND_CONTRACT=1 pytest --ds=config.settings.test -q
```

```sh
cd frontend
npm run lint
npm run typecheck
npm test
./node_modules/.bin/playwright test tests/e2e/cms-phase8.spec.ts
./node_modules/.bin/playwright test tests/e2e/purchase.spec.ts tests/e2e/orders.spec.ts
```

## Pendientes antes del lanzamiento

Ejecutar PostgreSQL completo y revisar presupuestos; E2E móvil/escritorio; Caddy dev/prod y cierre del endpoint desde fuera; simulacro age/PostgreSQL con recuentos y archivos reales; medición antes/después; inspección visual del checkout con identidad personalizada. Configurar secreto, worker/beat y copia externa. Un despliegue multiinstancia de Next requiere caché compartida o invalidar todas las instancias: el compose actual tiene una sola. Revisar crecimiento del outbox/historial sin borrar referencias históricas.

No se dejaron servidores Next ni procesos Playwright/pytest iniciados por esta fase en ejecución. `.git` es de solo lectura según el perfil del entorno: entrega sin stage ni commit, sin scripts de commit. Al registrar fuera del sandbox, usar por ejemplo:

```text
CMS fase 8: invalidación segura y verificación de copias

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Revisión e integración (Claude)

Verificado contra el stack de desarrollo y una imagen de producción de la tienda.

- **Endpoint interno:** `export const runtime = 'nodejs'` impedía compilar la ruta con `cacheComponents` (500 en cada invalidación; todas quedaban pendientes). Se quitó (Node ya es el runtime por defecto). Desde Caddy, `POST /api/internal/revalidate` responde 404.
- **Primer intento inmediato:** `invalidation.dispatch` ejecuta el primer envío en línea tras el commit (tiempo máximo 5 s) y solo si falla programa la tarea Celery con reintentos. Así la visita siguiente a «Publicar» ya es fresca; si la tienda no responde, la publicación no falla.
- **Producción comprobada:** con la imagen `runtime` (`next start`) en la red de desarrollo, publicar un color de marca y restaurarlo se ve en la **primera** visita siguiente en ambos sentidos.
- **`next dev`:** el manejador en memoria sirve una vez la entrada obsoleta tras `revalidateTag` (comportamiento documentado en `next/dist/server/lib/cache-handlers/default.js`). En desarrollo las lecturas con etiqueta `cms*` son en vivo para que el panel y las pruebas reflejen cada publicación; producción usa caché con invalidación.
- **Fallo previo de Fase 6 corregido:** `snapshot_path` fallaba (`KeyError`) con revisiones antiguas de snapshot vacío y bloqueaba publicar cualquier página en una instalación nueva. Ahora esas revisiones no aportan dirección; las redirecciones automáticas y los menús las ignoran. Prueba añadida.
- `CacheInvalidation` usa `gettext_lazy` en todas sus etiquetas.
- **E2E `cms-phase8`:** espera solo las invalidaciones creadas por la prueba, busca la pieza dentro de la página del carrito (no en el cajón cerrado) y compara el formulario de compra cuando departamentos y totales ya cargaron. Pasó 4 de 4 veces.
- Desarrollo: `REVALIDATE_SECRET` aleatorio solo en `.env` local (no versionado). Producción debe definir el suyo en `.env.production` (Django y Next).

## Cierre técnico (Claude)

- **Medición real con `next start`** (imagen `runtime`, `infra/scripts/cms-cache-measure.py`, peticiones al backend por visita completa):

  | Ruta | Primera visita | Repetida antes del cierre | Repetida tras el cierre |
  |---|---|---|---|
  | `/es` | 10–11 | 2 (`cms/redirects`, `catalog/taxonomy`) | **1** (`cms/redirects`) |
  | `/es/legal/envios` | 2–3 | 2 | **1** |

- **Categorías en caché:** `getTaxonomy` usa la etiqueta `catalog`, que ya expiran los guardados de categorías, colecciones, piedras, materiales y piezas. Comprobado en `next start`: renombrar una categoría y enviar el aviso muestra el nombre nuevo en la primera visita siguiente.
- **Materiales:** guardar o borrar un `Material` ahora también avisa a la tienda (antes no; un material renombrado podía quedar desactualizado).
- **Redirecciones sin caché a propósito:** el proxy las consulta en cada visita (una petición pequeña con límite de 2 s). Guardarlas en memoria retrasaría hasta un minuto la redirección 301 de una dirección recién cambiada.
- **Desarrollo:** `next dev` lee siempre en vivo (CMS y catálogo); producción conserva la caché por etiquetas.
- **Limpieza del outbox:** tarea diaria `prune_cache_invalidations` (beat `prune-cms-invalidation`). Borra filas de más de 30 días que ya tienen una más reciente para su documento; nunca borra pendientes ni la última fila de cada documento, que es la que decide el aviso de la Propietaria.
- **404 de páginas:** con streaming, Next conserva HTTP 200 en rutas inexistentes, siempre con `noindex` (comportamiento ya documentado en `api-contract.md`). El seguimiento de pedidos inexistentes sí devuelve 404 real desde el proxy.
