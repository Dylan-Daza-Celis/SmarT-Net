# Evidencias14 — cierre técnico revisable

Ejecuciones locales aisladas del22-11-2026 (America/Mexico_City), timestamps UTC. No se accedió a datos operativos ni se cambiaron credenciales. Las prácticas Packet Tracer y los artefactos anteriores permanecen intactos.

## Resultados comprobados

| Ejecución | Resultado / evidencia |
|---|---|
| PostgreSQL16, suite completa |216 aprobadas,0 fallos/errores/omisiones;664.32s consola |
| SQLite, suite completa de cierre |216 aprobadas,0 fallos/errores/omisiones;177.43s consola. Conserva también el primer intento215 aprobadas/1 fallo,488.01s |
| Repetición de auditoría/flujo/concurrencia |7 aprobadas sin cambiar código,16.58s |
| Auditoría reforzada al cierre |5 aprobadas por base (5.01s SQLite,6.19s PG); cada operación protegida rechaza también Bearer inválido, no solo ausencia de cabecera |
| Playwright nuevo con PostgreSQL |6 casos aprobados; recarga, expiración, tres roles, seis secciones, filtros, panel/evidencia, gestión409, teclado,390/820/1440 y0 page_errors |
| Recorrido integral SQLite |1 caso navegador aprobado (30.1s),61 operaciones API, reinicio conservando tablas/modelos/experimentos y reportes JSON/CSV/PDF |
| Suricata + agente + API PostgreSQL |1 caso navegador aprobado;4 alertas,1 incidente,4 duplicados al replay, evidencia/checkpoint conservados |
| Agente Windows por TCP |12 eventos,5 lotes,25 apariciones; lectura incremental, rotación, reinicio y recuperación |
| Suricata8.0.3 en WSL2 |-T y -r offline correctos; general4 alert+1 flow, dedicado4 alert; ninguna interfaz abierta |
| npm ci y build |66 paquetes,67 auditados y0 vulnerabilidades conocidas reportadas por npm; TypeScript/Vite correctos,459 módulos,47.96s Vite |
| Docker Compose |Imágenes construidas, head0009, health/web, proxy cookie, reinicio db/api/web y conservación del usuario/cookie; volumen conservado |

Son8 ejecuciones de casos de navegador, no un benchmark ni una validación productiva. La prueba de fallo de red del frontend usa aborto controlado y se distingue de las respuestas HTTP reales. La cookie Secure se comprueba mediante TestClient HTTPS, no una infraestructura PKI productiva. npm no sustituye una auditoría externa. Persiste la advertencia TestClient/httpx.

## Archivos de evidencia

- [Manifiesto y versiones](iter14_validacion.json), [resumen CSV](iter14_validacion.csv).
- [Auditoría adicional de credenciales y permisos](iter14_auditoria_adicional.json), incluida en los cinco casos nuevos, sin sumar repeticiones como casos distintos.
- [Frontend PostgreSQL](iter14_frontend_postgresql_final.json), [Chromium](iter14_frontend_postgresql_final.browser.json).
- [Resumen SOC](iter14_frontend_postgresql_final.dashboard.png), [incidentes](iter14_frontend_postgresql_final.incidentes.png), [evidencia contextual](iter14_frontend_postgresql_final.evidencia.png), [historial](iter14_frontend_postgresql_final.historial.png), [móvil](iter14_frontend_postgresql_final.movil.png).
- [Analítica](iter14_frontend_postgresql_final.analitica.png), [importación](iter14_frontend_postgresql_final.importacion.png), [evaluación sintética](iter14_frontend_postgresql_final.evaluacion.png), [ML de fixture](iter14_frontend_postgresql_final.ml.png).
- [Integral SQLite](iter14_integral_sqlite_final.json), [navegador](iter14_integral_sqlite_final.browser.json), [reporte JSON](iter14_integral_sqlite_final.reporte.json), [CSV](iter14_integral_sqlite_final.reporte.csv), [PDF](iter14_integral_sqlite_final.reporte.pdf).
- [Agente Windows](iter14_agent_http_postgresql_final.json), [lotes CSV](iter14_agent_http_postgresql_final.csv).
- [Pipeline EVE PostgreSQL](iter14_pipeline_postgresql_final.json), [CSV](iter14_pipeline_postgresql_final.csv), [navegador](iter14_pipeline_postgresql_final.browser.json).
- [Motor Suricata offline](iter14_suricata_offline.json), [bytes EVE sintéticos del motor](iter14_EVE_SINTETICO_OFFLINE.jsonl).

El manifiesto identifica el JSON Compose del proyecto nuevo verificado. Las capturas contienen exclusivamente cuentas/datos sintéticos. Se preservan los bytes de JSON/JSONL/CSV y PDF mediante atributos Git. El PCAP es determinista; los flow_id del motor pueden variar, por lo que se registra el SHA real de su salida.

## Registro de incidencias

| Hallazgo | Evidencia y tratamiento | Estado |
|---|---|---|
| Recursos insuficientes de Chromium |Primer intento Suricata navegador: ERR_INSUFFICIENT_RESOURCES. Se repitió con menor concurrencia y pasó |Repetición aprobada; límite del entorno documentado |
| Primer Compose sin health confirmado |Timeout del arnés en proyecto5b7a9b71; se detuvo solo ese proyecto conservando volumen. Segundo proyecto verificó ciclo completo |Repetición aprobada; no se atribuye una causa interna sin prueba |
| Login401 inesperado en fixture SQLite |Primer intento215/216. La fila aislada estaba activa y su contraseña verificó después; siete casos relacionados pasaron sin cambios. Suite completa repetida con OPENBLAS_NUM_THREADS=1 y OMP_NUM_THREADS=1 |Causa no confirmada; no se oculta ni se interpreta como bypass. Pendiente investigación bajo presión controlada |
| Falta de inventario transversal de permisos |Se agregan5 casos: operaciones sin identidad, dos roles sin exportación de referencias, cuenta EVE y SQL literal |Cobertura nueva; ningún algoritmo cambiado |
| Riesgos conocidos de sesión/despliegue |Sin revocación centralizada, cookie no aislada por puerto, limitador por proceso, Vite local, sin tenancy |Limitaciones vigentes; no aprobación para Internet |

No se detectó ni corrigió una vulnerabilidad crítica/alta nueva reproducible en los casos de cierre. Esto no demuestra ausencia de vulnerabilidades. El401 intermitente conserva causa pendiente; no se debilitaron Argon2, TTL ni límites para conseguir aprobación. Los fallos de los primeros intentos no se cuentan como éxitos.

Arquitectura, matriz requisito→prueba, comandos y recomendaciones: [VALIDACION_FINAL](../VALIDACION_FINAL.md). Las cifras de rendimiento09/10 son históricas y no se sustituyen. No se generan nuevas métricas de MTTD/MTTR, precisión o eficacia de captura; la captura real previa es la reportada manualmente por el usuario.
