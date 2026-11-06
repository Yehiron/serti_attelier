# Pedidos — etapa 1: pagos Wompi seguros

Fecha: 2026-11-06. Rama: `fase-9-produccion`. Sin push ni consultas externas. Se utilizaron los hechos oficiales incluidos en el pedido; no se consultó documentación por red.

## Cambios y decisiones

- El webhook conserva un recibo inmutable con campos permitidos de la transacción, sin datos de cliente. Se distingue con `provider_event=transaction.updated.received` y `outcome=ignored_event`: recibir no implica aplicar. Así se reutiliza el registro existente sin agregar estados ni cambiar sus constraints.
- Solo una respuesta de `WompiClient.get_transaction(id)` puede aplicarse desde el webhook. Se cotejan ID, referencia e importe del evento con la canónica; una discrepancia deja un evento `mismatch`, un log sin PII y ningún cambio en el pedido. Una referencia canónica desconocida deja `unknown_reference` y log, sin vender.
- `apply_transaction` concentra el cotejo con el intento Wompi: referencia, ID conocido/no reutilizado, importe, moneda COP e igualdad con la moneda del intento. Sync verifica además el ID solicitado y la pertenencia al pedido; conciliación pasa referencia e ID esperados. Solo las discrepancias con un intento identificado siguen el camino existente de atención, sin venta.
- El estado del evento puede estar desactualizado: se aplica el canónico. Se conserva el control de duplicados, la venta única y los avisos existentes. La firma y `test_official_event_vector` permanecen sin cambios.
- Si la consulta no devuelve transacción, el recibo ya está persistido y se encola `verify_wompi_event(receipt_id)`. Reconsulta la API y reintenta a 1, 5, 15 y 60 minutos; al agotarse registra advertencia. El webhook devuelve `{}` con 503 si falla la persistencia, aplicación o publicación de la tarea; devuelve 200 después de aplicar/registrar el resultado o persistir y publicar la tarea.
- Persistencia y broker no forman una transacción distribuida. Un fallo al publicar devuelve 503 para que Wompi reintente; la conciliación es la red de seguridad. No se introduce ni modifica outbox. Deben estar operativos worker, broker y scheduler existentes.
- `is_configured`, producción, warning de desarrollo y `check_production` comparten el diagnóstico de las cuatro llaves y las dos URLs exactas. Los prefijos deben coincidir entre sí y con la URL; los errores nombran variables, sin mostrar valores. Producción admite todas las llaves vacías para deshabilitar Wompi; cualquier llave presente obliga a completar una configuración coherente.
- Cotización omite Wompi si está incompleto. La creación de intentos lo rechaza con el esquema habitual de error y una explicación en español. No se modifican las formas públicas de respuesta.
- Conciliación incluye pendientes de más de 10 minutos mientras el pedido continúe pendiente, sin límite de 48 horas. Los pendientes sin ID de más de `WOMPI_RECONCILE_PENDING_MAX_DAYS` se omiten y contabilizan en log. Con ID continúan siendo elegibles mientras el pedido siga pendiente.
- También consulta aprobados cuyo `updated_at` corresponde a los últimos `WOMPI_RECONCILE_APPROVED_DAYS`, permitiendo detectar VOIDED. Esta fecha se actualiza al aplicar el estado; registrar una conciliación no la extiende. El lote máximo es `WOMPI_RECONCILE_BATCH`, con valores predeterminados 7 días / 7 días / 50 consultas y prioridad para `last_reconciled_at` nulo o más antiguo.
- Una respuesta API disponible reinicia `reconcile_failures`; ausencia de respuesta incrementa el contador y desde cinco fallos genera advertencia sin PII. Se eligió **solo log**, como permite el alcance: un fallo de consulta no demuestra un pago aprobado y no marca atención automáticamente.
- VOIDED desde PENDING termina el intento, conserva pendiente el pedido y permite reintento con reserva válida. VOIDED después de APPROVED conserva el comportamiento previo: anulado y atención, sin liberar la venta.
- La confirmación manual ya rechazaba pedidos Wompi. Se añadieron pruebas del servicio y del POST real del admin, sin cambiar el dashboard.

## Archivos

- `backend/apps/payments/{wompi,api,services,tasks,models,apps}.py`: disponibilidad, recepción, verificación canónica, aplicación y conciliación.
- Nuevos `backend/apps/payments/{configuration,checks}.py`: diagnóstico compartido y system check de desarrollo.
- `backend/apps/orders/services.py`: filtrado de canales de la cotización.
- `backend/config/settings/{base,prod,test}.py`, `.env.example`: opciones de conciliación, validación estricta y documentación individual de variables. Tests usan cuatro credenciales ficticias coherentes, sin heredar secretos locales.
- `backend/apps/core/management/commands/check_production.py`: reutilización del mismo diagnóstico para evitar criterios contradictorios.
- `backend/apps/payments/tests/{test_canonical,test_configuration,test_payments}.py`: casos obligatorios y actualización de mocks para la consulta canónica. El test de doble webhook de notificaciones también mockea Wompi; no se cambia código de notificaciones.
- `backend/conftest.py`: bloquea `urlopen` de Wompi durante tests; las pruebas del cliente usan su mock explícito.
- `backend/apps/orders/tests/test_checkout.py`: presupuesto de consultas explícito para Wompi deshabilitado (3) y habilitado (4); el segundo incluye la consulta de los campos del checkout que antes no se ejercitaba por defecto.

