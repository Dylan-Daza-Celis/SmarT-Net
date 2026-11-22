# Iteración 06: clasificación supervisada experimental

## Alcance y arquitectura inspeccionada

Se conservan FastAPI, PostgreSQL, SQLAlchemy, Alembic, React/TypeScript, JWT/RBAC, EVE JSON y los módulos de correlación/riesgo/evaluación existentes. Los incidentes operativos siguen usando weighted-v2 por defecto, o su versión congelada weighted-v1/v2. No se modifica ningún score, estado, evidencia o evaluación histórica al entrenar o predecir con ML.

La inspección encontró `evaluation_cases.features` separado de `evaluation_references`, enlaces opcionales a incidentes/eventos y métricas puras reutilizables. Los predictores disponibles son tipo de evento, severidades, criticidades, número de eventos y fechas. El generador `synthetic-scenarios-v1` de iteración 05 asigna etiquetas independientes de las señales: se conserva como prueba de software, **no se utiliza como evidencia de capacidad predictiva**. Su endpoint no produce un manifiesto ML y `/api/ml/train` lo rechaza.

La nueva ruta experimental usa esos mismos contratos y tablas de datasets/referencias. Añade módulos separados para laboratorio, pipelines, codec numérico y API. No conecta los clasificadores a la ingestión operativa ni los despliega para decidir respuestas.

