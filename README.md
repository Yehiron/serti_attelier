# SERTI Atelier — e-commerce

Plataforma de venta de joyería de piezas únicas para SERTI: sitio público en español e inglés, compra como invitado, pagos con Wompi y panel administrativo.

> Estado: **Fase 1 — base del proyecto**. Infraestructura, configuración segura y CI; todavía sin funcionalidades de negocio.

## Documentación

| Documento | Contenido |
|---|---|
| [docs/requirements.md](docs/requirements.md) | Requisitos, origen, prioridad y criterios de aceptación |
| [docs/decisions.md](docs/decisions.md) | Decisiones del cliente, decisiones técnicas (ADR) y pendientes |
| [docs/architecture.md](docs/architecture.md) | Arquitectura y revisión del stack |
| [docs/database-design.md](docs/database-design.md) | Entidades, restricciones, índices y estados |
| [docs/api-contract.md](docs/api-contract.md) | Endpoints, errores y límites |
| [docs/ux-ui-plan.md](docs/ux-ui-plan.md) | Navegación, pantallas, personalización y dirección visual |
| [docs/security-plan.md](docs/security-plan.md) | Amenazas, controles, roles y datos personales |
| [docs/integrations.md](docs/integrations.md) | Wompi, pago manual, correo, WhatsApp y almacenamiento |
| [docs/development-plan.md](docs/development-plan.md) | Fases, tareas y criterios de finalización |
| [docs/testing-strategy.md](docs/testing-strategy.md) | Pruebas unitarias, integración, E2E y seguridad |

## Desarrollo local

Requisitos: Docker Desktop, Node.js 22.18+ (solo para correr el frontend fuera de Docker) y Python 3.13 (opcional).

```bash
cp .env.example .env
make up
```

| URL | Qué es |
|---|---|
| https://serti.localhost | Sitio público (redirige a `/es` o `/en`) |
| https://serti.localhost/api/v1/health/ready | Salud del backend (base de datos y Redis) |
| https://serti.localhost/api/v1/schema/ | OpenAPI (solo en desarrollo) |
| https://serti.localhost/dashboard/ | Dashboard (ruta configurable con `DJANGO_ADMIN_URL`) |
| https://mail.serti.localhost | Mailpit: correos de desarrollo |

El certificado lo emite la CA local de Caddy. Para que el navegador lo acepte sin aviso, confía en esa CA una vez:

```bash
docker compose -f infra/docker-compose.dev.yml cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

y agrégala al llavero del sistema (macOS: abrir el archivo → Llaveros → "Confiar siempre").

Otros comandos: `make test`, `make lint`, `make logs`, `make migrate`, `make down`.

### Estructura

```
backend/    Django 5.2 LTS + DRF (apps por dominio en backend/apps)
frontend/   Next.js 16 (App Router, rutas /es y /en)
infra/      Docker Compose y Caddy
docs/       Requisitos, arquitectura, decisiones y planes
```

## Stack

Next.js · TypeScript · Tailwind · Django · DRF · PostgreSQL · Redis · Celery · Caddy · Docker Compose.

La referencia visual es el prototipo editorial anterior (repositorio aparte), cuya paleta se conserva.
