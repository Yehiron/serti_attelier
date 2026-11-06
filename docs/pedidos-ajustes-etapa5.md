# Pedidos — ajustes posteriores a la Etapa 5

Fecha: 2026-11-06. Rama `fase-9-produccion`, base `9c39603`. Leídas las Etapas 5 y 7. Trabajo sin red externa, sin push y sin dependencias nuevas. No cambia el contrato de la API pública ni hay migraciones.

## Tarjetas móviles

Se conserva la tabla y las clases `field-*` de Django/Unfold. Hasta 760 px, cada fila usa flex con wrap: número, total y selección; cliente truncado y fecha corta de Bogotá; insignias; botón completo. Flex permite envolver las celdas de insignias sin introducir contenedores inválidos dentro de la tabla. No se duplican filas ni controles. Se ocultan el teléfono, el certificado falso y la ausencia de incidencia. La selección lleva etiqueta con número de pedido y superficie táctil de 44 × 44 px. El botón tiene 44 px como mínimo.

Las pestañas forman una sola fila con desplazamiento contenido en el propio nav. Los indicadores usan dos columnas en móvil. Se mantienen las variables y superficies de Unfold para claro/oscuro. El marcado de escritorio conserva sus datos, fecha larga y teléfono; la fecha móvil se oculta allí. El objetivo de altura normal es aproximadamente 180–190 px; una incidencia o texto excepcionalmente largo puede necesitar otra línea. La altura efectiva y el desbordamiento quedan pendientes de navegador.

## Indicadores y pestañas

`GET <admin>/orders/order/metrics/` devuelve JSON privado con indicadores y pestañas. Deniega anónimos y usuarios sin acceso con 403; solo admite GET. El middleware de acceso al admin conserva el segundo factor. Los filtros inválidos reciben 400. Se reutilizan los filtros y búsqueda reales de Django mediante un ChangeList sin resultados/paginación; las seis pestañas se agregan en una sola consulta.

Se conserva la semántica existente, documentada en Etapa 5: indicadores globales, período elegido para cobros; contadores de pestañas con búsqueda y filtros de pago/fecha/importe, sustituyendo la etapa operativa. No se cambian esas reglas al refrescar. Se eliminan importes del JSON y del contexto para quien no tiene `orders.view_order`, incluso si puede entrar por `change_order`.

Presupuesto previsto: tres consultas de `order_center_metrics`, una agregación de pestañas y hasta dos de permisos: **≤6**, sin contar sesión/autenticación/segundo factor del middleware. La prueba con usuario fresco exige ese máximo; no se ha validado en PostgreSQL desde este entorno.

La campana emite un evento local al recibir novedades. La lista refresca sus resúmenes entonces y, como respaldo independiente, cada 120 s mientras es visible. Al volver a la pestaña consulta de inmediato; timeout de 8 s, sin consultas programadas mientras está oculta y parada ante sesión vencida. No reemplaza filas: aparece «Hay pedidos nuevos · Actualizar lista». El enlace recarga la URL actual, conservando filtros.

Opacidad de 180 ms ease-out, números tabulares, espacios reservados para valores/subtotales y movimiento reducido. Solo un resumen oculto usa `aria-live="polite"`. No se pone live en cada número.

## Seguimiento: una lectura y 404 de marca

Se conserva la respuesta HTML directa del proxy para 404/410. Es la alternativa autorizada: sin poder arrancar Next no se puede demostrar que `NextResponse.rewrite(..., {status: 404})` sobreviva al streaming del layout con `cacheComponents` en Next 16. No se afirma haber validado ese rewrite ni se sustituye el mecanismo que ya fija el 404 antes de React.

El HTML directo incorpora cabecera y pie de marca, wordmark, paleta vino/crema, fuente Ninna local, textos ES/EN, enlace a inicio y página de contacto. **No es el layout React completo**: no carga catálogo, menús dinámicos, ajustes del CMS ni datos de soporte configurados. Contacto enlaza a la página localizada existente. El logo real del header es `wordmark-wine.webp`; no hay un SVG del wordmark en este checkout. Se reutiliza ese mismo recurso, no el favicon como sustituto.

Para un pedido válido, el proxy transporta el resultado de su única consulta al render mediante una cabecera interna de request comprimida, ligada a token e idioma. `getOrder` la consume sin volver al backend. También transporta errores 429/503 para evitar repetir consultas cuando falla el servicio. No hay caché compartida, almacenamiento de pedidos ni cambios en la respuesta pública de la API.

El proxy elimina siempre cualquier cabecera de preflight que venga del navegador antes de generar la propia. Los matchers explícitos de seguimiento incluyen tokens con puntos, aunque el matcher general excluya extensiones, para que ninguna página de seguimiento pueda saltarse ese saneamiento. La cabecera se configura solo en `request`, nunca como cabecera pública; E2E comprueba también su ausencia en la respuesta. Compresión y límites de decodificación reducen el tamaño de cabecera y acotan entradas corruptas. No se imprime el contenido ni se registran tokens. Una lectura significa una petición al detalle por visita de seguimiento; no incluye ajustes del sitio, polling posterior ni las consultas SQL internas del detalle.

Se conservan `no-store, private`, `no-referrer` y `noindex, nofollow`; 429 y fallos del servicio no se convierten en 404.

## Archivos

