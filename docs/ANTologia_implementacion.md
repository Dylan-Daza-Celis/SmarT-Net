# Diseño e implementación de SmartIR-Net — estado acumulado hasta iteración 07

Este capítulo describe la implementación actual. Las versiones anteriores y sus resultados de validación se conservan en el historial Git, AUTENTICACION_Y_RESPUESTA.md y CORRELACION_Y_RIESGO.md; sus limitaciones históricas no deben interpretarse como ausencia de componentes que ya se implementaron.

## Arquitectura y alcance

SmartIR-Net mantiene una arquitectura cliente-servidor con React/TypeScript, API FastAPI, SQLAlchemy y PostgreSQL. Alembic controla el esquema y Docker Compose coordina los servicios. Las credenciales se obtienen del entorno, no del repositorio. La aplicación usa contraseñas Argon2id, JWT de 15 minutos y control de permisos en backend: administrador gestiona usuarios y puede operar, analista importa y responde, observador consulta. No se afirma que estén implementadas todas las entidades del modelo conceptual original.

Pipeline actual: JSON SmartIR o archivo EVE JSONL → validación → adaptación cuando procede → servicio compartido de importación → deduplicación → correlación temporal → riesgo explicable con parámetros congelados → PostgreSQL → API protegida → interfaz web. El historial de estados, las acciones de respuesta y las evaluaciones de riesgo se almacenan por separado.

## Ingestión y evidencia

POST /api/events/import conserva el formato SmartIR normalizado y su fingerprint histórico. POST /api/events/import/eve recibe un archivo UTF-8 JSON Lines como cuerpo, valida alertas Suricata y procesa hasta 100 registros válidos por transacción, con límites de 10 MiB, 64 KiB por línea y 10000 registros no vacíos. Líneas inválidas se reportan por posición y no impiden procesar las válidas; se permiten resultados parciales por límite. Los tipos EVE distintos de alert se descartan explícitamente.

El adaptador extrae fecha UTC, IP, puertos, protocolo, firma, SID, categoría y severidad. La clasificación es una tabla explícita y versionada hacia acceso_no_autorizado, malware, dos, escaneo, uso_indebido y exfiltracion. Exfiltración usa una categoría personalizada explícita, no una inferencia desde cualquier fuga de información. Las categorías no mapeadas se conservan como desconocido. La severidad original y las políticas de transformación se guardan en metadata.

La primera línea EVE original permanece en events.raw_event; cada aparición válida, incluso duplicada, agrega una evidencia con archivo, sensor declarado, autor, fecha, línea y hash. El sensor no está autenticado criptográficamente. La huella EVE incorpora el sensor y el JSON original canónico; no sustituye ni altera fingerprints históricos SmartIR. Las líneas rechazadas requieren conservar el archivo fuente para su investigación.

Los seis ejemplos de examples/suricata_sintetico.eve.jsonl son sintéticos, etiquetados como tales. No se presentan como capturas reales, validación de detecciones ni mediciones de Packet Tracer.

## Correlación temporal

Versión utc-tumbling-v1, ventanas fijas UTC inicialmente de 900 segundos, configurables con CORRELATION_WINDOW_SECONDS. Identidad por tipo exacto, origen/destino normalizados, inicio y ancho de ventana. Intervalo `[inicio, inicio+ancho)`, alineado al epoch Unix. Campos IP desconocidos coinciden solo con desconocidos, no como comodines. Puertos y firmas no forman parte de la clave en esta versión.

El orden de llegada no modifica la partición. Un registro tardío actualiza la ventana correspondiente a su tiempo de evento sin reabrir automáticamente un caso cerrado. Cambiar el ancho no reagrupa eventos anteriores. Los incidentes legacy anteriores a la migración temporal no se mezclan con grupos nuevos.

Limitaciones: dos eventos casi simultáneos a ambos lados del límite quedan separados; dos episodios dentro de la misma ventana pueden agruparse. Direcciones desconocidas pueden producir agrupaciones ambiguas. No hay ventanas deslizantes, watermark ni retención automática.

## Priorización explicable y reproducibilidad

`riesgo = .35*S + .25*A + .15*R + .15*T + .10*C`, limitado a 0–100 y redondeado con mitades hacia arriba. S y A son máximos del incidente; R=min(100,20*n); T utiliza la tabla de ataque versionada y C=50 cuando no existe contexto. Prioridades: Baja 0–24, Media 25–49, Alta 50–74 y Crítica 75–100. Son parámetros iniciales de ingeniería que requieren validación experimental, sin evidencia de superioridad científica.

