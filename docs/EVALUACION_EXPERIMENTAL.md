# Iteración 05: evaluación experimental reproducible

## Pregunta e hipótesis

Pregunta: con una cohorte idéntica de incidentes disponibles y un presupuesto igual en número de selecciones, ¿el orden SmartIR selecciona una mayor proporción de incidentes críticos de referencia que el orden cronológico de recepción?

Hipótesis direccional de ingeniería H1: cobertura_crítica(SmartIR,K) > cobertura_crítica(FIFO,K). H0 descriptiva: la diferencia no es positiva. Esta iteración permite calcular la diferencia; **no implementa una prueba de significancia, intervalos de confianza ni inferencia causal**. La evidencia sintética obtenida no respalda H1 en la muestra documentada. No se concluye superioridad estadística ni inferioridad general del modelo a partir de una semilla.

## Diseño y separación de fuentes

Cada experimento es una comparación emparejada `paired-offline-v1`, guardada con UUID, fecha UTC, autor, dataset, versiones, parámetros, órdenes y resultados. **Su ejecución siempre es simulation/offline replay**, incluso si la fuente de datos está etiquetada como real. No es una sesión de operadores humanos.

La procedencia del dataset distingue synthetic, controlled y real. Synthetic corresponde a escenarios generados. Controlled identifica datos externos declarados de un ensayo controlado; real identifica registros externos declarados de operación. La aplicación no verifica esa declaración ni convierte un replay sobre esos datos en un experimento humano. No se generaron datos controlados ni mediciones reales como evidencia de esta entrega.

Ambas estrategias usan exactamente el mismo conjunto de casos, mismos factores, versiones y presupuesto efectivo `min(K,N)`. Toda la cohorte se considera disponible al comienzo del replay, como una cola pendiente fotografiada después de su recepción; no es una simulación dinámica de arribos ni de servicio.

- FIFO: primera fecha de recepción de sus eventos, ascendente; empate por UUID de caso en orden lexicográfico.
- SmartIR: score descendente; empate por esa misma recepción ascendente y UUID.
- Costo: una selección de incidente = una unidad de atención simulada, sin duración asignada. Seleccionar no equivale a resolver, responder ni atender efectivamente un caso en producción.

No se añade una prioridad ficticia a FIFO: es una estrategia de orden, no un segundo clasificador. Exactitud/matriz/F1 evalúan las prioridades predichas por SmartIR sobre toda la cohorte y son comunes a ambos órdenes. La comparación entre estrategias se hace mediante cobertura bajo presupuesto y carga de los seleccionados. La clasificación propia de FIFO se reporta como No calculable con su motivo.

## Variables, versiones y conservación

Variable independiente: estrategia de ordenación. Variables de resultado: cobertura crítica al presupuesto, pendientes y eventos seleccionados. Variables controladas: cohorte, instantánea de factores, algoritmo de riesgo, parámetros, K y regla de desempate. Las etiquetas y desenlaces solo se utilizan después de generar ambos órdenes.

El motor de riesgo existente se invoca sin duplicar su fórmula: `weighted-v2`, pesos 35/25/15/15/10 y política de contexto desconocido. Se guardan parámetros completos, `evaluation-metrics-v1`, versiones `received-asc-id-v1` y `score-desc-received-id-v1`, versión del generador, Python y versión de aplicación. Se recalcula el modelo seleccionado sobre los factores congelados; no se sobrescriben evaluaciones operativas ni se afirma reproducir un score histórico con parámetros diferentes.

Los casos de evaluación ya representan incidentes delimitados. **No se vuelve a ejecutar correlación** durante el experimento (`correlation_applied=false`). Se conservan sus eventos y UUID, y los enlaces operativos opcionales permiten consultar el origen. Las limitaciones de ventanas fijas siguen vigentes en cualquier cohorte producida por el sistema operativo: separaciones artificiales al cruzar un límite y posible mezcla de episodios dentro de la misma ventana.

Datasets, referencias y experimentos no tienen endpoints de modificación o borrado. Cada ejecución crea un experimento nuevo; sus resultados y órdenes quedan congelados. El hash SHA-256 de características usa JSON canónico y casos ordenados por UUID; se conserva también un hash de la lista de referencias recibida, dentro de configuración privada. Este último depende del orden de esa lista de origen, sin afectar el cálculo de métricas. Las tablas no son una cadena de custodia resistente a alteraciones por un administrador de PostgreSQL.

