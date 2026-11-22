# Iteración 09 — Seguridad, robustez y rendimiento

## Alcance y modelo de amenazas

Se inspeccionaron security.py, modelos/esquemas, main.py, ingestión SmartIR/EVE, lifecycle, reportes, experimentos, ML, migraciones, Compose, dependencias y pruebas antes de cambiar código. Base: commit **71494b9**, iteración 08. Se mantienen FastAPI, PostgreSQL 16, SQLAlchemy, Alembic, React/TypeScript, Argon2id, JWT/RBAC, algoritmos y datos históricos. No se reconstruye la aplicación.

Se consideran clientes locales sin autenticar, entradas malformadas, intentos repetidos de login, tokens manipulados/inactivos, abuso de operaciones costosas por usuarios autenticados y cabeceras de proxy/Host falsas. No se presupone que un administrador de BD o del sistema operativo sea un atacante contenido por la API. No es auditoría externa, certificación de seguridad, ensayo con operadores ni prueba ofensiva contra sistemas ajenos.

Las pruebas usan esquemas/archivos/contenedores aislados. No se cargan eventos de benchmark ni se limpian tablas en la BD habitual del usuario. No se modificaron .env, secretos, contraseñas, datos anteriores, modelos o evaluaciones existentes. Las credenciales aleatorias de los entornos nuevos de prueba no se exportan.

## Hallazgos reproducidos y correcciones

| Evidencia inicial | Corrección y alcance |
|---|---|
| Un error 422 de login devolvía en input una contraseña sintética demasiado larga | Handler de validación devuelve solo ubicación/tipo/mensaje genérico; elimina input y contexto, también en otros endpoints |
| Login aceptaba campos inesperados | SafeInput exige extra=forbid y texto UTF-8 sin NUL |
| SmartIR aceptaba texto NUL en SQLite, incompatible con PostgreSQL | Se rechaza antes de persistir. No se recortan ni normalizan cadenas válidas: se preservan fingerprints históricos |
| No había limitación de login/operaciones costosas | Ventanas de solicitudes, admisión no bloqueante por recurso y 429 con Retry-After |
| Crear reportes retenía el bloqueo operativo durante agregaciones | Lectura MVCC independiente; únicamente la inserción final/revalidación del autor usa el bloqueo corto |
| Ingestión ejecutaba decenas de miles de consultas para 10.000 eventos | Prefetch de fingerprints/ventanas, caché fuerte de incidentes por lote, inserciones por etapas FK y consultas agrupadas de evidencias/eventos |
| Listados históricos sin límites y /api/stats cargando objetos completos | Paginación, conteos SQL y metadata de lista sin recorrer relaciones por incidente |
| Cabeceras reenviadas podían influir en la IP vista por Uvicorn por defecto | Arranque local con --no-proxy-headers; middleware usa scope.client, no X-Forwarded-For |
| Versiones instaladas con avisos en catálogos de dependencias | Actualización compatible y repetición de auditorías, conservando los algoritmos ML |

La reproducción inicial dio **3 fallos en 2.55 s**: contraseña sintética reflejada, campo extra admitido y NUL admitido. Las pruebas nuevas pasan después. Nunca se usaron contraseñas reales para esa demostración.

JWT conserva HS256 explícito, issuer/audience y 15 minutos; el rol se consulta en BD, no se confía en claims de rol. Usuarios inactivos se rechazan. Tokens de más de 4096 caracteres se rechazan y sub tiene longitud acotada. Las operaciones costosas mantienen los permisos previos: entrenamiento/experimentos/etiquetas y exportaciones de investigación solo administrador; importación/reportes operativos, escritores; consulta operativa, autenticados. Se revalida autorización al publicar resultados tras computación, con rollback si el autor fue desactivado/degradado. No hay refresh tokens, revocación individual, MFA o rate limiting distribuido.

## Límites de abuso y concurrencia