**Criticidad predeterminada y contexto no son observaciones de red.** EVE no informa criticidad: se aplica A=50 con procedencia policy_default_50. En el formato SmartIR, una criticidad explícita es una declaración del importador, no una medición verificada. Para datos previos sin indicador, la procedencia es desconocida. El contexto permanece desconocido y aporta cinco puntos por política neutral.

Nuevos incidentes usan weighted-v2, que etiqueta la procedencia de criticidad en los factores sin cambiar la fórmula numérica. Incidentes con parámetros weighted-v1 mantienen su algoritmo congelado y las evaluaciones antiguas no se reescriben. Cada lote nuevo genera una evaluación anexada con parámetros, versión, factores y contribuciones. Los duplicados no recalculan el riesgo. GET /api/incidents/{id}/evaluations permite consultar las evaluaciones guardadas.

## Persistencia y migraciones

Tablas operativas iniciales: events, incidents, users, incident_history, response_actions, risk_evaluations y event_evidence. La iteración 05 agrega evaluación y 06 agrega ml_runs. La 07 añade assignment_history, incident_review_signals, review_acknowledgements e incident_time_evidence. Los seis estados se conservan, pero los saltos libres anteriores se sustituyen por lifecycle-v1, responsables activos y revisiones optimistas. Las acciones son registros, no comandos ejecutados en dispositivos.

Alembic 0001 adopta el esquema original; 0002 agrega autenticación e historial operativo; 0003 introduce ventanas y evaluaciones de riesgo; 0004 agrega metadata y procedencia EVE; 0005 crea tablas experimentales; 0006 agrega modelos JSON; 0007 incorpora ciclo de vida mediante columnas y tablas nuevas, sin reescribir estados o tiempos heredados. Se preservan datos, usuarios, riesgos, modelos y experimentos anteriores. No se eliminan volúmenes ni se cambian contraseñas. Los downgrades destructivos están deshabilitados.

## Interfaz, evidencias y límites de validación

React conserva login, métricas, filtros combinables por prioridad/tipo/estado, detalle de factores, historial y formularios según rol. Incorpora selector de formato, sensor declarado, reporte de importación y consulta de evidencia. El backend decide siempre los permisos; ocultar controles no sustituye la autorización.

La evidencia anterior permanece: Suricata (38 pruebas por base), evaluación de iteración 05 (54) y ML de iteración 06 (65). La validación actual está en GESTION_AVANZADA_INCIDENTES.md: 82 pruebas por base, carreras concurrentes, build React y Compose en 0007 con cierre y revisión sin cambiar riesgo. No se han hecho pruebas de navegador, validación científica del scoring, carga ni captura IDS real. El ML continúa experimental, sin validación de producción. Permanecen pendientes HTTPS gestionado por despliegue, MFA, recuperación de contraseña, ingestión en vivo, otros tipos EVE, retención y optimización de históricos. Los tiempos operativos no se presentan como mediciones reales de personas.

## Evaluación reproducible de la iteración 05

Se implementó un replay emparejado sobre una cohorte inmutable: orden cronológico por primera recepción y orden SmartIR por score descendente, ambos con desempates por recepción y UUID. Un presupuesto K consume una unidad por selección de incidente. Las referencias se almacenan fuera de las características, no entran al algoritmo y quedan reservadas al administrador investigador. Analista y observador consultan características y órdenes sin referencias ni métricas agregadas que permitan reconstruirlas. Los resultados se guardan con fecha, UUID, versiones y parámetros y se exportan como CSV/JSON.

El generador de semilla 202605 representa seis tipos y asigna etiquetas por desenlaces de escenario independientes del score. Esto valida el protocolo y la ausencia de copia de etiquetas desde la predicción, pero no emula una distribución IDS realista. Las fuentes externas autorizadas se declaran sintéticas, controladas o reales; ejecutar el replay sobre ellas sigue siendo una simulación. No se atribuyen tiempos ni resultados a operadores.

Se calculan exactitud, matriz, precisión/recall/F1, macro-promedios, FPR con definición binaria, cobertura crítica bajo presupuesto y carga con unidades explícitas. Faltas de referencias, denominadores cero o tiempos incompletos se presentan como No calculable. MTTD exige ocurrencia/detección y MTTR detección/finalización de respuesta, con evidencia temporal, orden válido y fuente no sintética. Son descripciones de la fuente, comunes a ambas colas; no una mejora causal de ordenación.

Resultado real de 60 casos sintéticos con K=10: cronológico seleccionó 7 de 23 críticos y SmartIR 4 de 23. Exactitud 0.25 y macro-F1 0.182850; MTTD/MTTR no calculables. Esta muestra no respalda la hipótesis direccional de mejora. No hay inferencia estadística, ensayo con personas ni generalización a redes reales. El reporte preservado, fórmulas y amenazas a la validez están en el documento experimental, sin borrar resultados históricos de iteraciones anteriores.

