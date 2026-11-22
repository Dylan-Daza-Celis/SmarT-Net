# Autenticación y respuesta a incidentes

Validación: 21 de noviembre de 2026, America/Mexico_City.

## Diseño

Se conserva FastAPI + SQLAlchemy + PostgreSQL y React + TypeScript. Los modelos originales `events` e `incidents` permanecen. Se agregan:

- `users`: UUID, usuario único, hash Argon2id con sal aleatoria, rol, activación y fecha UTC.
- `incident_history`: incidente, autor, estado previo nullable, nuevo estado, justificación y fecha UTC. La importación registra la creación en Nuevo. No se reconstruye historial de incidentes anteriores.
- `response_actions`: incidente, autor, descripción y fecha UTC. Son registros anexados; no hay endpoints para editarlos o eliminarlos.

JWT usa HS256 con secreto obligatorio del entorno, sin valor predeterminado. Se fija el algoritmo y se exigen `sub`, `iat`, `exp`, `iss` y `aud`. Duración: 900 segundos. El token identifica al usuario; el backend consulta su rol y activación en cada petición. Contraseñas nuevas: 12–128 caracteres. El login verifica un hash ficticio para usuarios inexistentes y actualiza hashes cuando cambian sus parámetros. Ningún endpoint devuelve hashes.

Referencias utilizadas: [PasswordHasher de argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/api.html), [validación de claims con PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html).

## Contrato HTTP

| Método y ruta | Acceso | Datos principales |
|---|---|---|
| POST `/api/auth/login` | Público | username, password; devuelve access_token, token_type, expires_in |
| GET `/api/auth/me` | Todos los roles | Identidad y rol actuales |
| GET / POST `/api/users` | Administrador | Listar / crear con username, password, role |
| PATCH `/api/users/{id}` | Administrador | role, active y password opcionales |
| POST `/api/events/import` | Administrador, analista | Lote de 1–1000 eventos, fecha con zona horaria |
| GET `/api/incidents`, `/api/incidents/{id}`, `/api/stats` | Todos los roles | Consultas originales protegidas |
| PATCH `/api/incidents/{id}/status` | Administrador, analista | status y justification obligatorios |
| GET `/api/incidents/{id}/history` | Todos los roles | Historial ordenado, con autor y fecha |
| POST `/api/incidents/{id}/actions` | Administrador, analista | description obligatoria |
| GET `/api/incidents/{id}/actions` | Todos los roles | Acciones con autor y fecha |

Respuestas: 401 sin autenticación válida, 403 por rol insuficiente, 404 por recurso inexistente, 409 por usuario duplicado o estado repetido y 422 por validación. Se rechazan justificaciones y descripciones de solo espacios y propiedades adicionales en las escrituras de usuarios, estados y acciones. Un administrador no puede desactivar ni degradar su propia cuenta.

Todos los estados pueden cambiar a cualquiera de los otros cinco, incluidas reaperturas: Nuevo, Asignado, En análisis, En respuesta, Resuelto, Cerrado. El cambio de estado y su historial usan la misma transacción, con bloqueo de fila PostgreSQL (`SELECT FOR UPDATE`). La importación, el scoring y el historial de creación también son transaccionales. El historial es inmutable desde la API.

## Migraciones

`0001` contiene una definición congelada del esquema original y crea solo tablas ausentes. `0002` agrega las tres tablas nuevas con claves foráneas e índices por incidente. No se usan los modelos vivos para construir las tablas de estas revisiones. `alembic upgrade head` admite bases nuevas y bases del MVP original sin tabla alembic_version. Se conserva el contenido de eventos e incidentes; no se les atribuye autor retroactivo.

Respaldar antes de actualizar, detener escrituras y conservar el volumen PostgreSQL. La adopción presupone el esquema original: variantes manuales requieren revisión. Downgrades destructivos deshabilitados explícitamente; recuperar mediante respaldo. En múltiples réplicas, ejecutar la migración una sola vez antes de arrancarlas. Bootstrap bloquea la tabla de usuarios en PostgreSQL para serializar la creación inicial. No se tocó ninguna base productiva del usuario.

## Archivos modificados o agregados

