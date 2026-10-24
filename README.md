# SERTI Atelier — e-commerce

Plataforma de venta de joyería de piezas únicas para SERTI: sitio público en español e inglés, compra como invitado, pagos con Wompi y panel administrativo.

> Estado: **Fase 0 — análisis y planificación**. Aún no hay código de producción.

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

## Stack

Next.js · TypeScript · Tailwind · Django · DRF · PostgreSQL · Redis · Celery · Caddy · Docker Compose.

La referencia visual es el prototipo editorial anterior (repositorio aparte), cuya paleta se conserva.
