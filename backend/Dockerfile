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
    COUPON_EMAIL_PEPPER=collectstatic-only \
    DATABASE_URL=sqlite:////tmp/unused.db \
    REDIS_URL=redis://unused:6379/0 \
    python manage.py collectstatic --noinput \
 && mkdir -p /srv/static /srv/media /srv/private_media \
 && chown -R app:app /srv/static /srv/media /srv/private_media
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/v1/health/live', headers={'Host': os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')[0], 'X-Forwarded-Proto': 'https'}), timeout=3)" || exit 1
CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
