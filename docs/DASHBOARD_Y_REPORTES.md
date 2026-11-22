# Iteración 08 — Dashboard analítico y reportes verificables

## Arquitectura y alcance

Se inspeccionaron modelos, main.py, ingestión, riesgo, lifecycle, métricas, evaluación/ML, pruebas y migraciones 0001–0007 antes de modificar el proyecto. Se conservan FastAPI, SQLAlchemy, PostgreSQL, Alembic, JWT/RBAC y React/TypeScript. No se reconstruye la aplicación ni se activa ML en el flujo operativo.

`analytics.py` define una cohorte SQL compartida mediante CTE. `analytics_api.py` aplica autorización, instantáneas de lectura, paginación y límites; `analytical_reports.py` renderiza CSV/JSON/PDF. React usa Recharts 3.11.0, compatible con React 18, y tablas accesibles alternativas. ReportLab 5.1.0 genera PDF con encabezado, fecha, filtros, resumen, distribuciones, incidentes, tendencias, metodología y limitaciones. Vite separa los bundles de gráficas/estado/vendor para evitar la advertencia inicial de más de 500 kB.

Las consultas nuevas agregan con COUNT, GROUP BY, MIN, AVG, EXISTS y ROW_NUMBER en SQL. No instancian todos los incidentes/eventos como objetos ORM ni recorren relaciones por cada fila. Los indicadores, gráficas y primera página se devuelven desde una única instantánea de base de datos. Las páginas posteriores son lecturas nuevas del estado actual. Los endpoints operativos anteriores conservan sus rutas; la nueva interfaz sustituye el listado completo por paginación analítica, manteniendo el detalle y las funcionalidades de importación, evidencia, experimentos y ML.

## Cohorte y filtros

Periodo UTC **[start,end)**: inicio incluido, fin excluido; fechas ISO 8601 con zona obligatoria. Los offsets se convierten a UTC antes de consultar. Si falta end se usa la fecha de consulta; si falta start se usan 30 días anteriores a end. El intervalo debe ser positivo y como máximo de 366 días. La respuesta devuelve los límites resueltos para repetir la consulta. La UI presenta y recibe UTC explícito, sin convertir silenciosamente a hora local; los controles datetime-local están rotulados UTC.

Filtros combinables exactos: priority (cuatro clases), event_type (incluye taxonomía, desconocido y valores heredados), status (seis estados), assignee (UUID o unassigned) y source (fuente exacta). No se interpreta source como certificado de origen IDS, sintético o real. Los valores son parámetros SQL, nunca fragmentos SQL. Se rechazan parámetros extra, texto NUL, fechas sin zona, intervalos inválidos y límites fuera de rango.

| time_basis | Selección de incidentes | Eventos contados | Día del incidente en tendencia |
|---|---|---|---|
| incident_created (predeterminado) | created_at en periodo; si hay source, debe existir un evento de esa fuente | Todos los eventos asociados que cumplan source, aunque su timestamp sea de otro periodo | created_at |
| event_timestamp | Debe tener al menos un evento con event_timestamp en periodo y source coincidente | Solo esos eventos coincidentes | Menor event_timestamp coincidente |
| received_at | Debe tener al menos un evento recibido en periodo y source coincidente | Solo esos eventos coincidentes | Menor received_at coincidente |

Prioridad, tipo, estado y responsable se aplican al incidente en los tres casos. Cada incidente se cuenta una vez, incluso si tiene eventos de varias fechas/fuentes. En eje creación, la gráfica de eventos atribuye sus eventos a la fecha del incidente; en los otros ejes, cada evento usa su propio timestamp. Así se mantienen sumas consistentes sin poner puntos fuera del periodo seleccionado. No se confunde esa atribución con una observación de detección.

Los estados, prioridades y responsables son los **actuales**, no los que tenía el incidente al final del intervalo. Los filtros seleccionan una cohorte, no recortan artificialmente las duraciones: una respuesta posterior al periodo sigue perteneciendo a un caso seleccionado. Para un análisis histórico inmutable se conserva un snapshot del resultado obtenido; no se promete reconstruir el pasado desde las tablas actuales.

Todos los indicadores, distribuciones, tablas, tendencias operativas y exportaciones usan estas reglas. Una creación de reporte consulta nuevamente con los mismos filtros: si hubo escrituras entre la vista y la creación, puede reflejar un estado más reciente. La fecha del snapshot identifica esa lectura.

## Catálogo y fórmulas

