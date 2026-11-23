# Diseño e implementación de SmartIR-Net — estado acumulado hasta iteración 11

**Borrador técnico para revisión académica; no antología final aprobada.** La validación10 amplía la evidencia anterior con HTTP concurrente y Chromium reales. Las limitaciones temporales de capítulos previos se conservan como contexto histórico; consultar [VALIDACION_INTEGRAL.md](VALIDACION_INTEGRAL.md) para el estado vigente y su matriz de trazabilidad.

Actualización11: agente desacoplado de lectura EVE y cuenta de mínimo privilegio, con migración aditiva0009. El estado actual de este módulo y la evidencia adicional están en [MONITOREO_CONTINUO_SURICATA.md](MONITOREO_CONTINUO_SURICATA.md). Los resultados10 y previos siguen siendo fotografías de sus versiones; no se sustituyen por cifras nuevas.

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

Nuevos incidentes usan weighted-v2, que etiqueta la procedencia de criticidad en los factores sin cambiar la fórmula numérica. Incidentes con parámetros weighted-v1 mantienen su algoritmo congelado y las evaluaciones antiguas no se reescriben. Los lotes nuevos de casos abiertos sin evidencia de cierre pendiente generan una evaluación anexada con parámetros, versión, factores y contribuciones. Cerrado conserva su riesgo; desde 08, la evidencia recibida durante cierre requiere reevaluación explícita tras reapertura antes de incorporarse al score, también frente a importaciones posteriores. Los duplicados no recalculan el riesgo. GET /api/incidents/{id}/evaluations permite consultar las evaluaciones guardadas.

## Persistencia y migraciones

Tablas operativas iniciales: events, incidents, users, incident_history, response_actions, risk_evaluations y event_evidence. La iteración 05 agrega evaluación y 06 agrega ml_runs. La 07 añade assignment_history, incident_review_signals, review_acknowledgements e incident_time_evidence. Los seis estados se conservan, pero los saltos libres anteriores se sustituyen por lifecycle-v1, responsables activos y revisiones optimistas. Las acciones son registros, no comandos ejecutados en dispositivos.

Alembic 0001 adopta el esquema original; 0002 agrega autenticación e historial operativo; 0003 introduce ventanas y evaluaciones de riesgo; 0004 agrega metadata y procedencia EVE; 0005 crea tablas experimentales; 0006 agrega modelos JSON; 0007 incorpora ciclo de vida mediante columnas y tablas nuevas, sin reescribir estados o tiempos heredados; 0008 agrega snapshots de reportes, auditoría/enlaces de reevaluación e índices temporales. Se preservan datos, usuarios, riesgos, modelos y experimentos anteriores. No se eliminan volúmenes ni se cambian contraseñas. Los downgrades destructivos están deshabilitados.

## Interfaz, evidencias y límites de validación

React conserva login, métricas, filtros combinables por prioridad/tipo/estado, detalle de factores, historial y formularios según rol. Incorpora selector de formato, sensor declarado, reporte de importación y consulta de evidencia. El backend decide siempre los permisos; ocultar controles no sustituye la autorización.

La evidencia anterior permanece: Suricata (38 pruebas por base), evaluación de iteración 05 (54), ML de iteración 06 (65) y ciclo de vida de 07 (82). La validación de dashboard/reportes, SQL, filtros, concurrencia y migración 0008 se documenta en DASHBOARD_Y_REPORTES.md. No se han hecho pruebas de navegador, validación científica del scoring, carga ni captura IDS real. El ML continúa experimental, sin validación de producción. Permanecen pendientes HTTPS gestionado por despliegue, MFA, recuperación de contraseña, ingestión en vivo, otros tipos EVE, retención y optimización de históricos. Los tiempos operativos no se presentan como mediciones reales de personas.

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

## Dashboard analítico, reportes y reevaluación: iteración 08

La nueva vista ejecutiva consulta una cohorte SQL común con periodo UTC [inicio,fin), eje de creación/evento/recepción y filtros combinables por prioridad, tipo, estado, responsable y fuente. Indicadores, tendencias, tablas paginadas y reportes operativos usan exactamente esa selección. Se distinguen conteos de incidentes únicos y eventos deduplicados. La tendencia crítica usa la prioridad actual, sin presentarla como reconstrucción histórica. El dashboard muestra abiertos/resueltos/cerrados, responsabilidad, señales, atención prioritaria y tiempos con cobertura y motivos de No calculable.

