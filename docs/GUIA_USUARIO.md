# Guía de usuario — SmartIR-Net, iteración 10

Prototipo académico local. Esta guía describe funciones comprobadas en el repositorio; no acredita detección IDS, eficacia de operadores ni un producto certificado. Para resultados y cobertura exacta consultar [VALIDACION_INTEGRAL](VALIDACION_INTEGRAL.md).

## Requisitos y acceso

Docker Desktop con motor activo y Compose v2, navegador moderno, puertos localhost5173/8000 disponibles y configuración local indicada en [GUIA_DESPLIEGUE](GUIA_DESPLIEGUE.md). Conservar las credenciales existentes. En instalación nueva, un administrador ejecuta `docker compose exec api python -m app.bootstrap`: solicita usuario y contraseña oculta; solo funciona si no existen usuarios.

Abrir `http://localhost:5173`. Introducir usuario y contraseña; **Entrar**. El token dura15 minutos y permanece en memoria, no en localStorage. Recargar requiere iniciar sesión. **Cerrar sesión** borra la copia local; otra copia del JWT sigue válida hasta expirar. Un usuario inactivo deja de acceder aunque conserve un token. No existen refresh, MFA, recuperación automática ni revocación individual.

| Capacidad | Administrador | Analista | Observador |
|---|---|---|---|
| Consultar incidentes/evidencia/dashboard/reportes guardados | Sí | Sí | Sí |
| Importar SmartIR/EVE y guardar snapshot | Sí | Sí | No |
| Asignar | Cualquier escritor activo | Tomarse caso libre/transferir uno propio | No |
| Estado/acción/reevaluación | Sí, con reglas de estado/revisión | Caso propio, con reglas | No |
| Reabrir Cerrado | Sí | No | No |
| Usuarios y evidencias temporales revisadas | Sí | No | No |
| Generar datasets, experimentar, entrenar y exportar referencias | Sí, investigador | No | No |
| Consultar características/órdenes/versiones e inferencia sin etiquetas | Sí | Sí | Sí |

La administración de usuarios está en la API/OpenAPI `http://localhost:8000/docs`, no en un formulario React. Usar Authorize con un token propio obtenido en POST `/api/auth/login`. No mostrar ni guardar ese token en capturas, tickets o documentos. No pueden desactivarse/degradarse responsables de incidentes abiertos sin reasignación previa.

## Importar eventos

Seleccionar **Formato** en Importación de eventos. Solo administrador y analista ven controles de carga.

- **SmartIR JSON / JSONL**: array o contenedor `{"events":[...]}` en JSON; JSONL con un objeto normalizado por línea. Campos: source, event_timestamp con zona, event_type, severity0–100; IP opcionales válidas; asset_criticality0–100 (default50), message máximo2000. Batch máximo1000 eventos/5 MiB por API; frontend rechaza archivos mayores10 MiB, por lo que una carga SmartIR entre5–10 MiB todavía puede ser rechazada por el backend. Dividir antes de importar.
- **Suricata EVE JSON Lines**: archivo UTF-8, un objeto por línea, seleccionar sensor estable. Alertas válidas se adaptan; otros event_type se descartan y categorías sin correspondencia quedan desconocido. No acepta arrays, gzip ni multipart. Máximo10 MiB/archivo,64 KiB/línea,10000 registros, lotes100. Criticidad50 es política **no observada**. Una severidad ausente también usa un default explícito.

**Importar archivo** muestra importados, duplicados, descartados, desconocidos, lotes y errores por línea. Líneas inválidas no eliminan las válidas. Un413 puede tener reporte parcial: los lotes confirmados permanecen. Revisar antes de repetir. Fingerprint SmartIR conserva el contrato histórico; EVE usa JSON canónico y sensor, no nombre de archivo. Repetir idéntico sensor/registro conserva el evento y agrega evidencia de aparición; cambiar sensor representa otra procedencia y puede crear otro evento.

Ejemplos `examples/eventos_demo.json` y `examples/suricata_sintetico.eve.jsonl` son **sintéticos**. No importarlos en una base habitual si se pretende medir actividad real. Preferir el runner de validación aislado. En **Evidencia** del detalle se muestran original y primeras diez procedencias; contienen IP/mensajes potencialmente sensibles: no capturarlos si son datos reales.

## Dashboard y detalle

Por defecto últimos30 días UTC por **creación del incidente**. Fechas `[Desde incluido,Hasta excluido)`, máximo366 días. El control datetime se interpreta explícitamente en UTC, no en hora local de México. Los timestamps del detalle/línea temporal se muestran en UTC; no confundirlos con el reloj local.

Combinar prioridad, tipo, estado, responsable y fuente exacta; pulsar **Aplicar filtros**. Cambiar un selector no aplica hasta guardar los filtros. Puede elegirse tiempo del evento o recepción: solo cuentan eventos coincidentes, cada incidente una vez y en su primera fecha coincidente. Por creación, sus eventos se atribuyen a la fecha del incidente. Los atributos estado/prioridad/responsable son **actuales**, no reconstruidos al final del periodo. Un ejemplo antiguo requiere ajustar fechas/eje; una tabla vacía puede ser correcta.

Indicadores, gráficos, tabla y nuevos snapshots usan la misma cohorte. Las distribuciones incluyen prioridad/tipo/estado y las tendencias cuentan eventos deduplicados, no apariciones de evidencia. El archivo de snapshots y comparaciones experimentales son independientes de los filtros operativos. La tabla pagina50; detalle pagina100 eventos. **Detalle** presenta score/100, prioridad, factores/pesos/aportes, política de contexto y algoritmo congelado. Los pesos son parámetros iniciales de ingeniería, no científicamente validados.

## Responsables, estados y acciones

