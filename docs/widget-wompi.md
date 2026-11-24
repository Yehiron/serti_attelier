# Widget de Wompi

La política CSP permite únicamente `https://checkout.wompi.co` para el script y el iframe del widget, y conserva ese origen en `form-action` para el respaldo. Durante la prueba real en sandbox, revisar la consola: si Wompi necesita otro dominio bloqueado, verificarlo y agregarlo explícitamente a la directiva correspondiente. La confirmación del pago depende del servidor, nunca del callback del widget.

## Comportamiento observado en sandbox (2026-11-24)

- El widget inserta `.waybox-backdrop` (fixed) y `.waybox-modal` (absolute, ~1300 px en celular) en `body`; depende del scroll de la página. Mientras está abierto, el panel pasa a no modal (`paying`) y se desbloquea el scroll; al cerrarlo se restaura.
- Al cerrarlo con su ✕ **no** llama al callback: conserva el nodo y agrega `waybox-modal-final-close` (`watchWidgetClose`).
- Solo carga `https://checkout.wompi.co/widget.js` y el iframe `https://checkout.wompi.co/p/`; la CSP actual basta.
- Un fallo de `payment-sync` no es fatal: el panel consulta igualmente el estado del pedido (webhook/conciliación pueden haberlo resuelto).
- Pendiente: pago con tarjeta completo dentro del widget hecho por una persona (los selectores del iframe no se pudieron operar con la herramienta automática).
