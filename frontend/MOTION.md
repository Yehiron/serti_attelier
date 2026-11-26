# Movimiento editorial

- `RouteScrollReset` vive en el layout persistente de `[locale]`: `usePathname` y `useLayoutEffect` reinician el scroll antes del pintado del cambio de ruta. El listener de `popstate` omite ese reinicio en atrás/adelante. Los cambios de ancla de la misma ruta no disparan el efecto. No se usa `template.tsx`.
- `ScrollReveal` instala un único `IntersectionObserver`, compartido por las secciones de portada marcadas `data-scroll-reveal` y las tarjetas. Umbral: 15 %; al mostrar se elimina el estado pendiente y se llama `unobserve`. Un `MutationObserver` incorpora contenido servido por streaming y navegaciones posteriores sin observers por tarjeta. Se desconectan ambos al desmontar.
- El HTML del servidor no incluye estados ocultos. Tras hidratar, JS activa `motion-ready` y marca únicamente elementos fuera del viewport. El hero y las tarjetas visibles inicialmente quedan fuera de la aparición al scroll. Las filas escalonan 70 ms; la transición dura 600 ms y desplaza 16 px. No se cambian dimensiones ni posiciones de layout.
- El hero mantiene el recurso prioritario y las imágenes responsivas. El zoom de 7,4 s se aplica a cada slide activo en ambos tamaños; el texto entra una vez por montaje en 600 ms, con 12 px y demoras de 0/120/240 ms.
- En dispositivos sin hover, las mismas dos fotos forman un contenedor horizontal nativo con scroll-snap. Dos puntos reflejan la foto actual. No se intercepta el desplazamiento: solo se cancela el click posterior a un gesto que se haya movido más de 10 px. Un tap nuevo conserva el enlace.
- Con movimiento reducido no hay zoom, aparición ni presión; el scroll nativo de fotos permanece disponible. Sin soporte de IntersectionObserver todo el contenido queda visible.

## Validación pendiente en navegador

Las E2E cubren el primer pintado del scroll destino, la restauración al volver, movimiento reducido, aparición y swipe a 390 px. No se ejecutaron por instrucción del encargo. Verificar también Safari/iOS y dispositivos híbridos: la selección táctil depende de `hover: none`. LCP y CLS requieren medición en navegador; el código conserva las imágenes prioritarias y no anima propiedades de layout.
