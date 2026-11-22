# Iteración 03: correlación temporal y riesgo explicable

## Algoritmo temporal

Versión `utc-tumbling-v1`. Ventanas fijas, alineadas al epoch Unix UTC, inicialmente de 900 segundos. Configuración: `CORRELATION_WINDOW_SECONDS` en el entorno de la API (entero entre 1 y 86400); Compose lo toma de `.env`, con 900 por defecto. Un valor inválido impide arrancar. No se usa la hora de recepción para agrupar.

Para un timestamp UTC `t`, epoch `E` y ancho `W`:

```
inicio = E + floor((t - E) / W) * W
intervalo = [inicio, inicio + W)
atributos = (tipo exacto, IP origen normalizada, IP destino normalizada)
clave = SHA256(JSON([versión_correlación, tipo, origen, destino]))
identidad = (clave, inicio, W)
```

El cálculo usa aritmética de datetime/timedelta, sin redondeo flotante. El tipo es obligatorio, sensible a mayúsculas y se compara exactamente. Las direcciones IPv4/IPv6 se validan y normalizan con `ipaddress`: representaciones IPv6 equivalentes comparten grupo. IP ausente, null o cadena vacía se trata como desconocida (`null`) al correlacionar. Desconocida coincide solo con desconocida en esa posición; nunca actúa como comodín. No se inventa una IP ni se deduce del mensaje. Esto puede agrupar eventos de equipos desconocidos en una misma ventana y es una limitación explícita.

Cada fecha debe contener zona horaria; se convierte a UTC. Ejemplos para W=900:

| Eventos con los mismos atributos | Resultado |
|---|---|
| 18:00:00 y 18:14:59.999999 UTC | Mismo incidente |
| 18:14:59.999999 y 18:15:00 UTC | Incidentes distintos |
| 18:00 UTC hoy y 18:00 UTC mañana | Incidentes distintos |
| 12:01:00-06:00 y 18:02:00Z | Misma ventana UTC |
| Mismos tiempos, distinto origen, destino o tipo | Incidentes distintos |

Las ventanas no se deslizan ni se encadenan. Dos eventos muy cercanos a ambos lados de un límite quedan separados; es una decisión deliberada que hace la partición independiente del orden de llegada. No se juntan sesiones separadas por más de W. Dos episodios dentro de la misma ventana y con los mismos atributos todavía pueden quedar juntos.

## Eventos tardíos, desorden e idempotencia

No hay watermark ni descarte por antigüedad: un evento tardío se agrega al incidente de su ventana de tiempo de evento o crea uno si no existe. No mueve eventos previos ni fusiona incidentes. El estado operativo existente, incluso Cerrado, permanece; el nuevo evento genera otra evaluación del riesgo sin reabrir automáticamente el caso. Eventos fuera de orden producen la misma partición y puntuación final, aunque la secuencia de evaluaciones intermedias refleja los lotes realmente recibidos.

Se conserva la función de fingerprint anterior: SHA-256 del evento serializado por Pydantic, JSON con claves ordenadas. No se alteran ni reescriben los fingerprints antiguos. La repetición del mismo payload validado no crea eventos, historial ni evaluaciones nuevos. Diferentes representaciones de un timestamp o una IP, o cambios de mensaje, pueden tener fingerprints diferentes aunque correlacionen en el mismo incidente; la idempotencia es por payload, no por equivalencia semántica. La normalización de IP se utiliza para agrupar, sin modificar la representación del payload original.

La importación completa es transaccional. PostgreSQL usa un bloqueo asesor transaccional compartido por todos los workers de esta API para serializar importaciones, incluida deduplicación, creación de incidentes y scoring. SQLite usa BEGIN IMMEDIATE en pruebas. El índice único de fingerprint sigue siendo la última defensa. Se conserva el límite de 1000 eventos por lote. Escrituras externas que omitan estos bloqueos no están soportadas.

Cambiar W no reagrupa datos anteriores: las nuevas importaciones usan la nueva partición y los incidentes anteriores mantienen W. Reimportar un evento ya conocido sigue siendo duplicado aunque cambie W. Por ello, durante un cambio de configuración pueden coexistir incidentes con ventanas diferentes; no hay una migración automática entre particiones.

## Priorización explicable

Versión `weighted-v1`. Parámetros iniciales de ingeniería, sin validación científica ni afirmaciones de eficacia experimental:

