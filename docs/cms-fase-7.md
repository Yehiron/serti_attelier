# CMS — Fase 7: identidad de marca limitada

Trabajo en `fase-9-produccion`, base `3735ab3`, sin red externa, push ni dependencias nuevas. Se conservan las reglas de `docs/marca.md` y los flujos de Fases 1–6. No hay campañas ni publicación programada. `docs/capturas/` permanece intacto.

## Documento y permisos

`brand:identity` es un documento independiente con `ContentDocument.brand_identity` y puntero tipado a `BrandPublication`, basado en el mismo snapshot inmutable de publicaciones. Guardar exige `edit_content`, versión explícita y bloqueo del documento; devuelve 409 si alguien guardó antes. Revisar/publicar exige `publish_content` y exactamente la versión revisada. Repetir la publicación sin diferencias reutiliza la publicación existente. Restaurar exige `restore_content`, crea `DraftRevision.restored_from_brand`, aumenta la versión del borrador y deja intacta la tienda hasta publicar.

La constraint de restauración admite exactamente uno de cuatro orígenes tipados. No hay constraints diferibles; los bloqueos con relaciones anulables conservan `select_for_update(of=("self",))`. Propietaria publica/restaura; Contenido edita/previsualiza; Operaciones recibe 403. Las nuevas rutas reutilizan sesión, CSRF y segundo factor del panel.

La revisión e historial muestran nombres y valores legibles por campo, incluidos colores, fuentes, porcentajes y «foto N». No se incorporan campos de marca a páginas, Inicio ni menús, evitando pendientes falsos en documentos ajenos. El registro exporta `brand_document` separado de las once secciones existentes.

## Colores y contraste

Se verificaron los siete tokens en `frontend/app/globals.css`: vino `#651c32`, carmesí `#8a1538`, crema `#ead9cb`, papel `#dfc9b8`, tinta `#330414`, oliva `#7a7256` y oliva oscuro `#58513d`. Esmeralda `#0b6e4f` sigue fijo como señal funcional de favoritos.

Solo se admite `#rrggbb`, normalizado a minúsculas; no hay CSS libre. El panel ofrece selector, campo hexadecimal y «Volver a los colores originales». Se calcula luminancia sRGB linealizada y contraste `(Lclaro + 0,05)/(Loscuro + 0,05)`, sin librerías adicionales. La decisión usa el ratio sin redondear; la pantalla muestra dos decimales.

Son obligatorios 4,5:1: tinta/crema, crema/vino, vino/crema, crema/carmesí y oliva oscuro/crema. Esmeralda/crema usa 3:1 como aviso. Guardar contraste insuficiente está permitido y muestra los pares fallidos; publicar lo rechaza en servidor. Para conservar los contextos de logos oficiales, la luminancia del principal debe ser como máximo **0,08** y la del fondo como mínimo **0,60**, incluso en borrador. Estos límites conservadores mantienen el principal oscuro y el fondo claro; además se siguen exigiendo los ratios de texto antes de publicar.

La tienda solo genera variables para hex válidos distintos de los originales. Con identidad original no añade tokens ni cambia su orden: conserva el atributo de escalas anterior. Las lecturas de marca usan `cmsRead` y `connection()`, también en draft. No se añade invalidación por tags.

## Fuentes y escalas

Títulos: Ninna (oficial) o Cormorant Garamond; cuerpo: Inter. No se descargan fuentes nuevas. La elección oficial conserva exactamente la cadena CSS existente y su respaldo; Cormorant omite Ninna. Continúa vigente la condición de licencia web de Ninna descrita en `marca.md` antes del lanzamiento.

Las escalas de títulos/texto tienen las mismas opciones 90/100/110/120 %. La migración copia los valores existentes de SiteSettings, incluidos valores distintos del 100 %. El formulario de Configuración deja de ofrecer esos dos campos; las columnas y los valores numéricos de la API histórica se conservan para compatibilidad y reversa. El layout usa exclusivamente las escalas de identidad; no consulta SiteSettings para tipografía. Se mantiene sin debilitar `test_settings_serializer_numeric_scales`.

## Logos, íconos y biblioteca

Ranuras fijas: logotipo claro/oscuro, monograma claro/oscuro, monograma con lema del pie, ícono e imagen para compartir. `null` significa archivo original (o sin imagen global de compartir). Los originales siguen siendo los archivos existentes de `public/brand/logo` y los favicon/iOS actuales. No se regraban ni reemplazan esos archivos.

