# SmartIR-Net

Gestión de incidentes con FastAPI, SQLAlchemy, PostgreSQL y React/TypeScript. Incluye Argon2id, JWT de 15 minutos, permisos en backend, acciones de respuesta e historial de estados. La iteración 04 incorpora archivos Suricata EVE JSON Lines al motor de correlación UTC y riesgo versionado existente, con evidencia y reporte de importación.

La **iteración 05** incorpora evaluación experimental reproducible: datasets separados del flujo operativo, comparación emparejada FIFO/SmartIR, métricas con motivos de «No calculable» y exportación CSV/JSON. Los reportes no representan trabajo de operadores ni demuestran mejoras estadísticas.

La **iteración 06** añade LogisticRegression y RandomForest experimentales, pipelines scikit-learn, test aislado por grupos y comparación con weighted-v2. **Weighted-v2 sigue siendo el motor operativo predeterminado**; no se activan modelos ML en producción ni se alteran scores históricos.

La **iteración 07** agrega responsables, máquina de estados, revisiones optimistas, acciones tipificadas, línea temporal y métricas operativas documentales. Los eventos recibidos para casos cerrados generan señales de revisión y conservan su riesgo.

La **iteración 08** incorpora dashboard analítico con Recharts, agregación SQL, filtros UTC comunes, paginación y snapshots inmutables exportables como CSV/JSON/PDF. Agrega reevaluación explícita y auditada tras reapertura y revisión obligatoria al registrar acciones. [Diseño, indicadores, procedimiento y evidencias](docs/DASHBOARD_Y_REPORTES.md).

La **iteración 09** añade límites de solicitudes/admisión, respuestas sin valores sensibles, protección Host/proxy, cabeceras defensivas, paginación de históricos y actualizaciones de seguridad compatibles. Optimiza la ingestión por lotes y publica mediciones sintéticas reproducibles de 100/1000/10000 eventos, con igualdad semántica antes/después. [Auditoría interna, protocolo, resultados y límites](docs/SEGURIDAD_Y_RENDIMIENTO.md).

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

Importar `examples/eventos_demo.json`: 4 eventos y 4 incidentes; repetir detecta 4 duplicados. El detalle muestra riesgo, eventos, responsable, primeros/últimos timestamps y timeline. El dashboard combina periodo, eje temporal, responsable, prioridad, tipo, estado y fuente; por defecto muestra los últimos 30 días por creación del incidente. Para ejemplos de fechas antiguas, elegir su periodo y eje de evento. Desde iteración 07, la asignación inicial mueve Nuevo a Asignado y los estados siguen la máquina de trabajo; los saltos libres de versiones anteriores quedan sustituidos por transiciones y reaperturas explícitas. Se registran autor, UTC y justificación en una transacción.

## Dashboard y reportes (iteración 08)

Indicadores, gráficas, tabla paginada y exportaciones comparten la misma cohorte. El periodo UTC es `[start,end)`, máximo 366 días. Se elige creación del incidente, timestamp del evento o recepción. En los dos últimos ejes, solo cuentan eventos coincidentes y cada incidente aparece una vez en su primer evento coincidente. En creación, los eventos se atribuyen a la fecha del incidente. Los estados/prioridades/responsables son actuales, no una reconstrucción histórica.

GET `/api/analytics/dashboard` y `/incidents` devuelven conteos, denominadores, tendencias y tiempos disponibles; los usuarios autenticados consultan. Administrador/analista guardan un snapshot mediante POST `/api/analytics/reports`; cualquier rol autenticado puede descargar los snapshots saneados en CSV, JSON o PDF. Límite de 2000 incidentes/5 MiB, sin truncamiento silencioso. La exportación excluye IP, mensajes, evidencias originales y nombres de usuarios; conserva filtros y UUID necesarios para trazabilidad. El origen operativo/sintético de eventos anteriores no se infiere: se identifica como no certificado.

Las comparaciones ML guardadas conservan su cohorte experimental y permisos de administrador investigador. Se presentan en un apartado independiente de los filtros y exportaciones operativas, con procedencia sintética/controlada/real declarada. No se filtran métricas congeladas ni se recalculan resultados para aparentar una comparación sobre otra población.

Comprobar integridad del ejemplo **sintético generado por HTTP**, sin credenciales ni base de datos:

```powershell
.venv\Scripts\python backend/app/verify_report.py docs/resultados/iter08_reporte_sintetico.json
```

**Cambio de contrato 08:** POST `/api/incidents/{id}/actions` exige ahora `expected_revision` además de descripción/categoría/fecha; ausente 428, obsoleta 409. El texto y las acciones históricas permanecen intactos. Tras reabrir Cerrado, POST `/api/incidents/{id}/reevaluate` exige revisión y justificación, responsabilidad/admin y nuevas señales de cierre. Reutiliza parámetros congelados, anexa evaluación y auditoría, y nunca reescribe las anteriores. Una importación posterior a reapertura conserva el score mientras esa evidencia esté pendiente de reevaluación. Reconocer una señal sigue siendo una operación separada.