## Protección de etiquetas

`evaluation_cases.features` contiene exclusivamente FeatureCase y FeatureEvent validados con propiedades extra prohibidas. La referencia reside en `evaluation_references`, no en los eventos, mensajes, modelo de riesgo ni endpoint operativo de importación. `rank_cases` recibe solo características y parámetros; no acepta referencia, razón de anotación ni timestamps de desenlace. Los IDs del generador dependen de semilla e índice, nunca de la clase.

Administrador actúa como investigador/curador: genera/importa datasets, ejecuta experimentos y consulta resultados contra etiquetas y exportaciones. Analista y observador consultan casos y órdenes sin referencias. Para esos roles también se ocultan semilla, hashes de referencia, relato de procedencia, nombre libre del dataset y métricas agregadas contra etiquetas. Esto impide reconstruir respuestas mediante consultas repetidas con distintos presupuestos. Los nombres visibles para operadores son pseudónimos por UUID.

Las predicciones del modelo, factores y sus órdenes sí son información disponible al operador; no son la referencia. Un investigador con acceso a etiquetas no debe participar como operador ciego. Un dataset sintético públicamente reproducible puede reconstruirse si se conoce su generador y semilla: sirve para probar el software, **no prueba cegamiento de participantes**. Un ensayo humano futuro exige corpus reservado, asignación de funciones y protocolo independiente; esta entrega no implementa ese ensayo ni atribuye resultados a personas.

## Dataset sintético y etiquetas independientes

Generador `synthetic-scenarios-v1`, semilla predeterminada **202605**, 60 casos (configurable entre 6 y 500). Representa cíclicamente los seis tipos de la taxonomía; cada caso tiene 1–5 eventos, IDs UUID5 estables, fechas con zona, recepción, severidad y criticidad enteras. Dos flujos PRNG independientes producen características y escenarios de referencia: `Random(seed)` y `Random(seed XOR 0x5EED)`. Se registra Python para reproducir la generación.

La etiqueta se asigna por el desenlace independiente del escenario:

| Escenario de referencia | Prioridad | malicious |
|---|---|---|
| Actividad benigna, sin daño confirmado | Baja | false |
| Intento malicioso contenido, sin compromiso confirmado | Media | true |
| Compromiso local confirmado, impacto limitado | Alta | true |
| Interrupción de servicio esencial o exposición regulada confirmada | Crítica | true |

Las severidades/criticidades son muestras independientes del escenario, no se calcula la etiqueta a partir del score, sus umbrales ni de sus pesos. Esta independencia deliberada estresa la separación de referencias y la implementación de métricas, pero **no representa una distribución realista de correlación entre señales e impacto**. No es un benchmark de eficacia IDS ni evidencia de calidad predictiva general.

La criticidad de estos casos es una entrada declarada y sintética, nunca una observación de red. El contexto del modelo sigue siendo un prior de política. No se convierten event_timestamp o received_at en ocurrencia/detección real. Los timestamps de respuesta no se fabrican según rango, presupuesto o duración supuesta.

## Importación externa autorizada y trazabilidad

Contrato de ejemplo en `examples/evaluacion_externa_sintetica.json`; es una plantilla etiquetada como sintética, no un experimento real. Importar JSON exige `authorized=true`, name, data_kind, provenance y 1–500 cases. Cada caso tiene UUID, tipo taxonómico y 1–10 eventos con UUID, event_timestamp y received_at con zona, severity y asset_criticality de 0 a 100. Los enteros y el booleano de autorización son estrictos. Tamaño máximo 2 MiB, leído por bloques antes de validar. Propiedades de referencia dentro de características se rechazan.

References es una lista opcional, con case_id único dentro de la cohorte, priority opcional de las cuatro clases, malicious opcional booleano y rationale obligatoria. La anotación externa debe proceder de un protocolo o juicio independiente del score. El sistema no puede certificar la calidad de un juicio ni que el curador no haya consultado el modelo; debe documentarse y auditarse fuera de la aplicación. No se infiere una etiqueta binaria externa desde priority.

Los tiempos opcionales de referencia son occurred_at (inicio real documentado), detected_at (detección documentada), response_completed_at (finalización de respuesta documentada) y timing_evidence. Se validan zona y formato. Un orden temporal negativo invalida la observación para los tiempos y se informa como No calculable, sin inventar valores.

