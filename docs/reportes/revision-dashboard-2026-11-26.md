# Revisión del dashboard y pruebas de CRUD — 26 nov 2026

## 1. Resumen

- Módulos ya rediseñados y verificados: Pedidos, Piezas, Categorías, Piedras, Colecciones y Materiales.
- Batería nueva de pruebas en navegador real (`frontend/tests/e2e/admin-crud.spec.ts`): **20 casos, 20 pasan** (13 positivos, 6 negativos y 1 de humo en móvil).
- Las pruebas encontraron **2 fallos reales** y **2 fallos de limpieza de datos de prueba**. Los cuatro quedaron corregidos:
  - el botón de WhatsApp daba un error de hidratación en el checkout de la tienda;
  - la bandeja de Pedidos ya no actualizaba sus cifras en vivo.
- Prototipos de mejora para los 4 módulos que más lo necesitan: Inicio, Mensajes, Biblioteca de fotos y Datos del sitio (`docs/prototipos/modulos/`).

## 2. Pruebas de CRUD desde el navegador

Cada prueba entra al dashboard con una sesión real, hace la acción con la interfaz y comprueba el resultado tras recargar la página. Si aparece cualquier error de JavaScript en la página, la prueba falla. Todo lo que crean usa el prefijo E2E y se borra al terminar.

| # | Módulo | Tipo | Qué se comprobó | Resultado |
|---|---|---|---|---|
| 1 | Categorías | Positiva | Crear con nombre y descripción en ES y EN | ✅ |
| 2 | Categorías | Positiva | Editar la descripción; se conserva al recargar | ✅ |
| 3 | Categorías | Positiva | Mover (reordenar); el orden se conserva | ✅ |
| 4 | Categorías | Positiva | Eliminar una categoría vacía | ✅ |
| 5 | Categorías | Negativa | Guardar sin nombre → error, no se crea | ✅ |
| 6 | Categorías | Negativa → positiva | Eliminar con piezas → bloqueado y muestra las piezas; moverlas a otra categoría desde esa pantalla → ya se puede eliminar | ✅ |
| 7 | Piedras | Positiva | Crear con color, editar la descripción y eliminar | ✅ |
| 8 | Piedras | Negativa | Color inválido (`verde`, `#12345`) → error; eliminar una piedra con piezas → bloqueado | ✅ |
| 9 | Colecciones | Positiva | Crear, agregar 2 piezas, reordenar, quitar 1 y guardar | ✅ |
| 10 | Colecciones | Negativa | Nombre vacío → error; guardar con una pieza inexistente → 400 y nada cambia | ✅ |
| 11 | Materiales | Positiva | Crear con tono, editar el inglés, reordenar y eliminar | ✅ |
| 12 | Materiales | Negativa | Tono inválido → error | ✅ |
| 13 | Piezas | Positiva | Alta completa: nombre, SKU, descripciones, categoría y precio; aparece en la vitrina | ✅ |
| 14 | Piezas | Positiva | Cambiar el precio y poner oferta en la ventana flotante; la vitrina y la tienda muestran el precio nuevo | ✅ |
| 15 | Piezas | Negativa | Precio vacío, negativo o con texto, y SKU duplicado → no se guarda; el precio no cambia en la base de datos | ✅ |
| 16 | Piezas | Positiva | Ocultar y volver a publicar desde el menú ⋯ | ✅ |
| 17 | Piezas | Positiva | Eliminar definitivamente una pieza sin historial; su dirección deja de servir la ficha | ✅ |
| 18 | Piezas | Positiva | **Compra real pagada → eliminar la pieza vendida.** El pedido sigue en la bandeja con nombre y SKU, la marca «Pieza eliminada», subtotal, total y pago intactos, y la página de seguimiento de la clienta sigue cargando | ✅ |
| 19 | Piezas | Negativa | Pieza con pago pendiente → el borrado definitivo queda bloqueado con el motivo | ✅ |
| 20 | Móvil | Humo | Piezas, Categorías, Piedras, Colecciones y Materiales abren sin errores ni scroll horizontal | ✅ |

Cobertura que ya existía y se volvió a ejecutar:
- Backend: suite completa (más de 1.550 pruebas).
- Frontend: 111 pruebas unitarias.
- Suite e2e completa de tienda y dashboard (ver la sección 6).

## 3. Fallos encontrados y corregidos