Ventana deslizante de **60 segundos**, reloj monotónico, almacenamiento acotado a 4096 buckets por proceso. Los buckets expirados se retiran; al agotar capacidad se rechaza, sin expulsar buckets activos para permitir evadir cuotas. No se registra contraseña ni token como clave. No se bloquean cuentas permanentemente.

| Operación | Cuota | Máximo simultáneo por proceso |
|---|---|---|
| Login | 20 por IP real/minuto | 2 operaciones Argon2, compartidas con administración de contraseñas |
| Importación SmartIR/EVE | 30 por usuario/minuto | 2 |
| Generación/importación experimental y entrenamiento | 12 por administrador/minuto | 1 |
| Crear reporte | 10 por escritor/minuto | 2 |
| Exportar/revisar comparaciones guardadas | 30 por usuario autorizado/minuto | 2 |
| Dashboard/listado/estadísticas y lecturas lifecycle protegidas | 120 por usuario/minuto | 4 |
| Administración con coste de contraseña | 10 por administrador/minuto | 2 |

Autorización precede a la admisión de trabajo costoso; un observador no ocupa plazas de entrenamiento. Al agotarse la cuota se devuelve **429**, Retry-After=ceil(instante de liberación−ahora), mínimo 1 segundo. Si no hay plaza de recurso se devuelve 429/Retry-After=1, sin esperar en una cola global. Las plazas se liberan también ante excepciones. React muestra Retry-After y no reintenta escrituras automáticamente.

Las cuotas son **locales al proceso**: varios workers multiplican cuotas/plazas y no comparten contadores. Un reinicio pierde contadores; IP compartida/NAT puede afectar a varios usuarios. Detrás de proxy, el modo predeterminado cuenta la IP del proxy. Si se habilitan cabeceras en otro despliegue, deben aceptarse solo desde proxies explícitamente confiables y con acceso directo a la API restringido; no usar forwarded-allow-ips='*'. No se añadió Redis ni otro servicio.

Las mutaciones conservan el bloqueo transaccional de coherencia de 07/08, necesario para deduplicación/cierre/asignación concurrentes. PostgreSQL limita espera de bloqueo a 2 s; lecturas de instantánea usan statement_timeout=15 s. Se responde 503/Retry-After=1 ante esos conflictos temporales, sin devolver SQL/valores. El timeout es **por sentencia**, no un presupuesto total de toda la petición. No se sustituyó la serialización de datos por un simple bloqueo en memoria.

## Entradas, respuestas y despliegue local

- Login: cuerpo máximo 4096 bytes; administración: 16 KiB; JSON general: 32 KiB; SmartIR: 5 MiB, además de 1000 eventos; datasets: 2 MiB.
- EVE conserva su lectura por lotes, 10 MiB, 64 KiB/línea, 10000 registros y lotes internos de 100; se mantiene el reporte parcial anterior. No se prebufferiza arbitrariamente todo un EVE.
- Longitud incoherente, Content-Length duplicado/inválido o combinado con Transfer-Encoding: 400. Espera del próximo fragmento: máximo 10 s, con 408. La espera no incluye el cómputo de ingestión; lotes ya confirmados pueden permanecer y la repetición es idempotente.
- Cabeceras totales hasta 16 KiB (431 si excede); ruta hasta 512 caracteres (414). Los límites ASGI no sustituyen protección de transporte/proxy. Uvicorn limita concurrencia a 32 conexiones/tareas; su sobrecarga devuelve 503, distinta del rate limiting 429.
- Host se valida antes de reconstruir URL: nombres locales permitidos por defecto localhost, 127.0.0.1, ::1 y api; se rechazan separadores, userinfo, puertos inválidos y duplicados. SMARTIR_ALLOWED_HOSTS permite una lista literal explícita para otro despliegue, sin modificar secretos. No se utiliza request.url.path para decidir permisos.
- API: nosniff, DENY, no-referrer, Permissions-Policy restrictiva, Cache-Control=no-store y CSP sin contenido activo. Swagger mantiene sus recursos para uso local. CORS sigue limitado a localhost/127.0.0.1:5173 y expone Retry-After y cabeceras de exportación. Se deshabilitó Server en Uvicorn.
- Vite recibe cabeceras defensivas de desarrollo. Compose publica API/web solo en 127.0.0.1 y no publica PostgreSQL. **Compose sigue siendo desarrollo local**, con Vite dev server. Un despliegue productivo requiere servir dist mediante hosting estático apropiado, HTTPS/proxy confiable y política de cabeceras propia; no se proporciona una instalación productiva certificada ni se confunde npm run build con ella.