Un caso puede indicar incident_id y cada evento operational_event_id. Esas claves deben existir y corresponder entre sí. Se comprueban tipo, timestamps, recepción, severidad y criticidad contra el evento operativo. Se crean claves foráneas en evaluation_cases y evaluation_event_links; un error revierte la importación completa. Los UUID de caso/evento del dataset identifican la instantánea, aunque no haya enlaces operativos. Los enlaces opcionales no afirman por sí solos que el curador haya incluido todos los eventos históricos de un incidente: el corte y selección deben explicarse en provenance.

No se importan los datasets de evaluación al flujo operativo ni se mezclan etiquetas con events, correlación o evaluaciones históricas. La autorización y la procedencia son declaraciones del investigador, no una verificación legal o criptográfica automática.

## Métricas y fórmulas

Orden de clases: Baja, Media, Alta, Crítica. Matriz `C[i,j]`: cuenta con referencia i y predicción j. Todas las métricas se guardan con value, unit, status y reason; value=null se presenta como **No calculable**, no como cero.

- Exactitud = suma de la diagonal / N.
- Por clase: TP=C[i,i], FP=suma columna i−TP, FN=suma fila i−TP.
- Precisión=TP/(TP+FP), recall=TP/(TP+FN), F1=2TP/(2TP+FP+FN).
- Macro: media aritmética de las cuatro clases. Si algún término es indefinido por denominador cero, el macro correspondiente es No calculable; no se usa zero_division=0 silencioso. F1 puede ser cero con FN/FP positivos aunque precisión sea indefinida.
- Para exactitud, matriz y métricas multiclase se exige referencia de prioridad en toda la cohorte. Si falta, se registra cobertura labeled/total y No calculable; no se evalúa un subconjunto oportunista.
- FPR=FP/(FP+TN) con definición binaria explícita: predicción positiva = prioridad Alta o Crítica; referencia positiva = malicious=true. Se exigen booleanos de referencia en toda la cohorte y al menos un negativo. Esta es una tasa de alta prioridad sobre casos benignos según esa definición, no una estimación universal de falsos positivos del IDS.
- Cobertura crítica(K)=críticos de referencia entre los primeros min(K,N)/total de críticos. Requiere prioridades completas y al menos un crítico. K=0 produce cobertura 0 si existen críticos, no un tiempo cero.
- MTTD=media(detected_at−occurred_at), en segundos.
- MTTR=media(response_completed_at−detected_at), en segundos; aquí significa finalización de respuesta desde detección, no necesariamente reparación total o cierre administrativo.

Para tiempos se exige cohorte completa, pares no negativos, evidencia temporal no vacía y data_kind distinto de synthetic. No se sustituye detección por recepción ni respuesta por selección de cola. Se informa valid_pairs, invalid_pairs y total. Son tiempos descriptivos de la fuente, comunes a ambas estrategias; no se atribuyen cambios causales de MTTD/MTTR a un replay de ordenación.

Carga operativa simulada: selected y backlog en incidentes, selected_events en eventos y budget_used en unidades de selección. No se denominan horas-persona, tasa de resolución ni esfuerzo observado. Igual número de incidentes no garantiza igual trabajo real: diferentes incidentes pueden contener más eventos o requerir distinta complejidad de análisis.

## API, interfaz y procedimiento

| Endpoint | Acceso |
|---|---|
| GET /api/evaluation/datasets | Todos; metadata ciega para analista/observador |
| POST /api/evaluation/datasets/synthetic | Administrador; seed y count |
| POST /api/evaluation/datasets/import | Administrador; JSON externo autorizado |
| GET /api/evaluation/datasets/{id}/cases | Todos; solo características |
| GET /api/evaluation/datasets/{id}/export | Administrador; contrato con referencias |
| POST /api/evaluation/experiments | Administrador; dataset_id y budget |
| GET /api/evaluation/experiments | Todos; UUID, dataset y fecha |
| GET /api/evaluation/experiments/{id} | Todos; solo administrador recibe resultados privados |
| GET /api/evaluation/experiments/{id}/export?format=json o csv | Administrador |

No autenticado: 401; acceso a referencias/ejecución desde otros roles: 403; UUID no encontrado: 404; esquema/presupuesto/enlace inválido: 422; dataset demasiado grande: 413. El usuario conserva sus permisos operativos anteriores; estas restricciones se aplican exclusivamente a los datos de investigación.

