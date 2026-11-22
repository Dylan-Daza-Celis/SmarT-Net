# Evidencias reales — iteración 11

Todas las entradas proceden de pruebas aisladas y archivos **sintéticos**. No son capturas Suricata reales ni mediciones de MTTD/MTTR. [Método, comandos, resultados y limitaciones](../MONITOREO_CONTINUO_SURICATA.md).

| Evidencia | Alcance |
|---|---|
| [Resumen JUnit final auditado](iter11_validacion_cierre.json) |164 casos SQLite y164PostgreSQL,0 fallos; nombres/duraciones saneados,53 artefactos históricos sin cambios, algoritmos conservados y hashes del build |
| [Resumen JUnit anterior](iter11_validacion_final.json) |Primera suite164/164 aprobada, anterior a los eventos adicionales de auditoría de transporte; se conserva sin sustituir mediciones |
| [TCP SQLite auditado](iter11_agent_http_sqlite_auditado.json) / [CSV](iter11_agent_http_sqlite_auditado.csv) |Mismo recorrido con trazabilidad final de obtención JWT/envío/ciclo/retry,12 eventos/25 apariciones y segundo lector rechazado |
| [TCP PostgreSQL auditado](iter11_agent_http_postgresql_auditado.json) / [CSV](iter11_agent_http_postgresql_auditado.csv) |Repetición final en PostgreSQL con la misma conservación y semilla |
| [TCP SQLite JSON](iter11_agent_http_sqlite_cierre.json) / [CSV](iter11_agent_http_sqlite_cierre.csv) |Agente Windows independiente,5 lotes/15 registros no vacíos,12 eventos únicos y25 apariciones EVE tras replay; reinicio, incompleta, caída real de API, rotación, cuarentena y segundo lector rechazado |
| [TCP PostgreSQL JSON](iter11_agent_http_postgresql_cierre.json) / [CSV](iter11_agent_http_postgresql_cierre.csv) |Mismo procedimiento y resultados funcionales en otro schemaUUID de PostgreSQL 16 |
| [Compose Linux inicial](iter11_compose_smartir-iter11-35cc7f68.json) |Primera ejecución aprobada del perfil, reinicio y rotación;12 eventos/13 evidencias,3 lotes,1cuarentena |
| [Compose Linux cierre](iter11_compose_smartir-iter11-b573114f.json) |Repite con endurecimiento final; Linux/UID/Python verificados por exec, default3 servicios, perfil opcional, sin host mounts,head 0009,health/web200 |
| [Compose Linux auditado](iter11_compose_smartir-iter11-a7ae65f3.json) |Repite con eventos de transporte auditados del código final; mismo resultado funcional |
| [Compose base](iter11_compose_base_smartir-iter11-base-72e76ba9.json) |Tres servicios sin agente,head 0009 y health/web200; proyecto nuevo, volumen preservado |
| `iter11_agent_http_*_run1.*` |Ejecuciones TCP iniciales aprobadas antes del último endurecimiento de respuestas/spool; se conservan sin reemplazarlas |

El replay final de12 registros en TCP produce12 duplicados y0 importados. Antes de ese replay hay13 apariciones de evidencia (incluye una repetición intencional); después25. La cuarentena contiene el lote original de duplicado+JSON inválido+flow descartado; los BLOB se conservan **solo en el estado local privado**, no en este repositorio. Las fases miden espera de observación, no latencia garantizada de detección.

HTTP401/403/413/429/503 y renovación son pruebas de transporte controlado/mock; lost-response después del commit usa la API aislada con fallo inyectado. Las caídas/reintentos de red de los runners TCP son reales contra Uvicorn detenido/reiniciado en localhost. No se hace pasar un mock por resultado de un sensor físico.

Los CSV contienen secuencia, UUID, offsets/lineas, número de registros/intentos y conteos reales. Los JSON incluyen receipts/import_id y auditoría sin claves, tokens, hashes de contraseña ni eventos originales. Las credenciales de fixture son efímeras y no se exportan. Los resultados antiguos y las evaluaciones/ML no se recalculan.
