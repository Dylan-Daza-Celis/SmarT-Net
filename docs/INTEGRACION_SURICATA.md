# Iteración 04: integración de Suricata EVE JSON

## Alcance y arquitectura

Se conserva FastAPI, SQLAlchemy, PostgreSQL, Alembic, React/TypeScript, JWT y RBAC. Se añade un adaptador de archivos EVE JSON Lines, centrado en registros `event_type=alert`. No se ejecuta Suricata ni se configura captura de tráfico desde esta aplicación.

```
Archivo UTF-8 JSONL -> Request.stream -> lector acotado por línea
 -> validación EVE -> categoría explícita -> EventIn + evidencia
 -> ingestion.ingest (compartido con JSON SmartIR)
 -> deduplicación -> correlación UTC -> evaluación versionada -> PostgreSQL
```

`schemas.py` conserva el esquema de la importación SmartIR. `ingestion.py` contiene el único pipeline de persistencia, correlación, auditoría de creación y scoring. El endpoint normalizado conserva su cuerpo, respuesta y algoritmo histórico de fingerprint. `suricata.py` transforma los registros EVE y `eve_import.py` controla lectura, límites y lotes.

Referencias de formato: [EVE JSON de Suricata](https://docs.suricata.io/en/suricata-8.0.3/output/eve/eve-json-format.html) y [clasificaciones de OISF](https://github.com/OISF/suricata/blob/main/etc/classification.config). La correspondencia hacia SmartIR y la escala de severidad son políticas del proyecto, no equivalencias oficiales ni parámetros científicamente validados.

## Campos y transformaciones

| Campo EVE | Destino y validación |
|---|---|
| timestamp | event_timestamp; texto ISO 8601 con zona obligatoria, convertido a UTC |
| event_type | Debe ser texto; únicamente alert se importa en esta iteración |
| src_ip / dest_ip | source_ip / destination_ip; IPv4/IPv6 normalizadas; ausentes o null permitidas, cadena vacía inválida |
| src_port / dest_port | adapter_metadata.source_port / destination_port; entero 0–65535, no booleanos ni cadenas numéricas |
| proto | adapter_metadata.protocol; texto de 1–32 caracteres o null |
| alert.signature | message y adapter_metadata.signature; texto de hasta 2000 caracteres o null |
| alert.signature_id | adapter_metadata.signature_id; entero sin signo de 32 bits o null |
| alert.category | adapter_metadata.category y política de clasificación; texto de hasta 255 caracteres o null |
| alert.severity | adapter_metadata.suricata_severity, entero 0–255 o null; transformación a severity 0–100 |
| Campos adicionales | Se conservan en el JSON original, sin inferencias automáticas |

`alert` debe ser un objeto, aunque puede estar vacío. Si faltan signature, category, severity, direcciones, puertos o protocolo, no se inventan valores de origen. Timestamp, event_type y el objeto alert son obligatorios para alertas. Las fechas sin zona horaria se rechazan; no se supone la zona del servidor. Se aceptan offsets como `-0600`, `+0000` y `Z`. Los tipos son estrictos; por ejemplo `"severity":"1"` es inválido. Se rechazan JSON con claves repetidas, NaN/Infinity, texto UTF-8 inválido, NUL o sustitutos Unicode no representables. BOM UTF-8 se permite al inicio de la primera línea física.

Una prioridad Suricata numéricamente menor representa mayor urgencia. Política inicial de conversión: 0/1 → 100, 2 → 70, 3 → 40, 4–255 → 10. Si falta, severity=50 con `severity_defaulted=true`. La escala original permanece en metadata y en el evento original. Esta escala es una decisión explícita de ingeniería y no una medición de impacto.

EVE no informa criticidad del activo. Se aplica **asset_criticality=50 como predeterminado no observado**, con `asset_criticality_observed=false` y política `unknown_default_50` en metadata. El endpoint SmartIR también registra si la criticidad se suministró explícitamente; un valor suministrado es una declaración, no una medición verificada. Los eventos anteriores a 0004 conservan null en ese indicador: procedencia no registrada.

## Correspondencia de categorías

Comparación exacta tras quitar espacios exteriores y aplicar casefold. Se admiten el shortname y las descripciones listadas en `CATEGORY_GROUPS`; no se buscan palabras clave en signature ni se interpreta que un alert confirma un ataque exitoso.

| Tipo SmartIR | Categorías aceptadas (shortnames) |
|---|---|
| acceso_no_autorizado | attempted-admin, successful-admin, attempted-user, successful-user |
| malware | trojan-activity, command-and-control |
| dos | attempted-dos, successful-dos, denial-of-service |
| escaneo | network-scan |
| uso_indebido | policy-violation, inappropriate-content |
| exfiltracion | data-exfiltration / Data Exfiltration: **categoría personalizada explícita**, no una clasificación estándar garantizada por Suricata |

Las descripciones EVE de estas categorías también se reconocen: por ejemplo, `A Network Trojan was detected` se transforma en malware. El diccionario completo y sus alias están versionados en `backend/app/suricata.py`. Categorías genéricas como información filtrada, tráfico sospechoso, misc-attack o categorías locales no listadas quedan como **desconocido**, incluso si signature contiene palabras como malware o exfiltration. No se confunde una fuga genérica de información con exfiltración confirmada.

`desconocido` es un marcador fuera de la taxonomía de seis tipos, visible en filtros y metadata con `matched=false`; no se descarta la evidencia. El motor existente aplica su peso de tipo desconocido (40). La política es `exact_category_v1`, adaptador `suricata-eve-v1`.

## Ejemplo sintético de entrada y salida

Entrada ilustrativa, no captura real:

```json
{"timestamp":"2026-11-21T12:00:00-0600","event_type":"alert","src_ip":"192.0.2.10","dest_ip":"198.51.100.20","src_port":42000,"dest_port":443,"proto":"TCP","alert":{"signature":"SYNTHETIC example, not IDS capture","signature_id":9900002,"category":"A Network Trojan was detected","severity":1},"synthetic":true}
```

Evento normalizado (los datos EVE extraídos se adjuntan aparte como metadata):

```json
{"source":"suricata:lab01","event_timestamp":"2026-11-21T18:00:00+00:00","source_ip":"192.0.2.10","destination_ip":"198.51.100.20","event_type":"malware","severity":100,"asset_criticality":50,"message":"SYNTHETIC example, not IDS capture"}
```

La criticidad 50 de esta salida es un valor predeterminado. La evidencia conserva la línea original, sin sustituirla por el JSON normalizado. Con un solo evento así, el score inicial es `35 + 12.5 + 3 + 13.5 + 5 = 69`, prioridad Alta, con contexto desconocido y criticidad predeterminada identificados.

## Evidencia, procedencia y fingerprints

Cada evento nuevo guarda la primera línea EVE original en `events.raw_event` y los campos extraídos/políticas en `adapter_metadata`. `event_evidence` registra cada aparición válida, también las duplicadas: event_id, import_id, archivo, sensor declarado, número de línea, autor autenticado, fecha UTC, línea original y SHA-256 de esa línea. El nombre de archivo es solo metadata y nunca se utiliza como ruta de escritura. El sensor es una etiqueta declarada por el importador, no identidad criptográficamente verificada de un IDS.

La línea preservada excluye únicamente el delimitador LF; conserva CR de CRLF, espacios y BOM. Su hash corresponde a esos bytes UTF-8. No es el hash del archivo completo ni una cadena de custodia resistente a cambios por un administrador de base de datos. Líneas inválidas o eventos no alert no se almacenan: el reporte identifica sus posiciones, por lo que debe conservarse el archivo fuente para investigar descartes.

Fingerprint EVE: SHA-256 de JSON canónico de `["suricata-eve-fp-v1", sensor_id, objeto_original]`, con claves ordenadas, separadores compactos y escapes ASCII. No incluye nombre de archivo, número de línea, lote, ni versión de clasificación. Cambiar orden de claves, indentación exterior en la línea, CRLF o BOM no crea otro evento. Cambiar sensor, un valor o un campo adicional sí puede crearlo. Offsets textuales diferentes del mismo instante e IP con representaciones textuales diferentes también pueden generar huellas distintas, aunque correlacionen juntas. No se deduplica solo por SID o flow_id: distintas alertas reales pueden compartirlos.

Los fingerprints SmartIR anteriores mantienen exactamente SHA-256 de `json.dumps(EventIn.model_dump(mode="json"), sort_keys=True)`; no se actualizan huellas ni eventos existentes. Los espacios de identidad EVE y SmartIR son distintos. Exportar un registro a otro formato y volver a importarlo no garantiza deduplicación entre formatos.

## Endpoint y procedimiento

`POST /api/events/import/eve?filename=eve.json&sensor_id=lab01`, administrador o analista con Bearer. Observador recibe 403 y sin sesión se recibe 401. El cuerpo es el **archivo directamente**, no multipart ni un arreglo JSON. Tipos aceptados: application/x-ndjson, application/jsonl, application/octet-stream, application/json, text/plain. El contenido sigue siendo JSONL aunque se llame eve.json. Un tipo MIME distinto devuelve 415. Sensor: 1–80 caracteres alfanuméricos o `_.:-`; default suricata. Archivo: 1–255 caracteres sin controles U+0000–U+001F, default eve.json.

```powershell
# Obtener SMARTIR_TOKEN mediante el login existente; no guardarlo en Git.
curl.exe -X POST "http://localhost:8000/api/events/import/eve?filename=suricata_sintetico.eve.jsonl&sensor_id=lab01" -H "Authorization: Bearer $env:SMARTIR_TOKEN" -H "Content-Type: application/x-ndjson" --data-binary "@examples/suricata_sintetico.eve.jsonl"
```

En React: iniciar sesión → elegir Suricata EVE JSON Lines → indicar sensor estable → seleccionar archivo. Se envía el File como cuerpo, sin file.text() para EVE. Se muestra importados, duplicados, descartados, desconocidos, lotes y errores con línea/código. El cliente impide archivos mayores a 10 MiB y el backend aplica su propio límite. En detalle, Evidencia consulta `GET /api/events/{id}` y las primeras diez procedencias; `GET /api/events/{id}/evidence?offset=0&limit=50` permite paginación hasta 100. Ambos GET están disponibles para los tres roles autenticados. No hay endpoints de edición de evidencia.

`examples/suricata_sintetico.eve.jsonl` contiene seis alertas, una por tipo, con `synthetic=true`, firmas y dataset etiquetados como sintéticos. Usa IP reservadas para documentación y SIDs de demostración. En una base sin esos eventos: primera importación 6 importados, 0 duplicados, 0 descartados y 6 incidentes; segunda con el mismo sensor: 0 importados y 6 duplicados. El endpoint `POST /api/events/import` sigue funcionando para el formato SmartIR.

## Límites, errores y transacciones

| Límite backend | Valor |
|---|---|
| Archivo recibido | 10 MiB (10 × 1024 × 1024 bytes) |
| Línea sin delimitador LF | 64 KiB |
| Registros no vacíos procesados | 10000 |
| Lote de registros válidos | 100 |
| Errores detallados en respuesta | 100; se cuenta el resto en errors_omitted |

El lector usa Request.stream, un buffer de línea acotado y un lote acotado; no utiliza UploadFile/multipart, request.body ni lectura total del archivo. Al exceder una línea, consume hasta su LF y continúa con las siguientes. Las líneas vacías se ignoran sin contar como registro, conservando la numeración física. UTF-8 puede cruzar bloques de transporte. Un EOF sin LF también se procesa.

Respuesta completada HTTP 200, incluso si hubo descartes. Incluye import_id, imported, duplicates, discarded, processed, unknown, batches, bytes_received, discard_reasons, errors, errors_omitted y complete. Cada registro procesado cuenta exactamente como importado, duplicado o descartado. unknown cuenta apariciones válidas no clasificadas, incluidas duplicadas. `unsupported_event_type` se cuenta como descarte, sin tratarlo como JSON inválido. Los errores identifican línea y código y, cuando procede, nombres de campos; no devuelven el contenido íntegro rechazado.

Al exceder bytes o registros: HTTP 413, `complete=false`, reporte parcial con lo conservado. Se procesan las líneas completas dentro del prefijo permitido y se confirma también el último lote pendiente válido; el resto no se cuenta como procesado ni descartado. bytes_received puede superar el límite porque incluye el bloque de transporte donde se detectó. El servidor deja de consumir el archivo. No hay garantía de rollback de todo el archivo: cada lote es atómico y los lotes anteriores permanecen. Un error de base de datos o desconexión puede impedir entregar el reporte y dejar únicamente los lotes ya confirmados; reintentar es idempotente para eventos. Las apariciones de evidencia sí aumentan al reintentar.

El servicio compartido serializa importaciones con el mismo bloqueo asesor PostgreSQL de la iteración 03; no duplica reglas de correlación o scoring. Cada lote con eventos nuevos agrega una evaluación por incidente afectado; un archivo grande puede generar varias evaluaciones intermedias. Lotes de solo duplicados agregan procedencia, pero no riesgo ni historial operativo nuevos.

## Riesgo, criticidad e incidentes heredados

La fórmula numérica y los pesos no cambian. Nuevos incidentes usan `weighted-v2`: el factor de criticidad registra basis=supplied, policy_default_50 o legacy_untracked. Se revisan los eventos que aportan la criticidad máxima: si alguno carece de procedencia, se declara legacy_untracked; si alguno es predeterminado, no se marca toda la contribución como observada. La UI muestra el origen por evento y basis del factor.

Incidentes con parámetros congelados weighted-v1 conservan exactamente su versión y semántica anterior al recibir nuevos eventos; no se reescriben evaluaciones históricas para corregir etiquetas antiguas. Sus registros nuevos sí tienen indicadores de procedencia consultables. El evaluador admite ambas versiones y falla ante una desconocida. Los pesos siguen siendo parámetros iniciales de ingeniería.

La correlación continúa con ventanas fijas UTC `[inicio, fin)` de 15 minutos por defecto, tipo/origen/destino; no se agregan puertos ni firma a la clave. Alertas de reglas distintas pueden compartir incidente. Dos eventos cercanos a ambos lados del límite quedan separados, y episodios dentro de la misma ventana pueden agruparse. IP ausente solo coincide con ausente. Eventos tardíos usan tiempo de evento, pueden actualizar casos cerrados sin reabrirlos y no se descartan por antigüedad. Cambiar ancho no reagrupa datos previos. Los incidentes legacy anteriores a 0003 permanecen excluidos de la correlación nueva.

## Migración 0004 y archivos

`0004_suricata.py` parte de 0003: agrega a events dos columnas nullable (`asset_criticality_observed`, `adapter_metadata`) y crea event_evidence con claves foráneas a events/users e índices por evento e importación. No elimina ni reconstruye tablas, no cambia credenciales, no reasigna incidentes, no modifica fingerprints, usuarios o evaluaciones. No inventa procedencia retroactiva. Respaldar y detener escrituras durante `alembic upgrade head`; conservar volúmenes y contraseña del PostgreSQL existente. Downgrade destructivo deshabilitado.

Archivos nuevos: backend/app/schemas.py, ingestion.py, suricata.py, eve_import.py; backend/migrations/versions/0004_suricata.py; backend/tests/test_suricata.py; examples/suricata_sintetico.eve.jsonl; este documento. Modificados: backend/app/main.py, models.py, risk.py; backend/tests/test_api.py; frontend/src/main.tsx; README.md; docs/ANTologia_implementacion.md. No se agregaron dependencias ni se cambió el stack.

## Validación y limitaciones

Las pruebas usan fixtures temporales y ejemplos sintéticos; no se presentan como capturas de un IDS real. Desde la raíz, PowerShell:

```powershell
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter04-final
```

Resultado: **38 passed, 1 warning in 14.11s**, con SQLite temporal. Para PostgreSQL:

```powershell
docker run --detach --rm --name smartir-iter04-test -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55434:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55434/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter04-pg
docker stop smartir-iter04-test
```

Resultado: **38 passed, 1 warning in 94.65s**, PostgreSQL 16. El modo trust se limita al contenedor temporal sin volumen, expuesto solo en loopback; no es la configuración de la instalación habitual. Cada prueba crea y retira su propio esquema de prueba. Se verificaron adaptador, tipos estrictos, UTC, IP, seis categorías, desconocidos, duplicados estables, evidencia de reimportaciones, errores, límites, lotes, roles, compatibilidad del endpoint anterior y conservación de todas las columnas originales de usuarios, eventos, incidentes, acciones, historial y evaluaciones al actualizar desde 0003. También se verificó que evaluaciones v1 permanezcan sin reescritura. La advertencia en ambas suites es la deprecación de BlockingPortal desde Starlette TestClient.

Se reforzó después la prueba de lotes para dividir cada carácter UTF-8 multibyte entre bloques de un byte. Ejecución dirigida de `backend/tests/test_suricata.py::test_stream_batching_limits_and_recovery`: **1 passed, 1 warning in 0.80s** en SQLite y **1 passed, 1 warning in 5.26s** en PostgreSQL. No cambió código de aplicación tras las suites completas.

`npm run build` desde frontend completó TypeScript y Vite 6.4.6, 26 módulos (1.02 s de build Vite). No se ejecutaron pruebas de navegador.

Compose: `docker compose -p smartir-iter04 -f compose.yaml -f .test-runs/compose-iter04.yaml up --build -d`, con proyecto/volumen nuevos y puertos de prueba 58004 para API y 55174 para web. El override usa `ports: !override` y no altera compose.yaml ni los servicios del usuario. Se usaron credenciales aleatorias solo en el entorno del proceso para la instalación de prueba, sin modificar .env ni contraseñas existentes. Resultado observado: los tres servicios arriba, PostgreSQL healthy, `/health` correcto, frontend HTTP 200, consultas sin token HTTP 401 y `alembic current` = **0004 (head)**. Se creó una cuenta exclusiva del entorno de prueba para comprobar importación autenticada: primera solicitud **6 importados, 0 duplicados, 0 descartados**; segunda **0 importados, 6 duplicados, 0 descartados**. Los servicios se detuvieron sin eliminar el volumen `smartir-iter04_postgres_data`. La interfaz conserva localhost:8000 como URL API; en los puertos aislados se comprobó HTTP e importación por API, sin navegación autenticada del navegador.

Fallos corregidos durante la ejecución: la primera regresión dio 13 passed/1 failed porque una prueba esperaba todavía head=0003; se actualizó la expectativa. La primera suite ampliada dio 37 passed/1 failed: el fixture destinado a probar v1 había eliminado category del segundo evento y, correctamente, creó un incidente desconocido diferente. Se corrigió el fixture para mantener la categoría. Se repitieron las suites completas sobre ambas bases con los resultados anteriores; no quedan pruebas fallidas.

No se soportan arrays JSON, ficheros comprimidos ni ingestión en vivo. Los tipos EVE distintos de alert se descartan. Las categorías locales no listadas quedan desconocidas; exfiltración requiere la categoría personalizada explícita. No se verifica la autenticidad del sensor ni la cadena de custodia contra administradores de base. Usar la etiqueta predeterminada suricata para varios sensores comparte su espacio de deduplicación: declarar un identificador estable y distinto por sensor. El sensor participa en el fingerprint pero no en la clave temporal del motor existente. Las ocurrencias duplicadas consumen almacenamiento de evidencia. No hay retención automatizada ni pruebas de navegador/carga. El scoring existente consulta todos los eventos del incidente para agregar factores: el lector de archivos es acotado, pero incidentes muy grandes aún requieren trabajo de optimización. Siguen vigentes las limitaciones de autenticación ya documentadas (sin MFA, recuperación ni rate limiting de login).
