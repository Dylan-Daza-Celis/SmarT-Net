# Iteración 07: gestión avanzada del ciclo de vida

Nota de continuidad: este documento conserva la especificación y resultados comprobados de 07. Desde 08, las nuevas acciones también requieren expected_revision y la evidencia recibida durante cierre exige reevaluación explícita después de reabrir; esas reglas sustituyen la compatibilidad sin revisión y el recálculo por importación descritos aquí. Véase [DASHBOARD_Y_REPORTES.md](DASHBOARD_Y_REPORTES.md). No se borran resultados históricos.

## Alcance y arquitectura inspeccionada

Se inspeccionaron main.py, models.py, ingestion.py, endpoints de acciones/usuarios, esquemas, migraciones y pruebas. Antes de esta iteración, Asignado no tenía responsable y cualquier escritor podía saltar entre los seis estados. La nueva política `lifecycle-v1` se aplica en backend, sin sustituir FastAPI, PostgreSQL, SQLAlchemy, Alembic, JWT/RBAC o React/TypeScript.

Se conservan usuarios, eventos, evidencias EVE, fingerprints, ventanas, risk_evaluations, experimentos y modelos ML. No se modifica el motor weighted ni se activan modelos supervisados en operación. Las acciones siguen siendo texto y metadata: no ejecutan comandos de red.

## Responsabilidades y permisos

| Operación | Administrador | Analista | Observador |
|---|---|---|---|
| Consultar incidentes, responsables, historial, métricas y timeline | Sí | Sí | Sí |
| Asignar/reasignar a escritor activo | Cualquier caso | Tomar para sí si no hay responsable; transferir un caso propio | No |
| Retirar asignación | Desde Asignado; también administración de Cerrado | Caso propio en Asignado | No |
| Cambiar estado | Con máquina y responsable elegible | Solo caso propio | No |
| Reabrir Resuelto a En análisis | Sí | Caso propio | No |
| Reabrir Cerrado a En análisis | Sí | No | No |
| Registrar comentario | Sí | Sí, también en casos ajenos/cerrados | No |
| Registrar acción de respuesta tipificada | Con estado compatible y responsable válido | Caso propio y estado compatible | No |
| Revisar evidencia de tiempos | Solo administrador | No | No |
| Reconocer señal de revisión | Sí | Responsable actual | No |

Un responsable nuevo debe existir, estar activo y tener rol administrador o analista. Los usuarios observadores e inactivos no son elegibles. GET /api/assignees devuelve únicamente id, username y rol de los elegibles; no expone hashes ni cambia la administración de usuarios existente.

Desactivar o degradar a observador a alguien con incidentes no cerrados asignados devuelve 409: primero reasignar o retirar según la máquina. Los responsables de casos Cerrados pueden desactivarse y permanecen como responsables históricos. Antes de reabrir hay que conservar o asignar un responsable activo. Un administrador puede corregir/reasignar o retirar el responsable de un Cerrado sin reabrirlo; se registra y no cambia el estado ni el riesgo.

Todos los autores provienen del usuario autenticado; no se aceptan author_id ni created_at del cliente en escrituras de asignación, estado o comentarios. Tras adquirir el bloqueo se vuelve a comprobar el usuario activo y su rol para evitar usar una autorización obsoleta mientras esperaba.

## Máquina de estados

| Estado actual | Destinos por PATCH /status |
|---|---|
| Nuevo | Ninguno: la asignación inicial lo mueve a Asignado |
| Asignado | En análisis |
| En análisis | En respuesta; Asignado (devolución a triage) |
| En respuesta | Resuelto; En análisis (reinvestigación) |
| Resuelto | Cerrado; En análisis (reapertura) |
| Cerrado | En análisis (reapertura solo administrador) |

