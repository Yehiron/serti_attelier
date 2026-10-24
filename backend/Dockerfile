# syntax=docker/dockerfile:1

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app

FROM base AS deps
ARG REQUIREMENTS=base
COPY requirements/ requirements/
RUN pip install -r requirements/${REQUIREMENTS}.txt

FROM deps AS runtime
COPY --chown=app:app . .
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=collectstatic-only \
    DATABASE_URL=sqlite:////tmp/unused.db \
    REDIS_URL=redis://unused:6379/0 \
    python manage.py collectstatic --noinput \
 && mkdir -p /app/media && chown app:app /app/media
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