Los logos elegidos en biblioteca requieren PNG/WebP decodificable con transparencia efectiva, al menos 96 px de ancho y 32 de alto (24 para monogramas). SVG se rechaza porque puede contener scripts. La ayuda recuerda espacio libre, tamaños mínimos y prohibición de deformar/recolorear/sombrear. Se sirven los píxeles completos del original normalizado y congelado, sin aplicar el recorte fotográfico de la referencia. Los monogramas personalizados se usan en el encabezado móvil; sin sustitución se conserva la composición actual verificada en código (el encabezado actual usa logotipo también en móvil).

Ornamento y monograma floral continúan en código. Las máscaras de marca de agua también conservan el monograma original **aunque se sustituya el monograma visible**: una máscara recolorea la pieza y recorta su silueta; aplicarla a un logo arbitrario infringiría la prohibición de recolorear y podría deformar un lema. Esta decisión preserva la pieza de marca de agua aprobada.

El ícono exige imagen cuadrada de al menos 512 px. El servicio Pillow que ejecuta el worker existente prepara PNG 32/180/192/512 e ICO y los congela en la generación de biblioteca. Las nuevas generaciones cuadradas aptas incluyen estas rendiciones; para una foto anterior sin ellas, guardar sus datos en biblioteca prepara una generación nueva, sin modificar las antiguas. Metadata utiliza estos archivos; si se elige original, conserva exactamente los íconos anteriores. No existe manifest en el proyecto y no se añade uno, para mantener el head original.

La foto global para compartir usa el recorte existente 1.91:1. Se aplica como respaldo en layout y metadata editorial/Inicio; una imagen SEO propia tiene prioridad. Una edición de título/descripción conserva la imagen global de Twitter. Los metadatos específicos del catálogo conservan su control de imágenes.

JSON-LD usa la URL absoluta del logotipo claro publicado; el original conserva literalmente la URL anterior. Las referencias internas siguen `{asset,crop,version}`. «Dónde se usa» incluye cada ranura, borrador, publicación e historial. La eliminación queda bloqueada incluso si solo permanece un uso histórico. El índice reutiliza la consulta UNION existente para no sumar consultas a la biblioteca; no se cambia su presupuesto de 18.

**Carrito, checkout, Wompi, pedidos, catálogo y correos transaccionales no se modifican. Los logos de los correos transaccionales siguen en código**, igual que el monograma floral del certificado.

## Pulido de Fase 6

La tarjeta de Google usa el título real de la página o el título del diccionario de Inicio cuando SEO está vacío, con la descripción del diccionario que usa la tienda. La dirección se muestra en un bloque separado del contador. Las entradas Editor visual, Menús, Identidad de marca, Redirecciones y Traducciones tienen selección activa exclusiva por ruta/documento.

## Migraciones y reversa

- `0025_brandpublication_and_more`: tabla inmutable, fuente/puntero del documento y cuarto origen de restauración. La reversa comprueba primero que no haya identidad/historial que perder.
- `0026_initial_brand`: usa modelos históricos y alias de conexión; crea una sola publicación y documento, con paleta/fuentes/logos originales y las escalas actuales de SiteSettings. Repetir no sobrescribe un documento existente ni duplica publicaciones. No publica otros borradores ni reescribe publicaciones anteriores.

La reversa de datos solo retira la semilla intacta: se niega si hubo guardados, publicaciones posteriores o restauraciones. Repone sus escalas en las columnas antiguas antes de volver al código anterior. Exportar/adaptar la identidad y su historial antes de revertir una fase ya utilizada. La prueba de migración vuelve en `finally` a `loader.graph.leaf_nodes()` y consulta modelos históricos durante las transiciones.

## Endpoints y archivos

- `GET /api/v1/cms/brand?locale=es|en[&preview=token]`: identidad pública; en preview exige token vigente y responde `private, no-store`. Documentado en OpenAPI y `docs/api-contract.md`, con tipos TypeScript y registro JSON actualizados.
- `GET/POST /<ADMIN_URL>/editor/documento/?document=brand:identity`: estado y acciones `update`, `media-select`, `discard`, con `expected_version`.
- `GET/POST /<ADMIN_URL>/revisar-publicacion/brand:identity/`: revisión/publicación.
- `GET/POST /<ADMIN_URL>/publicaciones/?document=brand:identity`: historial/restauración confirmada.