Las gráficas interactivas usan Recharts y disponen de tablas alternativas. La comparación de modelos utiliza exclusivamente resultados ya registrados y mantiene la restricción al administrador investigador. Sus cohortes congeladas, a menudo sintéticas y sin incidentes operativos vinculados, permanecen en un apartado independiente de los filtros/exportaciones operativos; no se recalculan métricas para una población diferente ni se muestran etiquetas a operadores. No se altera el motor ML ni el scoring operacional predeterminado.

Los reportes se guardan como snapshots inmutables con UUID, fecha UTC, autor autenticado interno y hash SHA-256 del JSON canónico. Se descargan en CSV/JSON/PDF; incluyen metodología, denominadores y limitaciones y excluyen IP, mensajes, evidencias originales, nombres de usuarios y autenticación. Datos sin clasificación verificable de procedencia se identifican como unverified, sin inferir «real» por usar Suricata. El hash verifica integridad del contenido, no autenticidad física ni una cadena de custodia contra administradores de BD.

La iteración 08 sustituye la compatibilidad de nuevas acciones sin revisión: ahora POST /actions exige expected_revision, con 428/409 conforme a 07. Las acciones previas no se modifican. Un caso reabierto con evidencia de cierre conserva su score hasta POST /reevaluate explícito de responsable/admin; reutiliza parámetros congelados y anexa evaluación/auditoría con UUID de eventos y señales, autor, razón y revisiones. Ni reapertura, reconocimiento de señal ni una importación posterior hacen esa reevaluación silenciosamente.

La evidencia HTTP sintética de 08 produjo 6 incidentes/7 eventos; el score del caso de exfiltración se mantuvo 83 al recibir evidencia durante cierre y pasó a 86 solo con reevaluación explícita, conservando evaluaciones anteriores. Un intento de acción obsoleta devolvió 409 y MTTD/MTTR quedaron No calculable. Los archivos JSON/CSV/PDF y su verificación están en docs/resultados, claramente identificados como sintéticos. No son mediciones de detección IDS ni trabajo humano. [Arquitectura, fórmulas, migración 0008, archivos, pruebas e instrucciones de captura](DASHBOARD_Y_REPORTES.md).

Validación final 08: 106 pruebas aprobadas en SQLite (68.78 s) y 106 en PostgreSQL 16 (383.11 s), con advertencia heredada de Starlette/AnyIO. Build TypeScript/Vite correcto y Compose en 0008. Se verificó persistencia del hash tras recrear API y parada API/PostgreSQL con código 0, conservando volumen y servicios originales. No se realizaron capturas/pruebas de navegador o carga; se incluyen instrucciones reproducibles y los fallos reales corregidos, sin borrar las evidencias de iteraciones previas.

## Seguridad y rendimiento reproducible: iteración 09

La revisión interna reprodujo reflejo de una contraseña sintética en errores de validación, campos extra de login admitidos y NUL aceptado por SmartIR en SQLite. Se añadieron validación sin normalización de entradas válidas, errores sin valores del cuerpo, límites de tamaño/cabeceras/lectura, Host explícito y cabeceras defensivas. JWT sigue con HS256, issuer/audience y 15 minutos, roles/activación de BD y Argon2id, sin cambiar secretos. La configuración local deja de confiar automáticamente en cabeceras de proxy.

Las cuotas y plazas de trabajo son acotadas por proceso; devuelven 429/Retry-After sin una cola global. No constituyen control distribuido ni inmunidad a denegación de servicio. Se revalida autorización al publicar resultados tras cómputo. Los reportes leen una instantánea sin el bloqueo operativo largo y solo serializan su publicación. Los históricos incorporan paginación con navegación en React. FastAPI, Starlette, PyJWT y herramientas de desarrollo se actualizaron tras avisos de dependencias; las consultas finales npm audit/pip-audit no reportaron avisos, sin equivaler a certificación de seguridad.

El protocolo sintético de semilla 202609 se declaró antes de medir: 100/1000/10000 eventos, seis tipos, diez eventos por grupo, solicitudes EVE de hasta 1000 y lotes internos de 100. Se importó/reimportó en bases nuevas aisladas; no se limpiaron tablas de la BD habitual. TestClient mide ASGI sin TCP HTTP; PostgreSQL incluye E/S loopback. No hay ground truth de eficacia IDS ni operadores humanos. Se conservan mediciones iniciales, pares comparativos, errores, duplicados, percentiles de muestras pequeñas y recursos observables.

