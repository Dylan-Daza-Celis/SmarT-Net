# Iteración 12 — normalización, criticidad y salida EVE dedicada

Estado: implementación para revisión, validación aislada del 22-11-2026 (America/Mexico_City; artefactos con UTC). No modifica datos operativos ni acredita eficacia IDS. [Índice de evidencias](resultados/README_ITER12.md).

## Inspección y alcance

Se inspeccionaron `suricata.py`, `eve_import.py`, `ingestion.py`, `risk.py`, correlación, modelos, migraciones, agente/checkpoints, React y pruebas existentes. El adaptador v1 solo clasificaba categorías explícitas. Una categoría vacía quedaba `desconocido`, aunque se preservaban firma, SID y prioridad. **Severity 3 ya se convertía a severity normalizada 40; el 50 mostrado correspondía a criticidad del activo, no a esa severidad.** Se corrige la interpretación visible y se añade procedencia estructurada sin recalibrar el motor.

El usuario informó cuatro alertas ICMP reales en su instalación WSL2. No se leyó ni modificó su base, esos cuatro eventos ni su configuración Suricata. Los ensayos descritos aquí emplean archivos y bases nuevos. Sí se encontró Suricata 8.0.3 en Ubuntu WSL2 y se ejecutó su validación y reproducción **offline de un PCAP construido**, sin abrir interfaces ni generar paquetes en red.

Se conservan FastAPI, PostgreSQL, SQLAlchemy, JWT/RBAC, React/TypeScript, ML experimental y el agente. El head real es **0009**, añadido en iteración 11 para cuentas `eve_only`; no 0008. Esta iteración **no requiere migración**: usa metadatos JSON y tipos de evento textuales ya existentes. No se crean 0010/0012 por numeración.

## Clasificación conservadora v2

Orden de `category_then_declared_lab_v2`:

1. Categoría conocida: misma tabla de seis ataques de [iteración 04](INTEGRACION_SURICATA.md), comparación exacta tras strip/casefold. Tiene precedencia incluso ante firma de laboratorio.
2. Categoría ausente, null, vacía o solo espacios, **firma exactamente** `SMARTIR WSL2 LAB ICMP TEST` y protocolo ICMP, IPV6-ICMP o ICMPV6 (sin distinguir mayúsculas): tipo auxiliar **`prueba_icmp`**. Describe una prueba declarada por una regla; no confirma intención, autenticidad del sensor ni benignidad del tráfico.
3. Cualquier otro caso no clasificable permanece **`desconocido`**, con motivo. No se infiere DoS, escaneo o malware por contener palabras en la firma ni por ser ICMP. Firma parecida, protocolo ausente/incorrecto y categoría desconocida no activan la excepción.

`prueba_icmp` está fuera de la taxonomía de seis ataques. Las validaciones de datasets/ML siguen admitiendo solamente sus seis clases; esta excepción operativa no agrega etiquetas al entrenamiento. El SID se conserva pero no fija la excepción: el SID 9900012 de los ejemplos es **inventado para este laboratorio**, no el SID reportado por el usuario ni un identificador global de confianza.

Nuevos metadatos: `adapter_version=suricata-eve-v2`, `category_status` (missing/null/empty/provided), `classification` (tipo, base, motivo, taxonomía), `input_event_type`, `original_timestamp` y `alert_criticality`. Se conservan `signature`, `signature_id`, `category`, prioridad original, IP, puertos, protocolo, línea EVE original, sensor declarado, archivo, autor, número de línea, import_id y hash de evidencia. UTC conserva microsegundos; las IP siguen la validación IPv4/IPv6 anterior. Datos no proporcionados no se inventan.

## Tres magnitudes diferentes