- `backend/apps/orders/admin.py`: fecha corta, marcado de cliente y selección accesible; ruta JSON.
- `backend/apps/orders/card_admin.py`: selectores compartidos de pestañas, endpoint, permisos e importes.
- `backend/templates/admin/orders/change_list.html`: marcadores de valores, resumen accesible y aviso de actualización.
- `backend/apps/orders/static/orders/order-card.{css,js}` y `backend/apps/notifications/static/notifications/panel.js`: móvil, movimiento y refresco.
- `frontend/proxy.ts`, `frontend/lib/api/server.ts`, `frontend/lib/order-probe.ts` y `frontend/lib/order-http.ts`: transporte por request y 404 de marca.
- `backend/apps/orders/tests/test_stage5_adjustments.py`, `frontend/lib/{order-http,order-probe}.test.ts` y `frontend/tests/e2e/orders.spec.ts`: pruebas.
- `backend/apps/orders/api.py` y `backend/apps/payments/management/commands/e2e_tracking_reads.py`: contador E2E explícitamente armado, solo DEBUG. Guarda durante cinco minutos únicamente una clave hash y un entero en la caché compartida dev; sin endpoint de control ni modificación de JSON. El comando rechaza producción. Sin contador armado no se incrementa nada; con DEBUG falso ni se consulta la caché por este motivo.

## Comprobaciones

Ejecutables ya instalados, sin descargas. Backend con `DJANGO_SECRET_KEY=local-tests`, `DATABASE_URL=postgres://serti:serti@localhost:5432/serti` y `REDIS_URL=redis://localhost:6379/0`; no se cargaron secretos del `.env`.

- `cd backend && .venv/bin/pytest --ds=config.settings.test -q`: **97 passed, 964 errors, 5 warnings**, 104,65 s. Los errores ocurren al preparar PostgreSQL: psycopg informa `Operation not permitted` en localhost:5432. Esta ejecución recogió seis casos nuevos antes de añadir el séptimo de permisos sin importes. **Suite backend no validada**.
- Prueba enfocada final: `.venv/bin/pytest --ds=config.settings.test apps/orders/tests/test_stage5_adjustments.py -q`: **7 errores de conexión**, 1,07 s. No se ejecutó SQLite. Las siete pruebas cubren 403 anónimo, tres roles, período/filtros/presupuesto, marcado y acceso por change sin importes. El último ajuste de etiqueta de selección también queda pendiente de PostgreSQL.
- `manage.py check --settings=config.settings.test`: **sin problemas**.
- Ruff en todos los Python modificados/nuevos: **aprobado**. `node --check` de los JS del panel y tarjeta: **aprobado**. `git diff --check`: **aprobado**.
- `cd frontend && npm run lint && npm run typecheck && npm test`: **aprobados; 46/46 tests**. Última ejecución después de ajustar los E2E y el transporte comprimido.
- `frontend/node_modules/.bin/playwright test --list`, desde frontend: **50 tests en 6 archivos**, escritorio y Pixel 7. E2E preparados, **no ejecutados**, según la entrega solicitada.
- `npm run dev -- --hostname 127.0.0.1 --port 3105`: **bloqueado por `listen EPERM`**. `curl --max-time 3 -sS -o /tmp/pedidos-next-response.html -w '%{http_code}\n' http://127.0.0.1:3105/es/pedido/e2e-inexistente`: conexión rechazada, código 000. **HTTP real, altura y revisión visual no comprobados aquí**. No se ejecutó build que pudiera descargar fuentes.

Los E2E existentes ahora comprueban: incremento de Por preparar tras APPROVED mediante Wompi falso y aviso sin navegación del admin; en Pixel 7 ausencia de scroll de página y primera tarjeta <220 px; inexistente con 404/cabecera/pie; válido 200 con contador de backend exactamente 1 después de reiniciarlo. El contador se consulta con management command contra la misma caché Redis del backend, no contando peticiones del navegador que no ve las lecturas de servidor a servidor. Se reutilizan checkout, fake y sesiones E2E de Etapa 7.

## Verificación pendiente en tu entorno

1. Ejecutar `cd backend && pytest --ds=config.settings.test -q` con PostgreSQL y Redis disponibles, en especial las siete pruebas nuevas y la conservación de contadores de Etapa 5.
2. Con el stack dev existente, ejecutar `cd frontend && npx playwright test` (sin instalar navegadores ni tirar de red). Confirmar el contador compartido Redis y la única lectura, además de ambos códigos HTTP. Comprobar también mediante curl GET un token válido de prueba (200) y uno inexistente (404), tanto directo a Next como a través de Caddy; no pegar tokens reales en informes.
3. Revisar a 390/412, 768 y 1440 px, claro/oscuro: total y selección sin solaparse, elipsis, teléfono oculto solo en móvil, certificado verdadero, incidencias largas, botón de 44 px, pestañas desplazables y página sin desbordamiento. Confirmar que el escritorio conserva todos los datos.
4. Revisar teclado, lector de pantalla, movimiento reducido y valores cambiando sin mover el contenido; ocultar/mostrar la pestaña y conservar filtros/período. Verificar footer/header/fuente del 404 ES/EN y navegación a inicio/contacto. El 404 conserva un diseño de marca estático, no los menús completos del sitio.

## Commit

`.git` no es escribible (`test -w .git` devuelve 1). **Sin commit**, sin scripts de commit y sin push. Mensaje previsto:

```text
Compacta pedidos móviles y actualiza los indicadores del panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