El perfil inicial identificó ~81.000 sentencias para 10.000 eventos. Prefetch/caché por lote e inserciones agrupadas redujeron el conteo pareado a 3321 SQLite y 3428 PostgreSQL, sin cambiar fingerprints, ventanas, parámetros o evaluaciones. Hashes semánticos de las fases coinciden. Con librerías comunes actualizadas, 10.000 eventos pasaron de 28.95039 a 9.07892 s SQLite y de 101.70874 a 14.88929 s PostgreSQL. Son observaciones de host compartido, no superioridad estadística; varias latencias de dashboard/reportes empeoraron y se publican también. No se interpreta throughput como reducción de MTTD/MTTR.

Validación: 124 pruebas aprobadas por motor (SQLite 76.48 s, PostgreSQL 16 470.08 s), build React correcto, Compose con controles HTTP y parada exit=0 conservando volúmenes/servicios originales. Alembic permanece en 0008: los índices existentes fueron observados mediante EXPLAIN y no se justificó migración 0009. Se conserva advertencia de TestClient/httpx, cuotas no distribuidas, despliegue local y trabajo pendiente en grandes históricos. Métodos, archivos, fuentes, fallos y resultados completos: [SEGURIDAD_Y_RENDIMIENTO.md](SEGURIDAD_Y_RENDIMIENTO.md).

## Consolidación y cierre técnico provisional: iteración 10

Esta fase verificó el repositorio existente y agregó recorridos reproducibles, documentación de operación/despliegue y evidencia TCP/navegador. No cambió el backend, los algoritmos de riesgo/ML, sus evaluaciones congeladas ni las migraciones históricas. React centraliza ahora la URL de API en VITE_API_URL, conservando localhost8000 como default; el arnés utiliza un proxy same-origin hacia su instancia aislada. Playwright es dependencia de desarrollo. No se requirió migración0010: head0008 sigue vigente.

### Trazabilidad de las diez iteraciones

| Iteración | Implementación y resultado principal | Evidencia/alcance |
|---|---|---|
|01|Plataforma FastAPI/PostgreSQL/React, ingestión normalizada y esquema previo|Código y adopción legacy probada en test_api; no se inventa una ejecución01 separada |
|02|Argon2id/JWT/RBAC, usuarios, historial y acciones|AUTENTICACION_Y_RESPUESTA y regresiones actuales |
|03|Ventanas UTC por tipo/IP, fingerprint y riesgo congelado|CORRELACION_Y_RIESGO; extremos/límites/tardíos/migración |
|04|EVE JSONL, taxonomía conservadora y originales/procedencia|INTEGRACION_SURICATA;38 pruebas históricas, regresión10 |
|05|Evaluación emparejada FIFO/SmartIR con referencias separadas|60 casos sintéticos,7/23 vs4/23 críticos conK 10;54 pruebas históricas |
|06|LR/RF interpretables, test por grupos y artefacto JSON seguro|Laboratorio288 casos, macro-F1 .5656/.7086/.4188, crítica31/33 weighted vs23/33 ML;65 pruebas |
|07|Responsables, máquina de estados, ciclos, revisiones y métricas documentales|GESTION_AVANZADA_INCIDENTES;82 pruebas históricas |
|08|Agregación SQL, Recharts, snapshots/PDF y reevaluación explícita|Reportes/hashes reales sintéticos;106 pruebas por motor |
|09|Controles de abuso/seguridad, consultas paginadas y optimización por lotes|124 pruebas por motor; pares ASGI10.000 eventos con igualdad semántica, mejoras y regresiones documentadas |
|10|Integración completa, reinicio conservando datos, Chromium, TCP concurrente y guías|126 pruebas por motor,1test navegador final,61 checks HTTP por base y320 muestras de carga |

Los conteos por iteración son fotografías históricas y no se suman para aparentar una muestra mayor: la suite10 incluye regresiones previas. Tampoco se suman assertions o checks del journey a los casos pytest.

### Flujos completos comprobados

El recorrido parte de una BD nueva con migraciones, crea tres roles y autentica por la API. Importa SmartIR y EVE, repite para deduplicar y conserva evidencia EVE; distingue ventanas/IP y valida desglose weighted-v2. Asigna a analista y recorre Nuevo→Asignado→En análisis→En respuesta→Resuelto→Cerrado, registrando acción y autores. Un evento posterior al cierre produce señal sin recalcular; administrador reabre y el responsable solicita reevaluación explícita con revisión y parámetros congelados. Evaluaciones anteriores permanecen idénticas.

