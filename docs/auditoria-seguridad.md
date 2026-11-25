# Auditoría de seguridad local (2026-11-13)

Revisión de la rama `fase-9-produccion` en el entorno de desarrollo, sin servicios externos ni escáneres descargados.

## Resultado

| Área | Comprobación | Resultado |
|---|---|---|
| Dashboard sin sesión | GET/POST a las 24 vistas propias (editor, biblioteca, publicar, pedidos, comprobantes, 2FA…) | Login o 403 en todas |
| Permisos por rol | 21 rutas con sesión local de Operaciones, Contenido y Propietaria | Operaciones sin CMS; Contenido edita y no publica; auditoría general de solo lectura para Propietaria y superusuarios; tablas internas (grupos, TOTP, intentos de pago) cerradas a los demás roles |
| API pública | 25 rutas `AllowAny` | Todas son de la tienda; límites de peticiones en lectura, carrito, cotización, pedidos y pagos |
| Endpoint interno | `/api/internal/*` desde Caddy | 404 |
| Esquema API y `/media/` por Django | `urls.py` | Solo en desarrollo |
| Archivos privados | Comprobantes de pago y videos originales | Almacenamiento privado; descarga solo desde el dashboard |
| Fotos públicas | Piezas y biblioteca CMS | Recodificadas sin EXIF/GPS, nombres UUID |
| XSS | `dangerouslySetInnerHTML` en tienda | HTML del CMS saneado con nh3 (solo `https`/`mailto`); JSON-LD escapa `<`; enlaces externos de menú y redes solo `https` |
| Vista previa | `cms/preview/verify` | Token firmado con caducidad y permiso `preview_content` |
| Login | django-axes + TOTP | Bloqueo tras 5 intentos (usuario + IP); 2FA para Propietaria |
| Comandos E2E | `e2e_admin_session`, `e2e_piece` | Fallan si `DEBUG` es falso |
| Producción | `check --deploy` con `config.settings.prod` | Sin avisos; rechaza el simulador de Wompi |
| Cabeceras | Caddy prod | HSTS, nosniff, DENY, COOP, Permissions-Policy, CSP por zona (tienda, dashboard, API, media con `sandbox`) |
| Secretos | Archivos versionados e historial | Solo marcadores y valores de prueba |

## Cambios

- `pillow-heif` 1.1.1 → **1.3.0** (CVE-2026-28231, lectura fuera de límites al **codificar** HEIF). SERTI solo decodifica HEIC y guarda WebP, así que no era explotable aquí, pero se elimina igualmente. 62 pruebas de imágenes en verde; `pip-audit` sin hallazgos.

## Pendientes

- `npm audit`: 7 avisos moderados de `minimatch` dentro de `typescript-eslint` (solo herramientas de desarrollo; no llegan a la tienda). Se resolverán al actualizar eslint.
- OWASP ZAP *baseline*: requiere descargar su imagen Docker; ejecutar con autorización, idealmente contra *staging*.
- Rutas inexistentes de la tienda responden 200 con `noindex` (streaming de Next; documentado en `api-contract.md`).

La auditoría registra cambios en Datos del sitio con campos sensibles redactados y cambios de estado de mensajes de contacto sin copiar el mensaje. La lista omite la IP y el navegador; el detalle conserva los datos técnicos existentes. Operaciones y Contenido no tienen acceso a la auditoría general.

## Decisión: CSP de la tienda sin nonce (25/11/2026)

Se evaluó una CSP con nonce por petición para quitar `'unsafe-inline'` de `script-src`. Según la [guía oficial de Next.js](https://nextjs.org/docs/app/guides/content-security-policy), el nonce es incompatible con el prerenderizado parcial: obliga a renderizar cada página por petición y a servir el HTML con `Cache-Control: private, no-store`, lo que revierte parte de la mejora de rendimiento (ver `docs/rendimiento.md`). La cliente eligió **mantener la política anterior** (`script-src 'self' 'unsafe-inline' https://checkout.wompi.co`, sin `unsafe-eval` en producción, `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`).

Mitigaciones de XSS verificadas con ataques reales en local: React escapa todo el texto dinámico, el contenido del CMS se limpia con `nh3`, el JSON-LD escapa `<`, y los datos de clientes (mensajes de contacto, nombres en pedidos) se muestran escapados en el panel y en los correos. Si en el futuro se necesita la CSP estricta, la alternativa es hashes/SRI de scripts, aún experimental en Next.

CI incluye Gitleaks para detectar secretos; los valores de prueba se mantienen claramente ficticios (`backend/apps/payments/tests/fakes.py`).
