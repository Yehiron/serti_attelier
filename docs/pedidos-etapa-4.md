# Pedidos — Etapa 4: seguimiento del cliente

Fecha: 2026-11-06. Rama `fase-9-produccion`. Base: commits `d3b5538`, `072af27`, `7b736a6` y lectura de `docs/pedidos-etapa-{1,2,3}.md`. La auditoría original de pedidos no está en este checkout: se aplican D11–D13 y sección J según la solicitud. Sin push ni dependencias nuevas. No se consultaron servicios externos; el build intentó obtener las fuentes ya configuradas y falló por falta de conectividad.

## Resultado y decisiones

La respuesta pública conserva sus campos y añade `fulfillment` y `payment_review`; los serializadores OpenAPI, tipos TS y `docs/api-contract.md` reflejan la ampliación. `fulfillment` contiene estado, transportadora, guía, URL HTTP(S) validada (omitida si no es válida), fechas de envío/entrega y hitos `{key, label_key, at}`. No serializa historial interno: notas, motivos, responsables e incidencias permanecen privados. `payment_review` es solo un booleano para incidencias financieras abiertas, excluyendo «Otra».

Las fechas existentes tienen prioridad; el historial aporta preparación, cancelación, devolución y respaldo de envío/entrega. Se consulta mediante `Subquery`/`Exists`, sin migraciones, sin N+1 ni aumento del presupuesto de consultas del detalle existente (3 sin checkout configurado, 4 con él). No se inventan fechas intermedias en pedidos históricos. Las etiquetas de hitos se traducen en el frontend.

La página conserva tipografía, paleta, resumen y componentes de la tienda. Cronología vertical con estado actual marcado mediante texto, punto y `aria-current="step"`; futuros atenuados, fechas en Colombia, bloque Envío con transportadora/guía y enlace seguro a nueva pestaña. Revisión de pago, cancelación y devolución tienen texto humano ES/EN. Contacto usa `site/settings`, igual que el footer: WhatsApp y correo solo si están configurados; un fallo del CMS no impide consultar el pedido.

Se mantienen pago, reintento, idempotencia y sync con `?id=` (incluso al mostrar revisión/cancelación, aunque se oculten controles de pago). Sync e intentos muestran mensaje humano para 429. Polling solo durante pago pendiente/manual o reintento pendiente; pagados y estados terminales no tienen polling continuo, solo actualización al enfocar. El contador reserva espacio desde el primer render. Estilos limitados a la página, enlaces de al menos 44px y transición de opacidad de 180ms ease-out, anulada por `prefers-reduced-motion`.

## Protección del enlace

- GET por IP: `THROTTLE_ORDER_PUBLIC`, por defecto `60/min`. No omite el límite por tener token interno de SSR. Next reenvía solo el último hop de `X-Forwarded-For` para que todos los clientes no compartan la IP del contenedor. Se presupone el despliegue existente con Caddy como único proxy público y los servicios internos sin exposición directa. Sin proxy/IP disponible se comparte el identificador de origen que llega a Django.
- Sync conserva su throttle por IP `10/min`; intentos también `10/min`. Los límites DRF usan caché y no son una garantía atómica ante ráfagas concurrentes extremas.
- API GET/sync/intentos: `Cache-Control: no-store, private`, `Referrer-Policy: no-referrer`, también en 404/429. Next: proxy limitado a rutas de pedido, con las mismas cabeceras y `X-Robots-Tag: noindex, nofollow`; metadata robots noindex. Caddy refuerza las cabeceras al salir del proxy, incluyendo rutas canónicas, alias e idioma aún no seleccionado. Las lecturas del pedido siguen usando fetch `no-store` y datos dinámicos.
- Caducidad terminal: 180 días por defecto (`ORDER_TRACKING_TTL_DAYS`) desde entrega/cancelación/devolución. Entrega usa columna o historial; cancelación/devolución, historial. Registros antiguos sin fecha terminal usan `updated_at` conservadoramente; nuevas modificaciones de esos registros pueden extender ese respaldo. Nunca pagados: 30 días desde vencimiento de reserva; se considera también aprobación histórica para no confundir un pago posteriormente anulado con uno nunca pagado.
- Se elige **404 idéntico en la API para inexistente y caducado**, no 410. Sync/intentos también comprueban caducidad antes de consultar a Wompi. Next usa `notFound()` con página local amable ES/EN; con streaming ya iniciado el framework puede conservar HTTP 200, siempre con noindex. Revisar el código HTTP efectivo tras Caddy en el despliegue.
- Token: `secrets.token_urlsafe(32)`, 256 bits aleatorios, 43 caracteres habituales; índice único. Sin búsqueda por número ni comparación en tiempo constante añadida.