El mismo recorrido consulta filtros analíticos y genera snapshot JSON/CSV/PDF, crea evaluación experimental y laboratorio ML, entrena y compara en test reservado, consulta inferencia cegada y verifica No calculable con motivo. Después de reiniciar Uvicorn compara hashes/conteos de todas las tablas y exportaciones y vuelve a consultar modelo/experimento. El backend conserva sus contratos expected_revision: acciones sin revisión428, obsoletas409.

Los flujos analíticos y experimentales siguen separados. Las características no contienen etiquetas de referencia, grupos/IDs/desenlaces o score ponderado como predictor. Los resultados congelados, a menudo sintéticos, no se filtran como si fueran incidentes operativos actuales. En la interfaz, otros roles pueden inferir sin conocer referencias, pero entrenar/gestionar modelos y consultar métricas etiquetadas requiere administrador investigador. No hay activación ML operacional.

### Resultados y procedencia de la validación10

Suite completa: **126 passed SQLite 102.83 s y126 passed PostgreSQL 16.16 119.27 s**, sin fallos u omisiones. Se conserva advertencia TestClient/httpx. Build TypeScript/Vite correcto,442 módulos,4.56 s; npm ci final correcto. npm audit y pip-audit con dependencias transitivas resueltas/dev no reportaron avisos conocidos a fecha de consulta; no es certificación ni pentest. Compose separado migró a0008, health/web200 y se detuvo conservando volumen; servicios originales no fueron modificados.

Playwright/Chromium 149.0.7827.55 ejecutó un test final con tres roles,14 checks descriptivos, importación de archivos, filtros/estado vacío, responsable/transición/acción/timeline,409 visible por otro escritor y descarga de tres formatos.401 y429 se verificaron también en formulario;403/422 por HTTP desde el navegador. Sin errores JS. Capturas PNG y reportes provienen de esa ejecución, con datos sintéticos y sin credenciales. No se generaron imágenes ficticias ni trazas/HAR con tokens. Los intentos iniciales fallidos de arnés/npm están documentados, sin contarlos como éxitos del producto.

Protocolo TCP previo: seed 202610, una API Uvicorn por condición, PostgreSQL temporal/schemaUUID,40 solicitudes para cada operación×clientes1/5/10/20,100 eventos por solicitud EVE, fixture1000 eventos y cuotas predeterminadas. Total320 solicitudes: **114 éxitos,206 HTTP429,0 HTTP503 y0errores inesperados**. En ingestión, éxitos30/3/3/2; dashboard40/20/8/8. La admisión bajo ráfaga elevada es baja: cumplir los criterios funcionales predeclarados no equivale a satisfacer una demanda de producción. Cada429 tuvo Retry-After; las cargas aceptadas conservaron conteos, duplicados y baseline.

Se publican p50/p95/p99, duración, solicitudes/s, eventos nuevos/s y muestras individuales, incluyendo rechazos. No se midió CPU/RSS del servidor en ese runner. Son ráfagas breves de host compartido, sin repeticiones estadísticas ni carga sostenida. Los resultados09 ASGI no son un control antes/después comparable a TCP10. No se deduce mejora de MTTD/MTTR ni eficacia humana.

### Estado documental, prácticas y límites metodológicos

[VALIDACION_INTEGRAL](VALIDACION_INTEGRAL.md) incluye matriz requisito→componente→prueba→evidencia→estado, entorno, fórmulas de carga, fallos/correcciones y límites. [GUIA_USUARIO](GUIA_USUARIO.md) explica roles, importación, trabajo operativo, modelos y reportes. [GUIA_DESPLIEGUE](GUIA_DESPLIEGUE.md) documenta variables sin secretos, actualización aditiva, liveness/readiness, respaldo y restauración **como procedimiento todavía no ensayado** en esta fase.

Las cinco [prácticas Packet Tracer](PRACTICAS_PACKET_TRACER.md) se ampliaron con topología/puertos, tabla IPv4, configuraciones por dispositivo, teoría, secuencias, pruebas positivas/negativas, criterios, diagnóstico y evidencias que debe entregar otro implementador. Estado de cada una: **DISEÑADA; implementación y validación pendientes**. VLAN/ACL/SSH-AAA/Syslog proporcionan conceptos de intercomunicación, control y observabilidad; la quinta propone traducción **manual y explícita** a JSON de laboratorio. No existe receptor Syslog/IOS en SmartIR, ejecución Suricata en Packet Tracer ni captura EVE real desde esas topologías. No hay `.pkt` ni capturas PT creadas en esta entrega.

