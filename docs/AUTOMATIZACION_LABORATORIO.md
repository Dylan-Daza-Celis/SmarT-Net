# Iteración14.1 — automatización Windows/WSL2

Alcance: supervisor local opcional, sin cambios de API, esquema, scores o datos. No inicia Docker Desktop por su cuenta, no abre captura durante las pruebas y no instala privilegios automáticamente. Las prácticas Packet Tracer y la iteración15 quedan fuera del alcance.

## Instalación revisada por el operador

Copiar automation/lab.example.json a automation/lab.local.json (ignorado por Git) o a un directorio privado. Completar rutas ABSOLUTAS, distribución real (`wsl -l -v`), proyecto Compose existente, Python del venv y archivo EVE real. No cambiar sensor, ruta de origen ni checkpoint de la instalación habitual. Si se cambia de eve.json a smartir-alerts.json, mantener el estado anterior y crear otro directorio de checkpoint, conforme a11/12; no editar offsets ni resetear silenciosamente. Detener primero cualquier agente manual mediante su cierre cooperativo; el lock del Store existente sigue evitando lectores simultáneos. Un lock ocupado provoca salida, no reintentos infinitos.

La contraseña existente permanece fuera del repositorio, en password_file; no introducirla en JSON, argumentos o tarea programada. Revisar DACL de ese archivo y de runtime/state: solo operador y administradores autorizados; no otorgar Everyone ni usar chmod777. Los ejemplos no contienen secretos. La cuenta sensor-lab-agente debe continuar activa, analista y eve_only=true. El agente verifica este alcance en la API. No se crea ni modifica ninguna cuenta.

Para WSL, preparar un wrapper **privado** usando tools/suricata_alerts_config.py de12, que conserve los outputs del principal y añada logger regular, nombre fijo, threaded=false y types:[alert]. Ejecutar --check y `suricata -T` sobre la configuración REAL antes de habilitar inicio automático. El archivo dedicado debe corresponder exactamente a la ruta Windows configurada, por ejemplo /mnt/c/SmartIRLab/smartir-alerts.json. Revisar propietario, ACL y rotación/retención. No se validó aquí la configuración privada del usuario ni esa ruta concreta.

Revisar automation/smartir-suricata.service.example y sustituir sus rutas. Crear explícitamente un usuario Linux dedicado smartir-sensor si no existe, con acceso únicamente a reglas/configuración y directorio de logs. Copiar helper/tools y config necesarios a /opt/smartir bajo propiedad root, sin escritura del operador. Instalar el wrapper privado y su base en /etc/smartir-lab, root-owned. La unidad y todos los archivos ejecutables/config/reglas deben ser confiables y no modificables por quien tenga permiso sudo de inicio. **No apuntar un servicio con capacidades a scripts editables desde /mnt/c.**

La unidad usa PCAP `--pcap=eth0` (comprobado en --help de Suricata8.0.3), no AF_PACKET. Cambiar eth0 solo tras comprobar `ip link show eth0` y autorización del laboratorio. ExecStartPre rechaza otro Suricata visible, verifica hash/configuración del wrapper y ejecuta -T. Restart=no evita bucles ante configuración inválida. CAP_NET_RAW/CAP_NET_ADMIN son las capacidades de captura, con usuario no root, NoNewPrivileges y UMask0077; comprobar compatibilidad real de libpcap/interfaces en ese entorno.

Un operador Linux autorizado instala la unidad en /etc/systemd/system/smartir-suricata.service y ejecuta `sudo systemctl daemon-reload`. No habilitar también otro servicio Suricata sobre la misma fuente. El supervisor inicia la unidad explícitamente; no es necesario enable en paralelo. Verificar que WSL tenga systemd activo (`systemctl is-system-running`); si no lo tiene, detener preparación y habilitarlo según la política local antes de seguir.