| Archivo | Cambio |
|---|---|
| backend/app/main.py | Login, usuarios, protecciones, historial, acciones y estado; fecha de evento con zona horaria |
| backend/app/models.py | Extracción de modelos existentes y tres nuevos modelos |
| backend/app/database.py | Motor SQLAlchemy, PostgreSQL por defecto y sesiones |
| backend/app/security.py | Argon2id, JWT y dependencias de permisos |
| backend/app/bootstrap.py | Alta interactiva del primer administrador |
| backend/alembic.ini, backend/migrations/env.py | Configuración de Alembic |
| backend/migrations/versions/0001_existing.py, 0002_auth.py | Adopción original y ampliación aditiva |
| backend/requirements.txt, backend/requirements-dev.txt | Dependencias de autenticación, migraciones y pruebas |
| backend/tests/conftest.py, backend/tests/test_api.py | Fixtures con migraciones reales y pruebas de API |
| backend/Dockerfile, backend/.dockerignore | Empaquetado y arranque con migraciones |
| frontend/src/main.tsx, frontend/src/style.css | Login, listado y detalle editable según rol |
| frontend/Dockerfile, frontend/package-lock.json, frontend/.dockerignore | Instalación con npm ci, dependencias reproducibles y exclusiones |
| compose.yaml | Contraseña DB y secreto JWT obligatorios desde el entorno |
| .gitignore, .env.example | Exclusiones y ejemplo con valores vacíos |
| .env, backend/app/__pycache__/main.cpython-313.pyc | Retirados del índice Git, conservados localmente |
| README.md y este documento | Operación, resultados y limitaciones |

## Comandos y resultados reales

Entorno: Windows, Python 3.11.15; dependencias en .venv. PostgreSQL 16 en contenedor desechable, puerto local 55432. SQLite se utilizó únicamente en pruebas.

```powershell
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/sqlite
```

Resultado tras las correcciones: **8 passed, 1 warning in 5.89s**.

```powershell
docker run --detach --rm --name smartir-test-postgres -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55432:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55432/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/postgres
docker stop smartir-test-postgres
```

El modo trust se usa exclusivamente en este contenedor temporal, publicado en loopback y sin volumen persistente. Resultado: **8 passed, 1 warning in 48.06s**. El fixture crea un esquema aleatorio por prueba y lo elimina al finalizar. TEST_DATABASE_URL debe apuntar a una base desechable con permiso de crear esquemas. El warning en ambas ejecuciones es una deprecación de `anyio.abc.BlockingPortal` desde Starlette TestClient.

La suite comprueba login correcto e incorrecto, hash Argon2id, caducidad de 15 minutos, tokens vencidos/falsificados, protección de consultas, permisos de los tres roles, gestión y desactivación de usuarios, cambios de rol efectivos con tokens ya emitidos, importación de 4 eventos/3 incidentes, deduplicación, validación, seis cambios de estado, autor/fecha/justificación, acciones y adopción de una base antigua con un evento y un incidente conservados. Aplica Alembic realmente; no simula hashing ni permisos.

Desde frontend: `npm install` terminó con 0 vulnerabilidades informadas por npm; `npm run build` completó TypeScript y Vite 6.4.6 (26 módulos). Se conserva package-lock.json para usar `npm ci`.

Fallos observados y corregidos durante la ejecución:

- pip falló inicialmente por restricciones de red (WinError 10013) y npm por EPERM al resolver el directorio del usuario. Ambas instalaciones terminaron al usar los permisos adecuados.
- Un intento de npm desde la raíz no encontró package.json; se instaló desde frontend.
- Los dos primeros intentos de pytest PostgreSQL produjeron 8 errores de preparación cada uno: permisos del temporal de Windows y luego directorio padre inexistente. Se creó .test-runs y se usó --basetemp local con la caché desactivada. Esos intentos no se cuentan como pruebas exitosas.
- Se detectó y corrigió corrupción de acentos introducida por el transporte de texto de PowerShell antes de repetir las pruebas finales.

## Limitaciones

No se ejecutaron pruebas de navegador, carga o concurrencia, ni un arranque completo de Compose. Sin rate limiting de login, MFA, recuperación de contraseña o revocación individual de tokens. Cambiar la contraseña no invalida tokens emitidos; desactivar la cuenta bloquea peticiones y rotar JWT_SECRET invalida todas las sesiones. Cerrar sesión solo elimina el token en memoria. El frontend puede mostrar permisos anteriores hasta iniciar sesión otra vez, pero el backend aplica el rol actual.

Las importaciones concurrentes del mismo evento pueden producir un conflicto de unicidad que requiere reintento. No hay paginación. Asignado es un estado sin responsable asociado. Las acciones no ejecutan comandos en dispositivos. La correlación y scoring originales siguen siendo provisionales. No se realizó una auditoría exhaustiva del historial Git. El .env revisado tenía un marcador de laboratorio; si se publicó cualquier credencial real, debe rotarse. Eliminarla del índice no borra su historial.
