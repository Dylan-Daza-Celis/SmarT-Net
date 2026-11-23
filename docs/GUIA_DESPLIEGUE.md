# Guía de despliegue y conservación — iteración 10

**Actualización13:** frontend y backend deben actualizarse juntos para las nuevas rutas /api/auth/session. El navegador usa /api del mismo origen, por proxy Vite; Compose configura SMARTIR_API_PROXY_TARGET=http://api:8000 en web. No se cambia head0009, credenciales ni volúmenes. Una recarga restaura identidad con cookie HttpOnly; mutaciones por cookie exigen Origin y cabecera CSRF. Dist requiere su propio proxy /api si se sirve fuera de Vite. [Configuración, contratos y límites de seguridad13](REDISENO_FRONTEND.md). No se presenta Vite/HTTP local como despliegue productivo.

Ámbito: **prototipo local**, no receta de producción ni certificación de seguridad. Docker Desktop/Compose, PostgreSQL16, API FastAPI/SQLAlchemy/Alembic y React/TypeScript con Vite. Actualización11: head0009 agrega únicamente users.eve_only/defaultFalse para el agente restringido. En10 no se necesitaron migraciones nuevas; sus resultados se conservan como históricos. Configuración opcional y validación actual en [MONITOREO_CONTINUO_SURICATA](MONITOREO_CONTINUO_SURICATA.md).

## Variables y requisitos

| Variable | Uso/default | Tratamiento |
|---|---|---|
| DB_PASSWORD | Compose exige valor para un volumen nuevo/existente | Secreto local; mantener contraseña del volumen existente; URL-safe por interpolación |
| JWT_SECRET | Exigida, mínimo32 bytes | Secreto aleatorio; conservar al actualizar, no publicar |
| DATABASE_URL | Backend fuera de Compose; Compose la construye | Secreto si contiene contraseña; no imprimir config expandida |
| CORRELATION_WINDOW_SECONDS | 900 | Cambiar no reagrupa históricos; rango validado por motor |
| SMARTIR_ALLOWED_HOSTS | localhost,127.0.0.1,::1,api | Nombres literales permitidos; no sustituye autenticación/CORS |
| VITE_API_URL | http://localhost:8000 | URL pública sin secretos; build/dev Vite. Vacío=same-origin, usado por proxy de prueba |
| TEST_DATABASE_URL | Solo pytest, SQLite temporal si ausente | Únicamente PostgreSQL desechable; nunca DATABASE_URL operativa |
| VALIDATION_* | Solo arnés10, efímeras | Runner genera valores; no copiarlos a .env ni evidencias |

.env y cachés están ignorados; .env.example tiene secretos vacíos. No hay credenciales predeterminadas. El ejemplo antiguo retiró un valor con apariencia de secreto: si fue utilizado/compartido debe rotarse de forma planificada; retirarlo del archivo no elimina su exposición histórica. Esta iteración no modificó secretos ni contraseñas.

## Instalación nueva y arranque

Comprobar Docker Desktop activo y puertos5173/8000 libres. En PowerShell desde la raíz:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Completar localmente DB_PASSWORD y JWT_SECRET, sin publicarlos.
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose exec api python -m alembic current
docker compose exec api python -m app.bootstrap
Invoke-RestMethod http://localhost:8000/health
```

Para un volumen nuevo generar valores independientes con un gestor de secretos o `secrets.token_urlsafe(48)` y guardarlos solo localmente. Bootstrap solicita contraseña oculta y se niega si ya hay usuarios. **No ejecutar bootstrap como recuperación de una instalación existente**. Completar otros usuarios mediante API administrativa/OpenAPI.

API ejecuta `alembic upgrade head` antes de Uvicorn; head esperado0009 en11. `/health` es liveness y devuelve estado del proceso: **no consulta la base de datos**. Verificar también Alembic, estado healthy de db y una consulta autenticada para readiness. Frontend `http://localhost:5173`; API/docs localhost8000. PostgreSQL no publica puerto al host en Compose habitual. Puertos web/API enlazados a127.0.0.1.

