# Plan de entrega de 48 horas

## Día 1
- [ ] Instalar Docker / ejecutar `docker compose up --build -d`.
- [ ] Confirmar `GET /health`, dashboard y documentación OpenAPI.
- [ ] Importar datos sintéticos; capturar conteos y explicación del score.
- [ ] Validar deduplicación y comportamiento de reimportación.
- [ ] Packet Tracer P01: VLAN y enrutamiento inter-VLAN; guardar `P01_Segmentacion.pkt`.
- [ ] Packet Tracer P02: ACL con tráfico permitido/denegado; guardar `P02_ACL.pkt`.

## Día 2
- [ ] Packet Tracer P03: SSH y AAA según dispositivos soportados.
- [ ] Packet Tracer P04: Syslog, eventos y comprobación de registros.
- [ ] Packet Tracer P05: correlación entre eventos controlados y dataset importable.
- [ ] Capturar evidencia real de cada prueba (configuración, conectividad, logs).
- [ ] Registrar resultados medidos y limitaciones en la antología.
- [ ] Ensayar demostración completa de 5–8 minutos.

## Criterios mínimos verificables
1. Dashboard visible localmente.
2. Datos persistentes en PostgreSQL.
3. Al menos una importación correcta y una duplicada.
4. Puntaje y explicación de incidentes visibles.
5. Cinco archivos `.pkt` funcionales guardados por el estudiante.
6. Documento final que separe claramente propuestas, pruebas realizadas y pendientes.

## Riesgos
- Las imágenes Docker y dependencias requieren conexión a Internet durante la instalación.
- Packet Tracer tiene diferencias por versión/modelo: registrar comandos aceptados y no simular capacidades inexistentes.
- El prototipo v0.1 no equivale a todos los 44 requisitos funcionales del documento base.
- MTTD y MTTR solo pueden reportarse con marcas temporales adecuadas; no atribuir mejoras no medidas.
