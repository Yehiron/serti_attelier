# Snapshots históricos del CMS

Estos fixtures reproducen las formas históricas de publicación con textos versionados en las migraciones del repositorio. **No son un volcado de la base de desarrollo**: PostgreSQL no fue accesible desde el sandbox (`Operation not permitted`). No contienen datos personales.

- `home_legacy_paired.json`: los ocho tipos históricos; textos de `0002_initial_content` y `0011_home_category_grid`; portada con el formato de diapositivas emparejadas previo a `0008_split_hero_slides`, todavía admitido por las publicaciones inmutables. Las rutas de foto y los identificadores son sintéticos y no requieren archivos.
- `page_phase1.json`: títulos, pasos, preguntas, respuestas y Markdown del contenido aprobado de `0013_personalize_editorial_content`, con las fuentes y posiciones históricas. Se omite la procedencia interna de la migración, que no forma parte de la respuesta pública.

Las pruebas comprueban que adaptar solo añade `schema_version`, conserva los originales y mantiene idénticos los bytes de ambos endpoints ES/EN al expandir y normalizar el esquema. Antes de producción conviene agregar muestras anonimizadas de publicaciones reales de desarrollo; la limitación de acceso impidió extraerlas aquí.