Suricata define prioridad de regla ordinal: 1 es la mayor, con rango 1–255; el `priority` explícito puede sobreescribir el de `classtype`. No es porcentaje ni medición de impacto. [Documentación oficial 8.0.3](https://docs.suricata.io/en/suricata-8.0.3/rules/meta.html).

| Prioridad original `alert.severity` | Índice de criticidad de alerta | Nivel | Tratamiento |
|---|---:|---|---|
| 1 | 100 | Crítica | Mayor prioridad ordinal |
| 2 | 70 | Alta | Parámetro de ingeniería |
| 3 | 40 | Media | Parámetro de ingeniería; **no 3%** |
| 4–255 | 10 | Baja | Banda residual conservada de v1; no calibrada con datos reales |
| Ausente/null | 50 | Sin nivel atribuible | Predeterminado neutral explícito, no observado |
| 0 | 100 | Sin nivel atribuible | Entrada no estándar admitida por v1; compatibilidad numérica, marcada `legacy_nonstandard_zero` |

Política `suricata-alert-criticality-v1`: conserva exactamente los valores numéricos anteriores para evitar cambios de scores. `source_value` conserva el entero original; `observed=false` indica que el índice **se deriva por una política**, aunque se haya observado el número de prioridad en EVE. `standard_priority`, `source_provided`, `defaulted` y `basis` distinguen estándar, ausencia y caso legado. No es una equivalencia oficial ni científicamente validada.

La **criticidad del activo** es otra variable: EVE no incluye inventario de negocio. Permanece 50 como predeterminado `unknown_default_50`, con `asset_criticality_observed=false`. Nunca se sustituye por severity 3 ni por el índice 40. Cambiarla necesitaría una fuente explícita de inventario y un procedimiento futuro; esta iteración no escribe valoraciones retroactivas.

El **riesgo del incidente** sigue weighted-v2 y sus parámetros congelados. Para cuatro alertas del ensayo: severidad 40, activo 50, recurrencia 80, tipo no catalogado 40 y contexto desconocido 50:

`0.35×40 + 0.25×50 + 0.15×80 + 0.15×40 + 0.10×50 = 49.5 → 50 (Alta)`.

Esa salida genérica no demuestra que la prueba ICMP sea un ataque de riesgo alto. No se redujo artificialmente su puntuación ni se cambió el fallback del motor. React muestra la advertencia y separa prioridad Suricata original, criticidad derivada y criticidad del activo. La explicación histórica del factor severity conserva su contrato `observed=true` (entrada disponible para el motor); eso no certifica impacto observado: el metadato del adaptador identifica su transformación. No se reescriben explicaciones históricas para cambiar esa semántica.

## Compatibilidad y conservación

La huella mantiene **`suricata-eve-fp-v1`**: SHA-256 del JSON canónico `[namespace, sensor_id, objeto_original]`. Versión de adaptador, nombre de archivo, orden de claves y posición no participan. No se utiliza el nuevo tipo normalizado para calcularla. Una repetición añade evidencia, pero no modifica la fila original ni sus incidentes/evaluaciones. SmartIR JSON mantiene su fingerprint anterior.

Por tanto, reimportar las cuatro alertas antiguas **no las reclasifica** ni cambia activo/riesgo. Se prueban filas representativas v1 con weighted-v1 y weighted-v2: detalle, parámetros y evaluaciones permanecen idénticos. No es una intervención sobre las cuatro filas reales del usuario. Las alertas nuevas que cumplan la excepción tendrán tipo auxiliar; la correlación incluye el tipo, por lo que no se fusionan automáticamente con incidentes antiguos `desconocido`. Se conserva la ventana UTC existente y las reglas de eventos tardíos/casos cerrados.

POST `/api/events/import/eve` mantiene cuerpo JSONL, query, reporte, RBAC y límites: 10 MiB por petición, 64 KiB por línea, 10000 registros y lotes de 100. El agente conserva límites menores propios. Las respuestas de incidentes/eventos solo reciben metadatos aditivos; endpoints de consulta/evidencia y dashboard permiten el tipo textual auxiliar. Las cuentas solo EVE siguen sin acceso interactivo. No se modifican estados, reportes anteriores, experimentos ni modelos.

El agente no cambia: mismo esquema de checkpoint, outbox y entrega al menos una vez. **Cambiar de `eve.json` a `smartir-alerts.json` exige un directorio de estado NUEVO**, pues el checkpoint está ligado a ruta/API/sensor. Conservar el estado anterior; no resetearlo ni editar offsets. Utilizar el mismo sensor solo si representa el mismo origen. Dos salidas se deduplican únicamente si el objeto EVE completo y sensor coinciden: campos adicionales/flow_id diferentes pueden cambiar la huella; no se garantiza deduplicación por SID o por parecido.

## Salida EVE exclusiva de alertas sin sobreescribir el principal

Suricata permite varias instancias EVE. `config/suricata/alert-logger.yaml` describe el logger adicional: regular, `threaded=false`, `buffer-size=0`, `filemode=600`, nombre fijo y **types: [alert]**. [Configuración EVE oficial](https://docs.suricata.io/en/suricata-8.0.3/output/eve/eve-json-output.html).

El fragmento no se debe pasar solo como si anexara listas: un bloque `outputs` reemplaza la lista efectiva. `tools/suricata_alerts_config.py` genera un **wrapper nuevo y privado** con `include` del principal y una lista que conserva todos los outputs originales y agrega uno. No inicia Suricata ni edita servicios. Rechaza sobrescrituras, colisión de filename, includes activos, claves raíz repetidas, lista flow-style y alias externos no resolubles. Para configuraciones complejas hay que revisar manualmente la configuración efectiva; el rechazo no autoriza simplificar el archivo del usuario.

El wrapper contiene SHA-256 del principal. `--check` comprueba hash, outputs preservados y configuración del logger; si el principal cambió, generar otro wrapper y repetir `-T`. Un wrapper puede copiar settings sensibles de outputs originales: **mantenerlo fuera de Git**, con acceso restringido. En Linux se crea 0600; en Windows debe revisarse la DACL. No es una firma criptográfica ni impide que el propietario reemplace ambos archivos. Las rutas relativas del principal requieren su directorio de trabajo original.

Preparación WSL2 (revisión local por el operador; no ejecuta captura). Ejecutar desde el repositorio montado en `/mnt/c`, con su ruta entre comillas si contiene espacios:

```bash
suricata -V
python3 -c 'import yaml; print(yaml.__version__)'
# Si PyYAML no existe, instalar tools/requirements-suricata.txt en un venv de herramientas.
install -d -m 700 "$HOME/smartir-suricata-config" "$HOME/smartir-suricata-config/test-logs"
python3 tools/suricata_alerts_config.py \
  --base /etc/suricata/suricata.yaml \
  --output "$HOME/smartir-suricata-config/with-smartir-alerts.yaml" \
  --eve-file smartir-alerts.json
python3 tools/suricata_alerts_config.py --check "$HOME/smartir-suricata-config/with-smartir-alerts.yaml"
# Solo test de configuración, con logs de prueba separados; no abrir interfaz.
(cd /etc/suricata && sudo suricata -T --init-errors-fatal \
  -c "$HOME/smartir-suricata-config/with-smartir-alerts.yaml" \
  -l "$HOME/smartir-suricata-config/test-logs")
```

Los comandos anteriores son instrucciones, **no prueba de la configuración principal del usuario**. Si no se puede leer el principal sin elevar privilegios o contiene includes activos, detener la preparación y revisar localmente; no cambiar permisos globales ni usar chmod 777. Un directorio/nombre de salida distinto debe ser escribible por la cuenta del sensor y legible por el agente autorizado; 0600 requiere planificar propietario/ACL. No se modifica aquí la unidad systemd, interfaz ni proceso existente. Activar ese wrapper en el sensor requiere la revisión de su operador, rutas/reglas y política de rotación. No ejecutar dos sensores sobre la misma interfaz por copiar estos ejemplos.

Para comprobar un archivo de laboratorio, sin imprimir cuerpos:

```bash
python3 -c 'import json,collections,sys; c=collections.Counter(json.loads(s)["event_type"] for s in open(sys.argv[1]) if s.strip()); print(dict(c)); assert set(c)<= {"alert"}' /ruta/privada/smartir-alerts.json
```

Si el log está en NTFS compartido, `/mnt/c/SmartIRLab/smartir-alerts.json` corresponde a `C:\SmartIRLab\smartir-alerts.json`. Es un ejemplo, no una ruta montada por defecto. Para logs Linux/UNC, comprobar permisos, semántica de archivo/rotación y soporte de identidad del agente en esa ruta; este ensayo no valida todos esos modos. No trasladar checkpoints entre rutas.

## Laboratorio reproducible realmente ejecutado

`validation/synthetic_icmp.py` fabrica cuatro tramas ICMP con direcciones de documentación 192.0.2.10 → 198.51.100.20, fechas fijas, checksums y payload etiquetado SYNTHETIC OFFLINE. Usa únicamente bytes: no envía paquetes. Regla `lab-icmp.rules`: firma declarada, `priority:3`, SID sintético 9900012, sin classtype para producir categoría vacía.

`validation/suricata_offline_wsl.py` exige 8.0.3, crea un directorio privado nuevo en `/tmp`, copia **solo la base/rules de laboratorio del repositorio**, genera wrapper, ejecuta `-T` y luego `-r PCAP --runmode single -S regla -l directorio`. `-r` lee offline y `-S` restringe reglas al archivo del ensayo. [Opciones oficiales](https://docs.suricata.io/en/suricata-8.0.3/command-line-options.html).

```powershell
# Ejecutar desde la raíz, con un nombre NUEVO en cada ejecución.
$repoWsl = (wsl -d Ubuntu --exec wslpath -a (Get-Location).Path).Trim()
wsl -d Ubuntu --exec python3 "$repoWsl/validation/suricata_offline_wsl.py" `
  --output-dir "$repoWsl/.test-runs/iter12-engine-nueva"
# Ensayo real del agente Windows contra API/base aisladas, sin URL operativa.
.venv\Scripts\python -m validation.run_suricata12 `
  --source-dir .test-runs/iter12-engine-nueva --database sqlite --label nueva
# PostgreSQL: usar exclusivamente el contenedor temporal descrito abajo.
.venv\Scripts\python -m validation.run_suricata12 `
  --source-dir .test-runs/iter12-engine-nueva --database postgresql --label nueva
# Añadir --browser para Chromium real con analista/observador (Playwright instalado).
# Usa proxy loopback aislado, nunca la API habitual; no guarda login ni trazas.
```

El flujo HTTP real verificó: JWT con cuenta nueva `eve_only`, importación de las cuatro alertas emitidas offline, un incidente, checkpoint confirmado, reinicio del agente sin replay, repetición API de cuatro duplicados, dos apariciones de evidencia por evento y una evaluación de riesgo. Las credenciales se generaron en memoria para bases temporales; no se exportan tokens/passwords. La segunda ejecución del motor generó otros flow_id/hash EVE: el PCAP es determinista, pero Suricata puede generar identificadores de flujo distintos entre ejecuciones. Se registra el hash real de cada fuente; no se finge EVE byte a byte determinista.

Pruebas automatizadas:

```powershell
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider `
  --basetemp .test-runs/iter12-sqlite-nueva --junitxml=.test-runs/iter12-sqlite-nueva.xml
# Instancia de validación desechable, sin volumen persistente, puerto solo loopback.
# Usar un nombre libre: nunca sustituir contenedores/puertos existentes.
docker run --name smartir-iter12-pg --label smartir.validation=iter12 --rm `
  --tmpfs /var/lib/postgresql/data -e POSTGRES_HOST_AUTH_METHOD=trust `
  -e POSTGRES_DB=smartir_validation -p 127.0.0.1:55440:5432 -d postgres:16-alpine
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55440/smartir_validation'
.venv\Scripts\python -m pytest backend/tests -q -p no:cacheprovider `
  --basetemp .test-runs/iter12-pg-nueva --junitxml=.test-runs/iter12-pg-nueva.xml
Remove-Item Env:TEST_DATABASE_URL
Push-Location frontend
npm run build
Pop-Location
# Arranque aislado adicional: nuevo proyecto/volumen, solo se detiene ese proyecto.
.\validation\compose_smoke.ps1 -Iteration 12 -ExpectedHead 0009
```

La autenticación trust pertenece **solo al contenedor aislado en loopback de ensayo**, no a una recomendación operativa. Las fixtures generan schemas UUID y migran head; nunca apuntar TEST_DATABASE_URL a la BD habitual. `validation.isolated` conserva su prefijo histórico `iter10_` para directorios/schemas nuevos: reutilización del arnés, no evidencia reutilizada. No ejecutar limpieza de tablas, downgrade ni eliminación de volúmenes. Para retirar el contenedor temporal, comprobar su etiqueta/nombre y detener únicamente ese contenedor; no usar down -v.

## Resultados y límites

Los resultados finales detallados, conteos y tiempos se publican en [README_ITER12](resultados/README_ITER12.md) y su manifiesto. La primera suite completa obtuvo 197/197 por base; luego se agregó un caso de alteración del wrapper y se repitió la suite. El primer ensayo de los nuevos tests tuvo dos fallos de arnés: esperaba `incidents_updated`, campo inexistente del reporte EVE. Se corrigieron las aserciones para verificar importados/duplicados y el número real de incidentes; no se cambió el contrato para satisfacer el test. Persiste la advertencia de deprecación TestClient/httpx.

Limitaciones: mapa numérico inicial sin calibración empírica; identificación de prueba basada en declaración de firma, no autenticación del IDS; auxiliar fuera de ML; ventanas fijas heredadas con sus límites; escenarios de laboratorio pequeños; configuración principal y captura real del usuario sin validar; no se midió eficacia de reglas, latencia prolongada, MTTD/MTTR ni interoperabilidad de todas las rutas WSL/Windows. Los cuatro eventos reales anteriores seguirán mostrando su política histórica. No hay backfill, reconversión ni degradación silenciosa del score. No se modifica el algoritmo operativo para tratar el auxiliar como una séptima clase de ataque.

## Archivos y endpoints afectados

| Archivo / grupo | Cambio |
|---|---|
| backend/app/suricata.py, suricata_policy.py | Política v2, procedencia y criticidad de alerta derivada |
| backend/tests/test_suricata12.py, test_suricata.py | Regresiones nuevas y versión esperada de adaptador para eventos nuevos |
| frontend/src/SuricataEventDetails.tsx, main.tsx, AnalyticsDashboard.tsx | Tres magnitudes diferenciadas, firma/SID/política, advertencia y filtro auxiliar |
| config/suricata/*, tools/suricata_alerts_config.py, requirements-suricata.txt | Fragmento/logger, laboratorio, wrapper no destructivo y dependencia de tooling |
| validation/synthetic_icmp.py, suricata_offline_wsl.py, run_suricata12.py | PCAP sintético, motor WSL offline y recorrido aislado con agente |
| README, antología, integración/monitoreo, docs/resultados, .gitattributes | Documentación y evidencia nueva; históricos conservados |

POST `/api/events/import/eve` usa el nuevo adaptador sin cambiar su contrato. GET `/api/events/{id}`, `/api/incidents/{id}` y evidencia devuelven metadatos aditivos; dashboard filtra `prueba_icmp` con su contrato textual previo. No hay endpoints nuevos, cambios de roles ni migraciones de esquema/checkpoint.