Cada escritura exige justificación no vacía y revisión vigente. Las transiciones requieren un responsable elegible. Asignar un Nuevo crea **asignación y cambio a Asignado en la misma transacción**. Retirar desde Asignado crea asignación a null y transición a Nuevo, también atómicas. En trabajo activo, retirar directamente devuelve 409: volver primero a Asignado con las transiciones y justificaciones correspondientes o reasignar directamente a otro escritor activo.

Una reapertura Resuelto/Cerrado → En análisis incrementa cycle_number; Resuelto → Cerrado no crea otro ciclo. Los retrocesos de análisis/respuesta permanecen en el mismo ciclo. El autor, estado previo/nuevo, fecha y razón se anexan a incident_history con policy_version y ciclo. No hay edición ni eliminación de esos registros por API.

## Compatibilidad y revisión optimista

Se conserva PATCH /api/incidents/{id}/status, pero ahora debe incluir expected_revision además de status y justification. Es un cambio necesario y deliberado: sin revisión se devuelve **428**, con revisión obsoleta **409**, y con transición incompatible **409**. Un recurso inexistente devuelve 404 y un rol no autorizado 403; un observador no puede eludir la política enviando otro responsable o autor.

Ejemplo de cuerpo tras consultar la revisión actual:

```json
{"status":"En análisis","justification":"Triage completado y responsable confirmado","expected_revision":3}
```

Asignación usa PATCH /api/incidents/{id}/assignment:

```json
{"assigned_to_id":"UUID_DEL_USUARIO_ACTIVO","justification":"Responsable de turno confirmado","expected_revision":2}
```

Retirar usa assigned_to_id=null. Cadena vacía no equivale a retirar y se rechaza. Después de un conflicto se consulta de nuevo el detalle y se decide la operación; no se reintenta sobrescribiendo automáticamente. Los IDs de usuario son valores reales de /api/assignees; el ejemplo anterior es un marcador explicativo.

El detalle/listado agrega assigned_to_id, assignee, revision, needs_review y lifecycle_legacy sin quitar campos anteriores. GET /history y GET/POST /actions conservan sus rutas. POST /actions con solo description sigue siendo válido y se interpreta como comentario, sin atribuirle una ejecución real. Las validaciones rechazan texto NUL/Unicode no representable y propiedades extra.

## Concurrencia e integridad

Todas las asignaciones, transiciones, acciones, evidencias, reconocimientos, cambios de rol/activación e importaciones comparten el mismo bloqueo asesor transaccional PostgreSQL `739031503`. Los incidentes también se seleccionan con FOR UPDATE al modificar estado/asignación. SQLite usa BEGIN IMMEDIATE. Revision es monotónica por incidente y se comprueba dentro del bloqueo.

Una importación con eventos nuevos incrementa la revisión una vez por incidente afectado y lote, incluso si el caso está cerrado. Duplicados no cambian esa revisión ni crean señales. Comentarios/acciones son anexos transaccionales y mantienen el cuerpo compatible sin revisión obligatoria; incrementan la revisión para invalidar detalles anteriores. Asignaciones, estados, evidencia temporal y reconocimientos sí exigen la revisión vigente.

Dos cambios simultáneos con la misma revisión tienen un ganador y un 409; no se pierde historial. Asignar frente a desactivar se serializa: o la asignación rechaza al usuario inactivo, o la desactivación exige reasignar. Cerrar frente a importar se serializa: si gana cierre, el evento genera revisión sin recalcular; si gana importación, el cierre del detalle obsoleto devuelve 409.

Las lecturas de detalle/listado y del módulo de métricas/timeline usan una instantánea de lectura (REPEATABLE READ transaccional en PostgreSQL, BEGIN en SQLite) para no mezclar filas de distintas versiones dentro de una respuesta. Distintas peticiones del navegador pueden ver revisiones diferentes; la interfaz bloquea la escritura hasta recargar si sus vistas discrepan. La revisión en backend sigue siendo la autoridad.

