# Diseño e implementación de SmartIR-Net — estado acumulado hasta iteración 04

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

Tablas actuales: events, incidents, users, incident_history, response_actions, risk_evaluations y event_evidence. Los estados son Nuevo, Asignado, En análisis, En respuesta, Resuelto y Cerrado; cada cambio exige justificación y guarda autor, fecha y estado previo. Se permiten saltos y reaperturas. Asignado no implementa todavía una relación con un responsable. Las acciones son registros, no comandos ejecutados en dispositivos.

Alembic 0001 adopta el esquema original; 0002 agrega autenticación e historial operativo; 0003 introduce ventanas y evaluaciones de riesgo; 0004 agrega metadata y procedencia EVE. Las migraciones preservan datos, claves, usuarios y evaluaciones. No se eliminan volúmenes ni se cambian contraseñas al actualizar. Los downgrades destructivos están deshabilitados: se requiere respaldo y recuperación explícita.

## Interfaz, evidencias y límites de validación

React conserva login, métricas, filtros combinables por prioridad/tipo/estado, detalle de factores, historial y formularios según rol. Incorpora selector de formato, sensor declarado, reporte de importación y consulta de evidencia. El backend decide siempre los permisos; ocultar controles no sustituye la autorización.

Los resultados reales y comandos de la iteración actual se registran en [INTEGRACION_SURICATA.md](INTEGRACION_SURICATA.md), junto con campos, ejemplos, límites, archivos y endpoints afectados. La validación de iteración 03 quedó documentada como evidencia histórica, no se reutiliza como prueba de esta integración. No se han hecho pruebas de navegador, validación científica del scoring, pruebas de carga ni captura IDS real. Permanecen pendientes HTTPS gestionado por el despliegue, MFA, recuperación de contraseña, ingestión en vivo, otros tipos EVE, retención y optimización para incidentes muy grandes. No se implementaron entrenamiento ML ni métricas formales MTTD/MTTR.