## Seguridad y rendimiento (iteración 09)

Login tiene 20 solicitudes/IP/minuto; importación 30/usuario/minuto; investigación 12/administrador/minuto; reportes 10/escritor/minuto y exportaciones 30/usuario autorizado/minuto. Las plazas de operaciones costosas son acotadas y no bloquean esperando una cola global. Exceso: **429 y Retry-After**. Las cuotas son por proceso, se pierden al reiniciar y no son distribuidas. Se ignoran cabeceras de IP reenviada en el despliegue local; detrás de proxy debe configurarse explícitamente la confianza. Host predeterminado local; SMARTIR_ALLOWED_HOSTS permite otros nombres literales sin cambiar secretos.

Se rechazan NUL/UTF-8 inválido y campos extra, sin normalizar cadenas válidas o alterar fingerprints. Errores 422 ya no reflejan valores del cuerpo. Se mantienen límites EVE/datasets y se acotan otros cuerpos/cabeceras. PostgreSQL limita espera de bloqueos y sentencias de lectura; un presupuesto agotado puede devolver 503/Retry-After. Se conservan JWT, Argon2id y autorización real en BD.

Listados legacy agregan offset/limit: incidentes 100 por defecto, datasets/experimentos 50 y versiones ML 20. El detalle pagina eventos (100 por defecto, máximo 500), conservando event_count total. React permite recorrer eventos y cargar más catálogos. No se borran filas para cumplir límites.

FastAPI/Starlette/PyJWT y herramientas de desarrollo se actualizaron con regresiones; Scikit-learn/NumPy/SciPy, algoritmos y modelos históricos permanecen iguales. npm audit y pip-audit reportaron **0 avisos** en la consulta final; esto no certifica que la aplicación esté libre de vulnerabilidades. Las versiones, hallazgos iniciales y exportaciones están documentados.

En el benchmark pareado de 10.000 eventos: SQLite **28.95 → 9.08 s**, PostgreSQL 16 **101.71 → 14.89 s**, con cero errores y hashes semánticos coincidentes. Son ejecuciones ASGI sintéticas en host compartido, sin TCP HTTP; varias latencias de dashboard/exportación empeoraron y también se reportan. **Throughput no es MTTD/MTTR ni eficacia de respuesta humana.** Los scripts usan únicamente bases nuevas aisladas; no reciben la URL habitual del usuario ni ejecutan limpieza de tablas existentes. No se necesita migración 0009; head sigue en 0008.

## Gestión avanzada de incidentes (iteración 07)

Flujo normal: **Nuevo → Asignado → En análisis → En respuesta → Resuelto → Cerrado**. El administrador asigna a escritores activos; un analista puede tomar para sí un caso sin responsable y transferir uno propio. Para retirar desde trabajo activo debe volver primero a Asignado; retirar desde Asignado lo devuelve a Nuevo. Se permiten retrocesos y reaperturas documentados; reabrir Cerrado exige administrador y responsable activo. Observador conserva solo lectura.

**Cambio necesario de contrato:** PATCH `/api/incidents/{id}/status` y el nuevo PATCH `/assignment` exigen `expected_revision`, obtenido al consultar el detalle. Ausente: 428; obsoleto: 409. Recargar y revisar antes de reintentar. No puede desactivarse/degradarse un responsable con incidentes abiertos sin reasignarlos. Los estados heredados se conservan sin inventar asignaciones o tiempos.

Las acciones agregan categoría y fecha declarada/registrada; los comentarios anteriores permanecen intactos. Desde iteración 08, los cuerpos de nuevas acciones incluyen también expected_revision. No ejecutan comandos. Un evento nuevo correlacionado con Cerrado se conserva con señal de revisión: no cambia estado, score ni evaluaciones. Reconocer una señal anexa un registro, sin borrarla.

Los intervalos de asignación, inicio de respuesta y resolución se basan en transacciones registradas. MTTD/MTTR requieren evidencia operacional documental revisada por administrador: nunca se infieren desde event_timestamp, received_at o un cambio de estado. Sin datos válidos se presenta **No calculable** y motivo. [Reglas, fórmulas, permisos, migración y resultados](docs/GESTION_AVANZADA_INCIDENTES.md).

## Suricata EVE JSON (iteración 04)