Vite de Compose es servidor de desarrollo. CORS del backend permite localhost/127.0.0.1:5173, GET/POST/PATCH, Content-Type/Authorization. Otra URL VITE_API_URL no amplía CORS automáticamente. El arnés de navegador usa proxy same-origin en otro puerto hacia su propia API; no cambia la política operativa. No exponer Vite ni API HTTP a Internet.

## Actualización sin pérdida

1. Identificar proyecto/volumen reales con `docker compose ps` y `docker volume ls`. No ejecutar down-v, prune, DROP, TRUNCATE, downgrade ni crear un volumen vacío para ocultar fallos.
2. Programar pausa de escrituras y hacer respaldo consistente antes de actualizar. Conservar .env, contraseña de PostgreSQL, volumen, evidencias y modelos.
3. Ensayar restauración/upgrade en **otra base temporal**, comprobar conteos/hashes y migraciones. Las pruebas automatizadas usan esquemas UUID propios y cubren datos legacy; no prueban una copia particular del usuario.
4. Actualizar código y dependencias fijadas; `docker compose build`, `docker compose up -d`; comprobar Alembic0009 y health/readiness. Aplicar solo upgrade aditivo. Si falla, detener escrituras, inspeccionar logs saneados y recuperar desde copia ensayada; no bajar esquema destructivamente.
5. Verificar incidentes/evidencia, usuarios/roles, evaluaciones, experimentos, modelos y snapshots. Un reinicio no debe recalcular riesgos ni modificar históricos. Tokens en memoria del navegador no sobreviven recarga; persistencia de datos es independiente de sesión.

Historial:0001 esquema previo,0002 auth/acciones,0003 temporal/riesgo,0004 evidencia EVE,0005 evaluación,0006 ML,0007 ciclo de vida,0008 reportes/reevaluación/índices,0009 cuenta solo EVE. Los legacy mantienen estados/riesgos y tiempos desconocidos; asignaciones/tiempos no se fabrican. Ver [VALIDACION_INTEGRAL](VALIDACION_INTEGRAL.md) para las pruebas10 de preservación y el informe11 para el upgrade actual.

## Respaldo y restauración de prueba

Procedimiento **documental**, no se atribuye una restauración real en esta iteración. El respaldo puede contener IP, mensajes y hashes de contraseña: mantenerlo fuera de Git, con permisos restringidos, cifrado y retención definida. No incluirlo en docs/resultados.

Desde la instalación que se respalda, exportación binaria dentro del contenedor y copia (evita redirección binaria corrupta en PowerShell):

```powershell
docker compose exec -T db pg_dump -U smartir -d smartir -Fc -f /tmp/smartir-backup.dump
docker compose cp db:/tmp/smartir-backup.dump .test-runs/smartir-backup.dump
Get-FileHash .test-runs/smartir-backup.dump -Algorithm SHA256
```

La herramienta no borra el archivo del contenedor; administrar su retención de forma consciente. Para ensayo, crear **otro contenedor**, sin volumen operativo ni puerto público; usar un nombre nuevo y contraseña temporal propia definida localmente en `$env:RESTORE_TEST_PASSWORD`:

```powershell
docker run --name smartir-restore-test --tmpfs /var/lib/postgresql/data -e POSTGRES_DB=restore_test -e POSTGRES_USER=smartir -e POSTGRES_PASSWORD=$env:RESTORE_TEST_PASSWORD -d postgres:16-alpine
docker exec smartir-restore-test pg_isready -U smartir -d restore_test
docker cp .test-runs/smartir-backup.dump smartir-restore-test:/tmp/backup.dump
docker exec smartir-restore-test pg_restore --exit-on-error --no-owner -U smartir -d restore_test /tmp/backup.dump
docker exec smartir-restore-test psql -U smartir -d restore_test -c 'SELECT version_num FROM alembic_version'
```

Esperar pg_isready antes de restaurar. No añadir `--clean` ni apuntar pg_restore a la base habitual. Comparar conteos y muestras canónicas de todas las tablas, originales/hashes, riesgos congelados, artefactos y reportes. Para ensayo de migración conectar una API **aislada** a esa copia en la red Docker adecuada y ejecutar upgrade, nunca compartir la API del usuario. El contenedor/archivo de respaldo se conservan hasta terminar la revisión; cualquier eliminación posterior requiere decisión explícita del responsable.

