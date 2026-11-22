# Evidencias de la iteración 10

Solo ejecuciones reales en datos sintéticos y bases aisladas. Fecha local:22-11-2026. No hay credenciales, dumps, HAR, traces ni archivos Packet Tracer. [Métodos, fallos y matriz](../VALIDACION_INTEGRAL.md).

| Artefacto | Contenido y alcance |
|---|---|
| [Inventario de cierre](iter10_validacion_cierre.json) |126casos SQLite+126PostgreSQL, nombres/duraciones JUnit,78archivos de código/configuración con SHA,8migraciones,29evidencias anteriores sin cambios según Git, hardware/versiones/avisos |
| [Inventario preliminar](iter10_validacion_final.json) |Primera extracción real; comparación cruda CRLF/LF produjo falsos indicadores de cambio. Se conserva y queda sustituida **solo esa interpretación** por cierre; no son pruebas fallidas ni datos alterados |
| [Journey PostgreSQL](iter10_integral_postgresql_cierre.json) |61operaciones API, UUID,conteos/hashes de todas las tablas y exportaciones antes/después de reinicio; datos sintéticos |
| [Journey SQLite](iter10_integral_sqlite_final.json) |Mismo contrato/61operaciones, conservación tras reinicio en otra BD |
| [Navegador cierre](iter10_integral_postgresql_cierre.browser.json) |Chromium149.0.7827.55,14checks descriptivos en1test, tres roles,0erroresJS;401/403/409/422/429; sin mocks |
| [Dashboard PNG](iter10_integral_postgresql_cierre.dashboard.png) / [Incidente PNG](iter10_integral_postgresql_cierre.incidente.png) |Capturas auténticas de esa ejecución; usuarios nominales y direcciones de documentación, sin passwords/tokens |
| [Reporte JSON](iter10_integral_postgresql_cierre.reporte.json) / [CSV](iter10_integral_postgresql_cierre.reporte.csv) / [PDF](iter10_integral_postgresql_cierre.reporte.pdf) |Descargas reales desde botones; JSON canónico verificable; procedencia operacional no certificada en payload, origen **sintético conocido por el runner** |
| `iter10_integral_postgresql_run5.*` |Primera ejecución completa aprobada,1test/12checks; se conserva. Cierre amplía401/429 visibles y publicación después del éxito, sin reemplazarla |
| [HTTP JSON](iter10_http_concurrent_run1.json) / [320muestras CSV](iter10_http_concurrent_run1.csv) |40solicitudes×2operaciones×4concurrencias,114éxitos/206HTTP429,0HTTP503/errores inesperados; cada muestra/percentiles y criterios previos |
| [Compose](iter10_compose_smartir-iter10-9c8a60d4.json) |Proyecto/volumen nuevos,PostgreSQL16.16,head0008,health/web200; solo arranque, no navegador de ese Compose |
| [npm audit](iter10_auditoria_npm.json) / [pip-audit resuelto](iter10_auditoria_python_resolved.json) |Consultas reales:0avisos conocidos. Python72paquetes backend/dev/transitivos resueltos en esa fecha, no lock completo |

Verificar reporte sin API/base/token:

```powershell
.venv\Scripts\python backend/app/verify_report.py docs/resultados/iter10_integral_postgresql_cierre.reporte.json
```

Hash canónico realmente verificado: `233679146ca51b245f37d9b6213a9de98d50ebca45f3330eb38838c5f8c33a6f`.

El benchmark10 reutiliza `benchmarks/synthetic_events.py` de09 con semilla202610; el texto ITER09 de sus firmas significa reutilización del generador, **no captura real ni resultado de una ejecución09**. Cada condición se identifica en el protocolo/evidencia10. Las métricas ASGI09 no se sobrescriben ni se comparan causalmente con TCP10.

Las duraciones de generación/reposo/reinicio/navegador no son MTTD/MTTR. El tiempo total del journey puede incluir validación de navegador, mientras que las duraciones de carga son solo de cada fase medida. CPU/RSS no fueron medidos en el benchmark HTTP. La ausencia de avisos no equivale a ausencia de vulnerabilidades.

`.gitattributes` conserva los bytes PDF/PNG y CSV10 al versionar; la verificación previa al commit compara el índice Git con el archivo original descargado. Los hashes de contenido canónico JSON son independientes de CRLF/LF.

[Integridad Git](iter10_integridad_git.json) registra la comparación real de9artefactos binarios/CSV con el índice preparado. El report_id y export_sha256 del journey H corresponden a su snapshot API de cohorte filtrada; los archivos `.reporte.*` proceden de **otro snapshot**, creado desde el navegador con su propia cohorte y UUID. No deben compararse hashes entre snapshots distintos.