El bloqueo global reduce paralelismo y no sustituye control de escrituras externas. No se prometen invariantes frente a SQL directo que omita este protocolo. Las claves foráneas e índices protegen relaciones; la elegibilidad por rol/actividad se impone en el servicio. No se realizaron pruebas de carga ni multiproceso; sí carreras entre peticiones concurrentes y sesiones de base de datos separadas.

## Timestamps, ciclos y datos heredados

Nuevos incidentes tienen lifecycle_started_at igual a su registro de creación en la importación, ciclo 1 e historial Nuevo de lifecycle-v1. El timestamp es UTC del servidor. No representa ocurrencia del ataque ni detección IDS.

GET /lifecycle devuelve first_recorded y latest_recorded de asignación, análisis, respuesta, resolución y cierre. Se derivan de registros inmutables; reasignaciones, retrocesos y reaperturas no borran primeras ocurrencias registradas. Las fechas se entregan como ISO 8601 UTC explícito. first_recorded significa la primera fecha disponible en el historial, no necesariamente la primera de toda la vida de un caso heredado.

La migración no cambia estados, asigna personas ni rellena timestamps históricos. Los incidentes existentes tienen lifecycle_started_at=null, ciclo 0 y revisión 0; lifecycle_legacy=true. El historial/acciones previos permanecen intactos con metadata nueva null. Un Asignado/En análisis/En respuesta/Resuelto heredado puede recibir un responsable sin alterar su estado; antes de la siguiente transición debe tener uno elegible. Un Cerrado heredado se administra por asignación explícita del administrador y luego reapertura explícita si corresponde.

La ausencia de baseline completo mantiene los intervalos iniciales heredados en No calculable, incluso si después se asigna alguien. Una reapertura posterior crea un ciclo conocido y permite medir sus transacciones registradas por separado. El historial anterior no se reconstruye ni se presenta como respuesta verificable.

## Fórmulas y evidencia temporal

Por incidente nuevo, intervalos iniciales en segundos:

- time_to_assignment = primera asignación registrada − lifecycle_started_at.
- time_to_response = primer ingreso registrado a En respuesta − lifecycle_started_at.
- time_to_resolution = primer ingreso registrado a Resuelto − lifecycle_started_at.

Los current_cycle_metrics usan el baseline de creación para el ciclo inicial o el ingreso explícito de reapertura para ciclos posteriores. Si el responsable se conserva desde un ciclo anterior, no se inventa una nueva asignación con duración cero. Faltas de baseline/transición u orden negativo producen value=null, status=No calculable y razón. Los timestamps de últimas transiciones están disponibles aparte; no se sustituyen silenciosamente por las primeras.

**received_at, event_timestamp y created_at no se convierten en detected_at ni occurred_at.** Tampoco Resuelto/Cerrado o una acción textual prueban por sí solos finalización de respuesta. Para MTTD/MTTR se anexa una instantánea documental, exclusiva del administrador:

POST /api/incidents/{id}/time-evidence, con revisión, source_kind (operational/laboratory/synthetic), evidence_reference, review_note y las marcas disponibles occurred_at, detected_at, response_completed_at. Al menos una marca es obligatoria; fechas con zona, no futuras y orden cronológico. Se almacena quién revisó, cuándo y a qué ciclo corresponde. Cada nueva instantánea se anexa; no edita la anterior. La última instantánea del ciclo actual es la vigente, con todos sus campos, sin mezclar marcas de diferentes documentos/versiones.

Solo source_kind=operational permite calcular pares documentados; laboratory/synthetic quedan en No calculable para estas métricas operativas. El administrador debe haber revisado el soporte indicado. El software conserva la declaración y la referencia para auditoría: **no descarga ni autentica automáticamente documentos ni garantiza su veracidad**. La calidad y verificabilidad física dependen de ese soporte; no se presentaron soportes reales en esta entrega.

- Intervalo de detección: detected_at − occurred_at.
- Intervalo de respuesta: response_completed_at − detected_at. Esta definición de MTTR es finalización de respuesta desde detección, no cierre administrativo, reparación total ni tiempo activo de una persona.

