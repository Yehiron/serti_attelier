COMPOSE = docker compose -f infra/docker-compose.dev.yml

.PHONY: up down logs ps test lint migrate shell e2e

up: ## Start the local stack (https://serti.localhost)
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

test: ## Backend tests inside the stack + frontend unit tests
	$(COMPOSE) exec backend pytest
	cd frontend && npm test

lint: ## Needs backend/.venv: python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements/lint.txt
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check . && \
		DJANGO_SECRET_KEY=lint DATABASE_URL=sqlite:////tmp/lint.db REDIS_URL=redis://localhost:6379/0 .venv/bin/mypy .
	cd frontend && npm run lint && npm run typecheck

migrate:
	$(COMPOSE) exec backend python manage.py migrate

shell:
	$(COMPOSE) exec backend python manage.py shell

e2e: ## Browser tests (Playwright) against the running stack: make up && make seed first
	cd frontend && npx playwright test

seed: ## Demo catalog for development
	$(COMPOSE) exec backend python manage.py seed_catalog