```
S = máxima severidad de los eventos
A = máxima criticidad del activo
R = min(100, 20 * número_de_eventos)
T = tabla de tipo de ataque (40 para tipo no reconocido)
C = 50 por política neutral cuando el contexto es desconocido
total = .35*S + .25*A + .15*R + .15*T + .10*C
score = limitar(round_half_up(total), 0, 100)
```

Se usa Decimal para contribuciones y redondeo a entero, con mitades hacia arriba. Esta regla sustituye el redondeo bancario implícito del prototipo y se registra en parámetros. Prioridades: Baja 0–24, Media 25–49, Alta 50–74, Crítica 75–100.

Tabla inicial T: acceso_no_autorizado=75, malware=90, dos=80, escaneo=45, uso_indebido=55, exfiltracion=100. El contexto permanece desconocido: se registra `known=false`, la política y un aporte de 5 puntos. No se agrega contexto ficticio al evento. No hay un campo de contexto nuevo en el contrato de importación. La criticidad omitida conserva el default histórico del endpoint (50); tampoco constituye una medición de red.

Ejemplo con dos eventos dos, severidad máxima 80 y criticidad máxima 60: S aporta 28, A 15, R=40 aporta 6, T=80 aporta 12 y C=50 aporta 5. Total=66, score=66, prioridad Alta. Con todos los valores observables al máximo, cinco eventos exfiltracion y contexto desconocido: 35+25+15+15+5=95. Un evento desconocido con S=A=0 da 0+0+3+6+5=14. El rango de representación es 0–100; con esta política y los tipos actuales, los extremos reales están restringidos por el prior de contexto y la recurrencia.

`explanation` incluye `algorithm_version`, copia completa de `parameters`, número de eventos, `factors` con valor/peso/contribución/observed, política de contexto, puntuación sin redondear, puntuación final y prioridad. La tabla de ataque y sus valores son una transformación de ingeniería del tipo informado, no una medición física. `observed=false` identifica el contexto y el tipo desconocido; los factores conocidos pueden ser agregaciones o transformaciones de los campos recibidos.

## Reproducibilidad e historial de riesgo

Cada incidente nuevo congela sus parámetros en `risk_parameters` al crearse. Agregar eventos usa esos parámetros, aunque cambien los defaults del proceso. El evaluador verifica la versión congelada; una versión no soportada falla explícitamente en lugar de sustituirla por otra fórmula. Una futura versión debe conservar su implementación para evaluar incidentes existentes o incorporar una migración explícita.

Cada lote con eventos nuevos añade una fila en `risk_evaluations` por incidente afectado, con fecha UTC, versión, explicación completa, número de eventos, score y prioridad. No hay endpoints de edición o borrado. `incidents.score/priority/explanation` siguen siendo la evaluación más reciente para mantener la API y dashboard. Las evaluaciones anteriores no se sobrescriben; cambios de estado no recalculan riesgo y reimportaciones duplicadas tampoco. Para reconstruir un cálculo basta con los valores agregados y parámetros guardados; no se conserva una lista de IDs de eventos por evaluación ni un log inmutable contra administradores de la base.

## Migración 0003 y datos heredados

Requiere 0002. Ejecutar `alembic upgrade head` con respaldo y escrituras detenidas. Agrega columnas nullable a incidents: versión de correlación, origen, inicio/ancho de ventana y parámetros de riesgo. Sustituye el índice UNIQUE global `ix_incidents_correlation_key` por un índice normal y agrega el índice único compuesto `uq_incident_window(clave,inicio,ancho)`. Este cambio de índice es necesario para múltiples incidentes históricos de los mismos atributos; no se elimina ninguna tabla ni dato. La migración no reconstruye tablas, ni reasigna eventos o claves existentes.

Los incidentes heredados quedan con metadatos temporales null y la API los identifica como `legacy`. Se excluyen de la nueva correlación. Se conserva exactamente su score, prioridad, explicación, estado, eventos, acciones e historial. Se copia una evaluación `legacy-unknown` con sus valores originales; no se inventan parámetros históricos. Su fecha de snapshot es la ejecución de la migración, no la fecha histórica del cálculo. El fingerprint evita volver a importar eventos originales en grupos nuevos.

No hay downgrade destructivo; restaurar un respaldo si es necesario revertir. Verificado tanto desde 0002 como desde el esquema MVP sin tabla Alembic. No se tocaron volúmenes existentes ni se cambiaron contraseñas.

## API y frontend

POST `/api/events/import` conserva ruta, cuerpo y respuesta (`imported`, `duplicates`, `incidents_updated`), JWT y permisos administrador/analista. El número de incidentes puede cambiar porque ahora cuenta origen y ventana. El ejemplo original produce cuatro eventos y **cuatro incidentes** por tener IP de origen distintas. La segunda importación produce cuatro duplicados.

