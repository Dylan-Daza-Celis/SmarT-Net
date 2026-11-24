# SmartIR-Net — entrega académica

Prototipo de gestión y priorización de incidentes de seguridad de redes académicas, implementado con React/TypeScript, FastAPI/Python, PostgreSQL y Suricata. El agente Windows lee eventos EVE JSON de un sensor Suricata en Ubuntu WSL2 y los envía a la API. Los eventos se normalizan, correlacionan y priorizan mediante un modelo ponderado explicable. Se conservan historial de incidentes y reportes.

## Estructura de la entrega

- `backend/`: API, motor de riesgos, modelos y migraciones.
- `frontend/`: interfaz web, filtros, incidentes y reportes.
- `agent/`: lector incremental de Suricata EVE con checkpoint.
- `automation/`: scripts de inicio, estado, parada y servicio WSL2.
- `config/` y `tools/`: archivos y utilidades de configuración del sensor.
- `examples/`: archivos demostrativos.
- `docs/`: guías técnicas, arquitectura y diseño de las cinco prácticas Packet Tracer.

## Inicio en el equipo de laboratorio configurado

1. Encender Windows e iniciar Docker Desktop.
2. Desde PowerShell en la raíz del repositorio:

```powershell
.\automation\start.ps1
Start-Sleep -Seconds 15
.\automation\status.ps1
```

3. Verificar `supervisor_lock_held: true`, `agent_alive: true`, `api_health: true` y `suricata_unit_active: true`. El estado `running` confirma la observación más reciente del supervisor.
4. Abrir http://127.0.0.1:5173 e iniciar sesión con una cuenta autorizada.

Al terminar:

```powershell
.\automation\stop.ps1
```

El supervisor no instala Docker Desktop, Suricata, cuentas o permisos. Para reproducir una instalación nueva se requieren las configuraciones privadas, claves y permisos descritos en `docs/GUIA_DESPLIEGUE.md` y `docs/AUTOMATIZACION_LABORATORIO.md`. No se incluyen secretos. Para reconstruir contenedores tras cambios de código, usar `docker compose up -d --build`.

## Alcance y evidencias

La integración real Suricata → archivo EVE → agente Windows → FastAPI fue comprobada con tráfico ICMP de laboratorio, incluyendo recepción automática de tres alertas nuevas. Los datos se conservan en UTC y los horarios visibles se presentan para la zona de México. Las **cinco prácticas de Cisco Packet Tracer están diseñadas** en `docs/PRACTICAS_PACKET_TRACER.md`; su implementación y validación en `.pkt` están pendientes y no deben presentarse como ejecutadas.

Esta es la **versión ligera de entrega**. Se retiraron los arneses de pruebas, benchmarks, capturas y resultados históricos de iteraciones para reducir el tamaño del directorio. La versión íntegra (incluyendo `backend/tests/`, `frontend/tests/`, `validation/`, `benchmarks/` y `docs/resultados/`) se conserva en la rama Git `archivo/pre-entrega-2026-11-23`. Las guías históricas de validación pueden mencionar esos archivos archivados.

**No borrar** `.env`, `automation/lab.local.json`, `.venv`, volúmenes de PostgreSQL ni registros/checkpoints de Suricata. La limpieza local de generados se realiza con `automation/limpiar-entrega.ps1`.