## Clasificación supervisada experimental: iteración 06

El generador independiente de etiquetas de iteración 05 se conserva como prueba del evaluador y no se usa como evidencia predictiva. El nuevo laboratorio reproducible lab-outcomes-v1 define desenlaces benignos, intentos contenidos, compromisos locales e impactos críticos mediante un oráculo separado de señales y score. Las distribuciones de severidad, criticidad y eventos se condicionan al escenario con ruido y solapamientos: son supuestos impuestos, no mediciones de red. Tres casos relacionados de cada grupo se mantienen juntos.

Se entrenan pipelines scikit-learn con StandardScaler para cinco agregados numéricos y OneHotEncoder para tipo, seguidos de LogisticRegression o RandomForest. No entran etiquetas, IDs, grupos, scores ponderados ni desenlaces al vector de predicción. El test se reserva por grupos con semilla fija, y la CV estratificada solo usa train cuando hay suficientes clases y grupos. No se ajustan hiperparámetros con el test. Se guardan clases, características, coeficientes/importancias, parámetros y versiones; los modelos se persisten como arrays JSON numéricos con inferencia contrastada, sin deserialización de objetos no confiables.

La comparación reutiliza el mismo test y las métricas existentes para ambos ML y weighted-v2, que permanece como motor operativo predeterminado. En la ejecución documentada hay 288 casos, 216 train y 72 test; macro-F1 LR 0.5656, RF 0.7086, weighted-v2 0.4188. Weighted-v2 recupera más críticos como clase (31/33 frente a 23/33 para ML), y los tres cubren 10/33 al seleccionar 10 casos. Se conservan también los resultados desfavorables y los soportes desiguales del test.

Estas cifras describen un laboratorio sintético creado por el propio diseñador. No permiten afirmar superioridad estadística, eficacia IDS, calibración de probabilidades ni generalización a producción. La interfaz muestra probabilidades estimadas sin calibración y versiones; solo administradores entrenan o consultan resultados con referencias, manteniendo la separación de operadores. Métodos, fallos corregidos, particiones, pruebas, archivos y reporte preservado en [APRENDIZAJE_AUTOMATICO.md](APRENDIZAJE_AUTOMATICO.md).

## Gestión avanzada de incidentes: iteración 07

El responsable se vincula a un administrador o analista activo. La asignación inicial mueve Nuevo a Asignado en una transacción y registra autor, anterior/nuevo responsable, fecha UTC y justificación. El administrador gestiona cualquier caso; el analista toma para sí casos libres y transfiere casos propios. No se retira responsabilidad en pleno trabajo sin volver antes a triage; tampoco se desactiva/degrada un responsable de incidentes abiertos sin reasignar. Observador mantiene solo lectura.

La máquina conserva los seis estados, con flujo normal lineal, retrocesos definidos y reaperturas justificadas. Reabrir Cerrado requiere administrador y responsable activo. Revision y bloqueo transaccional común con la importación evitan sobrescrituras; PATCH /status conserva ruta pero exige expected_revision (428 si falta, 409 si es obsoleta). Las asignaciones y estados heredados no se inventan: se conserva el estado y se identifica la ausencia de baseline completo.

Primeros/últimos timestamps y ciclos proceden de auditoría inmutable. Los intervalos hasta asignación, respuesta y resolución se distinguen de MTTD/MTTR, que exigen marcas documentadas de ocurrencia/detección/finalización y revisión administrativa. La recepción, el timestamp del evento o un estado Resuelto no sustituyen esa evidencia. Fuente sintética o incompleta devuelve No calculable. Los agregados muestran cobertura de datos y no atribuyen tiempos a operadores humanos.

Las acciones añaden categoría y fecha declarada/registrada, manteniendo comentarios anteriores; no ejecutan comandos. Nuevos eventos asociados a Cerrado conservan evento y procedencia, generan señal y no recalculan score ni alteran estado. Su reconocimiento se anexa, no borra el aviso. La UI muestra responsable, filtros, tiempos y timeline combinado.

La comprobación HTTP sintética de esta entrega registró seis estados, una asignación y una acción; al importar evidencia después del cierre, el score permaneció 73 y surgió una señal, con MTTD/MTTR No calculable. No es un resultado humano ni una mejora de tiempo. Reglas, fórmulas, migración aditiva 0007, pruebas, fallos corregidos y límites en [GESTION_AVANZADA_INCIDENTES.md](GESTION_AVANZADA_INCIDENTES.md). Los reportes y cifras de iteraciones anteriores se mantienen como evidencia histórica.
