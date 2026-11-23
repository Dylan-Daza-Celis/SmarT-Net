# Evidencias de la iteración13

Validación local del **22-11-2026, America/Mexico_City**; archivos fechados en UTC del23-11. Bases nuevas, schemas UUID, usuarios efímeros y datos sintéticos. No se leyó/cargó la base habitual ni se capturó tráfico real. Los resultados01–12 permanecen intactos.

## Resultado de cierre

| Verificación ejecutada | Resultado |
|---|---|
| Pytest completo SQLite | **211 aprobadas**,0 fallos/errores/omisiones; consola134.89s |
| Pytest completo PostgreSQL16.16 | **211 aprobadas**,0 fallos/errores/omisiones; consola207.15s |
| Casos backend nuevos |13 parametrizados de sesión web: tres roles, CSRF/Origin, cookie, usuario inactivo/rol vivo, expiración/manipulación, servicios EVE, HTTPS/HTTP remoto, cuota compartida y Bearer compatible |
| E2E nuevo con API SQLite real | **6 aprobados**, Chromium149.0.7827.55 |
| E2E nuevo con API PostgreSQL real | **6 aprobados**, mismo navegador |
| Regresión integral anterior adaptada a rutas/panel | **1 aprobado** en navegador;61 operaciones API, reinicio con snapshot intacto y descargas JSON/CSV/PDF |
| Regresión Suricata12 adaptada | **1 aprobado** en navegador; agente Windows sin cambios,4 importados/1 incidente, repetición4 duplicados, reinicio/checkpoint y evidencia |
| Total de navegador de cierre | **14 ejecuciones aprobadas**,8 casos distintos; no sumar repeticiones intermedias como cobertura nueva |
| npm ci |Correcto:66 paquetes añadidos,67 auditados,0 vulnerabilidades conocidas reportadas por npm en esa ejecución |
| npm run build |TypeScript + Vite6.4.6 correctos,459 módulos,9.24s Vite; hashes de dist en manifiesto |
| Compose aislado |PostgreSQL16.16, head0009, health ok, web200, login/restauración/logout HttpOnly a través del proxy web; solo se detuvo su proyecto y se conservó el volumen |

Los tiempos de pytest de consola y testsuite JUnit tienen una pequeña diferencia interna; los JSON/CSV guardan exactamente los valores JUnit, sin ajustarlos. Son duraciones de QA en host compartido, no benchmarks. Persiste una advertencia TestClient/httpx. Node del host18.20.8 y npm10.8.2; Docker web usa su imagen Node22. La auditoría npm no es un análisis externo ni garantiza ausencia de vulnerabilidades.

El test de expiración firma un JWT de fixture5s con la clave efímera del servidor aislado; el TTL operativo continúa900s. Hay un aborto de red **controlado** para comprobar reintento del ciclo de vida; no se presenta como caída real503 del servidor. Los demás errores de autenticación,422,429 y conflicto409 se obtienen de la API real. No hay HAR, vídeo, storageState ni tokens/contraseñas en capturas.

## Artefactos principales

| Archivo | Contenido |
|---|---|
| [iter13_validacion.json](iter13_validacion.json), [CSV](iter13_validacion.csv) |JUnit saneado, versiones, resúmenes E2E, intentos fallidos, hashes y conservación Git |
| [SQLite estable](iter13_frontend_sqlite_estable.json), [metadatos de navegador](iter13_frontend_sqlite_estable.browser.json) |6 casos,61 pasos backend previos de fixture, verificación de sesión/roles/UI |
| [PostgreSQL con capturas](iter13_frontend_postgresql_capturas.json), [metadatos](iter13_frontend_postgresql_capturas.browser.json) |6 casos; mismo recorrido y captura móvil tomada después de recibir el detalle |
| [Regresión integral](iter13_integral_postgresql_final.json), [navegador](iter13_integral_postgresql_final.browser.json) |61 checks API, conservación después de reinicio y recorrido histórico con tres roles |
| [Regresión Suricata](iter13_pipeline_postgresql_regresion.json), [CSV](iter13_pipeline_postgresql_regresion.csv), [navegador](iter13_pipeline_postgresql_regresion.browser.json) |Reutiliza los bytes **sintéticos offline** emitidos en12; no vuelve a ejecutar Suricata ni captura red en13 |
| [Compose de cierre](iter13_compose_base_smartir-iter13-base-55afa103.json) |Volumen nuevo con una cuenta observador efímera; cookie a través del proxy y sin cambios a servicios habituales |

Capturas auténticas de Chromium, con datos sintéticos y credenciales ya retiradas del formulario:

- [Resumen con cinco incidentes y diez eventos del laboratorio](iter13_frontend_postgresql_capturas.dashboard.png).
- [Cola y filtros](iter13_frontend_postgresql_capturas.incidentes.png).
- [Panel contextual y evidencia original](iter13_frontend_postgresql_capturas.evidencia.png).
- [Historial de asignación, estados y acciones](iter13_frontend_postgresql_capturas.historial.png).
- [Analítica](iter13_frontend_postgresql_capturas.analitica.png).
- [Importación](iter13_frontend_postgresql_capturas.importacion.png).
- [Evaluación experimental sintética](iter13_frontend_postgresql_capturas.evaluacion.png).
- [ML experimental con una versión registrada de fixture](iter13_frontend_postgresql_capturas.ml.png).
- [Panel móvil390px](iter13_frontend_postgresql_capturas.movil.png).

