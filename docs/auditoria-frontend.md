# Auditoría de frontend y dashboard (octubre 2026)

Revisión previa al lanzamiento del sitio público y del dashboard, con correcciones aplicadas en la rama `fase-9-produccion`. Método: lectura del código, recorrido real en navegador (escritorio 1440 px, tablet 768 px y móvil 375–412 px), auditoría automática de 18 páginas × 3 tamaños (desbordes, áreas táctiles, alt, errores de consola, enlaces muertos, textos técnicos) y la suite Playwright + axe.

## 1. Correcciones solicitadas

| Tema | Causa encontrada | Solución |
|---|---|---|
| Menú: Joyería y Piedras abiertos a la vez | Cada categoría era un `<details>` independiente, sin estado compartido | Un único estado (`openMenu`) en `components/navigation.tsx`: abrir uno cierra el otro; se cierra al pulsarlo de nuevo, al hacer clic fuera, con Escape (el foco vuelve al botón) y al navegar. Mismo comportamiento en el menú móvil; Escape cierra el diálogo y su submenú |
| Botón ☰ visible en escritorio junto al menú completo | La regla `.utilities > button` tenía más especificidad que `.menu-trigger` | Regla con la misma especificidad; el breakpoint decide |
| Triángulos nativos del navegador en los menús y acordeones | Marcador por defecto de `<summary>` | Chevron fino de la marca, con rotación suave, en menú, ficha, preguntas frecuentes y checkout |
| Tarjetas de historias de piedras | Texto alineado a la izquierda; descripciones largas sin límite; párrafo vacío cuando no hay texto | Contenido centrado, ancho de lectura de 34 caracteres, máximo 4 líneas, títulos alineados entre tarjetas, párrafo omitido si está vacío |
| Doble imagen en tarjetas | La tarjeta solo usaba la imagen principal | Se reutiliza la galería: nuevo campo `PieceImage.is_hover` (máximo uno por pieza; no puede ser también principal). La API entrega `hover_image` en listados, búsqueda, relacionados, rieles del inicio y carrito. Fundido suave de 0,5 s solo en dispositivos con cursor; mismo recuadro (sin saltos de diseño); en táctiles no se muestra ni se descarga; respeta `prefers-reduced-motion` |
| Acceso al dashboard | No existía ningún usuario | Usuario local `admin.pruebas` (rol Propietario, hash Argon2) creado con `createsuperuser`; contraseña temporal solo en `.env.dashboard-local` (ignorado por git) |

**Dashboard de imágenes:** en *Catálogo › Piezas › (pieza) › Imágenes de piezas* cada foto muestra una vista previa y dos interruptores: «Imagen principal» e «Imagen al pasar el cursor». Reemplazar el archivo o borrar la fila funciona como antes; validación en español si se marcan dos imágenes hover o una imagen como principal y hover a la vez.

## 2. Hallazgos de la auditoría

Prioridad: **A** afecta la confianza o una tarea; **M** se nota y resta calidad; **B** detalle.

| # | Prioridad | Hallazgo | Estado |
|---|---|---|---|
| 1 | A | Menús que se superponían (punto anterior) | Corregido |
| 2 | A | Dashboard con textos en inglés y plurales erróneos: secciones (Catalog, Orders, Payments, Axes, Otp_Totp), modelos («Coleccións», «Cupóns», «Configuración del sitios»), **todas las etiquetas de los formularios** (Name, Position, Cover image, Is visible, Starts at…) e indicadores con códigos crudos (`approved`, `awaiting_manual_payment`, `unfulfilled`) | Corregido: nombres en español en apps, modelos y 379 campos; indicadores con etiquetas legibles; prueba automática que exige etiqueta en español para campos nuevos |
| 3 | M | En la página de verificación en dos pasos se veía el menú completo del dashboard antes de verificar (sin acceso a datos) | Corregido + prueba |
| 4 | M | Búsqueda: en móvil no había caja de búsqueda visible (estaba dentro de «Filtros») y sin resultados se mostraba un paginador «1» | Corregido: barra de búsqueda visible, mensaje «No encontramos piezas para «…»», paginador solo con más de una página |
| 5 | M | Ficha de pieza: acordeones que se abrían vacíos (p. ej. «Historia» sin texto) | Corregido: se omiten las secciones sin contenido |
| 6 | M | Login del dashboard con «Return to site» | Corregido: «Volver al sitio» |
| 7 | B | Botón del carrito de 20 px (mínimo WCAG 2.2: 24 px) | Corregido |
| 8 | B | Casillas de filtro de 18 px | Aceptado: la etiqueta completa es clicable (excepción de WCAG 2.5.8) |
| 9 | B | «TOTP devices» en el menú del dashboard | Pendiente: texto fijo del paquete `django-otp`, no traducible sin modificarlo |

Verificado sin problemas: ningún desplazamiento horizontal en 54 combinaciones página × tamaño; imágenes con `alt`; un único `h1` por página; sin errores de consola ni textos técnicos visibles; estados vacíos de carrito, deseos y búsqueda; checkout con validación por campo, indicador de carga, prevención de doble envío, errores de red y conflictos de pieza reservada; rutas del dashboard protegidas sin sesión, sin verificación en dos pasos y después de cerrar sesión; operaciones de borrado con confirmación (nativa del admin).

## 3. Pendientes y mejoras que requieren aprobación

1. **Reflejo inmediato de cambios del dashboard.** Hoy la tienda refleja lo guardado en 1–2 minutos (caché de 60 s, ADR-013). Propuesta: revalidación a demanda (el backend avisa a Next.js al guardar piezas, imágenes, piedras o el inicio). Esfuerzo medio.
2. **Código 404 real.** Las páginas inexistentes muestran la página de error correcta con `noindex`, pero responden 200 porque la decisión llega después de empezar el streaming (limitación conocida de Next.js con prerenderizado parcial). Requiere reorganizar la validación de rutas.
3. **Contenido real:** las descripciones de piedras, historias de piezas y fotos actuales son de demostración (las fotos llegan con P-10).
4. **Prueba en dispositivos físicos** (iPhone/Android reales) una vez esté el staging.

## 4. Cómo entrar al dashboard en local

1. Con el entorno levantado (`make up`), abre http://localhost:8090/dashboard/
2. Usuario: `admin.pruebas`. La contraseña temporal está en el archivo `.env.dashboard-local` de la raíz del proyecto (no se sube a git).
3. La primera vez el sistema pide configurar la verificación en dos pasos: escanea el código QR con Google Authenticator, Microsoft Authenticator o similar e ingresa el código de 6 dígitos.
4. Cambia la contraseña temporal:
   ```bash
   docker compose -f infra/docker-compose.dev.yml exec backend python manage.py changepassword admin.pruebas
   ```
5. Si pierdes el teléfono del autenticador, otro Propietario puede borrar el dispositivo en *Verificación en dos pasos*; en local también: `docker compose -f infra/docker-compose.dev.yml exec backend python manage.py shell -c "from django_otp.plugins.otp_totp.models import TOTPDevice; TOTPDevice.objects.filter(user__username='admin.pruebas').delete()"`.

Este usuario es solo para el entorno local. En producción el primer usuario se crea con `createsuperuser` siguiendo `docs/deployment.md`.
