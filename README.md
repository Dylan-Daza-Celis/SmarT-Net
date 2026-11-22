# SmartIR-Net | MVP ejecutable v0.1

Prototipo académico basado en `Antología.pdf` y `Proyecto_06_SmartIR-Net.pdf`.

## Requisitos
- Docker Engine / Docker Desktop y Docker Compose v2
- Puertos locales 5173 y 8000 libres

## Arranque
```bash
cp .env.example .env
# Editar .env con una contraseña sin caracteres especiales de URL para esta versión
# En Windows PowerShell: Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Abrir http://localhost:5173 (dashboard) y http://localhost:8000/docs (API OpenAPI).

## Prueba rápida
1. Abrir el dashboard.
2. Seleccionar **Importar JSON / JSONL** y elegir `examples/eventos_demo.json`.
3. Verificar 4 eventos y 3 incidentes; la segunda importación debe detectar 4 duplicados.
4. Inspeccionar prioridad y explicación de cada incidente.

Alternativa terminal (Linux/macOS):
```bash
curl -X POST http://localhost:8000/api/events/import -H 'Content-Type: application/json' --data-binary @examples/eventos_demo.json
curl http://localhost:8000/api/incidents
```

## Arquitectura
Fuentes / archivos -> FastAPI (validación, normalización inicial, deduplicación) -> PostgreSQL -> correlación simple -> scoring explicable -> React/TypeScript.

### Diseño temporal, no completo
- Correlación provisional por tipo y destino; aún no implementa ventana temporal ni IP origen en agrupamiento.
- Puntajes de 0 a 100 con ponderaciones propuestas (35% severidad, 25% activo, 15% recurrencia, 15% ataque, 10% contexto fijo a 50). Son **hipótesis de ingeniería**, no resultados validados.
- Prioridades: 0–24 baja, 25–49 media, 50–74 alta, 75–100 crítica.
- Acepta un formato JSON propio de laboratorio, no ingiere todavía EVE JSON original de Suricata.
- Sin autenticación, roles, auditoría, historial, tratamiento de archivos no confiables ni HTTPS. **No desplegar en Internet**.
- Datos sintéticos, las pruebas no representan capturas reales de Packet Tracer.

## Detener
```bash
docker compose down
```
Para borrar también la base de datos: `docker compose down -v` (destructivo).

## Próxima iteración prioritaria
Autenticación y RBAC, adaptador EVE JSON Suricata, estados e historial, ventana temporal de correlación, importación con reporte de errores, pruebas automatizadas y documentación de resultados.

Consulta `docs/PLAN_48_HORAS.md`, `docs/ANTologia_implementacion.md` y `docs/PRACTICAS_PACKET_TRACER.md`.
