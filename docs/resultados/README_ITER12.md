# Evidencia de la iteración 12

Ejecuciones del 22-11-2026, America/Mexico_City; artefactos fechados en UTC (23-11). No se inspeccionaron los cuatro eventos operativos del usuario ni se capturó tráfico real. Todos los datos publicados son de **laboratorio sintético**. Los resultados de iteraciones anteriores permanecen intactos.

| Verificación realizada | Resultado y evidencia |
|---|---|
| Suite completa SQLite | **198 aprobadas**, 0 fallos/errores/omisiones, 138.44 s |
| Suite completa PostgreSQL 16.16 | **198 aprobadas**, 0 fallos/errores/omisiones, 192.01 s |
| Casos nuevos de normalización/compatibilidad/configuración | 34 casos parametrizados incluidos en cada suite; test_suricata anterior también pasa |
| React/TypeScript, npm run build | Correcto, Vite6.4.6, 443 módulos, 6.52 s; hashes de artefactos en manifiesto |
| Suricata8.0.3 WSL2 | Dos ejecuciones reales de `-T` y `-r` sobre PCAP sintético: exit0 en ambas; **sin interfaz en vivo** |
| Outputs simultáneos Suricata | Base general:4 alert+1 flow; logger dedicado:4 alert exclusivamente; base de laboratorio inalterada |
| Agente Windows + API SQLite aislada | 4 importados, 1 incidente, restart sin replay, 4 duplicados en repetición explícita |
| Agente Windows + API PostgreSQL aislada | Mismo resultado; JWT real con cuenta temporal solo EVE |
| Chromium149.0.7827.55 + API PostgreSQL | 1 caso real con analista y observador, filtro UTC/tipo, firma/SID, índices separados y ausencia de controles de escritura para observador; 0 page_errors |
| Compose separado | API/web/PG arrancaron; health ok, web200, Alembic0009, PostgreSQL16.16; solo se detuvo el proyecto de prueba, conservando volumen |
| Historia / algoritmos / agente | Comparación de objetos Git en manifiesto; no se reescribieron resultados anteriores, motor ponderado, correlación, ingestor, ML, agente ni migraciones |

Las dos suites comparten host; sus tiempos no son un benchmark comparativo de motores. Hay una advertencia de deprecación FastAPI TestClient/httpx, sin fallo. Primeras ejecuciones completas:197/197 aprobadas (117.36s SQLite;164.68s PG); luego se agregó una prueba de alteración de logger y se repitió todo. Dos fallos previos del arnés nuevo por esperar un campo inexistente del reporte EVE se corrigieron, sin modificar el contrato del producto.

Las duraciones de la tabla son las impresas por pytest; el JUnit registra138.407s y191.988s para cada testsuite, y se conservan esos valores exactos en JSON/CSV. No se ajustaron artificialmente para hacer coincidir ambas mediciones internas.

## Archivos publicados

| Artefacto | Procedencia / alcance |
|---|---|
| [iter12_validacion_final.json](iter12_validacion_final.json), [CSV](iter12_validacion_final.csv) | Metadatos JUnit reales saneados, casos, versiones, hashes, conservación de históricos y fuentes; no stdout de pruebas ni credenciales |
| [iter12_suricata803_offline_1.json](iter12_suricata803_offline_1.json), [segunda ejecución](iter12_suricata803_offline_2.json) | Resultados medidos del motor8.0.3 en WSL2, hashes y conteo de outputs; nunca configuración principal |
| [EVE sintético emitido por motor, ejecución1](iter12_eve_SINTETICO_OFFLINE_motor_1.jsonl), [ejecución2](iter12_eve_SINTETICO_OFFLINE_motor_2.jsonl) | Bytes auténticos de salida del motor desde PCAP **construido**, no tráfico capturado; direcciones reservadas, SID9900012 sintético |
| [Pipeline SQLite](iter12_pipeline_sqlite_final.json), [CSV](iter12_pipeline_sqlite_final.csv) | Primera fuente offline → agente Windows sin cambios → API aislada;4 eventos,2259 bytes confirmados,1 lote, evidencia duplicada y score congelado |
| [Pipeline PostgreSQL](iter12_pipeline_postgresql_final.json), [CSV](iter12_pipeline_postgresql_final.csv) | Mismo recorrido con primera fuente offline sobre PG16.16 |
| [Pipeline PostgreSQL con interfaz](iter12_pipeline_postgresql_interfaz.json), [CSV](iter12_pipeline_postgresql_interfaz.csv) | Segunda fuente offline y repetición del recorrido; añade prueba real de navegador, no reutiliza resultados históricos |
| [Resultado Chromium](iter12_pipeline_postgresql_interfaz.browser.json), [captura auténtica](iter12_pipeline_postgresql_interfaz.evento.png) | React real contra API loopback; solo un evento sintético visible, sin login, token o contraseñas en imagen |
| [Compose aislado](iter12_compose_base_smartir-iter12-base-00547d69.json) | Arranque, migración y health; no se ejecutó el navegador contra ese Compose, sino contra el runner PG aislado |

El PCAP determinista se genera por código y tiene SHA-256 `ad71b879afbb1a102a74d4bfcb868eba96a1d6341cf6006338e663274b937774`. El motor puede generar flow_id diferentes, así que los dos EVE tienen hashes distintos; no se promete igualdad byte a byte entre nuevas ejecuciones. El fingerprint y los duplicados se comprueban repitiendo **el mismo archivo** con el mismo sensor. JSON/CSV/JSONL de esta iteración preservan sus bytes mediante .gitattributes.

## Interpretación correcta

Cada evento del laboratorio tiene prioridad de regla original3, índice derivado40/100 Media y activo50 **predeterminado, no observado**. Los cuatro correlacionan en un incidente `prueba_icmp`; weighted-v2 conserva resultado50 Alta por su fórmula genérica, que **no confirma un ataque ni riesgo real de esa prueba**. El tipo auxiliar no es una séptima etiqueta ML. El campo observado de severity del motor histórico significa entrada disponible; la nueva política deja claro que ese índice es derivado.

Las filas/evaluaciones v1 representativas se preservaron en pruebas con weighted-v1/v2. No se ejecutó backfill ni se comprobó el contenido real de la BD habitual. Migraciones/checkpoint y credenciales existentes no cambian. No se validó la configuración principal del usuario, captura live, ACL de todos los modos WSL/UNC, rotación de su sensor ni eficacia IDS/MTTD/MTTR.

## Reproducción y revisión

Comandos y límites en [NORMALIZACION_SURICATA](../NORMALIZACION_SURICATA.md). Las suites generan DB/schemas UUID; el runner PG solo usa la instancia temporal declarada en loopback55440. Los runners rechazan sobrescribir sus evidencias y requieren un label/directorio nuevo. `validation/collect_suricata12.py` es el colector de este cierre: lee los nombres exactos de JUnit y fuentes utilizados, exige198 casos por base, verifica Git y exporta un snapshot nuevo; para otra corrida, adaptar nombres/salida explícitamente, conservando estos resultados.

No confundir: (a) JSON construido por tests, (b) alertas emitidas por motor real leyendo PCAP sintético offline, (c) seguimiento automático de archivos por agente real, (d) captura de tráfico real. Aquí se ejecutaron **a, b y c**; **d no se realizó**.