En React, iniciar sesión como administrador → Evaluación experimental → generar semilla 202605, count 60 → seleccionar el dataset → budget 10 → comparar. Se muestran cobertura por estrategia, carga, matriz, precisión/recall/F1, tiempos, razones de No calculable y limitaciones. Descargar JSON conserva configuración, órdenes, características y referencias; CSV incluye configuración con versiones, filas por caso/estrategia, referencias/características completas en columnas JSON, filas de métricas y matriz serializada, con encabezados explícitos. Las referencias de exportación deben mantenerse fuera de la vista de participantes.

Repetir con el mismo dataset o generar de nuevo la misma semilla produce los mismos factores, órdenes, predicciones y métricas. UUID y fecha de ejecución son nuevos deliberadamente. Conservar las exportaciones, versión del código y parámetros para revisar el resultado. No cambiar parámetros después de mirar etiquetas para presentar la misma muestra como validación independiente; usar una partición reservada y un protocolo nuevo si se ajusta el modelo.

## Migración y archivos

`0005_evaluation.py`, desde 0004, crea únicamente evaluation_datasets, evaluation_cases, evaluation_references, evaluation_event_links y experiments con sus índices y claves foráneas. No modifica ni elimina filas de usuarios, incidentes, eventos, evidencia, acciones ni evaluaciones de riesgo. Los experimentos no actualizan estados operativos. Ejecutar Alembic con respaldo y sin escrituras concurrentes; conservar el volumen y las credenciales existentes. Downgrade destructivo deshabilitado.

Nuevos módulos: backend/app/evaluation_data.py (contratos y generador), evaluation_metrics.py (métricas puras), experiments.py (instantáneas y ranking), evaluation_api.py (RBAC/exportación). Modificados main.py (router y versión), models.py y las expectativas de head en tests/test_api.py y test_suricata.py. Nuevos tests/test_evaluation.py y migración 0005. Frontend: Evaluation.tsx y conexión desde main.tsx. Se agregan la plantilla externa, el resultado sintético en docs/resultados, este documento; se actualizan README y antología. No se cambió el stack ni se agregaron dependencias.

## Resultado experimental realmente obtenido

Reporte guardado: [iter05_semilla_202605.json](resultados/iter05_semilla_202605.json). UUID **83e64d22-896f-4fbe-baa6-2980885110d0**, generado por la API de Compose aislado con semilla 202605, 60 casos, presupuesto 10 y weighted-v2. Soportes de referencia: Baja 10, Media 14, Alta 13, Crítica 23.

| Indicador | Cronológico | SmartIR |
|---|---|---|
| Selecciones simuladas | 10 incidentes | 10 incidentes |
| Críticos seleccionados | 7 de 23 | 4 de 23 |
| Cobertura crítica | 0.304348 | 0.173913 |
| Pendientes | 50 incidentes | 50 incidentes |
| Eventos en seleccionados | 26 eventos | 46 eventos |

Clasificador común: exactitud **0.25**, macro-F1 **0.182850**, macro-recall **0.228559**. Macro-precisión No calculable porque no hubo predicciones Baja. FPR **0.6**: 6 falsos positivos y 4 verdaderos negativos bajo la definición binaria declarada. MTTD y MTTR **No calculable**: no hay marcas temporales observadas completas y el dataset es sintético.

Matriz observada (filas reales, columnas predichas en el orden indicado):

```
[[0,4,6,0],
 [0,1,4,9],
 [0,0,7,6],
 [0,4,12,7]]
```

La cobertura de SmartIR resultó menor en esta muestra: diferencia −3/23, aproximadamente −0.130435. No se oculta el resultado ni se cambia la semilla para mejorar la conclusión. Como las etiquetas son independientes de las señales por diseño, este resultado demuestra ejecución y transparencia del protocolo; no estima rendimiento real ni permite inferencia estadística sobre la población de incidentes.

## Validación técnica real

Desde la raíz, PowerShell, con las dependencias existentes de backend/requirements-dev.txt:

```powershell
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter05-final
```

Resultado final SQLite: **54 passed, 1 warning in 20.81s**. La primera regresión disponible de 38 pruebas también pasó (14.51 s); tras agregar pruebas experimentales se obtuvieron 53 aprobadas (20.96 s), y se añadió después la prueba de enlaces operativos y rechazo atómico que completa las 54. No hubo fallos de pytest en estas ejecuciones.

```powershell
docker run --detach --rm --name smartir-iter05-test -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55435:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55435/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter05-pg
docker stop smartir-iter05-test
```