## Logs: cobertura y límites

`apps.core.observability.normalize_order_path` reemplaza tokens por `:token` en `/api/v1/orders/<token>` (incluidos subpaths), `/pedido/<token>` y `/order/<token>`, con o sin locale. El logger Gunicorn `PrivateOrderLogger` normaliza el átomo `U` antes de interpolar su formato de acceso, que no incluye query ni referer. El filtro existente de logs Django y Sentry `before_send` usan la misma normalización recursiva para URLs, mensajes, breadcrumbs y excepciones; la clave estructurada `public_token` se redacta también.

Ambos Caddyfiles se revisaron: **no contienen directiva `log` ni access logging habilitado**, por lo que no hay un registro de URI de acceso que filtrar. Se deja comentario para mantener esa garantía. No hay Sentry del frontend instalado/configurado; no se agregó un SDK. Next ignora estas rutas en sus logs de acceso de desarrollo; no se añadieron `console.*`, y los fallos de fetch se convierten al error genérico existente.

Sin acceso a infraestructura no se verificaron logs reales, configuración efectiva de Caddy, cambios externos que activen access logs, logs de error del proxy, colectores, CDN, analítica, extensiones del navegador ni logs de errores propios del runtime Next. No hay garantía sobre tokens copiados como texto aislado en logs ajenos al normalizador. No se ejecutó `caddy validate`: no está instalado. Debe confirmarse en despliegue que no haya logs externos con URI y que los errores del proxy/runtime no impriman URLs sensibles. El historial de notificaciones privado conserva tokens por diseño de la etapa anterior; no se modifica aquí.

## Archivos

- Backend: `apps/orders/{api,selectors,response_serializers}.py`, nuevo `tests/test_stage4.py`; `apps/payments/api.py`; `apps/core/observability.py`, nuevo `apps/core/access_log.py`; `config/settings/base.py`, `gunicorn.conf.py`.
- Frontend: `app/[locale]/pedido/[token]/{page,not-found}.tsx` y CSS local; diccionarios ES/EN; `components/{order-live,order-payment}.tsx`; `lib/{commerce,order-state}.ts`, pruebas de estados, `lib/api/{server,types}.ts`; cambios de seguridad limitados a pedidos en `proxy.ts` y `next.config.ts`.
- Infra: `Caddyfile` y `Caddyfile.dev`, cabeceras específicas; documentación de contrato y este informe.

## Verificación

Se usan ejecutables de `backend/.venv/bin`, `DJANGO_SECRET_KEY=local-tests`, `REDIS_URL=redis://localhost:6379/0`, sin cargar secretos ni llamar proveedores. Los tests usan mocks existentes para proveedores. Resultados finales se indican debajo.