Sea C la cohorte de incidentes únicos y E los eventos deduplicados coincidentes asociados a C.

| Indicador | Definición / denominador | Unidad |
|---|---|---|
| incidents, events | \|C\|, \|E\| | incidentes, eventos |
| Prioridades | COUNT de cada prioridad persistida, incluidas categorías heredadas si existen | incidentes; denominador \|C\| |
| Tipos / estados | COUNT por tipo/estado actual | incidentes; denominador \|C\| |
| Fuentes | COUNT por source de E | eventos; denominador \|E\| |
| assigned / unassigned | Responsable no nulo / nulo, incluido responsable histórico de Cerrado | incidentes |
| open | Estado distinto de Resuelto y Cerrado | incidentes |
| resolved / closed | Estado exactamente Resuelto / Cerrado | incidentes |
| needs_review | EXISTS señal sin reconocimiento; múltiples señales cuentan una vez | incidentes |
| critical_open | Prioridad Crítica y open | incidentes |
| urgent_unassigned | Prioridad Alta/Crítica, open y sin responsable | incidentes |
| Tendencias | Conteo diario UTC de E y de C con la atribución de la tabla anterior | eventos, incidentes por día |
| Tendencia crítica | Casos de C cuya prioridad actual es Crítica | incidentes por día, no prioridad histórica |

Invariantes comprobadas: assigned + unassigned = incidents; open + resolved + closed = incidents; suma de cada distribución de incidentes = incidents; suma de fuentes y eventos diarios = events; suma de incidentes diarios = incidents. Los días sin registros observados se muestran con cero en conteos, sin afirmar que hubo cobertura completa de un sensor. Las métricas temporales ausentes permanecen null, nunca cero.

### Tiempos auditables

Se reutilizan las definiciones de 07, con agregación SQL equivalente:

- Hasta asignación = primera asignación no nula registrada − lifecycle_started_at.
- Hasta respuesta = primera transición registrada a En respuesta − lifecycle_started_at.
- Hasta resolución = primera transición registrada a Resuelto − lifecycle_started_at.
- MTTD documental = detected_at − occurred_at.
- MTTR documental = response_completed_at − detected_at; no cierre administrativo ni tiempo activo humano.

Para MTTD/MTTR se usa únicamente la última instantánea de evidencia del ciclo actual con source_kind=operational. Una nueva instantánea sintética/laboratorio/incompleta no se completa mezclándola con documentos previos. Se requieren pares no negativos y documentación revisada por administrador; el software no autentica físicamente ese soporte. Los casos heredados sin baseline no reciben marcas inventadas.

Para cada media: valid es el número de pares válidos; total=|C|. Se calcula suma de intervalos/|C| solo si |C|>0 y valid=total; de lo contrario value=null, status=No calculable y motivo. No se ocultan casos incompletos promediando un subconjunto. SQLite usa julianday y puede diferir en microsegundos por coma flotante; PostgreSQL usa EXTRACT EPOCH. La UI limita la precisión visual. Estas cifras describen registros/documentos, sin demostrar rendimiento de personas o mejoras causales.

## Comparaciones experimentales y separación de ámbitos

La comparación presenta **solo métricas ya guardadas en ml_runs**: weighted-v2, LogisticRegression y RandomForest, con exactitud, macro-F1, cobertura crítica, soporte y presupuesto del mismo test reservado. No abre artefactos, no entrena ni recalcula predicciones. Se conserva data_kind del dataset (synthetic/controlled/real), versión de protocolo y UUID/fecha de ejecución. Un resultado insuficiente aparece como No calculable, no como cero.

Los experimentos tienen poblaciones congeladas que frecuentemente no están vinculadas a incidentes operativos. Aplicar filtros de fuente/responsable/estado a sus métricas agregadas produciría una comparación falsa. Por eso se muestran en un apartado **independiente**, con selector/paginación de ejecuciones, fuera de los indicadores y reportes operativos. Los filtros operativos no se aplican a ese archivo experimental ni al archivo de snapshots históricos. No se presenta ese apartado como una gráfica filtrada de C.

Se conserva el cegamiento de 05/06: las comparaciones contra referencias son exclusivas del administrador investigador; analista/observador no reciben ni métricas experimentales ni etiquetas. El endpoint devuelve una lista permitida de agregados, sin referencias, predicciones por caso, coeficientes ni artefactos. Los reportes experimentales completos siguen en sus endpoints previos restringidos. Synthetic se rotula como datos sintéticos; un dataset declarado real sigue siendo evaluación offline, sin afirmar eficacia operacional o superioridad estadística.