En detalle, mttd/mttr representan esos intervalos de un caso; GET /api/operations/metrics calcula sus medias sobre la cohorte completa. Cada media devuelve valid/total y solo se calcula si todos los casos tienen el par válido; sin casos o con datos incompletos se devuelve No calculable. No se oculta un subconjunto conveniente ni se reemplaza información ausente por cero. Las medias iniciales usan la primera transición; MTTD/MTTR usan evidencia del ciclo actual de cada caso. Los filtros de la tabla de React no alteran esa cohorte global.

Estos valores describen transacciones registradas o fuentes documentales, no un experimento causal ni rendimiento de operadores humanos. No se inventan mejoras de tiempo. Se necesitan relojes sincronizados y evidencia fiable antes de interpretar resultados operativos reales.

## Acciones y timeline

Nuevas acciones incluyen category, performed_at, date_basis, autor, descripción y created_at. Categorías: comentario, contencion, erradicacion, recuperacion y verificacion. Contención/erradicación/recuperación exigen En respuesta; verificación permite En respuesta o Resuelto; todas estas exigen responsable activo y autor responsable/admin. Un comentario sigue permitido a cualquier escritor en cualquier estado para mantener seguimiento y compatibilidad.

Si no se proporciona performed_at, se usa la fecha de registro con date_basis=recorded_at; si se proporciona una fecha UTC no futura, date_basis=declared. Una declaración no se trata como evidencia independiente de ejecución. Las acciones anteriores conservan su fecha/texto/autor; category se presenta como legacy_unclassified y performed_at no se inventa.

GET /api/incidents/{id}/timeline combina estados, asignaciones, acciones, señales, reconocimientos y evidencia temporal con IDs y autores. Orden: fecha UTC, tipo e ID para desempates deterministas; un empate no establece causalidad adicional. La UI muestra fechas declaradas/registradas y permite inspeccionar los datos completos. No hay edición ni eliminación de registros por API; correcciones se anexan como nuevos comentarios o evidencias con justificación.

## Eventos recibidos tras cierre

La importación conserva su contrato y deduplicación. Si un evento **nuevo** correlaciona con un Cerrado, se guarda el evento y su evidencia original, se crea incident_review_signals con event_id único, autor importador, fecha y motivo, y se incrementa revisión. El estado, responsable, score, prioridad y explicación congelada permanecen; no se añade RiskEvaluation ni se modifican evaluaciones anteriores. Event_count sí refleja el nuevo registro: puede diferir del número de eventos de la evaluación conservada.

No se infiere que el instante del evento sea el instante de detección o de cierre; la señal significa recepción de evidencia nueva para un caso cerrado. Si corresponde a otra ventana temporal, el motor existente crea otro incidente, sin mezclar ventanas. Una reimportación duplicada no crea otra señal ni altera el riesgo; EVE puede seguir agregando procedencia de esa aparición duplicada.

El responsable/admin puede reconocer una señal mediante POST /api/incidents/{id}/review-signals/{signal_id}/acknowledge, con justificación y revisión. Se anexa review_acknowledgements; no se borra ni se edita la señal. Reabrir no la reconoce automáticamente. Tras reapertura tampoco se recalcula riesgo automáticamente: futuras importaciones de eventos nuevos en estado abierto podrán crear otra evaluación con todos los eventos y parámetros congelados, conservando las anteriores.

## Endpoints y frontend

Se agregan GET /api/assignees y GET /api/operations/metrics. Bajo /api/incidents/{id} se agregan PATCH /assignment, GET /lifecycle, GET /timeline, POST /time-evidence y POST /review-signals/{signal_id}/acknowledge. Status y acciones conservan sus rutas con las reglas de compatibilidad indicadas. PATCH /api/users/{user_id} agrega el bloqueo de desactivación/degradación mientras haya responsabilidad abierta.

