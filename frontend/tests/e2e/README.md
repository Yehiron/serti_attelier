# Pruebas E2E

Al finalizar Playwright, `globalTeardown` ejecuta `e2e_cleanup` en el backend de Docker Compose, también en CI. El comando exige `DEBUG=True`; conserva pedidos mixtos y las piezas que contienen. Para inspeccionar los datos después de una corrida, usa `E2E_KEEP_DATA=1 npx playwright test`. Para previsualizar la limpieza, ejecuta `docker compose -f infra/docker-compose.dev.yml exec -T backend python manage.py e2e_cleanup --dry-run` desde la raíz.

Se conserva `e2e-cms-publisher`, necesario para publicar el CMS entre pasos de CI, así como el contenido y las publicaciones del CMS. Las pruebas de contacto interceptan el envío; no hay una marca de prueba segura para borrar mensajes o cupones generales. Los usuarios efímeros con referencias protegidas también se conservan y se informan.
