# Capítulo propuesto: Diseño e implementación inicial de SmartIR-Net

## Arquitectura seleccionada
Se adoptó una arquitectura cliente-servidor de tres servicios: aplicación web React/TypeScript, API REST Python/FastAPI y PostgreSQL para persistencia. Los contenedores se orquestan mediante Docker Compose en ambiente local. La API valida eventos estructurados y los normaliza parcialmente, detecta duplicados mediante SHA-256, agrupa eventos por una clave provisional de correlación y estima riesgo explicable.

## Pipeline implementado en la versión 0.1
Archivo JSON o JSONL -> validación Pydantic -> estandarización de fechas a UTC -> deduplicación por fingerprint -> agrupamiento por tipo de evento y destino -> cálculo ponderado -> almacenamiento PostgreSQL -> consulta REST -> visualización en dashboard.

## Cálculo de riesgo propuesto
Riesgo = 0.35(S) + 0.25(A) + 0.15(R) + 0.15(T) + 0.10(C), donde S es severidad, A criticidad de activo, R recurrencia, T tipo de amenaza y C contexto; cada factor se expresa de 0 a 100. Estos pesos son una elección provisional que **requiere validación experimental**. La recurrencia es `min(100, 20*n_eventos)`, mientras que C es un valor neutral 50 hasta integrar contexto de red. Los pesos y la escala se han seleccionado para crear una línea base explicable; no hay evidencia aún de superioridad frente a revisión cronológica.

El sistema conserva los intervalos del documento: 0–24 Baja, 25–49 Media, 50–74 Alta y 75–100 Crítica.

## Tablas iniciales
- `events`: UUID, huella, fuente, tiempo, direcciones IP, tipo, severidad, criticidad, mensaje, registro original e incidente asociado.
- `incidents`: UUID, clave correlativa, tipo, destino, estado, puntuación, prioridad, explicación y fecha de creación.

Este esquema es una **implementación parcial** del modelo conceptual de 14 entidades del documento base. No se afirma que los demás requisitos estén implementados.

## Prueba de aceptación propuesta
1. Ejecutar contenedores, verificar `/health`.
2. Importar `examples/eventos_demo.json` por interfaz web.
3. Verificar 4 eventos y 3 incidentes; medir el puntaje obtenido por caso.
4. Importar nuevamente el archivo; esperar 0 registros nuevos y 4 duplicados.
5. Cerrar y reabrir contenedores sin eliminar volumen y comprobar persistencia.

## Evidencias a insertar al ejecutar
- [ ] Captura del dashboard con números observados.
- [ ] Captura de Swagger en `http://localhost:8000/docs`.
- [ ] Captura de `docker compose ps`.
- [ ] Resultado de importación original y duplicada.
- [ ] Detalle del incidente y explicación del score.

## Diferencias respecto del alcance final
Sin autenticación/RBAC, cifrado HTTPS, auditoría, historial de acciones, importación nativa de Suricata EVE JSON, correlación temporal, entrenamiento de ML, ni cálculo formal de MTTD/MTTR. Deben documentarse como pendientes o incorporarse en nuevas versiones, nunca afirmarse como completados.