Resultado PostgreSQL 16: **54 passed, 1 warning in 134.19s**. Se usa un contenedor temporal sin volumen, trust solo para esa prueba en loopback y esquemas aislados por fixture. Las bases y volúmenes existentes del usuario no se modificaron. El warning de ambas suites es la deprecación BlockingPortal de Starlette/AnyIO. Se verifican fórmulas conocidas, matriz/F1, clases ausentes, datos incompletos, FPR, tiempos inválidos, semilla, desempates, ausencia de etiquetas en ranking, autorización, exportaciones, trazabilidad, rechazo atómico y migración preservando tablas operativas. También pasan las regresiones de autenticación, EVE, correlación y riesgo.

Después se completó la exportación CSV con configuración y columnas JSON de características/referencias para permitir revisión independiente. La prueba dirigida `backend/tests/test_evaluation.py::test_replay_results_exports_and_no_operational_writes` pasó en SQLite (**1 passed in 0.77s**) y PostgreSQL (**1 passed in 5.74s**), con la misma advertencia en ambas. Se reconstruyó y arrancó de nuevo la API Compose reutilizando exactamente las credenciales de prueba, sin modificar la base; se volvió a consultar el experimento guardado y descargar el CSV final. Este ajuste no cambió los órdenes ni las métricas del reporte sintético.

Desde frontend, `npm run build`: TypeScript correcto, Vite 6.4.6, 27 módulos transformados; build Vite 977 ms. No se ejecutaron pruebas de navegador.

Compose se ejecutó con `docker compose -p smartir-iter05 -f compose.yaml -f .test-runs/compose-iter05.yaml up --build -d`, con proyecto/volumen nuevos y puertos aislados 58005 (API) y 55175 (web). El override usa `ports: !override` de Compose moderno. Solo se generaron credenciales nuevas de prueba en el entorno del proceso; no se modificó .env ni se cambiaron contraseñas existentes. Se observaron tres servicios arriba, PostgreSQL healthy, health correcto, web HTTP 200, evaluación sin token HTTP 401 y Alembic **0005 (head)**. Con una cuenta exclusiva del proyecto de prueba se generó el dataset, se ejecutó el experimento cuyo UUID figura arriba y se descargó CSV con HTTP 200. Los servicios se detuvieron sin eliminar el volumen `smartir-iter05_postgres_data`.

La primera extracción del reporte mediante el decodificador de Windows PowerShell alteró acentos de las cadenas. Se volvió a descargar como bytes UTF-8 y se regeneró el artefacto JSON antes de guardarlo; las métricas numéricas no cambiaron. No hay fallos técnicos pendientes conocidos en las comprobaciones ejecutadas, aparte de la advertencia de dependencia; los límites metodológicos continúan vigentes. Las iteraciones anteriores conservan sus resultados históricos en sus propios documentos.

## Amenazas a la validez y trabajo pendiente

Validez de constructo: las etiquetas sintéticas de desenlace y la urgencia estimada no miden exactamente lo mismo; no hay participantes ni esfuerzos reales. Validez interna: referencias externas pueden contener sesgos del curador, timestamps erróneos o decisiones informadas por el score; la aplicación separa campos y roles pero no certifica el juicio. Enlaces operativos pueden representar cortes parciales. Un investigador que conoce etiquetas no es un operador ciego.

Validez externa: una semilla, 60 casos y distribuciones independientes no representan tráfico IDS real, condiciones de red, activos ni ataques reales. No se efectuó una captura, estudio humano, ensayo controlado nuevo ni benchmark de rendimiento. Validez de conclusión: no hay replicaciones estadísticas independientes, intervalos, pruebas de hipótesis ni control de comparaciones múltiples. Los promedios macro y la cobertura dependen de soportes y denominadores; se hacen visibles los no calculables.

El presupuesto uniforme omite dificultad y duración; la cola fotografiada omite llegadas durante servicio. Las ventanas fijas pueden alterar la cohorte original. Se requieren datasets reservados representativos, anotación independiente auditada y diseño predefinido de un futuro ensayo humano para afirmar mejoras de atención o tiempos. Los reportes no son resistentes a manipulación por un administrador de base de datos. La interfaz mantiene localhost:8000; no se hicieron pruebas automatizadas de navegador. Listados aún no tienen paginación. Las limitaciones de seguridad y despliegue ya documentadas siguen vigentes.
