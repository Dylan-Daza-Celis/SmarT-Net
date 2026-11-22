# SmartIR-Net

Gestión de incidentes con FastAPI, SQLAlchemy, PostgreSQL y React/TypeScript. Incluye Argon2id, JWT de 15 minutos, permisos en backend, acciones de respuesta e historial de estados.

## Arranque

Requiere Docker Compose v2 y puertos locales 5173 y 8000 disponibles.

```powershell
Copy-Item .env.example .env
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
| Importar JSON/JSONL | Sí | Sí | No |
| Cambiar estado y registrar acciones | Sí | Sí | No |
| Crear usuarios, cambiar rol, contraseña o desactivar | Sí | No | No |

Importar `examples/eventos_demo.json`: 4 eventos y 3 incidentes; repetir detecta 4 duplicados. El detalle muestra eventos, historial y acciones. Los roles con escritura pueden cambiar entre Nuevo, Asignado, En análisis, En respuesta, Resuelto y Cerrado, con justificación obligatoria. Se permiten saltos y reaperturas. Repetir el estado actual devuelve 409. Autor, fecha UTC, estado previo y justificación se guardan en una transacción.

## Migraciones sin borrar datos

Respaldar PostgreSQL y detener escrituras antes de actualizar. Conservar el volumen postgres_data; no ejecutar `docker compose down -v`. Alembic adopta las tablas originales y agrega usuarios, historial y acciones. Los incidentes previos conservan su estado; no se inventa historial retroactivo.

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

SQLite se usa solo como base temporal de pruebas por defecto. Para PostgreSQL real, definir TEST_DATABASE_URL hacia una base desechable y usar otro --basetemp. Cada prueba crea y elimina un esquema aislado. Consultar [documentación técnica y resultados reales](docs/AUTENTICACION_Y_RESPUESTA.md).

## Alcance

Solo health, login y documentación OpenAPI son públicos; los endpoints de datos requieren Bearer. El frontend guarda el token en memoria: recargar exige iniciar sesión. El backend consulta rol y activación en cada petición. Cerrar sesión borra el token local; una copia sigue válida hasta expirar. No hay refresh tokens, revocación individual, MFA, recuperación de contraseña ni limitación de intentos de login. La gestión administrativa de usuarios se ofrece por API/OpenAPI.

Se conserva la correlación por tipo y destino sin ventana temporal, y el scoring original con ponderaciones de ingeniería aún no validadas. Las acciones son registros de texto, no ejecutan comandos en equipos. Asignado es un estado, sin usuario responsable. La interfaz apunta a localhost. Configurar HTTPS y controles de exposición antes de un despliegue externo.

.env y __pycache__ fueron retirados del índice; .env.example tiene campos vacíos. El .env inspeccionado contenía un marcador de laboratorio. Si alguna credencial real fue publicada, debe rotarse: retirarla del commit actual no la elimina del historial.

Los documentos previos de contexto en docs describen el prototipo anterior. Este README y AUTENTICACION_Y_RESPUESTA.md documentan la implementación actual.