En la interfaz elegir **Suricata EVE JSON Lines**, indicar un sensor estable y seleccionar el archivo. Se admiten archivos UTF-8 con un objeto JSON por línea, incluido el habitual `eve.json`; no arrays ni archivos comprimidos. Administrador y analista importan, observador consulta. Se muestran importados, duplicados, descartados y errores por línea. En el detalle de eventos, **Evidencia** muestra el registro original y su procedencia.

Endpoint: `POST /api/events/import/eve?filename=eve.json&sensor_id=lab01`, con Bearer y el archivo como cuerpo `application/x-ndjson`, sin multipart. Límites: 10 MiB por archivo, 64 KiB por línea, 10000 registros, lotes de 100 válidos. Las líneas inválidas no anulan las válidas; al superar bytes o registros se devuelve HTTP 413 con reporte parcial. Los lotes confirmados se conservan. El endpoint SmartIR anterior mantiene su contrato y sus fingerprints.

Se importan alertas; otros tipos EVE se descartan explícitamente. Las categorías se asignan mediante una tabla conservadora y versionada, sin inferencias desde la firma. Categorías no mapeadas quedan como `desconocido`. Exfiltración requiere una categoría personalizada explícita. `examples/suricata_sintetico.eve.jsonl` incluye seis alertas claramente **sintéticas, no una captura IDS real**: primera importación en base sin esos registros, 6 importados y 6 incidentes; segunda con el mismo sensor, 6 duplicados.

La criticidad EVE predeterminada 50 **no procede de una observación**. Se identifica como política en eventos y en el riesgo `weighted-v2` de incidentes nuevos. Los incidentes con parámetros `weighted-v1` y sus evaluaciones permanecen sin reescrituras. Especificación, correspondencias, campos, pruebas y limitaciones en [INTEGRACION_SURICATA.md](docs/INTEGRACION_SURICATA.md).

## Correlación y riesgo (iteración 03)

Definir opcionalmente `CORRELATION_WINDOW_SECONDS=900` en `.env`. Las ventanas fijas UTC son `[inicio, fin)`, alineadas al epoch Unix; se agrupa por tipo, IP de origen e IP de destino. Un evento tardío usa su fecha de evento y puede actualizar una ventana anterior. Cambiar el ancho no reagrupa datos previos. Los incidentes heredados permanecen separados, con sus eventos y riesgo intactos.

Se mantienen los pesos 35/25/15/15/10 como parámetros iniciales de ingeniería. La explicación devuelve valores, contribuciones, política de contexto desconocido, versión y parámetros congelados por incidente. Cada lote nuevo de un caso abierto sin evidencia de cierre pendiente agrega una evaluación consultable mediante `GET /api/incidents/{id}/evaluations`; Cerrado y los casos pendientes de reevaluación explícita conservan el riesgo. No se recalculan silenciosamente evaluaciones históricas por cambios de configuración.

Algoritmo, fórmulas, campos ausentes, límites, eventos tardíos, migración 0003 y resultados: [CORRELACION_Y_RIESGO.md](docs/CORRELACION_Y_RIESGO.md).

## Migraciones sin borrar datos

Respaldar PostgreSQL y detener escrituras antes de actualizar. Conservar el volumen postgres_data; no ejecutar `docker compose down -v`. Alembic aplica hasta `0008`, que añade snapshots de reportes y auditoría/enlaces de reevaluación, además de índices de fechas. La 0007 conserva la gestión de ciclo de vida. Ninguna de estas migraciones elimina o recrea tablas existentes. Los incidentes previos conservan estado, eventos, parámetros y evaluaciones; no se inventa procedencia retroactiva ni se modifican modelos/experimentos. No cambiar credenciales durante la actualización.

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

SQLite se usa solo como base temporal de pruebas por defecto. Para PostgreSQL, definir TEST_DATABASE_URL hacia una base desechable y usar otro --basetemp. Cada prueba crea y elimina únicamente su esquema UUID aislado. Iteración 09: **124 aprobadas en SQLite y 124 en PostgreSQL 16**, build TypeScript/Vite y arranque/controles HTTP en Compose con head `0008`. Se conserva una advertencia de TestClient/httpx; no se realizaron pruebas de navegador ni carga TCP distribuida. [Comandos, benchmarks, resultados y fallos corregidos](docs/SEGURIDAD_Y_RENDIMIENTO.md). Evidencia histórica: [08 (106 por base)](docs/DASHBOARD_Y_REPORTES.md), [07 (82)](docs/GESTION_AVANZADA_INCIDENTES.md), [06 (65)](docs/APRENDIZAJE_AUTOMATICO.md), [05 (54)](docs/EVALUACION_EXPERIMENTAL.md) y [04 (38)](docs/INTEGRACION_SURICATA.md).

## Evaluación experimental (iteración 05)

