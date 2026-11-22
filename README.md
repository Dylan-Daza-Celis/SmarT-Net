# SmartIR-Net

Gestión de incidentes con FastAPI, SQLAlchemy, PostgreSQL y React/TypeScript. Incluye Argon2id, JWT de 15 minutos, permisos en backend, acciones de respuesta e historial de estados. La iteración 04 incorpora archivos Suricata EVE JSON Lines al motor de correlación UTC y riesgo versionado existente, con evidencia y reporte de importación.

## Arranque

Requiere Docker Compose v2 y puertos locales 5173 y 8000 disponibles.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Completar DB_PASSWORD y JWT_SECRET localmente.
docker compose up --build -d
docker compose exec api python -m app.bootstrap
```

Generar valores independientes con `python -c "import secrets; print(secrets.token_urlsafe(48))"`. JWT_SECRET necesita al menos 32 bytes. DB_PASSWORD debe usar caracteres seguros para URL (como token_urlsafe), pues se interpola en DATABASE_URL. No guardar valores en Git. En instalaciones existentes conservar la contraseña real de PostgreSQL: cambiar Compose no cambia la contraseña del volumen existente.

La API ejecuta `alembic upgrade head` antes de Uvicorn. Bootstrap crea solo el primer administrador y pide la contraseña sin mostrarla; no hay cuentas predeterminadas. Crear otros usuarios desde http://localhost:8000/docs: obtener un token con POST /api/auth/login y usar Authorize. Abrir http://localhost:5173 e iniciar sesión.

## Roles

| Operación | Administrador | Analista | Observador |
|---|---|---|---|
| Consultar incidentes, estadísticas, historial y acciones | Sí | Sí | Sí |
| Importar SmartIR JSON/JSONL y Suricata EVE | Sí | Sí | No |
| Cambiar estado y registrar acciones | Sí | Sí | No |
| Crear usuarios, cambiar rol, contraseña o desactivar | Sí | No | No |

Importar `examples/eventos_demo.json`: 4 eventos y 4 incidentes, porque las IP de origen son distintas; repetir detecta 4 duplicados. El detalle muestra factores de riesgo, parámetros, eventos, historial y acciones. Los filtros combinan prioridad, tipo y estado. Los roles con escritura pueden cambiar entre Nuevo, Asignado, En análisis, En respuesta, Resuelto y Cerrado, con justificación obligatoria. Se permiten saltos y reaperturas. Repetir el estado actual devuelve 409. Autor, fecha UTC, estado previo y justificación se guardan en una transacción.

## Suricata EVE JSON (iteración 04)

En la interfaz elegir **Suricata EVE JSON Lines**, indicar un sensor estable y seleccionar el archivo. Se admiten archivos UTF-8 con un objeto JSON por línea, incluido el habitual `eve.json`; no arrays ni archivos comprimidos. Administrador y analista importan, observador consulta. Se muestran importados, duplicados, descartados y errores por línea. En el detalle de eventos, **Evidencia** muestra el registro original y su procedencia.

Endpoint: `POST /api/events/import/eve?filename=eve.json&sensor_id=lab01`, con Bearer y el archivo como cuerpo `application/x-ndjson`, sin multipart. Límites: 10 MiB por archivo, 64 KiB por línea, 10000 registros, lotes de 100 válidos. Las líneas inválidas no anulan las válidas; al superar bytes o registros se devuelve HTTP 413 con reporte parcial. Los lotes confirmados se conservan. El endpoint SmartIR anterior mantiene su contrato y sus fingerprints.

Se importan alertas; otros tipos EVE se descartan explícitamente. Las categorías se asignan mediante una tabla conservadora y versionada, sin inferencias desde la firma. Categorías no mapeadas quedan como `desconocido`. Exfiltración requiere una categoría personalizada explícita. `examples/suricata_sintetico.eve.jsonl` incluye seis alertas claramente **sintéticas, no una captura IDS real**: primera importación en base sin esos registros, 6 importados y 6 incidentes; segunda con el mismo sensor, 6 duplicados.

La criticidad EVE predeterminada 50 **no procede de una observación**. Se identifica como política en eventos y en el riesgo `weighted-v2` de incidentes nuevos. Los incidentes con parámetros `weighted-v1` y sus evaluaciones permanecen sin reescrituras. Especificación, correspondencias, campos, pruebas y limitaciones en [INTEGRACION_SURICATA.md](docs/INTEGRACION_SURICATA.md).

## Correlación y riesgo (iteración 03)

Definir opcionalmente `CORRELATION_WINDOW_SECONDS=900` en `.env`. Las ventanas fijas UTC son `[inicio, fin)`, alineadas al epoch Unix; se agrupa por tipo, IP de origen e IP de destino. Un evento tardío usa su fecha de evento y puede actualizar una ventana anterior. Cambiar el ancho no reagrupa datos previos. Los incidentes heredados permanecen separados, con sus eventos y riesgo intactos.

Se mantienen los pesos 35/25/15/15/10 como parámetros iniciales de ingeniería. La explicación devuelve valores, contribuciones, política de contexto desconocido, versión y parámetros congelados por incidente. Cada lote nuevo agrega una evaluación consultable mediante `GET /api/incidents/{id}/evaluations`. No se recalculan silenciosamente evaluaciones históricas por cambios de configuración.

Algoritmo, fórmulas, campos ausentes, límites, eventos tardíos, migración 0003 y resultados: [CORRELACION_Y_RIESGO.md](docs/CORRELACION_Y_RIESGO.md).

## Migraciones sin borrar datos

Respaldar PostgreSQL y detener escrituras antes de actualizar. Conservar el volumen postgres_data; no ejecutar `docker compose down -v`. Alembic aplica hasta `0004`, que agrega metadata y evidencia EVE a `0003` sin eliminar datos, usuarios ni evaluaciones existentes. Los incidentes previos conservan su estado y parámetros; no se inventa procedencia retroactiva. No cambiar credenciales durante la actualización.

Fuera de Docker, definir DATABASE_URL y JWT_SECRET en el entorno; desde backend ejecutar `python -m alembic upgrade head`, `python -m app.bootstrap` y `python -m uvicorn app.main:app`. La API ya no crea tablas al arrancar.

## Pruebas

Desde la raíz, PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/sqlite
Push-Location frontend
npm ci
npm run build
Pop-Location
```