## Endpoints y límites

| Método y ruta | Acceso | Contrato |
|---|---|---|
| GET /api/analytics/dashboard | Autenticado | Filtros, indicadores, tendencias, medias, metodología, limitaciones y página de incidentes en una misma instantánea |
| GET /api/analytics/incidents | Autenticado | Mismos filtros; offset 0–100000, limit 1–100, orden created_at descendente y UUID ascendente |
| GET /api/analytics/options | Autenticado | Fuentes/responsables elegibles o actualmente asignados, offset y limit hasta 100; flags de más resultados; sin hashes ni listado general de observadores |
| POST /api/analytics/reports | Admin/analista | Cuerpo con filtros; captura completa e inmutable; devuelve UUID, fecha y SHA-256 |
| GET /api/analytics/reports | Autenticado | Archivo de snapshots, paginado hasta 100; sin payload ni autor personal |
| GET /api/analytics/reports/{id}?format=json/csv/pdf | Autenticado | Descarga de snapshot saneado; no vuelve a consultar incidentes |
| GET /api/analytics/comparisons | Administrador | Archivo de resultados ML registrados, offset y limit máximo 20 |
| POST /api/incidents/{id}/reevaluate | Responsable analista/admin | Justificación y expected_revision; condiciones de reapertura y señales |
| POST /api/incidents/{id}/actions | Escritor conforme a responsabilidad/estado | Ahora también exige expected_revision |

Cada distribución admite hasta 200 categorías. Si se supera devuelve 422 para estrechar filtros, sin truncar conteos. El reporte admite máximo 2000 incidentes y 5 MiB de payload; devuelve 413 antes de guardar si supera el límite, sin exportar solo la página actual. El periodo limita el número de puntos diarios a 367 como máximo por límites parciales. Las opciones están paginadas; la UI sugiere los primeros 100, y permite escribir fuentes exactas.

Se mantienen GET /api/incidents, /api/stats y /api/operations/metrics por compatibilidad. Los nuevos paneles usan los endpoints SQL acotados. El endpoint histórico de operaciones sigue representando la cohorte global, no los filtros nuevos.

## Snapshots, exportaciones y verificación

analytics_reports guarda UUID, autor autenticado (FK interna), fecha UTC, payload saneado y SHA-256. La captura usa el bloqueo común con las escrituras operativas; el resultado congelado permanece igual después de cambiar incidentes. Las lecturas analíticas usan REPEATABLE READ en PostgreSQL y BEGIN en SQLite. No hay edición o borrado de snapshots por API.

El JSON contiene payload y content_sha256. Hash: SHA256 de JSON UTF-8 con claves ordenadas, ensure_ascii=True, separadores `,`/`:`, sin NaN. El generador/fecha/UUID y filtros se guardan en el payload. CSV incluye metadata, indicadores, distribuciones, tendencias, métricas con status/motivo e incidentes; se neutralizan celdas que puedan ejecutarse como fórmulas. PDF usa los mismos valores y fecha de snapshot, tablas paginadas y metodología; el modo invariant evita variación accidental del identificador/metadatos PDF entre descargas con la misma versión. La fecha real del snapshot está impresa en el contenido.

Se excluyen IP, mensajes, eventos originales, tokens, contraseñas/hashes, referencias de evaluación, modelos y nombres de usuarios. El filtro de responsable puede conservar su UUID para reproducibilidad; no su nombre. Los UUID de incidentes permiten consultar la procedencia con permisos, pero el snapshot no copia todos los eventos. Las exportaciones usan Cache-Control: no-store; CORS expone Content-Disposition y X-Content-SHA256 para descargas locales con nombre correcto.

Verificación fuera de línea, solo biblioteca estándar Python:

```powershell
.venv\Scripts\python backend/app/verify_report.py docs/resultados/iter08_reporte_sintetico.json
```

El hash detecta corrupción respecto al checksum guardado. No es firma digital, certificación de la fuente, prueba contra un administrador de BD que reescriba payload y checksum, ni cadena de custodia completa. Repetir una consulta sobre datos vivos puede producir otro resultado; para reproducir una publicación se distribuye el snapshot guardado y se registra la versión del código/dependencias.