Ingresar como administrador investigador y abrir **Evaluación experimental**. Generar semilla `202605`, 60 casos y presupuesto de 10 selecciones para reproducir el protocolo. También se admite un JSON externo de hasta 2 MiB con autorización y procedencia explícitas; plantilla sintética: `examples/evaluacion_externa_sintetica.json`. Las etiquetas se almacenan aparte, no se pasan al modelo y no se muestran a analistas/observadores. Estos roles pueden consultar características y órdenes sin resultados contra referencias; solo el investigador ejecuta, consulta métricas y exporta datos etiquetados.

Se guardan UUID, fecha, versiones, parámetros, cohorte, órdenes y resultados. La comparación mide cobertura de críticos bajo el mismo número de selecciones, sin inventar duraciones. Exactitud, matriz, precisión/recall/F1 evalúan el clasificador común; FIFO no emite otra prioridad. FPR requiere etiquetas binarias explícitas. MTTD/MTTR requieren marcas válidas completas, evidencia temporal y datos no sintéticos, y son descripciones de la fuente, no mejoras causadas por la simulación.

Resultado real del replay sintético documentado: FIFO seleccionó **7/23 críticos**, SmartIR **4/23**, ambos con 10 selecciones. Exactitud del clasificador 0.25; macro-F1 0.182850. MTTD/MTTR: **No calculable**. Esta muestra no respalda una mejora y no constituye evidencia estadística sobre incidentes reales. [Diseño, fórmulas, amenazas a la validez y resultados](docs/EVALUACION_EXPERIMENTAL.md).

## Aprendizaje automático experimental (iteración 06)

Actualizar las dependencias del backend e ingresar como administrador investigador. En **Aprendizaje automático experimental**, generar laboratorio con semilla `202606`, 96 grupos (288 casos), luego entrenar con la misma semilla y presupuesto 10. El manifiesto separa grupos, referencias y características. Repetir el mismo manifiesto devuelve 409: reutilizar el dataset existente. El generador de iteración 05 queda excluido como evidencia predictiva.

El sistema reserva grupos completos para test (216 train / 72 test en la ejecución documentada), ajusta preprocesamiento solo en train y ejecuta CV estratificada por grupos cuando es viable. Usa parámetros fijos, sin optimizar con test. Modelos, parámetros, clases, versiones y resultados se guardan en JSON numérico; no existe carga de pickle/joblib ni de artefactos de terceros. La inferencia y sus probabilidades estimadas sin calibrar son consultables por usuarios autenticados; entrenamiento, resultados con referencias y exportaciones quedan para administrador, conforme al protocolo de cegamiento anterior.

Resultado del laboratorio guardado: macro-F1 test LR **0.5656**, RF **0.7086**, weighted-v2 **0.4188**. Sin embargo, recall de críticos fue mayor con weighted-v2 (**31/33**, frente a **23/33** en ML), y los tres cubrieron **10/33** críticos con presupuesto 10. Son resultados descriptivos sobre supuestos sintéticos, sin superioridad estadística ni validez de producción. [Metodología, manifiesto externo, limitaciones y resultados completos](docs/APRENDIZAJE_AUTOMATICO.md).

## Alcance

Solo health, login y documentación OpenAPI son públicos; los endpoints de datos requieren Bearer. El frontend guarda el token en memoria: recargar exige iniciar sesión. El backend consulta rol y activación en cada petición. Cerrar sesión borra el token local; una copia sigue válida hasta expirar. No hay refresh tokens, revocación individual, MFA o recuperación de contraseña. Login y operaciones costosas ahora tienen cuotas locales; no reemplazan protección de transporte ni limitación distribuida. La gestión administrativa de usuarios se ofrece por API/OpenAPI.

Las ventanas fijas pueden separar eventos cercanos a ambos lados de un límite y agrupar episodios distintos dentro de una ventana; puertos y firmas no forman parte de la clave. El contexto desconocido usa un prior neutral 50, sin inventar observaciones. Las métricas de tiempo requieren soporte documental y no acreditan rendimiento humano. El bloqueo de escrituras es global y los históricos grandes requieren optimización. La interfaz apunta a localhost; configurar HTTPS y controles de exposición antes de un despliegue externo.

.env y __pycache__ permanecen fuera del índice; .env.example contiene únicamente campos secretos vacíos y el ancho de ventana. Se retiró del ejemplo un valor con apariencia de secreto JWT. Si se utilizó o compartió, debe rotarse: retirarlo del commit actual no elimina su exposición anterior. No se modificaron .env ni contraseñas existentes.

El estado actual está en este README, [la antología](docs/ANTologia_implementacion.md) y [seguridad/rendimiento](docs/SEGURIDAD_Y_RENDIMIENTO.md). Los documentos anteriores conservan especificaciones y resultados históricos; las reglas actuales de paginación, límites, revisión de acciones y reevaluación explícita prevalecen sobre contratos anteriores.