SQLite se usa solo como base temporal de pruebas por defecto. Para PostgreSQL real, definir TEST_DATABASE_URL hacia una base desechable y usar otro --basetemp. Cada prueba crea y elimina un esquema aislado. Iteración 04: **38 pruebas aprobadas en SQLite y 38 en PostgreSQL 16**, build TypeScript/Vite correcto y Compose aislado verificado en `0004`, incluida importación/reimportación sintética de 6 alertas. Permanece una advertencia de deprecación de Starlette/AnyIO. Consultar [resultados y fallos corregidos](docs/INTEGRACION_SURICATA.md).

## Alcance

Solo health, login y documentación OpenAPI son públicos; los endpoints de datos requieren Bearer. El frontend guarda el token en memoria: recargar exige iniciar sesión. El backend consulta rol y activación en cada petición. Cerrar sesión borra el token local; una copia sigue válida hasta expirar. No hay refresh tokens, revocación individual, MFA, recuperación de contraseña ni limitación de intentos de login. La gestión administrativa de usuarios se ofrece por API/OpenAPI.

Las ventanas fijas pueden separar eventos cercanos a ambos lados de un límite y agrupar episodios distintos dentro de una misma ventana; los puertos y firmas no forman parte de la clave. El contexto desconocido usa un prior neutral 50 declarado como política, sin inventar datos observados. Las acciones son registros de texto, no ejecutan comandos en equipos. Asignado es un estado, sin usuario responsable. La interfaz apunta a localhost. Configurar HTTPS y controles de exposición antes de un despliegue externo.

.env y __pycache__ permanecen fuera del índice; .env.example contiene únicamente campos secretos vacíos y el ancho de ventana. Se retiró del ejemplo un valor con apariencia de secreto JWT. Si se utilizó o compartió, debe rotarse: retirarlo del commit actual no elimina su exposición anterior. No se modificaron .env ni contraseñas existentes.

El estado actual está en este README, [la antología actualizada](docs/ANTologia_implementacion.md) y [la integración Suricata](docs/INTEGRACION_SURICATA.md). AUTENTICACION_Y_RESPUESTA.md y CORRELACION_Y_RIESGO.md conservan la evidencia de sus iteraciones anteriores.
