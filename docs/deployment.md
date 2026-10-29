# Despliegue en producción

Guía para poner SERTI en el VPS. Todo corre con Docker Compose: `infra/docker-compose.yml` levanta
PostgreSQL, Redis, el backend (Gunicorn), Celery (worker y beat), el frontend (Next.js standalone),
Caddy (HTTPS automático) y el servicio de copias de seguridad. Solo Caddy publica puertos (80 y 443).

> Nada de esta guía se ejecuta sin autorización explícita del equipo. Las llaves de producción
> nunca se escriben en el repositorio ni en chats: solo en `.env.production` dentro del VPS.

## 1. Requisitos del VPS

- Ubuntu 24.04 LTS (u otra distribución con Docker Engine 27+ y el plugin `docker compose`).
- Mínimo 2 vCPU, 4 GB de RAM y 40 GB de disco (las fotos crecen con el catálogo).
- Usuario sin privilegios de root, con acceso por llave SSH, en el grupo `docker`.
- Firewall: solo 22 (idealmente limitado a IPs conocidas), 80 y 443 (TCP) y 443/UDP (HTTP/3).
- Actualizaciones de seguridad automáticas (`unattended-upgrades`) y `fail2ban` para SSH.

```bash
sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443 && sudo ufw enable
```

Si el VPS ya aloja otros sitios con su propio proxy en 80/443, hay que decidir antes quién termina
TLS: o Caddy de SERTI pasa a ser el proxy de todo, o el proxy existente reenvía el dominio a Caddy en
puertos internos (`HTTP_PORT`/`HTTPS_PORT`) y entonces Caddy debe usar `tls internal` o certificados
del proxy principal.

## 2. DNS

En el proveedor del dominio del cliente:

| Registro | Nombre | Valor |
|---|---|---|
| A | `@` | IP pública del VPS |
| A | `www` | IP pública del VPS |
| AAAA | `@`, `www` | IPv6 del VPS (solo si el VPS la tiene configurada) |
| CAA (opcional) | `@` | `0 issue "letsencrypt.org"` |

Para el correo transaccional, el proveedor SMTP indicará los registros SPF, DKIM y DMARC; sin ellos
los correos de pedidos terminan en spam.

Comprobar antes del primer arranque: `dig +short CHANGE-ME.co` debe devolver la IP del VPS. Caddy
pide el certificado al iniciar; si el DNS aún no apunta, Let's Encrypt falla y reintenta con espera.

## 3. Preparar el servidor

```bash
git clone https://github.com/Yehiron/serti_attelier.git /opt/serti && cd /opt/serti
cp .env.production.example .env.production && chmod 600 .env.production
sudo mkdir -p /var/backups/serti && sudo chown "$USER" /var/backups/serti
```

Completar `.env.production` (cada `CHANGE-ME`):

- `DJANGO_SECRET_KEY`, `INTERNAL_API_TOKEN`, `COUPON_EMAIL_PEPPER`, `POSTGRES_PASSWORD`: valores
  aleatorios distintos (`python3 -c "import secrets; print(secrets.token_urlsafe(64))"`). La contraseña
  de PostgreSQL se repite dentro de `DATABASE_URL`.
- `DJANGO_ADMIN_URL`: ruta del panel difícil de adivinar (por ejemplo `gestion-7f3k/`).
- Wompi: llaves de **sandbox** hasta que el cliente apruebe la salida en vivo (P-11). La URL del
  evento a registrar en Wompi es `https://<dominio>/api/v1/payments/wompi/events`.
- SMTP y `SERTI_ORDERS_EMAIL` cuando el cliente elija proveedor (P-09).
- `BACKUP_AGE_RECIPIENT`: llave pública de copias (sección 6).

## 4. Primer despliegue

```bash
infra/scripts/deploy.sh --no-pull
```

El script construye las imágenes, aplica migraciones y `collectstatic` (servicio `migrate`), arranca
todo, corre `check_production` y espera a que `/api/v1/health/ready` responda. Luego:

```bash
COMPOSE="docker compose -f infra/docker-compose.yml --env-file .env.production"
$COMPOSE exec backend python manage.py createsuperuser
```

Entrar a `https://<dominio>/<DJANGO_ADMIN_URL>`, activar la verificación en dos pasos (obligatoria),
crear los usuarios del equipo con sus roles, y cargar: ajustes del sitio (WhatsApp, redes, correo de
soporte), páginas legales definitivas, portada y catálogo con fotos reales.

`check_production` debe terminar sin ❌ antes de anunciar el sitio. Las advertencias ⚠️ se aceptan
solo si están en la lista de pendientes del cliente.

## 5. Despliegues siguientes

```bash
cd /opt/serti && infra/scripts/deploy.sh
```

Hace `git merge --ff-only origin/main`, saca una copia de seguridad **antes** de migrar, reconstruye,
reinicia y verifica. Las imágenes quedan etiquetadas con el commit (`SERTI_VERSION`).

**Volver a la versión anterior:** `git checkout <commit-anterior> && infra/scripts/deploy.sh --no-pull`.
Si la versión nueva traía migraciones que no son compatibles hacia atrás, restaurar la copia previa
(sección 7) en lugar de solo cambiar el código.