Se conserva el bosquejo histórico de prácticas, pero los IDs RPT/RF sin catálogo verificable no sirven para declarar cumplimiento externo. Las referencias Cisco incluidas son primarias y no prueban soporte de todos los comandos del simulador: se exige registrar versión/subset. La antología tampoco contiene una bibliografía fabricada o una aprobación académica inexistente.

La verificación de resultados anteriores compara blobs Git normalizados para CRLF/LF de Windows y registra hashes de disco aparte; un colector preliminar confundió esas representaciones, se conserva y se aclara en el informe. No se reescribieron evidencias históricas. La BD del usuario no se inspeccionó ni modificó; la preservación exhaustiva y reinicios se demostraron en bases aisladas. No se publicaron secretos, dumps o datos reales.

Pendientes: ensayo de restauración, implementaciones PT, otros navegadores/accesibilidad, carga sostenida/multiproceso/proxy, autenticación/defensa distribuidas de producción, validación con datos reales autorizados y ensayos humanos/estadísticos. Las ventanas fijas y los priors de criticidad/contexto conservan sus limitaciones; No calculable permanece como ausencia de evidencia, sin convertirse a cero. El cierre es técnico y provisional, no validación operacional ni aprobación final de esta antología.

## Agente de seguimiento continuo EVE: iteración 11

La nueva etapa añade un proceso Python desacoplado, `agent/smartir_agent`, que utiliza la API EVE existente. No incorpora captura ni un segundo motor de normalización/correlación/scoring. Sus únicas dependencias de ejecución son Python estándar y httpx fijado. FastAPI/PostgreSQL, React, JWT/RBAC, riesgo versionado y ML experimental permanecen en sus módulos anteriores; el inventario verifica que los algoritmos y53artefactos históricos no cambiaron.

La restricción de cuenta `users.eve_only` se añadió mediante Alembic0009, booleano con defaultFalse para todos los usuarios previos. Se conserva la taxonomía de roles: una cuenta analista de servicio restringida solo puede autenticar, consultar su propia identidad e importar EVE. No puede consultar incidentes, operar estados, exportar, entrenar o administrar usuarios; tampoco ser responsable. La restricción se obtiene de BD en cada petición, con revalidación transaccional para mutaciones. Es persistente y no desaparece por perder una lista de configuración. La API de usuarios acepta el campo adicional; los clientes antiguos mantienen comportamiento por defecto. No se editaron migraciones históricas ni contraseñas existentes.

El flujo del agente es archivo regular→lectura binaria de líneas completas→outbox SQLite local durable→JWT de privilegio mínimo→POST EVE→adaptador/fingerprint/evidencia/motor existentes→receipt verificado→commit de checkpoint y auditoría. Solo hay un lote pendiente y un lector con bloqueo del kernel. Guarda generación física, offsets, líneas, request SHA, intentos/deadline y reporte; el payload rechazado permanece en cuarentena local. API y checkpoint no comparten transacción: la semántica es **al menos una vez**, con replay exacto y deduplicación en servidor. Cada reenvío puede añadir otra evidencia aunque no otro Event.

El cliente renueva JWT en memoria, ignora proxies de entorno, no sigue redirects, verifica TLS y rechaza HTTP remoto por defecto. El origen remoto HTTPS requiere configuración explícita. No imprime credenciales, tokens ni cuerpos. Windows requiere ACL adecuadas de los archivos privados; POSIX valida permisos del secreto/directorio. No se presenta el estado como cifrado o inmune a administradores del host.

El lector espera LF y termina generaciones anteriores antes de una rotación inequívoca; soporta cadena numérica de archivos retenidos y detecta brechas observables. Truncamiento, reescritura detectada, generación desaparecida, crecimiento tardío retirado, línea excesiva o respuesta no verificable bloquean el avance. Un reset exige intervención explícita y registra posible pérdida; no fabrica recuperación. Retención append-only y límites locales son condiciones de operación, no garantías de cero pérdida si el productor borra bytes entre sondeos.

| Componente11 | Implementación / evidencia |
|---|---|
|Configuración y transporte|Loopback/HTTPS, TLS obligatorio, secreto fuera de Git, renovación y códigos permanentes/transitorios |
|Estado local y lectura|FULL-sync, application_id, checksum de outbox, bloqueo lector, generaciones/offsets y cuarentena |
|Backend mínimo privilegio|eve_only, auth/me/usuarios, filtros de elegibilidad y actor revalidado; migración0009 |
|Compose opcional|Overlay/perfil eve-agent;3servicios base intactos, sin host-source mounts, UID10001, raíz readonly y capacidades retiradas |
|Pruebas/recorridos|38casos nuevos; procesos HTTP independientes Windows con SQLite/PG; Linux Docker con restart/rotación/cuarentena |
|Documentación|MONITOREO_CONTINUO_SURICATA, índice de evidencias11, guías actualizadas y snapshot JUnit saneado |