El esquema de eventos anterior no certifica origen operacional/sintético; el reporte lo identifica como unverified. No se deduce «real» por usar Suricata ni por el nombre source. Los reportes del ejemplo son explícitamente **sintéticos**, conforme a su generación controlada descrita abajo, sin atribución a capturas IDS o personas.

## Reevaluación explícita y concurrencia

Un evento nuevo correlacionado con Cerrado conserva evidencia, estado, riesgo y evaluación anterior, como en 07. Genera señal de revisión. Desde 08, al reabrir se conserva el riesgo también durante futuras importaciones mientras alguna señal de cierre no haya sido cubierta por una reevaluación explícita. Así una importación en un caso reabierto no incorpora silenciosamente la evidencia retenida al score.

Procedimiento:

1. Administrador asigna un responsable activo si es necesario y reabre Cerrado a En análisis con revisión/justificación.
2. Responsable analista o administrador consulta la revisión vigente.
3. Envía POST /api/incidents/{id}/reevaluate con expected_revision y justification.
4. El servicio exige estado En análisis/En respuesta, responsable elegible, reapertura registrada de Cerrado y señales aún no cubiertas.
5. Reutiliza exclusivamente incident.risk_parameters congelados, carga el conjunto actual de eventos y llama al evaluador existente weighted-v1/v2. No modifica parámetros, fórmula, ML ni evaluaciones previas.
6. En una transacción anexa RiskEvaluation, auditoría con autor/UTC/motivo/revisión previa y resultante/ciclo/UUID de eventos y señales/parámetros, y enlaces únicos señal-reevaluación. Actualiza únicamente la vista actual del riesgo e incrementa revision.

Sin parámetros heredados compatibles devuelve 409; no inventa una configuración. Sin nuevas señales devuelve 409. Reconocer una señal y reevaluar son operaciones independientes: reevaluar no borra ni reconoce automáticamente señales; reconocer no recalcula riesgo. Las importaciones normales sin evidencia de cierre pendiente siguen con su comportamiento de riesgo previo.

Todas las nuevas acciones, incluso comentarios, ahora requieren expected_revision: 428 si falta, 409 si es obsoleta. No se reintenta sobrescribiendo una revisión nueva. Se mantienen categorías, fechas y restricciones de responsabilidad/estado de 07. Se registran autor real y fecha de servidor; no hay actualización/eliminación de historial ni ejecución de comandos de red.

Reevaluación, acciones, transiciones, asignaciones e importación comparten el bloqueo transaccional y la revisión monotónica. Dos solicitudes con la misma revisión tienen un ganador y un 409, con rollback de la otra; no duplican evaluación ni acción. El timeline incorpora la auditoría de reevaluación. Este protocolo requiere que las escrituras usen la API; no protege frente a SQL directo que lo omita.

## Migración 0008 y archivos

0008 depende de 0007 y solo crea analytics_reports, risk_reassessments y risk_reassessment_signals, con FKs/índices y unicidad por señal/evaluación. Añade índices de incidents.created_at y events.received_at. No cambia columnas, estados, usuarios, contraseñas, eventos, evidencias, evaluaciones o modelos existentes. Las migraciones anteriores se conservan. Downgrade destructivo deshabilitado.

Respaldar la instalación y detener escrituras antes de `alembic upgrade head`. Compose ejecuta la actualización antes de Uvicorn. Se corrigió su CMD para usar `exec uvicorn`, con el fin de recibir SIGTERM directamente y resolver la parada forzada observada en 07. No se ejecutó esta entrega sobre la BD de los servicios originales del usuario; la validación usa esquemas/contenedores propios.

Nuevos: analytics.py, analytics_api.py, analytical_reports.py, risk_audit.py, reassessment.py, verify_report.py; migración 0008; test_analytics.py; AnalyticsDashboard.tsx y vite.config.ts; este documento y ejemplos en docs/resultados. Modificados: models.py, main.py, ingestion.py, lifecycle.py/lifecycle_api.py, Dockerfile/requirements backend; expectativas de pruebas históricas para head/acciones; main.tsx, IncidentLifecycle.tsx, style.css, package.json/package-lock.json; README, antología y nota de continuidad en documento 07.

## Evidencias y procedimiento académico reproducible

Los archivos `docs/resultados/iter08_reporte_sintetico.json`, `.csv`, `.pdf` y `iter08_verificacion_api.json` se obtuvieron realmente por HTTP contra Compose aislado. No son capturas de navegador ni mediciones de operadores. El JSON canónico fue verificado con el CLI incluido.