React muestra responsable, registro UTC y señal de revisión en dashboard, con filtros combinables por responsable/estado/prioridad/tipo. El detalle incluye asignación/reasignación, transiciones permitidas, primeros/últimos timestamps, intervalos y motivos de No calculable, timeline combinado, categorías de acciones y evidencia documental revisada. Observador no ve formularios de escritura. Las restricciones de propiedad/rol se revalidan en backend aunque se envíen solicitudes manuales.

## Migración 0007 y archivos

La migración agrega a incidents responsable nullable con FK, revisión, ciclo y baseline nullable; agrega versión/ciclo a incident_history y categoría/fecha/procedencia a response_actions. Crea assignment_history, incident_review_signals, review_acknowledgements e incident_time_evidence, con FKs e índices por incidente y unicidad de evento/señal donde corresponde. No borra ni recrea tablas existentes; el FK nullable de responsable se añade inline para admitir SQLite y PostgreSQL sin reconstrucción. No cambia estados o datos históricos y no modifica tablas experimentales/ML.

Antes de actualizar: respaldo y detener escrituras; `alembic upgrade head` o arranque API existente en Compose. Mantener .env y el volumen. Downgrade destructivo deshabilitado. No se aplicó esta entrega sobre una base productiva del usuario.

Archivos nuevos: backend/app/lifecycle.py, lifecycle_api.py, operational_metrics.py; backend/migrations/versions/0007_lifecycle.py; backend/tests/test_lifecycle.py; frontend/src/IncidentLifecycle.tsx; este documento y reporte sintético en docs/resultados. Modificados: backend/app/main.py, models.py, ingestion.py; expectativas/flujo de test_api.py y comparaciones de columnas originales en test_evaluation.py/test_ml.py/test_suricata.py; frontend/src/main.tsx; README y antología. No se agregaron dependencias ni se cambió el stack.

## Validación y resultados reales

Desde la raíz, PowerShell:

```powershell
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter07-final
```

SQLite: **82 passed, 1 warning in 55.73s**. PostgreSQL 16:

```powershell
docker run --detach --rm --name smartir-iter07-test -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55437:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55437/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter07-pg
docker stop smartir-iter07-test
```

PostgreSQL: **82 passed, 1 warning in 274.65s**. El contenedor temporal y sus esquemas son de prueba; no se usaron bases existentes del usuario. La validación final de ID vacío y texto seguro en `test_preconditions_and_observer_read_only` se repitió: **1 passed in 1.53s** SQLite y **1 passed in 5.47s** PostgreSQL, con la misma advertencia. La advertencia común es la deprecación BlockingPortal de Starlette/AnyIO.

También se comprobó la respuesta final de timeline con IDs de autor y responsable (`test_assignment_reassignment_withdraw_and_real_author`): **1 passed in 1.46s** SQLite y **1 passed in 5.58s** PostgreSQL. Las fechas de incidentes/historial se normalizan a UTC explícito también al consultar SQLite.

La revisión final reforzó la conversión a UTC antes de persistir fechas declaradas, para no depender de que el dialecto conserve su offset. Las regresiones de evidencia temporal y acciones usan offsets diferentes para un mismo instante: **2 passed in 2.74s** SQLite. Después de ese ajuste se repitió el módulo completo de ciclo de vida, incluidas esas regresiones y migración: **17 passed, 1 warning in 14.24s** SQLite y **17 passed, 1 warning in 101.21s** PostgreSQL 16. No se usan estos fixtures como mediciones operativas.

Comando final: `python -m pytest backend/tests/test_lifecycle.py -q -p no:cacheprovider --basetemp .test-runs/iter07-final-utc-sqlite`; PostgreSQL usa TEST_DATABASE_URL como arriba y basetemp `.test-runs/iter07-final-utc-pg`.