- **PostgreSQL, comando exigido:** `cd backend && pytest --ds=config.settings.test -q`, usando `DATABASE_URL=postgres://serti:serti@localhost:5432/serti`: **81 passed, 911 errors**, 98,20 s. Error de conexión `Operation not permitted` en localhost IPv4/IPv6. **PostgreSQL no es accesible desde este sandbox; NO está validada la suite en PostgreSQL.** Los 81 aprobados son pruebas que no necesitan la base; los errores no son un resultado funcional del código. Una ejecución anterior, antes de añadir dos pruebas, dio 81 aprobados y 909 errores por la misma causa.
- **SQLite, solo complemento:** mismo comando completo con `DATABASE_URL=sqlite:////tmp/pedidos4-suite.sqlite`: **967 passed, 24 skipped, 1 failed**, 65,70 s. Único fallo: `apps/core/tests/test_health.py::test_ready_reports_dependencies`, 503 porque Redis es inaccesible. Las omitidas incluyen pruebas PostgreSQL. No sustituye la prueba obligatoria con PostgreSQL. La primera pasada detectó dos fallos de presupuesto de consultas, corregidos mediante anotaciones antes de esta pasada final.
- Pruebas enfocadas: `pytest --ds=config.settings.test backend/apps/orders/tests/test_stage4.py backend/apps/orders/tests/test_checkout.py -q` desde la raíz: **38 passed**, SQLite, 5 s. Comprobación previa de Etapa 4 y observabilidad: **33 passed**. Incluyen los seis estados, forma y fechas de hitos, ausencia de notas/motivos e incidencias, URLs inseguras, TTL a 179/181 y 29/31 días, caducidad por historial, 429 por IP y sync, cabeceras, token de 256 bits, normalizador, átomos de Gunicorn y saneamiento Sentry.
- `python manage.py check --settings=config.settings.test`: sin problemas. `python manage.py makemigrations --check --dry-run --settings=config.settings.test`: **No changes detected**, ambos con SQLite.
- Frontend `npm test`: **41/41 passed**; incluye todos los estados de pago existentes, cronología operativa y textos ES/EN. `npm run lint` y `npm run typecheck`: **aprobados**.
- `npm run build`: **no completado**. `next/font` intenta obtener Cormorant Garamond e Inter de Google Fonts y falla sin red. No se cambiaron las fuentes ni se añadieron dependencias para sortearlo. El error no valida ni invalida el resto del build; repetir en un entorno con las fuentes disponibles.
- Ruff sobre los Python modificados y `git diff --check`: **sin errores**.
- `npm run dev -- --hostname 127.0.0.1 --port 3104`: servidor bloqueado por sandbox (`listen EPERM`); **no se hizo revisión visual real**. Caddy no está instalado, por lo que tampoco se validó su configuración con el binario.

## Pendientes y revisión visual

1. Ejecutar **`cd backend && pytest --ds=config.settings.test -q` contra PostgreSQL**, con Redis accesible para la prueba de salud. Validar también las pruebas existentes de concurrencia y los planes de las subconsultas en datos representativos. No hay migración nueva de esta etapa.
2. Repetir build con fuentes disponibles. Revisar página ES y EN en escritorio (~1440px) y celular (~390px): pendiente online, intento rechazado/reintento, pendiente manual, pagado sin preparar, preparación, enviado con/sin guía/URL, entregado, cancelado con/sin pago, devuelto y revisión de pago. Verificar punto actual, futuros atenuados, fechas, textos largos, totales y ausencia de saltos al aparecer el contador. Comprobar foco de teclado, ≥44px táctil y movimiento reducido.
3. Probar regreso Wompi con `?id=`, sync 429 y reintento 429; comprobar que el ID se retira de la URL, que no se pierde idempotencia y que pedidos pagados solo se actualizan al enfocar. Revisión/cancelación mantienen sync sin mostrar botones de pago.
4. Probar enlace inexistente, caducado y exceso de consultas, con/sin contacto CMS. Misma página amable para inexistente/caducado, sin datos del pedido. Revisar `no-store, private`, `no-referrer` y noindex en respuesta HTML, RSC, API, errores y redirects. Next streaming puede conservar HTTP 200 en HTML de notFound; la API debe devolver 404 uniforme.
5. Validar Caddyfiles y cabeceras efectivas. Con un token de prueba, revisar stdout Gunicorn (`:token`), Django y un evento Sentry simulado. Confirmar que Caddy/CDN/colectores no tienen access logging externo de estas URLs y revisar errores de proxy/runtime Next; esa parte no se pudo comprobar aquí.
6. Revisar datos antiguos terminales sin fechas/historial; el respaldo `updated_at` no recupera la fecha real de cierre. Ajustar la política operativa si requieren una caducidad histórica estricta.

## Commit

Sin commit: `.git` no es escribible (`test -w .git` devuelve falso). No se crearon scripts de commit ni se hizo push. Mensaje propuesto:

```text
Añade seguimiento público de pedidos y protege los enlaces del cliente

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