Fixture de generación: seis eventos, uno por tipo de la taxonomía, fecha 2026-01-01T12:00:00Z, source=iter08-synthetic-example, origen/destino de documentación 192.0.2.1/192.0.2.100, severidad y criticidad respectivamente 10,30,50,70,85,100; texto marca SYNTHETIC DEMONSTRATION ONLY. El evento de exfiltración se asignó, pasó por análisis/respuesta, registró contención textual, se resolvió y cerró. Una segunda aparición distinta conservó score **83** durante cierre; tras reapertura y reevaluación explícita pasó a **86**, anexando una evaluación sin modificar las previas. Un intento de acción con revisión obsoleta devolvió **409**.

Filtro del reporte: [2026-01-01T00:00Z,2026-01-02T00:00Z), eje event_timestamp y fuente exacta. Resultado observado: **6 incidentes, 7 eventos, 1 asignado, 5 sin responsable, 6 abiertos, 1 crítico abierto, 1 pendiente de revisión**. Reevaluación y reconocimiento son separados, por eso subsiste la señal. MTTD/MTTR: **No calculable**, sin soporte operacional. Estos números prueban el flujo y la consistencia, no rendimiento de detección.

Para obtener capturas propias reproducibles:

1. En una instalación de laboratorio autorizada y con respaldo, actualizar a 0008 y abrir el frontend en localhost:5173 contra API localhost:8000. No cambiar contraseñas de volúmenes existentes.
2. Importar el ejemplo EVE sintético de seis tipos o generar el fixture anterior como SmartIR JSON. Marcar en el pie de cada figura «Datos sintéticos de laboratorio» y conservar el archivo original. El ejemplo EVE tiene sus propias fechas/valores; no atribuirle los números del fixture HTTP anterior.
3. Aplicar periodo, eje temporal y fuente; expandir filtros/denominadores, tablas accesibles y limitaciones. Capturar dashboard y filtros juntos; registrar versión Git, UTC y rol. No capturar login, tokens ni documentación con Bearer visible.
4. Guardar snapshot como escritor y descargar los tres formatos. Verificar SHA-256 y conservar UUID/JSON con la figura. Un observador solo consulta/descarga snapshots ya guardados.
5. Para la gráfica de modelos, entrar como administrador investigador y seleccionar una ejecución ya registrada. Capturar UUID, data_kind y soporte/presupuesto. Si no existe ninguna, capturar «No hay resultados registrados», sin inventar barras o entrenar para simular un resultado existente.
6. Guardar las imágenes obtenidas con nombres/leyendas que incluyan la procedencia y el snapshot. Esta entrega proporciona instrucciones; no afirma haber generado capturas de navegador.

## Validación comprobada

Desde la raíz, PowerShell, con dependencias de requirements-dev.txt instaladas:

```powershell
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter08-release-sqlite --junitxml=.test-runs/iter08-release-sqlite.xml
Push-Location frontend
npm ci
npm run build
Pop-Location
```

Suite final SQLite: **106 passed, 1 warning in 68.78s**. La ejecución completa anterior de 105 pruebas dio **105 passed, 1 warning in 93.35s**. PostgreSQL 16 temporal, loopback y almacenamiento de prueba, sin usar BD existentes:

```powershell
docker run --detach --rm --name smartir-iter08-test --tmpfs /var/lib/postgresql/data -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55438:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55438/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter08-release-pg --junitxml=.test-runs/iter08-release-pg.xml
docker stop smartir-iter08-test
```

La primera suite completa PostgreSQL aprobó **105 passed, 1 warning in 407.87s**. La ejecución final, con el verificador offline y los ajustes de autorización/CORS, obtuvo **106 passed, 1 warning in 383.11s**. La advertencia común procede de BlockingPortal de Starlette/AnyIO, no de una prueba fallida. El ajuste final de privacidad del selector de responsables (sin listado general de observadores) se verificó además con **1 passed in 1.14s** SQLite y **1 passed in 5.75s** PostgreSQL. La preservación de tablas con metadata de índices alineada se repitió en SQLite: **1 passed in 0.71s**.