Los tests incluyen RBAC, responsables elegibles, transferencia/retiro, usuarios inactivos/observadores, propiedad, transiciones/reaperturas, revisión ausente/obsoleta, tres carreras adicionales (asignación frente a asignación, transiciones simultáneas, desactivación frente a asignación) y carrera cierre/importación. Verifican primeros/últimos timestamps, ciclos, evidencia incompleta, pares sintéticos de prueba, acciones, señales idempotentes y migración desde 0006 preservando columnas originales y modelos/experimentos. Las cifras de intervalos de los fixtures controlados son comprobaciones matemáticas, no mediciones reales.

`npm run build`: TypeScript y Vite 6.4.6 correctos, 29 módulos; build Vite final **1.61 s**. No se realizaron pruebas de navegador.

Compose aislado: `docker compose -p smartir-iter07 -f compose.yaml -f .test-runs/compose-iter07.yaml up --build -d`, volumen/proyecto nuevos y puertos 58007/55177 mediante `ports: !override`. Se crearon credenciales exclusivamente para ese entorno y se reutilizaron sin cambios al actualizar la API. No se modificó .env ni contraseñas existentes. Se observaron tres servicios arriba, PostgreSQL healthy, health correcto, web HTTP 200 y Alembic **0007 (head)**. La comprobación con esos puertos alternativos fue HTTP directa; el frontend existente apunta a localhost:8000 y CORS admite el puerto 5173, por lo que no se afirma una prueba de navegación integral en ese entorno alternativo.

La comprobación HTTP sintética recorrió asignación, análisis, respuesta, acción tipificada, resolución y cierre. Se registraron seis filas de estado, una asignación y una acción; un evento recibido después produjo una señal y **mantuvo score 73 antes y después**, con estado Cerrado. MTTD/MTTR quedaron **No calculable** por falta de evidencia operacional. Reporte: [iter07_verificacion_api.json](resultados/iter07_verificacion_api.json). No representa respuesta de una persona ni mejora de tiempo.

Fallos corregidos: la regresión inicial produjo 7 fallos/58 aprobadas por pruebas del contrato previo (saltos sin revisión y head=0006); se actualizaron conservando comprobación de columnas originales. La suite ampliada obtuvo 79 aprobadas/1 fallo al detectar que Resuelto→Cerrado incrementaba el ciclo indebidamente. Se corrigió para incrementarlo solo al reabrir a En análisis y se añadieron carreras adicionales; las suites posteriores completas dieron los resultados anteriores. No quedan fallos conocidos en las comprobaciones ejecutadas.

Los servicios de prueba se detuvieron conservando el volumen `smartir-iter07_postgres_data`; no se eliminaron volúmenes existentes. PostgreSQL terminó con código 0. En `compose stop --timeout 20`, la API requirió terminación forzada (código 137, OOMKilled=false); no se ha validado una parada ordenada de Uvicorn con el CMD actual, que lo lanza mediante sh. Se registra como limitación operativa pendiente, aunque las pruebas funcionales y el arranque fueron correctos. Los resultados previos de riesgo, evaluación y ML se mantienen en sus documentos históricos.

## Limitaciones

No hay certificación automática de documentos, cadena de custodia contra administradores de base de datos, notificaciones externas, SLA, planificación de turnos o ejecución de acciones. Las fechas declaradas no son telemetría física. Los incidentes heredados pueden tener huecos imposibles de reconstruir y por eso conservan No calculable. La transición a Cerrado no demuestra por sí sola finalización verificable de respuesta.

El bloqueo global limita capacidad; no se hicieron benchmarks ni pruebas de múltiples procesos bajo carga. Los listados/timeline/medias no están paginados y pueden requerir optimización en grandes históricos. Las medias globales exigen cohorte completa y no siguen los filtros visuales. Los riesgos cerrados pueden mostrar menos eventos evaluados que evidencias actuales por diseño. Se requiere revisión explícita; no se recalculan al reconocer una señal. Permanecen los límites de autenticación y de validación científica/ML ya documentados.