GET `/api/incidents` y GET `/api/incidents/{id}` agregan origen, versión de correlación e inicio/ancho de ventana; explanation es ahora estructurada para incidentes nuevos. Los heredados conservan su explicación original. GET `/api/stats` refleja la nueva cantidad de grupos. Nuevo GET `/api/incidents/{id}/evaluations`: historial de evaluaciones, permitido a todos los roles autenticados. Estados, usuarios, historial operativo, acciones y sus permisos no cambian.

React conserva login, métricas, importación, listado y formularios con permisos. Agrega filtros combinables por prioridad, tipo y estado (en cliente) y una tabla de factores en el detalle, con score, prioridad y JSON completo para inspeccionar parámetros. Distingue las explicaciones heredadas.

## Archivos de la iteración

- `backend/app/correlation.py`, `risk.py`: algoritmos separados y parámetros versionados.
- `backend/app/main.py`, `models.py`: integración, validación de IP/fecha, bloqueo de importación, snapshots y endpoint de evaluaciones.
- `backend/migrations/versions/0003_temporal.py`: columnas, índices y snapshots de riesgo heredados.
- `backend/tests/test_temporal_risk.py`: ventana, límites exactos, IP, UTC, tardíos, duplicados, extremos, parámetros congelados y preservación de datos.
- `backend/tests/conftest.py`, `test_api.py`: fixtures por revisión Alembic y expectativas de la correlación nueva.
- `frontend/src/main.tsx`: filtros y desglose explicable, preservando permisos.
- `compose.yaml`, `.env.example`: ventana configurable; ejemplo sin secretos.
- `README.md`, `docs/ANTologia_implementacion.md`, este documento: operación, capítulo de implementación y evidencia.

## Pruebas y verificación real

Desde la raíz en PowerShell (dependencias existentes de requirements-dev.txt):

```powershell
New-Item -ItemType Directory -Force .test-runs | Out-Null
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter03-final
```

Resultado: **14 passed, 1 warning in 12.00s**, SQLite temporal.

```powershell
docker run --detach --rm --name smartir-iter03-test -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55433:5432 postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55433/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter03-postgres
docker stop smartir-iter03-test
```

Resultado: **14 passed, 1 warning in 63.01s** con PostgreSQL 16. Contenedor temporal sin volumen, trust solo para pruebas en loopback; la instalación habitual exige contraseña. La advertencia es la deprecación de BlockingPortal en Starlette TestClient. La primera ejecución SQLite dio 13 passed y 1 failed: un JSON literal del fixture SQL fue interpretado como parámetro `:true`; se corrigió usando un parámetro enlazado y se repitieron ambas suites. No quedan fallos de pytest.

Desde frontend, `npm run build`: TypeScript y Vite 6.4.6 completados, 26 módulos. No hay pruebas automatizadas de navegador.

Compose arrancó con `docker compose -p smartir-iter03 -f compose.yaml -f .test-runs/compose-iter03.yaml up --build -d`, usando credenciales aleatorias solo en el entorno del proceso de prueba, volumen/proyecto independientes y override de puertos 58003 (API), 55173 (web). Se observaron los tres servicios arriba, PostgreSQL healthy, `/health` correcto, frontend HTTP 200, `/api/incidents` sin token HTTP 401 y `alembic current` = **0003 (head)**. El override sustituye ports mediante `!override`; requiere Compose moderno. Se detuvieron los servicios de prueba sin eliminar el volumen `smartir-iter03_postgres_data`. No se verificó navegación autenticada en esos puertos: el frontend mantiene la URL habitual localhost:8000; los flujos autenticados se verificaron mediante pytest.

## Limitaciones y secretos

Ventanas fijas con separación artificial en límites, coincidencias posibles entre equipos de IP desconocida, sin watermark/retención/paginación y con serialización global de importaciones (menor capacidad de procesamiento). No se han medido rendimiento ni concurrencia bajo carga. Los filtros operan sobre todo el listado recibido. Se conserva el resto de limitaciones de autenticación documentadas en la iteración anterior.

Se encontró un valor con apariencia de secreto JWT en el archivo de ejemplo y se retiraron los valores de configuración antes del commit. Si se utilizó o compartió, debe rotarse; borrar del archivo no borra su exposición anterior. No se modificó `.env` ni ninguna contraseña real, ni se publican sus valores en esta documentación.