Resultados finales: **164pruebas aprobadas SQLite154.44s y164PostgreSQL16.16 223.91s**, sin fallos/omisiones; persiste advertencia TestClient/httpx. Se conserva la primera suite164/164 de114.67/153.48s y los recorridos intermedios. La repetición final incluye auditoría explícita de obtención/renovación JWT y solicitud iniciada, sin secretos. Los ensayos comparten host y no se interpretan esas duraciones como comparación de rendimiento. Build React/TypeScript correcto:442módulos,7.67s. Los recorridos TCP auditados capturaron12eventos sintéticos únicos en5lotes, dos generaciones y15registros no vacíos, incluida cuarentena de dos descartes; tras replay12duplicados quedaron25apariciones EVE. Hubo reinicio del proceso, rotación, API realmente detenida/reiniciada y rechazo de un segundo lector. Los casos401/403/413/429/503/renewal utilizan transporte controlado y están diferenciados de las pruebas TCP reales.

El perfil Linux se probó con estado/input propios en proyectos Compose nuevos:12eventos,13evidencias,3lotes, una cuarentena, reinicio sin replay y rename/create. Se verificaron Linux/Python/UID mediante exec, Alembic0009 y health/web200; se detuvieron solo los proyectos de prueba, conservando sus volúmenes. La BD habitual no se migró ni se cargó; los servicios del usuario no se reconstruyeron. La validación base sin agente también se actualiza al head actual, sin reescribir evidencias10.

Se separan metodológicamente **generación sintética EVE**, **seguimiento automatizado del archivo** y **captura real de tráfico por Suricata**. Solo las dos primeras se ejecutaron. El default de sondeo1s no implica tiempo real estricto: intervienen flush, procesamiento, red, cuota y backoff. No es MTTD/MTTR ni respuesta humana. No se añadieron estadísticas de eficacia IDS, F1 de ML o mejoras experimentales nuevas; las evaluaciones anteriores siguen congeladas. Tampoco se añadió un badge de conectividad React sin heartbeat remoto.

Fallos reales se conservan en el informe: identidad vacía de DirEntry en Windows corregida con os.stat; mock de compresión que descomprimía antes de llegar al cliente corregido a stream crudo. Los intentos fallidos no se suman como éxitos. Fuente, schema de estado, límites, operación, comandos de laboratorio y artefactos: [MONITOREO_CONTINUO_SURICATA](MONITOREO_CONTINUO_SURICATA.md), [índice11](resultados/README_ITER11.md).

Pendientes: sensor real autorizado y su modo concreto de rotación/flush, operación prolongada, archivado/capacidad del estado, DACL Windows exhaustivas, NFS/locks distribuidos, PKI/proxy remoto y supervisión/heartbeat. Las cinco prácticas Packet Tracer continúan diseñadas, sin implementación/capturas nuevas; no existe conector Syslog/IOS ni Suricata dentro de Packet Tracer. Esta antología sigue en revisión y no constituye aprobación final o certificación productiva.

## Iteración 12 — normalización Suricata, magnitudes de criticidad y salida dedicada

Se conserva íntegra la historia01–11. El código inspeccionado distinguía severidad y criticidad del activo, pero React mostraba principalmente esta última. Severity3 ya se normalizaba a40; activo50 era un default desconocido. La categoría vacía de una regla ICMP propia no permitía justificar ninguno de los seis ataques. El usuario reportó cuatro alertas reales; **no se consultaron ni editaron esas filas** durante esta implementación.

El adaptador `suricata-eve-v2` conserva la categoría/firma/SID originales y añade procedencia de clasificación y una política explícita de criticidad de alerta. Categorías conocidas conservan su correspondencia. Solo la firma exacta SMARTIR WSL2 LAB ICMP TEST, protocolo ICMP compatible y categoría vacía/ausente/null se identifican como `prueba_icmp`, auxiliar fuera de la taxonomía de ataques. Otros casos siguen desconocidos con motivo. No se usa una coincidencia parcial para inventar DoS o escaneo.

