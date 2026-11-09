# CMS — Fase 1

Implementación sobre `fase-9-produccion`, base `ade06e6`. Sin red, sin push y sin nuevas dependencias. Se conserva el CMS actual. No se modificaron carrito, catálogo comercial, checkout, Wompi ni pedidos.

## Resultado

- Personaliza conserva la composición aprobada en `docs/ronda-cliente-serti.md`, punto G: cabecera, pasos, preguntas frecuentes y footer global. El contenido general y los servicios de personalización siguen fuera de esa página por decisión de la clienta.
- Los cuatro pasos y las cuatro preguntas/respuestas pueden editarse en español e inglés dentro de la página. Los inlines permiten arrastre y posición explícita, muestran límites y contadores. Guardar mantiene el borrador; publicar incorpora ambos idiomas a una revisión inmutable.
- `process_title` y `faq_title` pertenecen a `Page`: son encabezados de ese documento, comparten su traducción, borrador y publicación. No se introduce un sistema nuevo de secciones o documentos.
- `body` se oculta para Personaliza y se explica qué contenido sí se muestra. `PersonalizationService` conserva modelo, datos, formulario técnico y API, pero sale del menú «Página web».
- «Historial de publicaciones» ofrece selector de documento, 20 publicaciones por página, fecha de Bogotá, autor, nota y resumen legible. Restaurar exige confirmación, POST, CSRF y `cms.publish_content`. Restaura el borrador; la tienda conserva su publicación. Las pantallas técnicas de publicaciones y revisiones siguen restringidas a superusuario.
- Propietario y Contenido pueden consultar el historial. Operaciones carece de sus dos permisos de lectura. `sync_roles` se ejecuta al migrar y actualiza los grupos existentes.
- Auditoría editorial con responsable, solicitud y valores anteriores/nuevos en español. Los guardados pasan por servicios con parámetros opcionales `actor`/`request`, compatibles con llamadas anteriores. Las cargas múltiples y reordenamientos del editor visual generan un evento agregado; los guardados individuales generan un evento por objeto cambiado. Las diferencias editoriales se presentan como texto en auditoría, sin mostrar el JSON almacenado.
- El formulario de categorías del inicio incluye subtítulo y su contrato OpenAPI incluye `image`.
- Inicio distingue una publicación vacía de la ausencia de publicación; el preview vacío tampoco activa contenido de respaldo.
- Las respuestas localizadas con cookie de Draft Mode llevan `private, no-store`, `noindex, nofollow` y `no-referrer`; el layout añade metadatos de robots y referrer. La entrada `/preview` también incorpora X-Robots-Tag.

## Archivos

- `backend/apps/cms/models.py`, `translation.py`, `services.py`, `selectors.py`: modelos, traducción, snapshots, restauración, render Markdown y auditoría.
- `backend/apps/cms/admin.py`, `forms.py` existente y `static/cms/character-count.js`: edición integrada en Unfold.
- `backend/apps/cms/history.py`, `templates/admin/cms/history.html` y `confirm_publish_page.html`: historial y confirmaciones.
- `backend/apps/cms/editor.py`, `editor_services.py`: propagación de actor/solicitud y auditoría agregada.
- `backend/apps/cms/api/serializers.py`: contratos aditivos de proceso/FAQ e imagen de categorías.
- `backend/apps/accounts/roles.py`, `backend/apps/core/dashboard.py`, `backend/config/urls.py`: permisos, navegación y ruta del historial.
- `backend/apps/audit/admin.py`: representación legible del diff editorial.
- `frontend/components/editorial-page.tsx`, `personalize-content.ts`, `lib/api/types.ts`: contenido publicado y respaldo de dictionaries cuando faltan campos nuevos.
- `frontend/app/[locale]/{page,layout}.tsx`, `frontend/proxy.ts`, `frontend/app/preview/route.ts`, `lib/cms-preview.ts`, `app/globals.css`: home vacío, protección de preview y accesibilidad de FAQ.
- Pruebas: `backend/apps/cms/tests/test_phase1.py`, `frontend/lib/cms.test.ts`, `frontend/tests/e2e/cms-phase1.spec.ts`.

## Migraciones

1. `0012_page_faq_title_page_faq_title_en_page_faq_title_es_and_more`: campos traducidos de encabezados, `ProcessStep`, `FaqItem` y nota opcional de `PageRevision`. No añade constraints diferibles.
2. `0013_personalize_editorial_content`: copia literalmente pasos, preguntas y respuestas ES/EN de los dictionaries. Añade a la tercera respuesta el enlace Markdown a la ruta real de devoluciones, utilizando sus slugs existentes. Publica una revisión con esos contenidos. Si hay una publicación previa, conserva su contenido general y no publica cambios ajenos del borrador.

La segunda migración guarda procedencia en su revisión, incluidos los registros creados y el estado anterior de la página. La ejecución repetida no duplica registros. Si encuentra pasos/FAQ previamente personalizados, los respeta y no los sobrescribe. La reversa retira únicamente filas creadas que todavía coincidan con su contenido inicial y la revisión propia; restaura el estado anterior de la página si esa revisión sigue siendo la última. No deshace publicaciones posteriores ni elimina filas editadas desde entonces. La reversa completa del esquema `0012` elimina las tablas y columnas nuevas: exportar ese contenido antes de revertir toda la fase si ya se ha utilizado.

## Endpoints