1. **Error de hidratación en el checkout (tienda).** El botón flotante de WhatsApp se dibujaba en el servidor pero no en el navegador en `/es/checkout`. React rehacía la página y dejaba un error en la consola. Ahora el botón aparece solo después de cargar, así que servidor y navegador siempre coinciden (`frontend/components/whatsapp.tsx`).
2. **Fotos de prueba en la Biblioteca.** Había 19 «Portada de prueba …» que deja una prueba automática. No se pueden borrar porque el historial de publicaciones las conserva. La limpieza automática ahora las **archiva**, así que ya no aparecen.
3. **Pedidos: las cifras ya no se actualizaban solas (regresión del rediseño de la bandeja).** Al pasar a la bandeja (commit `c4d978f`) se quitó el script que, al llegar un pago, actualiza «Por preparar», los contadores y el aviso «Hay pedidos nuevos». Hacía falta recargar la página. Ahora ese código vive en su propio archivo (`orders/live-metrics.js`), la bandeja lo carga otra vez y el aviso volvió. La prueba de pagos PSE lo confirma en escritorio y celular.
4. **Pedidos de prueba huérfanos.** Si una prueba borraba definitivamente una pieza E2E vendida, la limpieza no encontraba su pedido. Ahora lo encuentra por el SKU guardado en la línea del pedido. Hay prueba de backend para ambos casos.

## 4. Qué podemos mejorar, módulo por módulo

| Módulo | Situación actual | Propuesta | Prioridad |
|---|---|---|---|
| **Inicio** | Indicadores en texto plano; «Ventas por mes» ocupa media pantalla con filas en $0; no dice qué hacer hoy | Panel del día: 4 cifras clave, lista de **pendientes** (mensajes, pedidos por preparar, fotos faltantes, textos de prueba), gráfico de barras, últimas ventas — *prototipo* | Alta |
| **Mensajes de contacto** | Tabla genérica: no se lee el mensaje ni se responde desde ahí; el único mensaje es basura («hkjhkjh…») | Bandeja como Pedidos: lista + lectura, respuestas rápidas, responder por correo o WhatsApp, marcar spam o archivar — *prototipo* | Alta |
| **Biblioteca de fotos** | Fotos de prueba mezcladas (corregido); no dice dónde se usa cada foto; hay fotos repetidas | Filtros «En uso / Sin usar / Duplicadas», insignia de dónde se usa, ficha lateral con descripción ES/EN — *prototipo* | Media |
| **Datos del sitio** | Una lista con un solo elemento antes de llegar al formulario; todo en una página larga | Abrir directo el formulario por secciones, con vista previa de los mensajes de WhatsApp — *prototipo* | Media |
| **Avisos de pedidos** | Página casi vacía y sin estilo | Unirla a la campana y a la bandeja de Pedidos | Baja |
| **Redirecciones** | Formulario con el estilo antiguo (campos pequeños, etiquetas en línea) | Igualarlo al resto (tarjeta, ayuda y validación del destino) | Baja |
| **Traducciones pendientes** | Cuenta «Cookies» como pendiente aunque es igual en inglés | Botón «Está bien así» para descartar falsos pendientes | Baja |
| **Página de inicio** | Repite lo que ya hace el Editor visual; Personalización está oculta | Llevar el orden y la visibilidad al editor y quitar este menú | Baja |
| **Auditoría** | 7.119 registros, casi todos de pruebas; las acciones salen con códigos («catalog.material_updated») | Frases legibles («Actualizó el material Oro rosa»), filtros por persona y módulo, ocultar las acciones de pruebas | Media |
| **Equipo** | La cuenta `admin` no tiene rol («—») | Asignarle «Propietario» y mostrar el último acceso | Baja |
| **Cupones** | Vacío; pantalla genérica | Sin urgencia hasta que se usen | — |

## 5. Datos que debes revisar tú (no son errores de código)

- **Instagram configurado como `instagram.com/qa.serti`**: parece una cuenta de pruebas. Revísalo en Datos del sitio.
- Esmeralda tiene «texto de prueba» en su descripción; la portada de Cadenas tiene marca de agua; Rubí, Aretes, Dijes y Pulseras tienen descripciones pendientes.
- Oro rosa no indica quilates; Plata 925 y Oro rosa no tienen piezas pero se ofrecen en Personaliza.
- El historial de publicaciones y las versiones de Páginas (Personaliza v140, Envíos v101) están infladas por las pruebas automáticas **en el entorno local**. En producción no corren estas pruebas. Aun así, conviene que en local las pruebas usen una base de datos aparte.

## 6. Resultado de la ejecución (con las correcciones aplicadas)

| Suite | Resultado |
|---|---|
| Batería de CRUD del dashboard (nueva) | 20 de 20 pasan |
| Navegador real, tienda y dashboard, escritorio y móvil (Playwright) | **179 pasan**, 0 fallan; 33 se saltan a propósito porque son solo de escritorio o solo de móvil |
| Backend (Django, modo de pago simulado) | **1.552 pasan**, 0 fallan; 13 se saltan |
| Frontend, pruebas unitarias | **111 pasan**, 0 fallan |
| Calidad: Ruff, mypy, TypeScript y ESLint | Sin errores; 3 avisos previos de ESLint por `<img>` |

Una prueba de Materiales falló una vez en móvil al recargar («page not attached») y pasó en la repetición y en la suite completa. Es intermitente; no se encontró ningún error de la aplicación detrás.