Paginación compatible en forma de respuesta (arrays), con cambio deliberado de alcance predeterminado: /api/incidents, 100 por defecto/máximo 1000; datasets/experimentos, 50/máximo 100; versiones ML, 20/máximo 50; offset hasta 100000. Detalle de incidente: events_offset y events_limit, 100 por defecto/máximo 500; event_count conserva el total. React permite recorrer eventos y cargar más catálogos. No se eliminan registros para cumplir límites. Los endpoints analíticos mantienen las reglas de 08.

## Dependencias y fuentes

`npm audit --json` se ejecutó: **0 avisos reportados** en la consulta. Se fija Vite 6.4.6 también en el manifiesto; ya estaba en el lockfile. Esa versión figura entre las corregidas para [GHSA-p4f5-76q4-ffq7, aviso oficial Vite](https://github.com/vitejs/vite/security/advisories/GHSA-p4f5-76q4-ffq7). No se ejecutó la prueba ofensiva del aviso.

`pip-audit 2.10.1` informó inicialmente **53 registros en 5 paquetes**, con IDs duplicados; no son 53 vulnerabilidades distintas demostradas en esta aplicación. Paquetes señalados: pip 24.0, PyJWT 2.10.1, pytest 8.3.4, setuptools 79.0.1 y Starlette 0.41.3. El export inicial conserva IDs/aliases/fixes y checksum del resultado original, omitiendo descripciones con ejemplos de JWT. El original local no fue alterado.

Starlette estaba en rangos afectados por [multipart grande](https://github.com/Kludex/starlette/security/advisories/GHSA-2c2j-9gv5-cj73), [Range en FileResponse](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8) y [Host/URL](https://github.com/Kludex/starlette/security/advisories/GHSA-86qp-5c8j-p5mr). La API no usa request.form/UploadFile ni FileResponse para estas importaciones/exportaciones; no se afirmó una explotación de esos componentes. Se actualizó el marco compatible y se añadió defensa Host propia.

Versiones fijadas: **FastAPI 0.165.0, Starlette 1.10.0, PyJWT 2.15.1**; desarrollo: pytest 9.0.3, setuptools 84.1.0, pip 26.3 y pip-audit 2.10.1. Se verificaron requisitos oficiales de compatibilidad; Pydantic sigue en 2.10.3. Scikit-learn 1.6.1, NumPy 2.2.3, SciPy 1.15.2 y algoritmos/riesgos permanecen iguales. El build Docker actualiza pip dentro de la imagen, sin cambiar credenciales.

Segunda consulta de pip-audit: **0 avisos reportados**. Eso describe los catálogos/versiones consultados; no demuestra ausencia de vulnerabilidades desconocidas, fallos de configuración o problemas de negocio. No fue un escaneo de infraestructura ni auditoría externa. Exportaciones reales: iter09_auditoria_npm.json, iter09_auditoria_python_inicial.json e iter09_auditoria_python_final.json.

## Protocolo reproducible del benchmark

El protocolo y sus criterios se escribieron en `benchmarks/protocol_iter09.json` **antes de la primera medición**. No hubo preregistro externo. Semilla **202609**, tamaños 100/1000/10000, seis categorías explícitas, severidades EVE 1–3, IP de laboratorio, UTC y texto SYNTHETIC BENCHMARK ONLY. Diez eventos por grupo; grupos con atributos propios y tiempos fuera de orden dentro de cada solicitud. No son capturas IDS, etiquetas de referencia, entrenamiento ML ni incidentes de personas.

| Eventos | Solicitudes EVE por fase | Registros máximos/solicitud | Lotes internos |
|---|---|---|---|
| 100 | 1 | 100 | 1 |
| 1000 | 1 | 1000 | 10 |
| 10000 | 10 | 1000 | 100 |

Cada escenario importa y reimporta exactamente los mismos bytes/sensor; espera N importados, N duplicados y N eventos persistidos, con 2N apariciones de evidencia. Se esperan 10/100/1000 incidentes y seis tipos presentes. Ventana 900 s. Consulta por event_timestamp [2026-01-01,2026-01-03). No se supera el límite de 2000 incidentes del reporte.

Se miden por separado importación nueva, repetición, 10 consultas de dashboard, 3 creaciones de reporte y 3 descargas de cada formato. Concurrencia **1**: es perfil secuencial reproducible, no saturación multiusuario. TestClient ejecuta la API ASGI en proceso: incluye validación, autorización, SQL y serialización, **excluye TCP HTTP**; PostgreSQL sí incluye E/S loopback hacia Docker. Preparar esquema/usuario/token queda fuera del tiempo de importación; el token no se exporta. La generación acotada de bytes durante la fase sí forma parte del tiempo total nuevo; las latencias por solicitud empiezan con el bloque preparado.

Fórmulas: throughput=N/segundos de la fase nueva; p50/p95/p99 por interpolación lineal en (n−1)*p sobre latencias observadas. Con n=1 (importaciones de 100/1000) los tres percentiles coinciden; con n=3/10 no caracterizan colas de producción. CPU/RSS son del proceso Python cliente+ASGI; RSS Windows proviene de GetProcessMemoryInfo. No se midieron CPU/RAM del servidor PostgreSQL. Su CPU no puede compararse con SQLite como coste total de BD. El peak RSS es acumulado del proceso, no memoria exclusivamente atribuible a una operación.

Criterios previos: cero errores HTTP inesperados; importados/duplicados/persistencia exactos; seis tipos; throughput >=20 eventos/s; dashboard p95 <=5 s; creación/exportación p95 <=10 s; peak RSS observado <=2 GiB cuando disponible. La comparación exige además igualdad de bytes sintéticos y hash semántico (fingerprints, asociación a ventanas, riesgos/evaluaciones y multiplicidad de evidencias). No cambia umbrales después de ver resultados.

Cada ejecución usa un SQLite nuevo bajo .test-runs o un esquema PostgreSQL bench_UUID nuevo en **localhost:55438/smartir_test**. La URL habitual se sustituye antes de importar la aplicación. No hay parámetro de destino HTTP arbitrario, limpieza/truncado o DROP en el runner. Los esquemas duran hasta el ciclo de vida del contenedor temporal; los archivos SQLite quedan en .test-runs. No se eliminan volúmenes del usuario. Los resultados existentes no se sobrescriben: usar otra etiqueta de ejecución.

## Entorno observado y comparación

Host reportado Windows 10.0.26300, AMD Ryzen 5 5600H with Radeon Graphics, **12 procesadores lógicos**, RAM física **7.883.206.656 bytes**. Python **3.11.15**, SQLite **3.50.4**, SQLAlchemy **2.0.36**. PostgreSQL **16.16**, x86_64 Alpine, en Docker. Host compartido con los servicios originales: no se controla toda actividad externa al proceso. El arranque de Compose usa Python 3.12 y Node 22 de sus imágenes; esas imágenes no se confunden con el proceso local del benchmark.

La primera exploración, con librerías anteriores, midió 10.000 eventos en 24.9116 s SQLite y 128.0873 s PostgreSQL; archivos baseline sin sufijo paired. Se conservan y **no se usan para ratios contra la fase actualizada**.

Para el par comparativo se archivó el código 71494b9 de solo lectura, sin checkout/revertir archivos, y se ejecutaron ambos códigos con las **mismas librerías actualizadas** y el mismo protocolo. Esto separa el cambio de aplicación del cambio de versiones. Semillas/bytes coinciden. Los hashes semánticos de las fases coinciden en todos los tamaños. Excluyen UUID y marcas de inserción generadas en cada ejecución, no contenido ni evaluaciones.

| BD | Eventos | Antes s | Después s | Antes eventos/s | Después eventos/s | SQL importación antes → después |
|---|---:|---:|---:|---:|---:|---:|
| SQLite | 100 | 0.19010 | 0.05543 | 526.04 | 1804.20 | 483 → 13 |
| SQLite | 1000 | 2.65335 | 0.75940 | 376.88 | 1316.83 | 8049 → 329 |
| SQLite | 10000 | 28.95039 | 9.07892 | 345.42 | 1101.45 | 81114 → 3321 |
| PostgreSQL | 100 | 0.68180 | 0.13511 | 146.67 | 740.13 | 483 → 14 |
| PostgreSQL | 1000 | 10.39866 | 1.59271 | 96.17 | 627.86 | 8048 → 345 |
| PostgreSQL | 10000 | 101.70874 | 14.88929 | 98.32 | 671.62 | 81114 → 3428 |

En ambos motores y todas las fases: **0 errores HTTP inesperados**, duplicados exactamente N, persistencia N e identidad semántica verificada. Todos los criterios declarados se cumplieron en estas ejecuciones. Ratios observados para 10.000: 3.19x SQLite y 6.83x PostgreSQL; son descripciones de una ejecución por fase, no superioridad estadística o generalización a una red real.

Latencias **después**, escenario 10.000; segundos redondeados (datos completos en JSON/CSV):

| Operación | SQLite p50 / p95 / p99 | PostgreSQL p50 / p95 / p99 |
|---|---|---|
| Solicitud de importación, 1000 registros | 0.92232 / 1.15618 / 1.17541 | 1.44144 / 1.61718 / 1.62736 |
| Dashboard | 0.58577 / 0.67090 / 0.68304 | 0.25138 / 0.28534 / 0.29997 |
| Crear snapshot | 0.61601 / 0.62628 / 0.62719 | 0.30547 / 0.32814 / 0.33015 |
| Descargar JSON | 0.01220 / 0.01889 / 0.01948 | 0.01998 / 0.02813 / 0.02885 |
| Descargar CSV | 0.01974 / 0.02881 / 0.02962 | 0.02958 / 0.04286 / 0.04404 |
| Descargar PDF | 0.95113 / 0.95711 / 0.95764 | 1.02915 / 1.15215 / 1.16308 |

No todas las cifras mejoraron. En PostgreSQL 10.000, dashboard p95 pasó de 0.27088 a 0.28534 s, creación de 0.21813 a 0.32814 s y PDF de 1.02555 a 1.15215 s. SQLite 100 también empeoró dashboard p95. No se ocultan esas observaciones ni se atribuyen a una causa única con tan pocas muestras; el objetivo medido de optimización fue ingestión.

Recursos del conjunto de operaciones del caso 10.000: SQLite, CPU de proceso 21.344 s y peak RSS 267.829.248 bytes; PostgreSQL, CPU de proceso 14.453 s y peak RSS 255.967.232 bytes. Incluyen cliente/ASGI, duplicados, consultas y exportaciones; excluyen el servidor PG. No son duración de ingestión pura ni carga humana. En el diagnóstico SQL bruto, la etiqueta export_pdf incluye las consultas finales de verificación; **las latencias de descarga se cronometraron antes de esas consultas**. El conteo SQL comparado de importación no incluye esa verificación.

## Optimización e índices

El perfil inicial identificó ~81.000 sentencias para 10.000 registros. Se agrupan búsquedas de fingerprints/ventanas (fragmentos de 400 para límites de bindings), se reutilizan objetos de incidente dentro del lote, se insertan padres/eventos/evidencias en etapas FK y se consultan en conjunto señales pendientes/eventos de incidentes afectados. Se reutiliza el evaluador existente; no se cambia fórmula, taxonomía, frontera UTC, fingerprint, número de evaluaciones por lote o evidencia por aparición. Las carreras siguen protegidas por el bloqueo de BD y restricciones UNIQUE.

EXPLAIN sobre las bases sintéticas verificó índices existentes: fingerprint, incident_id, event_timestamp, received_at, created_at y uq_incident_window. PostgreSQL usó índices para búsquedas puntuales de fingerprint/correlación; para rangos que cubren prácticamente toda la tabla eligió secuencial. No se interpreta un Seq Scan amplio como un índice ausente. Planes observados en iter09_indices_observados.json.

**No se necesita migración 0009**: no se añadieron tablas/columnas/índices sin evidencia. Alembic permanece en **0008** y se conservan todas las migraciones previas. Tampoco se modifican risk.py, correlation.py, ml_engine.py o artefactos históricos.

## Procedimiento y archivos de evidencia

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
# Solo BD temporal de pruebas; nunca DATABASE_URL habitual:
docker run --detach --rm --name smartir-iter09-test --tmpfs /var/lib/postgresql/data -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=smartir_test -p 127.0.0.1:55438:5432 postgres:16-alpine
.venv\Scripts\python benchmarks/run_load.py --phase baseline --baseline-ref 71494b9 --run-label local01
.venv\Scripts\python benchmarks/run_load.py --phase optimized --run-label local01
.venv\Scripts\python benchmarks/run_load.py --phase baseline --baseline-ref 71494b9 --postgres-isolated --run-label local01
.venv\Scripts\python benchmarks/run_load.py --phase optimized --postgres-isolated --run-label local01
# compare_runs.py recibe ambos JSON y un prefijo de salida nuevo.
```

Usar otra run-label si existen salidas. Si el puerto está ocupado, identificar primero el servicio; no reutilizar la base habitual ni detener servicios ajenos. En esta ejecución se reutilizó exclusivamente el servidor temporal de pruebas de 08 en ese puerto; cada escenario creó un esquema nuevo.

Evidencias realmente generadas: baseline iniciales, pares baseline/optimized por BD, comparaciones, CSV consolidado `iter09_mediciones_pareadas.csv`, auditorías, planes y comprobación HTTP. `compare_runs.py` deriva ratios y verifica identidad a partir de JSON existentes; no genera tiempos. `summarize_runs.py` exporta las observaciones registradas, no estimaciones. CPU/RSS ausentes quedarían null/vacíos, no cero.

## Pruebas y validación reales

```powershell
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter09-release-sqlite --junitxml=.test-runs/iter09-release-sqlite.xml
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@localhost:55438/smartir_test'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider --basetemp .test-runs/iter09-release-pg --junitxml=.test-runs/iter09-release-pg.xml
Push-Location frontend
npm ci
npm run build
npm audit --json
Pop-Location
.venv\Scripts\python -m pip_audit --format json
```

Resultados finales: **124 passed en SQLite, 76.48 s; 124 passed en PostgreSQL 16, 470.08 s**. Una advertencia de Starlette indica deprecación de httpx en TestClient y recomienda httpx2; no es fallo de prueba. Se conserva el cliente existente compatible, sin ocultar la advertencia.

Cobertura: regresiones 01–08, autenticación/tokens/roles/inactivos, validación sin credenciales reflejadas, tamaños, 429/Retry-After, expiración exacta de ventana sin sleep, X-Forwarded-For, Host malformado, capacidad de buckets, plazas no bloqueantes/liberación ante errores, lectura agotada, cuotas de cómputo, reportes sin bloqueo largo, revalidación del autor, duplicados en mismo lote y concurrentes con evidencias, paginación, generador/percentiles e invariantes históricas/migraciones.

Un ensayo intermedio dio **121 aprobadas/1 fallo**, SQLite 92.48 s y PostgreSQL 477.57 s: el límite inicial de seis solicitudes de investigación agotaba una prueba con siete intentos. Se ajustó a doce y la prueba dirigida pasó junto con controles (19 pruebas, 12.39 s), antes de las suites finales. Los fallos iniciales de auditoría no se presentaron como éxitos.

Build final: **TypeScript y Vite 6.4.6 correctos**, 441 módulos, **3.87 s**, sin advertencia de chunk >500 kB. Compose se construyó/arrancó en proyecto aislado smartir-iter09 (puertos 58009/55179), PostgreSQL healthy, API health correcto, web HTTP 200 y Alembic 0008. HTTP directo verificó 100 importados/100 duplicados, observador 403, Host inválido 400, NUL 422, error sin contraseña reflejada y login 429 con Retry-After observado **56 s**, pese a variar X-Forwarded-For. No apareció Server; CSV/JSON/PDF se descargaron. MTTD/MTTR quedaron No calculable. Registro: iter09_http_verificacion.json.

API y PostgreSQL de Compose terminaron con **exit=0, OOMKilled=false**. Se conservó smartir-iter09_postgres_data. El servidor efímero de pytest/benchmarks se detuvo al finalizar, sin eliminar volúmenes existentes. Los servicios originales smartir-net-mvp continuaron activos. No se afirma navegación integral en puertos alternativos: la UI conserva API localhost:8000/CORS 5173. No se ejecutaron capturas de navegador ni carga distribuida/TCP sostenida.

## Límites y trabajo pendiente

Archivos de implementación: backend/app/abuse.py y validation.py nuevos; cambios en security.py, schemas.py, main.py, ingestion.py, lifecycle.py/lifecycle_api.py, analytics_api.py, evaluation_api.py y ml_api.py. Se actualizan requirements.txt/requirements-dev.txt, Dockerfile, conftest.py y se agrega test_security_controls.py. Frontend: main.tsx, MachineLearning.tsx, Evaluation.tsx, vite.config.ts y manifiesto/lockfile. Nuevos scripts/protocolo en benchmarks y resultados en docs/resultados; README, antología y continuidad de documentación 08 actualizados. No hay nueva migración ni cambios en archivos de evaluaciones históricas.

El prototipo no queda declarado libre de vulnerabilidades. Persisten despliegue local sin HTTPS administrado, ausencia de MFA/revocación individual, cuotas no distribuidas, cuotas compartidas por NAT, límites por proceso, ausencia de auditoría externa y falta de ensayos de saturación/múltiples workers. Las cuotas son parámetros iniciales de ingeniería, no umbrales validados universalmente.

La agregación legacy global /operations/metrics conserva consultas por incidente, protegidas por admisión y presupuestos por sentencia; su optimización agregada y paginación de timelines requieren medición adicional. El evaluador todavía puede cargar eventos existentes de incidentes afectados: episodios individuales enormes pueden necesitar agregados SQL compatibles. No se hizo benchmark de cientos de miles/millones, durabilidad bajo caída, red/almacenamiento físico del servidor PG, ni envejecimiento de snapshots. Nada de esto se sustituye por los resultados favorables de 10.000 eventos.

**Duración de ingestión, throughput y latencias ASGI no son MTTD/MTTR**, tiempos de detección IDS, eficacia de ML o respuesta de operadores. Esas métricas mantienen sus requisitos de evidencia y algoritmos versionados anteriores.