- `GET /api/v1/cms/pages/kind/personalize?locale=es|en` y las páginas por slug incorporan `process: {title, steps: [{title, description}]}` y `faq: {title, items: [{question, answer_html}]}`. No se exponen posiciones, fuentes del borrador ni metadatos de migración.
- Las revisiones antiguas siguen respondiendo sin estos campos; el frontend utiliza el respaldo existente. Restaurarlas conserva los hijos actuales cuando no existe una fuente histórica para ellos.
- `GET /<ADMIN_URL>/publicaciones/?document=home|<página>&page=1`: historial. `&restore=<publicación>` presenta la confirmación; POST con CSRF y `confirm=yes` restaura.
- Se conservan endpoints públicos de servicios de personalización y acciones existentes del editor visual.

## Pruebas y resultados

- Frontend: `npm run lint`, `npm run typecheck`, `npm test`: correctos; 51 pruebas unitarias pasan, incluidas renderización real a HTML de pasos/FAQ desde API y respaldo, home vacío y cabeceras de preview.
- Backend: `manage.py check --settings=config.settings.test`, compilación de plantilla del historial y construcción del formulario Personaliza: correctos.
- `manage.py makemigrations --check --dry-run --settings=config.settings.test`: sin cambios pendientes; aviso de conexión bloqueada al comprobar historial de migraciones.
- Generación OpenAPI mediante `manage.py spectacular`: correcta, sin errores ni avisos de esquema.
- Ruff sobre archivos Python modificados y nuevos: correcto. `git diff --check`: correcto.
- Las pruebas de etiquetas españolas de modelos pasan (2/2).
- Suite completa solicitada: ejecutada con `pytest --ds=config.settings.test -q` usando PostgreSQL, sin sustituirlo por SQLite. El sandbox impide conectar tanto a `localhost:5432` como a `/tmp/.s.PGSQL.5432`: `Operation not permitted`. Los errores de preparación de base de datos impiden validar las pruebas de integración. Última ejecución completa: **115 pasadas y 1003 errores de preparación por PostgreSQL inaccesible**, en 121,45 s; ninguna prueba reportada como fallida. Estos resultados no validan las pruebas que requieren base de datos.
- Tras los ajustes finales, las 22 pruebas nuevas de `test_phase1.py` se recopilan correctamente (`--collect-only`); requieren la ejecución local PostgreSQL para validarse. La comprobación directa, sin base de datos, confirmó que `answer`, `answer_es` y `answer_en` rechazan 1501 caracteres.
- Se prepararon pruebas PostgreSQL para límites, validación, Markdown/enlaces internos, snapshots/publicación/restauración, snapshots antiguos, idempotencia/reversa, permisos, CSRF/confirmación, resúmenes, número acotado de consultas, auditoría, subtítulo y contrato real/esquema de categorías.
- Playwright preparado y sin ejecutar, según lo solicitado: `cd frontend && npx playwright test tests/e2e/cms-phase1.spec.ts`. Requiere stack de desarrollo migrado, Docker accesible y comando `e2e_admin_session` habilitado (DEBUG, sin 2FA). El escenario genera publicaciones de prueba y repone el contenido publicado inicial al finalizar; usar una base de desarrollo sin borradores que deban conservarse. Prueba cambios sucesivos ES/EN y preview de ambas rutas.

Para verificar localmente: aplicar migraciones en la base de desarrollo PostgreSQL y ejecutar `cd backend && pytest --ds=config.settings.test -q` con las variables habituales del proyecto. Ejecutar luego el escenario Playwright indicado.

## Riesgos y límites de verificación

No se pudo ejecutar la integración contra PostgreSQL ni inspeccionar visualmente el panel o la tienda en funcionamiento desde este sandbox. La revisión de plantillas, formularios, esquema y pruebas frontend no sustituye esas comprobaciones. No se aplicaron migraciones a una base existente.

`.git` no es escribible en este entorno: entrega sin commits. No se crearon scripts de commit. Al registrar los cambios, usar un mensaje en español y el tráiler solicitado `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `docs/capturas/` ya estaba sin seguimiento al iniciar y no se modificó.

## Verificación visual

1. Personaliza muestra exactamente sus cuatro bloques aprobados, con los textos iniciales ES/EN y enlace de devoluciones funcionando.
2. En Unfold claro/oscuro, editar y arrastrar pasos y FAQ, observar contadores, foco y posición; comprobar que `body` no aparece.
3. Guardar una pregunta y comprobar que la tienda sigue igual. Publicar con una nota y confirmar ambos idiomas, conservando la traducción no modificada.
4. Abrir historial como Propietario y Contenido; verificar fechas de Bogotá, paginación y resumen. Operaciones no debe acceder. Restaurar y comprobar que solo cambia el borrador.
5. Subir/reemplazar fotos, ordenar y ocultar secciones, guardar una página y sus hijos: verificar responsable y antes → después en auditoría técnica como superusuario.
6. Ocultar todas las secciones del inicio y publicar: no deben reaparecer secciones de respaldo.
7. Preview de rutas ES/EN: comprobar cabeceras con DevTools y metadatos, foco visible y navegación táctil. Revisar 390, 768 y 1440 px; controles del historial de al menos 44 px y movimiento reducido.

## Fase 2

Separación de permisos para editar, publicar y restaurar; documentos versionados; registry de secciones; editor de tres paneles y biblioteca multimedia quedan pendientes. Esta fase no crea esos sistemas. La auditoría conserva el almacenamiento existente en `apps.audit`; las revisiones siguen siendo snapshots inmutables del CMS actual.
