# SEO técnico

Los datos del negocio y los textos SEO de portada se editan en Ajustes del sitio, sección Negocio y buscadores. Los títulos, descripciones y textos visibles de categorías, colecciones y piedras se editan en sus fichas del catálogo; el SEO de páginas editoriales se edita en el CMS. La única piedra considerada colombiana por la plantilla automática es la esmeralda; las demás no reciben esa atribución.

| Página | Enfoque |
| --- | --- |
| Inicio | Joyería en Armenia, Quindío; oro 18k y esmeraldas |
| Categorías | Tipo de joya y oro 18k |
| Piedras | Piedra y joyería de autor |
| Personaliza | Joyas personalizadas en Armenia |
| Contacto | Atención con cita en Armenia |

El layout usa Suspense y `cacheComponents`: una respuesta transmitida antes de resolver `notFound()` conserva HTTP 200. El proxy consulta el API antes del render para piezas, taxonomías y páginas editoriales dinámicas y devuelve 404 cuando el API confirma ausencia; fallos transitorios no se convierten en 404. Caddy enruta las solicitudes al frontend y no corrige ese estado. Esta solución requiere verificar el comportamiento con el despliegue real y Googlebot.

El envío gratuito a Colombia se basa en el texto comercial publicado. El enlace de devoluciones apunta a la política existente; no se inventa un plazo. El sitemap usa `updated_at` de piezas y taxonomías; los registros anteriores a la migración conservan fecha desconocida hasta su próxima edición, con `published_at` como respaldo para piezas. Las páginas CMS usan `updated_at` y las piezas incluyen sus imágenes.

## Comprobación posterior al despliegue

- Verificar dominio, sitemap y cobertura en Google Search Console; inspeccionar inicio, listados y fichas con la prueba de URL.
- Revisar resultados enriquecidos, imágenes y disponibilidad en Google.
- Configurar el Perfil de Empresa como negocio con área de servicio, Colombia y atención con cita; ocultar la dirección y no publicar coordenadas.
- Confirmar teléfono, horarios y enlaces sociales con la propietaria.

Las descripciones automáticas distinguen catálogo, categoría, piedra y colección; el CMS prevalece cuando aporta SEO. Las fichas omiten metal y piedras repetidos en el nombre y limitan el título a 65 caracteres. Robots excluye rutas de compra, API, vista previa y consultas de búsqueda sin bloquear recursos estáticos.

### Recursos ausentes detectados por el proxy

El proxy consulta la existencia antes de iniciar el streaming. Ante un recurso inexistente hace `NextResponse.rewrite` a la **misma URL** con estado 404 (Next 16 conserva ese estado), más `X-Robots-Tag: noindex, follow` y `Cache-Control: no-store`. La ruta renderiza su `not-found.tsx`: `app/[locale]/piezas/[slug]/not-found.tsx` muestra «Esta joya encontró otro destino» y `app/[locale]/not-found.tsx` el texto general; ambos usan `components/not-found-content.tsx`. No se sirve HTML de otra ruta: la URL distinta rompía la hidratación y React volvía a pintar el 404 genérico.