Referencias técnicas: [ColumnTransformer](https://scikit-learn.org/1.6/modules/generated/sklearn.compose.ColumnTransformer.html), [pipelines](https://scikit-learn.org/1.6/modules/compose.html), [StratifiedGroupKFold](https://scikit-learn.org/1.6/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html) y [riesgos de persistencia pickle/joblib](https://scikit-learn.org/1.6/model_persistence.html). Se fijan scikit-learn 1.6.1, NumPy 2.2.3 y SciPy 1.15.2; se registran versiones efectivas y Python en cada entrenamiento.

## Pregunta, etiquetas y laboratorio

Pregunta: bajo un protocolo fijo con grupos de origen aislados, ¿qué métricas descriptivas obtienen LogisticRegression, RandomForest y weighted-v2 sobre el mismo test reservado de laboratorio? No se formula una conclusión de producción ni una prueba de superioridad estadística.

Generador `lab-outcomes-v1`, semilla predeterminada **202606**, 96 grupos, tres casos relacionados por grupo: 288 casos, 72 por clase antes de particionar. Admite 16–160 grupos, manteniendo el máximo de 500 casos del contrato existente. Los seis tipos se asignan de forma que cada clase aparezca con todos los tipos en el tamaño predeterminado. Los UUID dependen de semilla, grupo e índice, no se pasan al predictor.

El laboratorio define un oráculo de desenlace, separado de las señales:

| Desenlace ficticio documentado | Etiqueta |
|---|---|
| Actividad autorizada/benigna, sin compromiso | Baja |
| Intento malicioso contenido, sin compromiso | Media |
| Compromiso local confirmado de un servicio no esencial | Alta |
| Interrupción de servicio esencial o exposición de información regulada | Crítica |

`annotate` solo lee esos desenlaces. No recibe score, prioridad ponderada, severidad, criticidad ni modelo. Las etiquetas no son umbrales de weighted-v2. Las marcas de oráculo, motivos y grupo se guardan fuera de FeatureCase; no están en el vector predictor.

Para simular detectabilidad, el diseñador impone distribuciones de señales **condicionadas al escenario**. Es una hipótesis de laboratorio, no evidencia observada:

| Escenario | Centro de severidad | Centro de criticidad | Eventos por caso |
|---|---|---|---|
| Benigno | Uniforme 5–35 | Uniforme 5–60 | 1–2 |
| Intento contenido | 25–60 | 10–70 | 1–4 |
| Compromiso local | 45–85 | 25–90 | 2–6 |
| Impacto crítico | 65–95 | 55–100 | 3–8 |

Se añade ruido normal (desviación 12 para severidad, 8 para criticidad), redondeo y límites 0–100. El 15% de severidades se muestrea uniformemente en 0–100 para representar señales engañosas o incompletas. Los tres casos de un grupo comparten centros y desenlace; son dependientes y deben permanecer juntos. Las emisiones sintéticas tienen separación de 20 segundos, por lo que duración y cantidad están correlacionadas en este laboratorio. No se interpretan como MTTD/MTTR ni actividad humana.

La relación entre señales y desenlaces ha sido creada por el diseñador. Aprenderla no demuestra que exista en redes reales. La criticidad es una entrada declarada/sintética, nunca una medición verificada. No se hicieron capturas IDS, anotación humana independiente ni experimentos con operadores.

## Datos externos, duplicados y trazabilidad

`POST /api/ml/datasets/import` recibe un JSON de hasta 2 MiB, con:

- `dataset`: contrato ExternalDataset previo, `authorized=true`, procedencia, kind synthetic/controlled/real, casos y referencias independientes.
- `groups`: mapa completo UUID de caso → UUID de escenario/campaña/origen.
- `annotation_policy`: regla documentada de al menos 20 caracteres.
- `label_source`: `lab_outcomes` o `independent_review`; no acepta `weighted-v2` como origen de etiqueta.

La plantilla `examples/ml_manifest_sintetico.json` es sintética y contiene un solo caso: **es insuficiente para entrenar**, deliberadamente. Los contratos prohíben propiedades extra, duplicados de UUID y referencias fuera de cohorte. Los campos de referencia dentro de características se rechazan. Los enlaces operativos se validan mediante el servicio existente: identidad, incidente, timestamps, severidad y criticidad deben coincidir con los registros enlazados.

Casos que comparten incidente o evento operativo deben compartir grupo. Un evento operativo no se puede repetir dentro de un caso. Además se rechazan contenidos de eventos exactamente duplicados entre casos, aunque cambien sus UUID: huella del tipo, timestamps normalizados a UTC, recepción, severidad y criticidad, sin IDs, etiquetas o grupos. No se confunde una fila de predictores coincidente con un registro duplicado si los eventos originales son distintos. Clones aproximados, tiempos desplazados y dependencias no declaradas siguen requiriendo revisión de la fuente.

El manifiesto completo tiene un hash privado. Reimportar el mismo manifiesto devuelve 409 con el UUID existente; no crea otro dataset ML silenciosamente. La comprobación está serializada con bloqueo asesor PostgreSQL o BEGIN IMMEDIATE en SQLite. Cambios de anotación o de contenido constituyen otra versión de dataset. El endpoint de evaluación anterior conserva su comportamiento y resultados.

Los mapas de grupos, reglas, referencias, hashes y vínculos quedan asociados al dataset; cada MLRun referencia ese UUID. El investigador declara independencia y autorización: el software no puede certificar que un anotador externo no haya copiado el score ni la autenticidad del desenlace. Corresponde auditar esa procedencia antes de atribuir valor científico a los datos. Los tipos admitidos en evaluación son los seis taxonómicos; los operativos desconocidos no se recodifican automáticamente para este estudio.

## Características y separación de referencias

Extractor `incident-aggregates-v1`, con lista blanca y este orden:

1. Máxima severidad.
2. Máxima criticidad declarada.
3. Media de severidad.
4. Número de eventos.
5. Span de timestamps de evento, en segundos.
6. Tipo de evento, categórico.

No incluye score weighted, prioridades calculadas, prioridad de referencia, malicious, rationale, desenlaces, timestamps de respuesta, grupo, UUID o fecha absoluta de recepción. La recepción solo sirve para desempatar órdenes después de predecir. El extractor recibe un FeatureCase, cuyo esquema no permite etiquetas. Los grupos se utilizan para aislar particiones y las etiquetas para estratificación/entrenamiento/evaluación, nunca como columna de entrada.

La unidad es una instantánea de incidente con todos los eventos seleccionados para el corte. No se demuestra predicción temprana desde el primer paquete; un corpus externo debe documentar qué datos estaban disponibles en el momento de decisión para evitar anticipación temporal.

## Partición, CV y modelos

Protocolo `supervised-group-holdout-v1`, semilla 202606. Los casos se ordenan por UUID antes de particionar para que reordenar un archivo no cambie la muestra. Se toma **el primer fold** de StratifiedGroupKFold de cuatro particiones, con shuffle y semilla fija: aproximadamente 25% de test por grupos. Es estratificación aproximada; no garantiza soportes idénticos. No se buscan particiones alternativas mirando el rendimiento ni se fuerzan mejores resultados.

Se exigen referencias completas, al menos 32 casos, 16 grupos y cuatro grupos de cada clase; las cuatro clases deben estar presentes en train y test. Si falla, se guarda un intento `insufficient_data`, sin artefactos, con No calculable y motivo. No se entrena un clasificador incompleto y se lo presenta como válido para cuatro clases. En una comprobación inicial con 32 grupos, el fold predefinido carecía de una clase y se reportó No calculable; no se escogió otro fold para ocultarlo.

La CV usa exclusivamente train, tres folds StratifiedGroupKFold con semilla+1. Solo se ejecuta si hay al menos tres grupos por clase en train y cada fold mantiene las cuatro clases tanto en entrenamiento como en validación. Se guardan IDs de cada fold, grupos y macro-F1 por fold. Si no es posible, CV es No calculable. En el laboratorio documentado se ejecutaron tres folds. Test nunca participa en fit del preprocesamiento, del clasificador ni de CV.

Pipeline sklearn:

```
ColumnTransformer:
  numéricas -> StandardScaler (ajustado solo en train de cada fold)
  tipo -> OneHotEncoder(handle_unknown="ignore", sparse_output=False)
 -> LogisticRegression o RandomForestClassifier
```

Parámetros fijados antes del test, sin búsqueda de hiperparámetros:

- LogisticRegression: C=1, solver=lbfgs, max_iter=2000, class_weight=balanced, random_state=202606.
- RandomForest: 100 árboles, max_depth=6, min_samples_leaf=2, class_weight=balanced, random_state=202606, n_jobs=1; demás valores efectivos se guardan con get_params.

Se ajustan dos pipelines finales sobre el mismo train. Se evalúan ambos en el mismo test y se llama al motor weighted-v2 existente sobre esos mismos casos reservados con sus parámetros registrados. La CV es diagnóstica, no optimiza modelos. Elegir después un modelo por su test no proporciona otra evaluación independiente; un futuro ajuste necesita un test nuevo reservado.

## Métricas, ranking e interpretación

Se reutilizan evaluation_metrics: exactitud, matriz 4×4 (filas reales, columnas predichas), soporte, precisión, recall, F1 y macros, manteniendo No calculable para denominadores indefinidos. El archivo protegido contiene valores y razones completos, no solo métricas favorables.

Cobertura crítica: críticos de referencia entre las primeras K selecciones / críticos totales del test. Se mantiene el mismo K efectivo para los tres métodos. Weighted ordena por score; ML ordena por urgencia esperada `sum(indice_clase * probabilidad)` con índices Baja=0, Media=1, Alta=2, Crítica=3, luego recepción y UUID. Esa utilidad ordinal uniforme es una convención experimental, no una función de costo validada. No se inventa probabilidad para weighted-v2.

predict_proba produce estimaciones numéricas válidas, finitas y normalizadas; se verifican antes de guardar. **No se calibraron ni validaron como confianza**. La UI las etiqueta como estimadas y sin calibración, mostrando clase, algoritmo, UUID/versión del modelo y protocolo. No hay garantías fuera de distribución ni se convierte la probabilidad máxima en seguridad de la respuesta.

LR conserva coeficientes/interceptos por clase sobre variables estandarizadas y one-hot. El orden de columnas queda en feature_names; numeric__x0..x4 corresponde a las cinco variables numéricas listadas arriba y categorical__x5_* al tipo. RF conserva importancias de impureza. No son efectos causales; ruido, correlación entre variables y supuestos del generador limitan la interpretación.

## Persistencia segura y permisos

Alembic `0006_ml.py` crea solo `ml_runs`: UUID, dataset, autor, estado, configuración, artefactos JSON, resultados y fecha UTC. Es necesaria para conservar versiones entrenadas y comparaciones sin sobrecargar o modificar experimentos anteriores. No modifica ni recrea tablas o volúmenes existentes. Downgrade destructivo deshabilitado.

Formato `numeric-pipeline-json-v1`: scaler, categorías, coeficientes/interceptos o arrays numéricos de árboles producidos por el servidor. No hay upload de modelos, pickle, joblib.load, eval ni reconstrucción arbitraria de objetos. Joblib puede estar instalado como dependencia transitiva de sklearn; no se usa para deserializar modelos. La inferencia JSON se contrasta con predict_proba del Pipeline antes de persistir, con tolerancia 1e-7 relativa/1e-9 absoluta. El hash del artefacto detecta alteración accidental antes de inferir; no es una firma contra un administrador de base de datos que modifique datos y hash.

La inferencia verifica esquema congelado y formato, sin reinterpretar un artefacto con otra lista de características. Las versiones guardadas se consultan desde configuración persistida. No se sobrescriben modelos: cada entrenamiento genera otro UUID. No hay activación en producción ni sustitución del motor operativo.

| Endpoint | Permiso |
|---|---|
| POST /api/ml/datasets/laboratory | Administrador investigador |
| POST /api/ml/datasets/import | Administrador investigador |
| POST /api/ml/train | Administrador investigador |
| GET /api/ml/versions | Todos los roles autenticados; solo metadata ciega |
| GET /api/ml/runs/{id} | Todos; resultados, particiones e interpretación solo para administrador |
| POST /api/ml/runs/{id}/predict?algorithm=logistic o forest | Todos autenticados; FeatureCase sin etiquetas |
| GET /api/ml/runs/{id}/export | Administrador; JSON completo con manifiesto, referencias y modelos numéricos |

Analista/observador no reciben referencias ni métricas agregadas contra etiquetas, de acuerdo con iteración 05. La predicción de un modelo no es la etiqueta de referencia. Quien conoce la semilla y el generador sintético puede reconstruir el laboratorio: no se presenta como un ensayo ciego de personas. Exportaciones reales etiquetadas requieren aislamiento respecto a participantes.

## Procedimiento reproducible

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
# En instalación existente, conservar .env y credenciales:
docker compose up --build -d
```

El arranque API aplica Alembic hasta 0006. Iniciar sesión como administrador → Aprendizaje automático experimental → generar laboratorio con semilla 202606 y 96 grupos → seleccionar ese dataset → entrenar con semilla 202606 y presupuesto 10. Una repetición del mismo manifiesto devuelve 409: reutilizar el dataset, no generar duplicados. Se muestran los tres métodos, matriz, soporte, métricas y límites de CV. Descargar el JSON para conservar configuración, particiones completas, probabilidades, referencias y arrays numéricos.

Para inferencia, pegar un FeatureCase obtenido mediante GET /api/evaluation/datasets/{id}/cases o del export sin referencias, elegir algoritmo y predecir. Inferir sobre un caso de entrenamiento no es evaluar generalización; las métricas guardadas se calculan solo sobre el test reservado. No aceptar artefactos descargados de terceros: no existe un endpoint que los cargue.

Misma fuente/semilla/versión/entorno produce los mismos splits y resultados. Puede haber diferencias de últimos bits entre plataformas BLAS; no se exige identidad binaria de artefactos entre Windows y Linux. Se registran Python/sklearn/NumPy/SciPy y parámetros para auditarlo. No reutilizar este test para afinar hiperparámetros o semillas.

## Resultados reales de esta entrega

Reporte compacto: [iter06_semilla_202606.json](resultados/iter06_semilla_202606.json). Ejecución por API de Compose, UUID **cb7bdb6f-941c-4d50-aece-742d8100e01b**, laboratorio/entrenamiento semilla 202606. El export protegido conserva todos los modelos, grupos y predicciones; el archivo versionado reduce mapas/CV a hashes/resúmenes y omite predicciones individuales.

288 casos/96 grupos; **216 train y 72 test**, grupos disjuntos. Soporte del test: Baja 15, Media 9, Alta 15, Crítica 33. El desequilibrio del test se informa, no se corrige seleccionando otro fold.

| Método | Exactitud test | Macro-F1 test | Recall Crítica | Cobertura K=10 |
|---|---|---|---|---|
| LogisticRegression | 0.597222 | 0.565623 | 23/33 = 0.696970 | 10/33 = 0.303030 |
| RandomForest | 0.708333 | 0.708620 | 23/33 = 0.696970 | 10/33 = 0.303030 |
| weighted-v2 | 0.583333 | 0.418750 | 31/33 = 0.939394 | 10/33 = 0.303030 |

Los ML tuvieron mayor macro-F1 descriptivo en esta muestra; weighted-v2 tuvo **mayor recall de críticos** y no hubo diferencia de cobertura bajo ese presupuesto. No se afirma superioridad estadística, robustez ni generalización real. No se seleccionó otro presupuesto para ocultar esa igualdad o favorecer un método.

Matrices en orden Baja, Media, Alta, Crítica:

```
Logistic: [[7,7,1,0],[1,7,1,0],[0,2,6,7],[0,0,10,23]]
Forest:   [[10,4,1,0],[0,8,1,0],[0,1,10,4],[0,0,10,23]]
weighted: [[1,8,6,0],[0,3,6,0],[0,0,7,8],[0,0,2,31]]
```

Macro-F1 de los tres folds de CV de train: LR 0.632234, 0.505243, 0.399759; RF 0.561435, 0.534114, 0.537823. No se usan para ajustar hiperparámetros ni para presentar el mejor fold como resultado final. Los tiempos MTTD/MTTR no se estiman desde estas predicciones.

## Pruebas y fallos observados

Comandos desde la raíz, PowerShell:

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter06-final
```

Suite SQLite: **65 passed, 1 warning in 35.50s** (otra ejecución previa: 31.16 s). PostgreSQL:

```powershell
docker run --detach --rm --name smartir-iter06-test -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55436:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55436/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter06-pg
docker stop smartir-iter06-test
```

Suite PostgreSQL 16: **65 passed, 1 warning in 182.33s**. Contenedor temporal sin volumen, trust únicamente para esa prueba en loopback, con esquemas aislados por fixture. Después de cerrar las comprobaciones de manifiestos duplicados y metadatos congelados, se repitió `backend/tests/test_ml.py`: **11 passed in 7.29s** SQLite y **11 passed in 30.95s** PostgreSQL, con una advertencia cada uno. Se añadió y ejecutó la comprobación de artefacto alterado en `test_api_training_blinding_inference_and_persistence`: **1 passed in 2.41s** SQLite y **1 passed in 8.29s** PostgreSQL. No hubo fallos de pytest en estas ejecuciones.

Los tests cubren preprocesamiento ajustado solo en train, ausencia de etiquetas/IDs/grupos/score en features, aislamiento de grupos y CV, métricas sobre test idéntico, clases/referencias insuficientes, repetibilidad, categorías no vistas, inferencia JSON equivalente, formatos no admitidos, permisos, integridad, duplicados y conservación de experimentos y tablas previas al migrar 0005→0006. La advertencia común es la deprecación de BlockingPortal de Starlette/AnyIO.

Desde frontend, `npm run build`: TypeScript correcto; Vite 6.4.6, 28 módulos; build Vite final **1.84 s**. No se hicieron pruebas automatizadas de navegador.

Compose arrancó con `docker compose -p smartir-iter06 -f compose.yaml -f .test-runs/compose-iter06.yaml up --build -d`, proyecto/volumen nuevos y puertos aislados 58006 para API y 55176 para web. El override usa `ports: !override`. Se crearon credenciales solo para esa instalación de prueba y se reutilizaron sin cambiarlas al actualizar API/web; no se tocó .env ni contraseñas existentes. Se observaron tres servicios arriba, PostgreSQL healthy, health correcto, web HTTP 200, GET /api/ml/versions sin token HTTP 401 y Alembic **0006 (head)**.

Con una cuenta exclusiva de prueba se generó el laboratorio, se entrenaron ambos modelos por HTTP y se exportó el reporte real identificado arriba. La inferencia HTTP de RandomForest sobre un FeatureCase sin referencias devolvió Baja, `uncalibrated=true` y suma de probabilidades 0.9999999999999997 (redondeo flotante). Esa consulta es una comprobación funcional, no otra evaluación de generalización. Se detuvieron los servicios de prueba conservando el volumen `smartir-iter06_postgres_data`; no se eliminaron volúmenes existentes.

El fallo de equivalencia numérica detectado durante implementación se corrigió antes del commit: NumPy 2 promovía un umbral Python a float32 al compararlo con un escalar de árbol. Se convierte el valor a float Python para replicar la comparación de sklearn con umbral double. La discrepancia inicial máxima observada fue aproximadamente 0.03084 en probabilidades RF; la barrera de persistencia impidió guardar ese resultado. Los tests verifican ahora equivalencia tras serializar JSON, incluso entradas categóricas no vistas. Un script auxiliar inicial de compactación del reporte requirió corregir su ruta de importación; el artefacto final se creó desde el export JSON UTF-8, sin recodificación de PowerShell ni cambios de métricas.

## Amenazas a la validez y límites

La asociación señales/desenlaces fue impuesta por el generador. Ruido y variaciones no equivalen a diversidad de redes, campañas, reglas Suricata o activos reales. Réplicas por grupo no son observaciones independientes; se aíslan, pero la fuente externa debe declarar dependencias correctamente. La detección exacta de duplicados no sustituye búsqueda de clones aproximados ni auditoría de origen.

Solo hay un test reservado, sin intervalos de confianza, repetición estadística independiente ni prueba de hipótesis. Estratificación por grupos es aproximada y el soporte es desigual. Accuracy, macro-F1 y recall crítico responden a objetivos distintos; class_weight=balanced y la utilidad ordinal son elecciones, no costos reales. Span y cantidad están correlacionados en el laboratorio; coeficientes/importancias no explican causalidad.

Un cambio de distribución, disponibilidad de señales al corte o calidad de anotaciones puede invalidar estas cifras. La aplicación valida formato/roles/vínculos, no la verdad de la anotación ni la autorización declarada. Los tipos desconocidos operativos no se convierten a una clase conocida para entrenar. Un corpus real, reservado, independiente y auditado es necesario antes de estudiar eficacia; una calibración y otro test son necesarios antes de usar probabilidades como confianza.

No hay aprendizaje continuo, promoción automática, ejecución en dispositivos, evaluación humana, drift monitoring ni validación de producción. Entrenamiento síncrono acotado a 500 casos; sin cola de trabajos o benchmark de carga. No se hicieron pruebas de navegador. La UI conserva localhost:8000 y las limitaciones de despliegue y seguridad previas siguen vigentes.

## Archivos principales

Nuevos: backend/app/ml_data.py, ml_engine.py, ml_artifact.py, ml_api.py; backend/migrations/versions/0006_ml.py; backend/tests/test_ml.py; frontend/src/MachineLearning.tsx; examples/ml_manifest_sintetico.json; este documento y docs/resultados/iter06_semilla_202606.json. Modificados: main.py y models.py del backend, requirements.txt, expectativas de head de test_api.py/test_evaluation.py/test_suricata.py, main.tsx, README y antología. Las fuentes, contratos y resultados históricos de iteraciones 03–05 se conservan.