## 6. Copias de seguridad

El servicio `backup` guarda cada día a las 3:00 (hora de Colombia), en `BACKUP_DIR` del host:

- `db-<fecha>.dump.age`: `pg_dump` en formato personalizado.
- `media-<fecha>.tar.gz.age`: fotos públicas y comprobantes de pago privados.
- `checksums-<fecha>.sha256`.

Se cifran con [age](https://age-encryption.org) usando una **llave pública**: el servidor puede
cifrar pero no descifrar. Si alguien compromete el VPS, no puede leer copias anteriores. Se borran
las copias con más de `BACKUP_RETENTION_DAYS` días.

Generar la pareja de llaves **en un computador del equipo, no en el VPS**:

```bash
age-keygen -o serti-backup.key   # imprime "Public key: age1..."
```

- La línea `age1...` va en `BACKUP_AGE_RECIPIENT`.
- `serti-backup.key` se guarda en el gestor de contraseñas del equipo y en una copia offline. Sin
  ella las copias no sirven.

**Copia fuera del servidor (obligatoria):** una copia que vive en el mismo disco no protege contra la
pérdida del VPS. Programar en otro equipo o almacenamiento (por ejemplo un bucket S3/B2 con
`rclone`, o `rsync` a otra máquina) la descarga diaria de `/var/backups/serti`. Al estar cifradas, se
pueden guardar en cualquier proveedor.

Copia manual en cualquier momento:

```bash
$COMPOSE run --rm --entrypoint backup.sh backup
```

Vigilar que en `$COMPOSE logs backup` aparezca `backup ok` cada día; `backup FAILED` requiere acción.

## 7. Restaurar (y simulacro)

Hacer un simulacro antes del lanzamiento y luego cada trimestre: restaurar en una máquina de prueba,
no en producción.

```bash
$COMPOSE stop backend worker beat frontend
$COMPOSE run --rm -v "$PWD/serti-backup.key:/keys/backup.key:ro" --entrypoint restore.sh backup \
  /keys/backup.key db-20261028T080000Z.dump.age media-20261028T080000Z.tar.gz.age
$COMPOSE up -d
$COMPOSE exec backend python manage.py check_production
```

La llave privada se copia al servidor solo durante la restauración y se borra después.
`pg_restore --clean` reemplaza los datos actuales dentro de una única transacción: si falla, la
base queda como estaba.

## 8. Seguridad aplicada

- **Caddy:** HTTPS con HSTS, HTTP/3, compresión, cuerpo máximo de 20 MB, `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` y CSP por zona:
  sitio público (ADR-017), panel, API (solo JSON) y `/media` (sandbox, sin scripts).
- **Django:** cookies `__Host-`, `Secure` y `HttpOnly`, redirección a HTTPS, panel con 2FA
  obligatorio (ADR-011), límites de peticiones por IP, webhook de Wompi limitado (P-24).
- **Gunicorn** confía en `X-Forwarded-*` solo desde Caddy (`FORWARDED_ALLOW_IPS=172.30.0.10`, IP fija
  en la red de Compose).
- **Contenedores:** usuarios sin root, healthchecks, logs rotados (10 MB × 5), Redis con AOF para no
  perder notificaciones en cola.
- **Errores:** Sentry opcional (`SENTRY_DSN`) con limpieza de datos personales y llaves antes de
  enviar; los logs en JSON pasan por el mismo filtro.

## 9. Checklist de lanzamiento

- [ ] DNS apunta al VPS y el certificado se emitió (`curl -I https://<dominio>`).
- [ ] `check_production` sin ❌.
- [ ] Propietario con 2FA; usuarios del equipo creados con el rol mínimo.
- [ ] Páginas legales definitivas publicadas (sin "Texto provisional"), revisadas por el cliente (P-13).
- [ ] Catálogo real con fotos; datos de demostración (`DEMO-`, `E2E-`) eliminados.
- [ ] Wompi: compra de prueba completa en sandbox; URL de eventos registrada; cambio a llaves de
      producción aprobado por el cliente y una compra real de bajo valor reembolsada.
- [ ] Pago manual: instrucciones bancarias reales en ajustes; pedido de prueba cancelado.
- [ ] Correo: SPF, DKIM y DMARC válidos; correo de pedido recibido en Gmail y Outlook sin spam.
- [ ] WhatsApp: número del botón correcto; alertas por Cloud API si P-06 está resuelto.
- [ ] Primera copia de seguridad `backup ok`, copia fuera del servidor funcionando y simulacro de
      restauración hecho.
- [ ] Monitoreo externo de disponibilidad (por ejemplo UptimeRobot) sobre `/api/v1/health/ready`.
- [ ] Google Search Console con el `sitemap.xml`.

## 10. Operación diaria

| Tarea | Comando |
|---|---|
| Estado | `$COMPOSE ps` |
| Logs | `$COMPOSE logs -f --tail=100 backend worker` |
| Shell de Django | `$COMPOSE exec backend python manage.py shell` |
| Verificación | `$COMPOSE exec backend python manage.py check_production` |
| Reiniciar un servicio | `$COMPOSE restart frontend` |
| Espacio en disco | `docker system df && df -h /` |