Se conservan también archivos de intentos aprobados intermedios (`cuarta`, `final`, `cierre`, `verificado`) y el primer Compose13. No son versiones finales alternativas ni mediciones comparables de rendimiento. Algunas capturas intermedias muestran carga o la cohorte vacía que permitió detectar el truncamiento del minuto actual; las capturas principales enlazadas arriba esperan datos. No se reescribieron esas evidencias para ocultar el defecto.

## Matriz requisito → componente → prueba → evidencia

| Requisito | Componente | Prueba/evidencia | Estado |
|---|---|---|---|
| Sesión válida después de recargar | SessionProvider, web_session, current_user | Pytest cookie/identidad/exp y E2E tres roles; cookie HttpOnly, storage JS vacío |Demostrado |
| Expiración, logout y protección de rutas | api.ts, App, endpoints session | JWT5s real, logout+reload,401/403, Origin/CSRF y rechazo eve_only |Demostrado en entorno aislado |
| Secciones independientes | Shell, App, páginas, lazy chunks | Navegación entre6 rutas; ausencia de controles de otras páginas; build |Demostrado |
| Contexto de filtros y detalle cercano | navigation, useCohort, IncidentDrawer | Filtros URL, recarga del caso, cierre/Escape y vuelta a la cola |Demostrado |
| Gestión y concurrencia | IncidentLifecycle + APIs existentes |Asignación, transición, comentario,409, recarga/reintento y timeline |Demostrado |
| Evidencia Suricata12 sin reinterpretar historia | SuricataEventDetails, EvidenceViewer |Firma/SID,3 ordinal,40 Media, activo50 no observado, prueba_icmp, raw/procedencia y replay duplicado |Demostrado con datos sintéticos |
| Analítica, reportes y experimentos/ML | Módulos existentes reorganizados | Suites anteriores, journey61, descargas y selección de ejecuciones/modelos registrados |Demostrado en fixtures |
| Responsive y teclado | Tokens CSS, menú, dialog, Tabs |1440/820/390px, sin overflow de documento, foco/Escape, Enter en navegación |Demostrado en Chromium |
| Contraste/accesibilidad | Componentes UI y estilos |Cuatro pares de tokens>=4.5, etiquetas y foco; tablas en región desplazable |Parcial: no certificación WCAG ni lector de pantalla |
| Compatibilidad/datos/migraciones | Bearer, agente, algoritmos conservados |211 casos por motor, restart snapshot, head0009 y comparación Git |Demostrado en prueba; BD habitual no se inspeccionó |
| Despliegue local con proxy | compose, Vite y smoke13 |Login/restauración/logout por web, health y migración |Demostrado en proyecto nuevo |
| Internet/producción/múltiples navegadores | Fuera del alcance |No se ejecutó certificación, HTTPS productivo ni Safari/Firefox |Pendiente |

## Fallos encontrados y tratamiento

1. Primer intento nuevo:6 fallos de login por Origin403 del proxy de pruebas, que reescribía Host. Se conservó Host, sin debilitar CSRF.
2. Segundo intento:3 aprobados/3 fallidos. Se detectaron foco fuera del diálogo, petición de concurrencia sin revisión verificable (428) y overflow móvil. Se validó la respuesta de lectura antes del escritor y se corrigieron foco/contención.
3. Tercer intento:4 aprobados/2 fallidos. Se verificó una carrera al remontar formularios durante recarga y el texto accesible absoluto que ampliaba el documento734px en viewport390. Se mantuvo el formulario montado/deshabilitado durante carga y se ancló el contenido accesible a su región.
4. Intentos posteriores aprobaron los seis casos. La revisión visual halló indicadores cero porque el fin predeterminado truncaba el minuto actual; se corrigió el periodo y se añadió una aserción sobre los cinco incidentes realmente creados en la fixture.
5. Una ejecución SQLite concurrente produjo un error transitorio de transformación Vite/EOF en Shell (5 aprobados/1 fallido) mientras el archivo aún se actualizaba. La compilación posterior y repetición con árbol estable pasaron; no se publica ese intento como éxito.
6. La regresión antigua requería hacer una petición anónima con credentials:omit y cerrar el nuevo diálogo antes de logout. Se adaptó el recorrido, conservando los checks401/403/422/429, acciones, importación y descargas.
7. Un intento de build se inició mientras npm ci reemplazaba node_modules y no encontró tsc. Se esperó a finalizar la instalación y se repitió el build con éxito; no se presenta ese intento como validación aprobada.

El manifiesto conserva conteos de intentos nuevos desde sus logs reales sin exportar DOM/cuerpos ni credenciales de fixtures. Los archivos JSON/CSV/PDF/PNG anteriores no fueron modificados. No quedan fallos reproducibles en las comprobaciones de cierre ejecutadas. Se mantiene deprecación TestClient/httpx y las limitaciones descritas en [REDISENO_FRONTEND](../REDISENO_FRONTEND.md).

El primer pase del colector detectó JSON12 con finales CRLF en el árbol y LF en su blob Git, derivados del tratamiento de atributos de aquella entrega. Se verificó igualdad de contenido al normalizar **solo** esos delimitadores, sin reescribir archivos históricos ni cambiar sus objetos Git. El manifiesto distingue este modo de comparación del objeto Git idéntico; CSV, PDF y PNG requieren identidad de objeto.