No se modificaron Next.js, estados operativos, cancelación, outbox, correos ni dashboard. Se leyó `protection.py` y se mantuvieron sus límites y política de registro.

## Migración mínima

`backend/apps/payments/migrations/0005_paymentattempt_last_reconciled_at_and_more.py` agrega únicamente:

- `last_reconciled_at`: nullable, con índice para ordenar conciliaciones sin confundirlas con cambios de estado.
- `reconcile_failures`: entero no negativo, inicialmente cero, para detectar fallos seguidos entre ejecuciones.

No transforma datos ni altera constraints. Los bloqueos del servicio de pagos usan `select_for_update(of=("self",))`; se mantienen constraints inmediatas, no diferibles. **La migración y los bloqueos no están verificados en PostgreSQL en este sandbox.**

## Comandos y resultados

Se ejecutó desde `backend` con `.venv/bin` en los comandos equivalentes. Para las pruebas se suministraron `DJANGO_SECRET_KEY=local-tests`, `DATABASE_URL` local y `REDIS_URL=redis://localhost:6379/0`; no se cargaron secretos del `.env`.

1. `pytest --ds=config.settings.test -q`, con `DATABASE_URL=postgres://serti:serti@localhost:5432/serti`: PostgreSQL bloqueado por el sandbox, `Operation not permitted` para localhost IPv4/IPv6. **No verificado en PostgreSQL.** Una primera ejecución terminó con 81 pruebas sin base aprobadas y 791 errores de acceso; la repetición final terminó con **81 passed, 815 errors**, todos los errores debidos al acceso a PostgreSQL. No equivale a una suite aprobada.
2. `python manage.py makemigrations payments --settings=config.settings.test`: generó la migración 0005, con warning por falta de acceso a PostgreSQL.
3. `python manage.py makemigrations --check --dry-run --settings=config.settings.test`: `No changes detected`, con el mismo warning de acceso a PostgreSQL. Comprueba correspondencia de modelos, no aplicación real.
4. Verificación complementaria **SQLite, no sustitutiva de PostgreSQL**: `pytest --ds=config.settings.test apps/payments/tests apps/notifications/tests/test_notifications.py::test_double_webhook_one_set -q`: **90 passed, 1 skipped**. Incluye las pruebas canónicas, configuración, reintentos, conciliación y rechazo manual HTTP. La omitida requiere PostgreSQL.
5. Complementaria SQLite: `pytest --ds=config.settings.test apps/payments/tests/test_configuration.py apps/core/tests/test_production.py -q`: **18 passed** después de unificar el comando de producción.
6. Suite completa complementaria SQLite: `pytest --ds=config.settings.test -q`: **873 passed, 22 skipped, 1 failed**. El único fallo es `apps/core/tests/test_health.py::test_ready_reports_dependencies`, que necesita Redis accesible; la respuesta es 503 con Redis no disponible en el sandbox. No se cambió ese test ni la comprobación de salud.
7. Ruff en todos los módulos Python modificados y pagos: **All checks passed**. `git diff --check`: sin errores.
8. `mypy apps/payments apps/orders/services.py --no-incremental`: no pasa; reporta 82 errores en 8 archivos de catálogo/pedidos, en código fuera de las líneas de esta etapa (incluidos formularios y admin). No reporta errores en pagos. Se dejan fuera de alcance, sin afirmar que el gate global de tipos pasa.

Los resultados SQLite no prueban concurrencia, bloqueos con FKs anulables ni comportamiento de constraints de PostgreSQL. No hubo llamadas reales a Wompi.

## Pendiente de verificación del propietario

1. En un entorno con PostgreSQL y Redis accesibles, aplicar `python manage.py migrate` y ejecutar exactamente `cd backend && pytest --ds=config.settings.test -q`. Revisar especialmente las pruebas marcadas `postgres`, venta concurrente y constraints inmediatas.
2. Comprobar en despliegue la configuración completa, worker Celery, broker y periodicidad de `apps.payments.tasks.reconcile_pending` ya existente. Validar reintentos con proveedor simulado antes de usar credenciales reales.
3. Considerar los límites deliberados: agotados los cuatro reintentos, queda el log y la conciliación; pendientes sin ID de más de siete días se omiten según configuración y anulaciones posteriores a la ventana de aprobados requieren otra revisión.
4. Sin commit: `.git` no es escribible en este sandbox. No se crearon scripts de commit ni se hizo push. Al poder confirmar, usar un mensaje en español y el trailer solicitado: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