## Validación aislada reproducible

Python 3.11+ con `.venv` y dependencias-dev; Node 18+ para herramientas locales (Docker usa22). Instalar Playwright Chromium una vez. PostgreSQL de pruebas en55440 utiliza tmpfs y confianza **solo para laboratorio loopback**, sin volúmenes existentes; no reutilizar esta configuración en producción.

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
docker run --name smartir-iter10-pg --label smartir.validation=iter10 --rm --tmpfs /var/lib/postgresql/data -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_validation -p 127.0.0.1:55440:5432 -d postgres:16-alpine
docker exec smartir-iter10-pg pg_isready -U postgres -d smartir_validation
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/replay10-sqlite --junitxml=.test-runs/iter10-release-sqlite.xml
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55440/smartir_validation'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/replay10-pg --junitxml=.test-runs/iter10-release-pg.xml
Remove-Item Env:TEST_DATABASE_URL
Push-Location frontend
npm ci
npx playwright install chromium
npm run build
Pop-Location
.venv\Scripts\python -m validation.run_integral --database postgresql --browser --label replay10
.venv\Scripts\python -m validation.run_integral --database sqlite --label replay10
.venv\Scripts\python -m benchmarks.http_concurrent --label replay10
powershell -NoProfile -File validation/compose_smoke.ps1
```

Usar etiquetas nuevas: los runners rechazan sobreescribir evidencia. Ejecutar npm ci **antes** del navegador, sin Vite abierto: Windows puede bloquear esbuild. Cada runner crea base/tabla de prueba propia; no admite URL arbitraria de destino. El HTTP benchmark conserva cuotas predeterminadas. Schemas del runner permanecen mientras viva el PostgreSQL temporal; pytest retira solo sus esquemas UUID. Compose smoke crea proyecto/volumen nuevos, comprueba puertos58010/55180 y detiene solo ese proyecto, **sin eliminar volúmenes**. Su frontend se comprueba por HTTP200; el navegador usa el proxy aislado aparte, no ese Compose en puertos alternativos.

## Seguridad operacional y problemas frecuentes

Host tiene allowlist; Uvicorn ignora forwarded headers y no anuncia Server; CSP/no-store en API, nosniff/DENY/no-referrer. No confiar X-Forwarded-For de clientes. Detrás de proxy configurar confianza explícita solo a proxies conocidos y reevaluar CORS/Host/TLS y puertos. El rate limiting es **por proceso**, no distribuido, y se reinicia con el proceso. Con varios workers aumenta capacidad efectiva; no es una política global.

Para producción faltarían diseño HTTPS/proxy, servidor estático de frontend, secretos gestionados, backup/restore ensayado, observabilidad, protección distribuida, hardening de imágenes, revocación/MFA según riesgo, pruebas sostenidas y validación externa. No aumentar límites para ocultar429 ni equiparar mayor throughput a menor MTTD/MTTR.

| Síntoma | Diagnóstico/conservación |
|---|---|
| Docker unavailable | Iniciar Desktop; no reemplazar base por SQLite operacional |
| Puerto ocupado | Identificar proceso; usar runner/override aislado, no detener proyecto ajeno |
| Password authentication failed | Usar contraseña vigente del volumen; cambiar .env no rota PostgreSQL |
| Alembic falla | Ver estado/version/log saneado; respaldo y ensayo; no borrar volumen/downgrade |
| npm EPERM esbuild | Finalizar solo servidor de prueba propio; repetir npm ci; no instalar simultáneamente |
| 429/503 | Respetar Retry-After; distinguir cuotas/plazas de errores, consultar antes de repetir escritura |
| Dashboard vacío | Comprobar periodo UTC/eje/fuente; no significa pérdida de datos |
| 409 al editar | Recargar y revisar conflicto; no sobrescribir con revisión inventada |

Las auditorías npm/pip son consultas a avisos conocidos, con alcance y fecha; no equivalen a pentest, auditoría externa ni ausencia de vulnerabilidades.