automation/sudoers.example es una plantilla, NO un archivo listo para instalar. Sustituir LAB_USER, validar con `sudo visudo -cf /ruta/privada/plantilla` e instalar mediante visudo con root:root0440. Solo autoriza start/stop de esa unidad fija. No permitir sudo genérico sobre powershell, bash, python, editores, systemctl arbitrario o comandos con comodines. Los scripts usan sudo -n: falta de autorización falla sin pedir ni almacenar contraseña. Alternativamente un administrador inicia/detiene manualmente el sensor; el supervisor reutiliza la unidad activa sin adoptarla para apagarla.

## Operación

Desde la raíz del repositorio, con política PowerShell local compatible (no se modifica ExecutionPolicy):

```powershell
.\automation\start.ps1 -Config C:\SmartIRLab\lab.local.json
.\automation\status.ps1 -Config C:\SmartIRLab\lab.local.json
.\automation\stop.ps1 -Config C:\SmartIRLab\lab.local.json
.\automation\restart.ps1 -Config C:\SmartIRLab\lab.local.json
# Diagnóstico interactivo, mismo bloqueo y permisos:
.\automation\start.ps1 -Config C:\SmartIRLab\lab.local.json -Foreground
```

Start solicita un proceso oculto; su mensaje no certifica readiness. El supervisor toma un lock exclusivo en el checkpoint ANTES de Compose/WSL/lector, comprueba docker info, hace compose up -d (sin --build), espera API/web hasta120s, inicia la unidad declarada si está inactiva, espera EVE hasta30s y lanza el agente existente. Docker Desktop debe estar iniciado por el usuario. El supervisor no cambia contraseñas, no ejecuta bootstrap ni borra volúmenes.

status consulta salud HTTP y unidad Linux, existencia del archivo y lock del supervisor; last_observation lleva fecha UTC y puede estar obsoleta. No constituye heartbeat IDS ni prueba de nuevas alertas aceptadas. Revisar supervisor.log, agent-current.log, agent-current.err y `journalctl -u smartir-suricata.service --since today` localmente. No compartir cuerpos EVE o logs privados sin revisión. El supervisor solo escribe códigos constantes; nunca contraseña/token/cuerpo API. Los logs actuales del agente se reemplazan al nuevo arranque: archivarlos localmente si se requiere historia; los checkpoints y evidencias del servidor no se borran.

Stop crea una solicitud local. El agente acepta la nueva opción opcional --stop-file y cierra su Store/transporte en finally; el modo anterior sin esa opción permanece igual. La señal se observa entre operaciones y durante esperas, no interrumpe una transacción. Si una operación sigue bloqueada, el supervisor conserva su lock y registra shutdown_pending; no fuerza terminación ni libera propiedad para arrancar otro lector. Restart espera hasta90s a que se libere; si no ocurre, se niega a duplicar procesos. No usar kill de PID antiguo como recuperación automática.

Se detiene la unidad solo si este supervisor la inició. Compose se conserva por defecto; stop_owned_compose=true permite compose stop únicamente si no había servicios corriendo al inicio. Si el arranque encuentra un proyecto parcialmente activo, conserva el proyecto completo al parar: decisión conservadora para no detener componentes ajenos. Nunca down, rm, prune, eliminación de EVE/estado ni wsl --shutdown. No se cierra Docker Desktop globalmente.

Stop también escribe agent-stop.request directamente: puede solicitar cierre de un agente propio que haya sobrevivido a una caída abrupta del supervisor. No mata PIDs. Si el supervisor murió abruptamente, no se reconstruye ni inventa la propiedad de servicios WSL/Compose: comprobarlos y detenerlos manualmente si corresponde antes de recuperar.

## Supervisión y recuperación

Sondeo configurable5–300s. API o unidad caída producen degraded. Se conserva el agente para sus reintentos transitorios/backoff/Retry-After y dedup at-least-once existentes. No se reinicia automáticamente el sensor, Docker ni un agente terminado. Un error permanente provoca salida/registro del supervisor; revisar y corregir antes de start/restart. Estado failed queda en last_failure y log aunque el proceso ya haya terminado. Los controles de abuso y límites de EVE se mantienen.