La prioridad ordinal Suricata se conserva. El índice de alerta mantiene calibración numérica heredada:1→100 Crítica,2→70 Alta,3→40 Media,4–255→10 Baja. Ausente→50 sin nivel atribuible;0 conserva100 por compatibilidad, marcado no estándar. Son parámetros iniciales de ingeniería sin validación empírica, no probabilidades ni impacto observado. EVE no aporta valor del activo:50 continúa predeterminado no observado, hasta disponer de inventario. React presenta firma/SID, prioridad original, índice derivado, activo y advertencia para prueba declarada.

No se recalibra weighted-v2 ni se alteran riesgos/evaluaciones congeladas. En el ensayo, cuatro pruebas producen49.5→50 Alta por la fórmula genérica existente: no significa ataque de riesgo alto. Los metadatos señalan derivación; el campo histórico observed de severity significa disponibilidad de entrada al motor y no verificación de impacto. Tampoco se cambia el comportamiento de correlación/estado ante eventos tardíos.

Fingerprint `suricata-eve-fp-v1` y agente/checkpoint11 permanecen iguales. Reimportar eventos anteriores conserva tipo/metadatos/riesgos y añade evidencia; no hay reclasificación retroactiva ni fusión automática de un incidente desconocido con el nuevo auxiliar. Dos fixtures históricas weighted-v1/v2 prueban esa conservación. El head real sigue0009 (cuentas solo EVE de11), **sin migración nueva**. No se tocaron usuarios/credenciales, ML o experimentos operativos.

Se añade fragmento EVE solo alert y generador de wrapper privado: incluye el principal, preserva sus outputs y agrega un logger regular sin threading, buffer0 y permisos600. No sobreescribe el principal, inicia sensores ni modifica systemd; detecta cambios de hash/outputs y rechaza configuraciones ambiguas. Las listas no se anexan con un simple include, por eso se conserva explícitamente la lista. Hay instrucciones WSL2, validación -T y condiciones de permisos/rotación. Cambiar el archivo seguido requiere nuevo directorio de checkpoint, conservando el anterior.

Se encontró Suricata8.0.3 en Ubuntu WSL2 y se validó dos veces **offline**, con -T y -r sobre cuatro tramas ICMP construidas por código, SID9900012 sintético y direcciones de documentación. No hubo captura de interfaz ni tráfico enviado. El general produjo4 alert+1 flow; el dedicado solo4 alert. El principal del usuario no se leyó/modificó; se utilizó base/rule privada del repositorio. El PCAP es determinista; flow_id EVE puede cambiar entre ejecuciones, lo cual se registra mediante hashes diferentes.

| Validación12 | Resultado comprobado |
|---|---|
| Suites completas, incluido historial01–11 | **198 aprobadas SQLite,198 PostgreSQL16.16**;34 casos nuevos parametrizados |
| Duraciones de suites compartiendo host | SQLite138.44s, PG192.01s; no equivalen a benchmark de rendimiento |
| Agente Windows real y API aislada, SQLite/PG |4 nuevos,1 incidente,1 lote confirmado, reinicio sin replay, repetición4 duplicados y evidencia preservada |
| Chromium149 con datos offline en PG |Analista/observador, filtro UTC/tipo, separación de magnitudes,0 errores JS; captura auténtica solo de evento sintético |
| React/TypeScript |Build correcto,443 módulos,Vite6.4.6,6.52s |
| Compose separado |PG16.16, head0009, health ok y web200; proyecto de prueba detenido sin eliminar volumen |

Dos fallos iniciales del arnés esperaban un campo inexistente del reporte EVE; se corrigieron las aserciones sin cambiar la API. Persiste deprecación TestClient/httpx. Los resultados anteriores no se sustituyen; el manifiesto compara objetos Git de evidencia histórica, agente, migraciones y algoritmos conservados. No se probó captura real, configuración principal, todas las rutas Windows/WSL, eficacia de reglas, calibración en redes reales ni MTTD/MTTR. Las cuatro alertas anteriores conservan su política v1. No se añade una séptima clase ML ni se afirma generalización.

Metodología, archivos, contratos y reproducción: [NORMALIZACION_SURICATA](NORMALIZACION_SURICATA.md). Resultados JSON/CSV, fuentes sintéticas exactas, hashes, captura real de Chromium y matriz de evidencias: [índice12](resultados/README_ITER12.md). La relación con las cinco prácticas Packet Tracer continúa conceptual: todas **DISEÑADAS**, no implementadas/validadas; este ensayo no crea integración IOS/Syslog ni topologías .pkt. La antología continúa **en revisión**, sin aprobación final.

## Iteración13 — rediseño estructural y continuidad de sesión

