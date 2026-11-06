# Ronda del cliente SERTI

Cambios preparados en `fase-9-produccion`. Sin push ni acceso al remoto. No se modificaron credenciales, contraseñas ni autenticación.

| Bloque | Resultado | Archivos principales |
| --- | --- | --- |
| A | Alfa de cada parada del degradado multiplicado por 0.8; regla compartida por hero estático y carrusel en escritorio y móvil. Sombra suave del texto. | `frontend/app/globals.css` |
| B | Tarjetas de piedras con número, título y enlace; descripción y CSS retirados. | `frontend/components/editorial-interactions.tsx`, `globals.css` |
| C | Nuevo `category_grid`, serialización pública, editor visual y tarjetas oliva con monograma de agua, hover y movimiento reducido. Categorías raíz activas por posición/PK; conteos de piezas publicadas, incluidas subcategorías activas. Borrador Historia convertido en Comprar por categoría / Shop by category. | `backend/apps/cms/{models,selectors,editor}.py`, `api/serializers.py`, plantilla `admin/cms/editor.html`, `core/static/core/editor.css`, `frontend/components/home-sections.tsx`, `frontend/lib/api/types.ts`, `globals.css` |
| D | Listados de piedras sin portada; categorías y colecciones conservan sus imágenes. | `frontend/components/listing.tsx` |
| E | Escalas de títulos y texto 90/100/110/120 %, sección Tipografía del admin, API numérica, variables del documento y tamaños responsivos con `calc()`. Valores por defecto en el contrato frontend. | `backend/apps/core/{models,admin}.py`, `cms/selectors.py`, `cms/api/serializers.py`, `frontend/app/[locale]/layout.tsx`, `globals.css`, `frontend/lib/api/{types,server}.ts` |
| F | Wordmark completo también en móvil; ancho 112 px y espacios ajustados en el header. | `frontend/components/media.tsx`, `globals.css` |
| G | Personalización conserva cabecera, cuatro pasos y FAQ; elimina las otras secciones y las consultas de servicios/catálogo. Conserva contexto de WhatsApp y footer global. | `frontend/components/editorial-page.tsx` |
| H | AND entre palabras y OR entre campos; SKU, colección y descripciones. PostgreSQL permite similitud del nombre sin acentos >0.3, además de coincidencias parciales. Panel nativo dialog, foco en input, Esc, debounce 250 ms, mínimo dos caracteres, seis sugerencias y enlace a todos los resultados. GET normal sin JS. Solicitudes públicas al mismo origen `/api/v1/catalog/pieces`. Campo de búsqueda editorial grande. | `backend/apps/catalog/selectors.py`, `tests/test_search.py`, `frontend/components/{quick-search,navigation}.tsx`, diccionarios ES/EN, `globals.css` |
| I | Iconos SVG monocromos de redes con nombres accesibles; solo aparecen redes configuradas. | `frontend/components/{social-links,site-shell}.tsx`, `globals.css` |
| J | Botón existente de 56 px en vino, icono y sombra; margen de área segura y separación del sticky conservada. Aviso en Datos del sitio si falta el número. No se inventó número. | `backend/apps/core/admin.py`, `frontend/app/globals.css`; revisión de `frontend/components/whatsapp.tsx` |
| K | Medios de pago con SVG locales accesibles: Visa, Mastercard, American Express, PSE, Nequi, Bancolombia y Daviplata. | `frontend/components/{payment-methods,site-shell}.tsx`, diccionarios ES/EN, `globals.css` |
| L | Blanco en listados, resultados, fotos y rail del home; conserva foto alternativa al hover. | `frontend/app/globals.css` |

## Migraciones

- `cms/0010_alter_homesection_kind.py`: exclusivamente choices.
- `cms/0011_home_category_grid.py`: exclusivamente conversión de datos del borrador. Conserva las publicaciones inmutables y no restaura automáticamente los títulos anteriores al revertir.
- `core/0008_sitesettings_text_scale_sitesettings_title_scale.py`: escalas con Normal por defecto.

Aplicar con `cd backend && python manage.py migrate`. **Después hay que publicar el home desde el dashboard**: la migración no sustituye `HomePublication.snapshot`. La vista previa permite revisar antes de publicar.

## Verificación ejecutada

Se usó el virtualenv existente y se cargó la configuración local sin imprimir secretos. Para aislar las verificaciones se sobreescribió temporalmente `DATABASE_URL` con una base SQLite en `/private/tmp`; no se editaron archivos de configuración del proyecto.

- Backend `python manage.py check --settings=config.settings.test`: sin incidencias.
- Backend `python manage.py makemigrations --check --dry-run --settings=config.settings.test`: sin cambios pendientes.
- Backend `python manage.py migrate --settings=config.settings.test --noinput`: correcto en SQLite temporal.
- Backend `pytest --ds=config.settings.test -q`: **624 aprobados, 9 omitidos, 1 fallo**. Único fallo: `apps/core/tests/test_health.py::test_ready_reports_dependencies`, porque Redis no está disponible. No se debilitó el endpoint ni se alteró esa prueba.
- Tests nuevos: escalas y serializer, categorías/conteos/localización, conversión del borrador sin alterar la publicación, SKU/descripciones y búsqueda de varias palabras. Incluye regresión PostgreSQL para `esmeralds` y acentos; no pudo ejecutarse aquí.
- Ruff en los archivos Python cambiados, salvo migraciones generadas: correcto.
- Frontend `npm run lint && npm run typecheck && npm test`: correcto, **39 tests aprobados**. Avisos existentes de Node sobre módulos y de Django sobre futuros cambios de URLField.
- `git diff --check`: correcto.

PostgreSQL no está operativo localmente. El intento de crear una instancia temporal fue bloqueado por el sandbox al crear memoria compartida; las nueve pruebas PostgreSQL quedaron omitidas. `npm run dev -- --hostname 127.0.0.1 --port 3106` también fue bloqueado (`listen EPERM`). Por ello quedan pendientes la comprobación visual real a 375 px y escritorio, las interacciones del panel en navegador y la regresión sobre PostgreSQL. No se descargaron dependencias, imágenes ni fuentes.

## Commits y entrega

El intento de `git add` fue bloqueado: `Unable to create .git/index.lock: Operation not permitted`. No hay commits nuevos y el índice no se alteró. El entorno declara `.git` de solo lectura y no permite pedir elevación.

`scripts/commit-client-round.sh` prepara dos commits temáticos con mensajes en español y la línea final de coautoría solicitada:

1. A–G e I–L: tienda y dashboard, junto con CSS y traducciones compartidas.
2. H: implementación del buscador y sus tests.

Ejecutar desde la raíz, después de revisar el diff, en un entorno con escritura en `.git`: `sh scripts/commit-client-round.sh`. El script verifica la rama y que no haya cambios ya preparados; nunca toca remotos.

## Pendientes del cliente / despliegue

- Aplicar las tres migraciones y **publicar el home**.
- Completar el número real de WhatsApp y las URL reales de redes en Datos del sitio. Sin esos datos sus accesos permanecen ocultos.
- Ejecutar pruebas con PostgreSQL/Redis disponibles y verificación visual en navegador, en especial header de 375 px y escalas de 120 %.
- Ejecutar los commits locales preparados cuando `.git` sea escribible. No hacer push dentro de esta ronda.