En detalle: elegir responsable activo administrador/analista, escribir justificación y **Asignar / reasignar / retirar**. La primera asignación lleva Nuevo→Asignado. Observadores/inactivos no son elegibles. Un analista solo puede operar casos propios, tomarse un caso libre o transferir uno propio. Para retirar un caso activo volver primero a Asignado; se devuelve a Nuevo. El administrador puede gestionar un cerrado según política documentada.

Flujo habitual: **Nuevo→Asignado→En análisis→En respuesta→Resuelto→Cerrado**. Elegir Nuevo estado, justificar y **Guardar transición**. El backend valida saltos, responsable, rol y revisión. En análisis puede volver a Asignado; En respuesta a En análisis; Resuelto a En análisis (nuevo ciclo) o Cerrado. Cerrado solo reabre a En análisis con administrador y responsable activo. Estados históricos sin responsable no se corrigen automáticamente: asignar explícitamente y conservar su historia.

Las acciones requieren descripción, categoría (comentario, contención, erradicación, recuperación, verificación) y revisión vigente. Fecha UTC opcional declarada; sin ella se registra fecha de transacción y procedencia. **No ejecutan comandos de red**. Historial, acciones y asignaciones son anexos auditables, sin edición/eliminación silenciosa.

Si llega un evento para un Cerrado, se conserva su estado/score y aparece señal de revisión. Para incorporar ese nuevo material al riesgo: administrador reabre justificadamente, responsable/admin usa **Reevaluar explícitamente y anexar evaluación** con motivo. Reutiliza parámetros congelados, conserva evaluaciones anteriores y aumenta revisión. **Reconocer señal** anexa revisión humana documental; no recalcula riesgo ni borra evidencia.

## Interpretar tiempos y prioridades

Prioridades: Baja 0–24, Media 25–49, Alta 50–74, Crítica75–100. No son probabilidad de ataque. Las ventanas UTC fijas de15 min pueden separar sucesos cercanos al límite o juntar episodios distintos dentro de una ventana. Tipo/origen/destino son la clave; puertos/firmas no la integran.

Tiempo hasta asignación/respuesta/resolución usa baseline y transacciones registradas. MTTD exige ocurrencia y detección verificadas; MTTR detección y finalización de respuesta. Solo evidencia operacional revisada por administrador y ciclo vigente puede habilitarlos. **No calculable** con motivo significa evidencia insuficiente, no cero ni fallo de interfaz. Los timestamps event_timestamp, received_at y creación no sustituyen detección. No atribuir estos intervalos a productividad humana.

## Evaluación experimental y ML

Administrador: en **Evaluación experimental**, semilla 202605,60 casos, presupuesto10; **Generar dataset**, seleccionar y **Comparar estrategias**. FIFO/SmartIR comparten casos y número de selecciones, con desempates deterministas. Referencias/resultados quedan reservados al investigador; otros roles ven órdenes/características sin respuestas. Importar externo exige authorized=true y procedencia declarada; máximo2 MiB. Exportar JSON/CSV conserva contexto y limitaciones.

En **Aprendizaje automático experimental**: semilla 202606,96 grupos, **Generar laboratorio**, seleccionar dataset, presupuesto test10, **Entrenar y comparar**. Repetir manifiesto idéntico devuelve409: reutilizar el existente. Generador05 no sirve como evidencia predictiva. Grupos completos separan train/test; etiquetas independientes y desenlaces no son características. LR/RF y weighted-v2 se comparan sobre el mismo test reservado. Versiones/artifactos se guardan en JSON numérico, sin carga de pickle externo.

Para inferencia experimental pegar FeatureCase sin etiquetas y **Predecir**. Se muestran versión, clase y probabilidades estimadas **sin calibración**: no confianza validada. Los modelos no sustituyen weighted-v2 operativo. Diferencias de macro-F1 sintéticas no prueban superioridad en redes reales. Con pocos datos o clases faltantes puede figurar No calculable.

## Reportes y recuperación de errores

**Guardar snapshot y descargar JSON** conserva filtros, denominadores, indicadores, tabla completa y hash. Máximo2000 incidentes/5 MiB; si excede, acotar filtros, sin truncar. En **Snapshots guardados** descargar JSON/CSV/PDF. Todos los roles consultan; observador no genera. Excluyen IP, mensajes, originales y nombres de usuario. El UUID de filtros permite trazabilidad y puede requerir tratamiento interno.

Verificar sin base ni token:

```powershell
.venv\Scripts\python backend/app/verify_report.py docs/resultados/iter10_integral_postgresql_run5.reporte.json
```

| Error | Recuperación segura |
|---|---|
| 401 | Sesión ausente/expirada/inactiva: iniciar sesión; no pegar token en documentos |
| 403 | Rol o responsabilidad insuficiente: solicitar gestión al administrador |
| 409 | Revisión obsoleta/estado incompatible/dataset duplicado: **Recargar detalle y revisión**, revisar cambios y decidir; no reintentar ciegamente |
| 428 | Cliente antiguo sin expected_revision: consultar revisión y actualizar contrato |
| 422 | Revisar campos, UTC, IP, tamaño/tipo; el backend no refleja valores sensibles |
| 413 | Dividir archivo/filtros; conservar y revisar reporte parcial EVE |
| 429 | Esperar Retry-After; no aumentar cuotas ni abrir usuarios para eludirlas |
| 503 | Presupuesto de concurrencia/bloqueo/consulta: esperar y verificar estado antes de repetir escritura |
| API no disponible | Verificar Docker, logs locales saneados, health/migración; no reinicializar volumen ni cambiar contraseña |

Si una petición se interrumpe, consultar estado y repetir archivo idéntico usando idempotencia; no borrar datos para limpiar errores. Respaldos y restauración se describen exclusivamente con destino de prueba en la guía de despliegue.