La inspección identificó un JWT guardado únicamente en useState, perdido al recargar, y una composición que colocaba todas las funciones y el detalle de incidente en una sola página. Se separa montaje, autenticación, navegación, estructura visual, filtros, tabla, panel y páginas. Se mantienen React/TypeScript, Recharts y los módulos experimentales; no se añaden dependencias de frontend ni se reconstruye el backend operativo.

El espacio SOC contiene barra lateral y encabezado compacto con identidad/rol. El resumen limita sus indicadores a una cohorte explícita de30 días y muestra actividad/incidentes recientes. La cola tiene filtros combinables y paginación; el detalle contextual se abre sobre esa misma vista. Analítica/reportes, importación, evaluación y ML tienen rutas independientes. Rutas hash y parámetros de filtro/incidente conservan contexto tras recarga; no guardan credenciales. Las secciones experimentales se cargan diferidas y conservan sus restricciones de referencias/entrenamiento.

La sesión web se restaura con GET /api/auth/session y cookie HttpOnly, SameSite Strict, host-only, path/api y vencimiento absoluto900s. Secure se exige para HTTPS y HTTP solo se admite en loopback. POST sesión y DELETE logout verifican Origin exacto y cabecera personalizada; todas las escrituras por cookie mantienen el mismo control. Login y cuota Argon2 se reutilizan; JWT/RBAC/usuario activo se comprueban en el servidor. El contrato POST /api/auth/login Bearer del agente no cambia. No se agregó refresh ni revocación centralizada: logout borra la cookie actual, una copia robada del JWT conservaría validez hasta expiración. La interfaz no almacena tokens en localStorage/sessionStorage ni registra contraseñas.

Un proxy del mismo origen evita que JavaScript maneje el JWT. Vite apunta a127.0.0.1:8000 en ejecución independiente; Compose configura el target interno api:8000, conservando Host. No se abren puertos nuevos ni se cambian secretos, usuarios existentes o volúmenes. No se añade migración: head0009. La configuración sigue siendo un prototipo local; HTTPS remoto, dominio/proxy de producción y revocación central requieren diseño adicional.

El panel usa diálogo modal, foco, Escape, retorno al origen y scroll propio. Distingue resumen/riesgo, eventos/evidencia y gestión; esta última separa respuesta, historia y métricas. Evidencia original y procedencia se consultan junto al evento con paginación y JSON acotado. Se preservan firma/SID, prioridad Suricata original, criticidad de alerta derivada, activo predeterminado/no observado, tipo auxiliar prueba_icmp y advertencias de laboratorio. No se alteran valores weighted-v1/v2, algoritmos ML ni evaluaciones congeladas.

La validación encontró y corrigió una salida de foco del diálogo, desbordamiento móvil de un texto accesible absoluto, pérdida de campos durante la actualización de detalle y exclusión del minuto actual por truncar el fin del periodo en la UI. El resumen usa el periodo preciso del servidor y los formularios muestran el minuto siguiente como fin inicial. El arnés de proxy se corrigió para conservar Host y se adaptaron las pruebas antiguas a la navegación y cookie, conservando sus aserciones. Los intentos fallidos se documentan, no se suman como aprobados.

Las suites completas obtuvieron **211 aprobadas SQLite (134.89s) y211 PostgreSQL16.16 (207.15s)**, con la advertencia TestClient/httpx existente. Los recorridos Chromium comprueban tres roles, sesión tras recarga, vencimiento real de un JWT de fixture5s, logout, controles visibles, filtros, detalle, evidencia,409,422,429, teclado y tamaños1440/820/390. El recorrido integral histórico conserva61 operaciones API, reinicio/snapshots, importaciones y reportes; la regresión de Suricata usa el archivo sintético offline de12 y no afirma nueva captura. Compose aislado valida migración, health y sesión a través del proxy. Las cifras finales de navegador/build, capturas y manifiestos están en [índice13](resultados/README_ITER13.md).

Limitaciones: Chromium solamente, revisión de contraste por pares de tokens, sin certificación WCAG/lector de pantalla, sin despliegue público ni auditoría externa. Los borradores no se guardan al abandonar una sección. Cookie no se aísla por puerto y el entorno local debe ser confiable. No se midió eficacia IDS, MTTD/MTTR humano ni rendimiento nuevo. Los datos habituales se conservaron sin usarlos como fixtures y sus servicios no se reconstruyeron. Las cinco prácticas Packet Tracer permanecen **DISEÑADAS**, sin ejecución/capturas nuevas; esta antología sigue **en revisión**.