Cobertura nueva: agregaciones y sumas de denominadores, filtros combinados, tres ejes y offsets UTC, exclusión del extremo final, paginación determinista, ausencia de N+1 (mismo número de consultas al cambiar tamaño de página), cohortes vacías, validación de fechas/parámetros, RBAC, límites de exportación y SQL parametrizado. Se verifican snapshots inmutables, SHA-256/tamper, saneamiento, CSV/PDF, PDF repetible, exclusión de datos de autenticación/personales, evidencia no operacional sin cero artificial y visor experimental reservado. También reevaluación con parámetros congelados, preservación de evaluaciones previas, responsabilidad, importación posterior a reapertura sin recálculo silencioso, parámetros heredados desconocidos, carreras de reevaluaciones/acciones y migración desde 0007 comparando las filas de todas las tablas previas. La suite conserva las pruebas anteriores de autenticación, importación, correlación, riesgo, experimentos, ML y ciclo de vida.

`npm run build` final: TypeScript correcto, Vite **6.4.6**, **441 módulos**, **8.61s**, sin advertencia de chunks grandes tras separación (charts 437.62 kB, vendor 179.94 kB; tamaños sin gzip). Se ejecutaron npm install y npm ci (este último en build Docker); el proyecto conserva el lockfile.

Compose aislado se construyó y arrancó con proyecto `smartir-iter08`, volumen propio y override de puertos 58008/55178. Se observaron tres servicios arriba, PostgreSQL healthy, /health correcto, web HTTP **200** y `alembic current`: **0008 (head)**. La comprobación fue HTTP directa; no se afirma navegación con la URL API fija del frontend en esos puertos alternativos. Se verificó el mismo hash del reporte guardado después de recrear la API. Al detener el proyecto, **API exit=0, OOMKilled=false; PostgreSQL exit=0**: el uso de exec resolvió en esta comprobación la parada forzada de 07. Se conservó `smartir-iter08_postgres_data`; los servicios originales `smartir-net-mvp` continuaron arriba y no se modificaron. El contenedor PostgreSQL de pytest se detuvo al finalizar las pruebas, sin eliminar volúmenes existentes.

Fallos comprobados y corregidos:

- La primera selección de pruebas obtuvo **45 aprobadas/1 fallo en 41.33s**: una comprobación confundía el nombre del filtro assignee con un nombre personal exportado. Se corrigió para comprobar las filas y la ausencia de datos personales reales.
- La prueba dirigida siguiente detectó PDF no idénticos al repetir descarga. Se configuró invariant en SimpleDocTemplate (su valor sobrescribía el canvas parcial); la prueba pasó después: **1 passed in 1.69s**.
- La primera selección PostgreSQL obtuvo **14 aprobadas/7 fallos en 115.89s** por expresiones UTC construidas por separado en SELECT/GROUP BY con parámetros diferentes. Se reutilizó una expresión por eje; los tres casos dirigidos pasaron: **3 passed in 17.30s**, antes de las suites completas correctas.
- El primer build local fue impedido por EPERM al resolver la ruta de Node en el sandbox; se ejecutó con los permisos locales adecuados. El primer build correcto mostró chunk de 696.89 kB; la configuración de bundles eliminó esa advertencia.
- El primer intento del script HTTP transportó acentos como `?` por la tubería PowerShell y obtuvo 422, y el lanzamiento desde /tmp necesitó PYTHONPATH=/app. Se corrigió ejecutando el archivo UTF-8 en el contenedor con su ruta de módulos, conservando los registros de prueba y sin cambiar contraseñas.

No se presentaron estos intentos fallidos como éxitos ni se atribuyeron las cifras de fixtures a operadores humanos. No quedan fallos funcionales conocidos en las comprobaciones completadas.

## Limitaciones y despliegue

Despliegue local: los puertos de Compose se enlazan a 127.0.0.1, la API/URL del frontend y CORS conservan 8000/5173. Los puertos alternativos de pruebas sirven para comprobación HTTP aislada; no equivalen a una prueba integral de navegador. Se mantienen las limitaciones previas de JWT, autenticación y despliegue sin HTTPS público. No se tocó .env ni credenciales existentes.

No hay captura IDS real, prueba con operadores, inferencia causal, significancia estadística, validación de scoring/ML en producción o detección de cobertura de sensores. No se hizo benchmark de grandes históricos, multiproceso bajo carga ni revisión visual automática de PDF/navegador. El bloqueo global puede limitar concurrencia; el renderizado/exportación tiene límites de tamaño pero no cuotas de frecuencia o retención automática. Los snapshots consumen almacenamiento y requieren política administrativa posterior. Las ventanas fijas conservan sus limitaciones de 03/04. Datos históricos incompletos permanecen incompletos. Las comparaciones congeladas y los snapshots guardados tienen ámbitos propios, claramente separados del filtro operativo vivo.