Dominio: `cms/brand.py`, modelos, migraciones, biblioteca, adaptador visual, API, publicación e historial. Panel: `visual-editor.js/css`, plantilla de historial y navegación de `core/dashboard.py`; formulario de `core/admin.py`. Tienda: `cms-brand.ts`, lectores/tipos, layout, Inicio, metadata editorial, componentes de marca, navegación y pie. Pruebas: `test_phase7.py`, navegación del dashboard, `cms-brand.test.ts`, contrato/footer y `cms-phase7.spec.ts`. El fixture `tests/fixtures/layout-before-phase7.tsx.txt` conserva el layout del commit base para comparar todo el HTML del documento renderizado.

## Pruebas y resultados

La integración PostgreSQL y el E2E **no están validados en este entorno**. No se usó SQLite ni se aplicaron migraciones a una base existente.

- Suite completa solicitada: `cd backend && pytest --ds=config.settings.test -q`, con PostgreSQL: **245 correctas, 1.156 errores de preparación, 6 avisos**, 138,84 s. PostgreSQL `127.0.0.1:5432` devuelve `Operation not permitted`. Registro `/private/tmp/phase7-backend-full.txt`. Se añadieron después casos de logos/íconos y pruebas puras adicionales; se recopilaron y comprobaron por separado.
- CMS y navegación sin BD: **130 correctas**, 295 deseleccionadas, con `REQUIRE_FRONTEND_CONTRACT=1`. Registro `/private/tmp/phase7-pure-final.txt`.
- Fase 7: **29 casos recopilados**, incluidos permisos/403, 409, revisión exacta e idempotencia, restauración tipada, migración/reversa, hex, contraste/luminancia, fuentes/escalas, transparencia/tamaño/SVG, rendiciones y protección de borrado. Los casos de BD deben ejecutarse en PostgreSQL.
- Frontend: lint y typecheck correctos. Pruebas de tokens, escalas, selección de fuentes, metadata original/personalizada, prioridad SEO, JSON-LD y comparación del layout real con el fixture anterior. **79 pruebas correctas**, incluido el HTML del layout real frente al fixture del commit base, con escalas migradas. Registro `/private/tmp/phase7-frontend-final.txt`.
- OpenAPI generado/validado sin errores ni avisos en `/private/tmp/phase7-openapi.yaml`; registro/contrato regenerados. `makemigrations --check --dry-run`: sin cambios, con aviso de conexión PostgreSQL. Ruff, sintaxis JS y `git diff --check`: correctos.
- Presupuesto nuevo: identidad original una consulta (documento/publicación); logos personalizados dos (activos reunidos en una sola consulta, compartida por las siete ranuras). Las pruebas fijan estos límites sin elevar los existentes; falta medirlos en PostgreSQL.
- Playwright recopila el escenario de escritorio. Cambia el principal, comprueba iframe, guarda un mal contraste y comprueba rechazo al publicar, publica color/fuente/escala válidos y comprueba la tienda. Cierra la página para cancelar temporizadores; `afterAll` restaura/publica la publicación inicial bajo bloqueo, verifica igualdad completa y cero pendientes. No usa esperas de duración fija para limpiar; conserva el historial inmutable. Requiere DEBUG, base migrada, identidad sin pendientes ni logos personalizados, y ausencia de trabajo editorial simultáneo.
- Inspección visual bloqueada: `next dev --hostname 127.0.0.1 --port 3100` falla con `listen EPERM`. No se declara apariencia ni integración verificada por haber pasado pruebas estáticas.

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
./node_modules/.bin/playwright test tests/e2e/cms-phase7.spec.ts --project=desktop
```

## Riesgos y Fase 8

Ejecutar PostgreSQL, migraciones/reversas en una copia y Playwright antes de producción. Revisar con navegador logos claros/oscuros, escritorio/móvil, fuentes y tamaños, teclado y modo oscuro del panel. Los archivos no son transaccionales; un rollback del worker puede dejar archivos huérfanos que recoge la limpieza conservadora existente. Mantener copias de seguridad de base, medios y fuentes con licencia.

Fase 8 debe incorporar invalidación por tags al publicar, **incluida la identidad**, conservando preview privado, versiones revisadas y restauraciones. Debe ejecutar regresión de comercio completa (carrito, checkout, Wompi, pedidos y correos) y verificar copias/restauración. Las generaciones históricas y publicaciones siguen protegidas; no se añade retención destructiva.

## Registro de cambios

No se creó commit: el perfil del entorno concede solo lectura a `.git`. Los cambios quedan sin stage ni commit; no se crearon scripts de commit ni se hizo push. Mensaje propuesto al registrar fuera de este entorno:

```text
CMS fase 7: identidad de marca con revisión y publicación

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
