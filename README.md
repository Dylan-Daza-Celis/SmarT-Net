# SmartIR-Net

Gestión de incidentes con FastAPI, SQLAlchemy, PostgreSQL y React/TypeScript. Incluye Argon2id, JWT de 15 minutos, permisos en backend, acciones de respuesta e historial de estados. La iteración 04 incorpora archivos Suricata EVE JSON Lines al motor de correlación UTC y riesgo versionado existente, con evidencia y reporte de importación.

La **iteración 05** incorpora evaluación experimental reproducible: datasets separados del flujo operativo, comparación emparejada FIFO/SmartIR, métricas con motivos de «No calculable» y exportación CSV/JSON. Los reportes no representan trabajo de operadores ni demuestran mejoras estadísticas.

La **iteración 06** añade LogisticRegression y RandomForest experimentales, pipelines scikit-learn, test aislado por grupos y comparación con weighted-v2. **Weighted-v2 sigue siendo el motor operativo predeterminado**; no se activan modelos ML en producción ni se alteran scores históricos.

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

Respaldar PostgreSQL y detener escrituras antes de actualizar. Conservar el volumen postgres_data; no ejecutar `docker compose down -v`. Alembic aplica hasta `0006`, que agrega únicamente ml_runs a `0005` para guardar modelos numéricos y resultados sin eliminar ni modificar datos, usuarios, evidencias o experimentos existentes. Los incidentes previos conservan su estado y parámetros; no se inventa procedencia retroactiva. No cambiar credenciales durante la actualización.

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

SQLite se usa solo como base temporal de pruebas por defecto. Para PostgreSQL real, definir TEST_DATABASE_URL hacia una base desechable y usar otro --basetemp. Cada prueba crea y elimina un esquema aislado. Iteración 06: **65 pruebas aprobadas en SQLite y 65 en PostgreSQL 16**, comprobaciones finales específicas de ML en ambas, build TypeScript/Vite correcto y Compose aislado en `0006` con entrenamiento e inferencia por API. Permanece una advertencia de deprecación de Starlette/AnyIO. [Validación actual](docs/APRENDIZAJE_AUTOMATICO.md). Se conservan los resultados de [iteración 05 (54 por base)](docs/EVALUACION_EXPERIMENTAL.md) y [04 (38 por base)](docs/INTEGRACION_SURICATA.md) como evidencia histórica.

## Evaluación experimental (iteración 05)

Ingresar como administrador investigador y abrir **Evaluación experimental**. Generar semilla `202605`, 60 casos y presupuesto de 10 selecciones para reproducir el protocolo. También se admite un JSON externo de hasta 2 MiB con autorización y procedencia explícitas; plantilla sintética: `examples/evaluacion_externa_sintetica.json`. Las etiquetas se almacenan aparte, no se pasan al modelo y no se muestran a analistas/observadores. Estos roles pueden consultar características y órdenes sin resultados contra referencias; solo el investigador ejecuta, consulta métricas y exporta datos etiquetados.

Se guardan UUID, fecha, versiones, parámetros, cohorte, órdenes y resultados. La comparación mide cobertura de críticos bajo el mismo número de selecciones, sin inventar duraciones. Exactitud, matriz, precisión/recall/F1 evalúan el clasificador común; FIFO no emite otra prioridad. FPR requiere etiquetas binarias explícitas. MTTD/MTTR requieren marcas válidas completas, evidencia temporal y datos no sintéticos, y son descripciones de la fuente, no mejoras causadas por la simulación.

Resultado real del replay sintético documentado: FIFO seleccionó **7/23 críticos**, SmartIR **4/23**, ambos con 10 selecciones. Exactitud del clasificador 0.25; macro-F1 0.182850. MTTD/MTTR: **No calculable**. Esta muestra no respalda una mejora y no constituye evidencia estadística sobre incidentes reales. [Diseño, fórmulas, amenazas a la validez y resultados](docs/EVALUACION_EXPERIMENTAL.md).

## Aprendizaje automático experimental (iteración 06)

Actualizar las dependencias del backend e ingresar como administrador investigador. En **Aprendizaje automático experimental**, generar laboratorio con semilla `202606`, 96 grupos (288 casos), luego entrenar con la misma semilla y presupuesto 10. El manifiesto separa grupos, referencias y características. Repetir el mismo manifiesto devuelve 409: reutilizar el dataset existente. El generador de iteración 05 queda excluido como evidencia predictiva.

El sistema reserva grupos completos para test (216 train / 72 test en la ejecución documentada), ajusta preprocesamiento solo en train y ejecuta CV estratificada por grupos cuando es viable. Usa parámetros fijos, sin optimizar con test. Modelos, parámetros, clases, versiones y resultados se guardan en JSON numérico; no existe carga de pickle/joblib ni de artefactos de terceros. La inferencia y sus probabilidades estimadas sin calibrar son consultables por usuarios autenticados; entrenamiento, resultados con referencias y exportaciones quedan para administrador, conforme al protocolo de cegamiento anterior.

Resultado del laboratorio guardado: macro-F1 test LR **0.5656**, RF **0.7086**, weighted-v2 **0.4188**. Sin embargo, recall de críticos fue mayor con weighted-v2 (**31/33**, frente a **23/33** en ML), y los tres cubrieron **10/33** críticos con presupuesto 10. Son resultados descriptivos sobre supuestos sintéticos, sin superioridad estadística ni validez de producción. [Metodología, manifiesto externo, limitaciones y resultados completos](docs/APRENDIZAJE_AUTOMATICO.md).

## Alcance

Solo health, login y documentación OpenAPI son públicos; los endpoints de datos requieren Bearer. El frontend guarda el token en memoria: recargar exige iniciar sesión. El backend consulta rol y activación en cada petición. Cerrar sesión borra el token local; una copia sigue válida hasta expirar. No hay refresh tokens, revocación individual, MFA, recuperación de contraseña ni limitación de intentos de login. La gestión administrativa de usuarios se ofrece por API/OpenAPI.

Las ventanas fijas pueden separar eventos cercanos a ambos lados de un límite y agrupar episodios distintos dentro de una misma ventana; los puertos y firmas no forman parte de la clave. El contexto desconocido usa un prior neutral 50 declarado como política, sin inventar datos observados. Las acciones son registros de texto, no ejecutan comandos en equipos. Asignado es un estado, sin usuario responsable. La interfaz apunta a localhost. Configurar HTTPS y controles de exposición antes de un despliegue externo.

.env y __pycache__ permanecen fuera del índice; .env.example contiene únicamente campos secretos vacíos y el ancho de ventana. Se retiró del ejemplo un valor con apariencia de secreto JWT. Si se utilizó o compartió, debe rotarse: retirarlo del commit actual no elimina su exposición anterior. No se modificaron .env ni contraseñas existentes.

El estado actual está en este README, [la antología actualizada](docs/ANTologia_implementacion.md) y [el aprendizaje automático experimental](docs/APRENDIZAJE_AUTOMATICO.md). Los documentos anteriores conservan sus especificaciones y resultados históricos; no se sustituyen por la evidencia de la nueva iteración.