Después de reiniciar Windows/WSL/Docker: comprobar estado real, desbloqueo por cierre del proceso anterior, archivos retenidos, servicio y API. Iniciar de nuevo con las mismas rutas/identidad; el agente recupera outbox/checkpoint. Si WSL perdió la generación rotada, hay truncamiento o checkpoint bloqueado, seguir MONITOREO_CONTINUO_SURICATA, conservar evidencia y resolver explícitamente; no resetear ni saltar líneas. Si existe un agente manual, conservarlo o cerrarlo antes de iniciar esta gestión. Si Suricata ya corría fuera de systemd, la unidad debe rechazarlo; no lanzar otro sensor ni matarlo automáticamente.

Inicio al iniciar sesión, opcional y explícito:

```powershell
.\automation\register-logon.ps1 -Config C:\SmartIRLab\lab.local.json
# Retirar solo la tarea creada por estos scripts:
.\automation\register-logon.ps1 -Config C:\SmartIRLab\lab.local.json -Remove
```

La tarea usa usuario interactivo actual, RunLevel Limited, IgnoreNew, sin contraseña y sin reinicios automáticos. No ejecuta como SYSTEM. Espera Docker hasta docker_wait_seconds (ejemplo60, rango0–180); habilitar el arranque de Docker Desktop al iniciar sesión desde su configuración si se desea. Si Docker no está listo al vencer ese límite, falla y requiere inicio manual después; no hay bucle oculto de relanzamiento. No se registró tarea alguna en esta validación. Revisar historial del Programador y políticas corporativas. No duplicar otros arranques automáticos del agente/sensor.

## Pruebas y límites

`python -m pytest backend/tests/test_lab_automation.py backend/tests/test_agent.py -q` verifica sintaxis real PowerShell, stop idempotente y conservación, rechazo de URL remota, fallo Docker y reentrada, lock concurrente, inicio parcial y limpieza selectiva mediante servicios **simulados**. También prueba un agente real con stop-file preexistente, estado temporal y puerto1, sin enviar eventos. Las regresiones de agente cubren rotación, dedup, errores, reintentos y checkpoints. Evidencia saneada: docs/resultados/iter141_pruebas.json.

No se ejecutó start contra la instalación operativa, no se abrió eth0, no se creó unidad/sudoers/usuario/tarea y no se modificó ningún servicio existente. La configuración PCAP se contrastó con --help real de Suricata8.0.3, pero la unidad, permisos NTFS/WSL y arranque al logon requieren validación del operador sobre sus rutas privadas. No se afirma un ensayo completo Windows→captura real→API. No se reejecutan ML/build/frontend al no cambiar esos módulos; el foco es orquestación y compatibilidad del agente. No se introduce migración.

Una primera ejecución falló por una clave incorrecta en el arnés (password frente a password_file); se corrigió el test, sin cambiar credenciales. Los conteos finales se obtienen del JUnit real. La antología sigue en revisión y la iteración15 no se ha iniciado.

Resultados comprobados: **46 casos focalizados aprobados en17.39s** (incluido el guardado de stop durante arranque) y **224 casos de la suite completa SQLite aprobados en132.38s** sobre la versión final con espera Docker acotada. Ocho pruebas nuevas de automatización. Persiste la advertencia TestClient/httpx. No se repitieron PostgreSQL, build React ni Playwright en14.1 porque no hay cambios en esos módulos; los resultados14 se conservan como históricos, no se presentan como ejecuciones nuevas.

Después de esa suite se añadió la señal directa de parada para el agente huérfano: **8 pruebas de automatización aprobadas en9.96s**. El manifiesto conserva el snapshot de fuentes de la suite completa y el hash posterior de stop.ps1, sin atribuir aquella ejecución al ajuste posterior.
