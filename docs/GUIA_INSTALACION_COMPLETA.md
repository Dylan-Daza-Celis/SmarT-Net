# SmartIR-Net — guía de instalación y verificación integral

**Entorno:** Windows 11, PowerShell, Docker Desktop (WSL2), Ubuntu, Suricata 8.x, Python 3.12 y PostgreSQL 16. Esta guía es para un **prototipo local autorizado**, no para exponerlo a Internet. La instalación se considera funcional cuando supera los controles de la sección final. No existe garantía universal del 100 %.

## 1. Preparar las dependencias

Instalar Docker Desktop, Python 3.12, Git y Ubuntu WSL2. La primera instalación de WSL puede requerir PowerShell elevado y reinicio:

    wsl --install -d Ubuntu

Comprobar desde PowerShell:

    wsl --list --verbose
    docker info
    docker compose version
    py -3.12 --version

Ubuntu debe figurar como WSL versión 2. Abrir Docker Desktop en modo contenedores Linux antes de ejecutar Compose. Si `systemctl` no funciona dentro de Ubuntu, habilitar `systemd=true` bajo `[boot]` en `/etc/wsl.conf` y reiniciar WSL **solo antes de activar el laboratorio**.

Guías externas: [Microsoft WSL](https://learn.microsoft.com/es-es/windows/wsl/install), [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/), [Suricata Ubuntu](https://docs.suricata.io/en/suricata-8.0.3/install/ubuntu.html).

## 2. Instalar el proyecto, crear el backend y el administrador

En una instalación nueva, desde PowerShell:

    git clone https://github.com/Dylan-Daza-Celis/SmarT-Net.git smartir-net-mvp
    cd smartir-net-mvp
    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r agent\requirements.txt

Crear un archivo `.env` local con `DB_PASSWORD` y `JWT_SECRET` **diferentes, aleatorios y privados**. Se pueden generar mediante `py -3.12 -c "import secrets; print(secrets.token_urlsafe(48))"`. El secreto JWT necesita al menos 32 bytes. **No sobrescribir el .env si ya existe un volumen de PostgreSQL con otra contraseña.**

    docker compose config --quiet
    docker compose up -d --build
    docker compose ps
    Invoke-RestMethod http://127.0.0.1:8000/health
    docker compose exec api python -m alembic current

Esperado: `db` healthy, `api` y `web` ejecutándose; respuesta `status: ok` y migración Alembic `0009`. Para la base nueva, crear el administrador **una sola vez**:

    docker compose exec api python -m app.bootstrap

Seguir las preguntas interactivas; contraseña administrativa de al menos 12 caracteres. Si la base ya contiene usuarios, el bootstrap debe rechazarse: no reiniciar el volumen para repetirlo. Interfaz: http://127.0.0.1:5173 ; Swagger: http://127.0.0.1:8000/docs .

## 3. Crear la cuenta dedicada del sensor

En Swagger, llamar a `POST /api/auth/login` con el administrador, tomar el token obtenido y usar la opción **Authorize**. Llamar a `POST /api/users` con un cuerpo como:

    {"username":"sensor-lab-agente","password":"CONTRASENA_PRIVADA_NUEVA","role":"analista","eve_only":true}

Sustituir `CONTRASENA_PRIVADA_NUEVA` por una clave propia entre 12 y 128 caracteres. La cuenta no debe ser de administrador. Guardar la **misma contraseña** en un archivo privado en Windows; nunca incluir contraseñas en el repositorio. La API no ofrece credenciales por defecto. Más información: [monitoreo EVE](MONITOREO_CONTINUO_SURICATA.md).

## 4. Configurar rutas y secreto del agente Windows

Copiar `automation/lab.example.json` a `automation/lab.local.json`; llenar con **rutas absolutas**: `repo`, `python` (apuntando a `.venv\Scripts\python.exe`), `eve`, `state`, `runtime` y `password_file`. Se recomienda mantener estos últimos archivos bajo `$env:LOCALAPPDATA\SmartIR-Net\laboratorio` y una carpeta privada para la contraseña. Campos esenciales:

    "username": "sensor-lab-agente",
    "sensor": "suricata-wsl2-auto",
    "api": "http://127.0.0.1:8000",
    "web": "http://127.0.0.1:5173",
    "distro": "Ubuntu",
    "unit": "smartir-suricata.service",
    "compose_project": "smartir-net-mvp",
    "poll_seconds": 10,
    "docker_wait_seconds": 120

Crear la carpeta de estado y runtime, y el archivo EVE vacío si es una instalación nueva. No cambiar de ruta de origen ni de sensor reutilizando un checkpoint antiguo. El archivo secreto debe contener solamente la contraseña de la cuenta EVE y tener ACL NTFS restringida. Nunca publicarlo.

Para convertir las rutas Windows a Linux:

    $cfg = Get-Content .\automation\lab.local.json -Raw | ConvertFrom-Json
    wsl -d Ubuntu --exec wslpath -a $cfg.repo
    wsl -d Ubuntu --exec wslpath -a $cfg.eve

Anotar las dos rutas devueltas (`/mnt/c/...`); respetar comillas si tienen espacios.

## 5. Preparar Suricata en Ubuntu WSL2

Abrir Ubuntu: `wsl -d Ubuntu`. **Los comandos siguientes son Bash**. Instalar:

    sudo apt update
    sudo apt install -y software-properties-common python3 python3-yaml iputils-ping
    sudo add-apt-repository -y ppa:oisf/suricata-stable
    sudo apt update
    sudo apt install -y suricata
    suricata -V
    ip -4 -brief address show eth0

Se verificó el laboratorio original con Suricata 8.0.3; comprobar compatibilidad si se instala otra versión 8.x. Sustituir `RUTA_REPO_WSL` por la ruta Windows convertida:

    REPO_WSL='RUTA_REPO_WSL'
    cd "$REPO_WSL"

    sudo install -d -o root -g root -m 755 /opt/smartir/tools /opt/smartir/config/suricata
    sudo install -o root -g root -m 755 tools/suricata_alerts_config.py /opt/smartir/tools/
    sudo install -o root -g root -m 644 config/suricata/alert-logger.yaml /opt/smartir/config/suricata/

    if ! id smartir-sensor >/dev/null 2>&1; then
        sudo useradd --system --user-group --home-dir /var/lib/smartir-sensor --create-home --shell /usr/sbin/nologin smartir-sensor
    fi
    sudo install -d -o root -g root -m 755 /etc/smartir-lab
    sudo install -o root -g smartir-sensor -m 640 config/suricata/lab-icmp.rules /etc/smartir-lab/local.rules
    sudo install -d -o smartir-sensor -g smartir-sensor -m 750 /var/log/smartir-suricata
    sudo install -d -o root -g smartir-sensor -m 750 /var/lib/suricata/cache
    sudo install -d -o smartir-sensor -g smartir-sensor -m 750 /var/lib/suricata/cache/sgh

Para generar la salida de alertas, sustituir `RUTA_EVE_WSL` por la segunda ruta convertida y asegurarse de que el archivo Windows ya existe:

    EVE_WSL='RUTA_EVE_WSL'
    mkdir -p "$HOME/smartir-automation"
    chmod 700 "$HOME/smartir-automation"

    python3 tools/suricata_alerts_config.py --base /etc/suricata/suricata.yaml --output "$HOME/smartir-automation/suricata-windows.yaml" --eve-file "$EVE_WSL"
    python3 tools/suricata_alerts_config.py --check "$HOME/smartir-automation/suricata-windows.yaml"

    sudo install -o root -g smartir-sensor -m 640 "$HOME/smartir-automation/suricata-windows.yaml" /etc/smartir-lab/suricata.yaml
    sudo -u smartir-sensor test -w "$EVE_WSL"
    echo "Permiso EVE: $?"
    sudo -u smartir-sensor suricata -T -c /etc/smartir-lab/suricata.yaml -S /etc/smartir-lab/local.rules -l /var/log/smartir-suricata

Esperado: permiso `0` y validación Suricata exitosa. Si la configuración ya existe, inspeccionar y generar un archivo nuevo; **el generador no sobrescribe**. El archivo original `/etc/suricata/suricata.yaml` no debe modificarse innecesariamente.

## 6. Servicio systemd independiente

No copiar directamente `automation/smartir-suricata.service.example`: el servicio operativo requiere la regla explícita (`-S`) y un socket propio para evitar conflictos con `suricata.service`. Dentro de Ubuntu:

    sudo tee /etc/systemd/system/smartir-suricata.service > /dev/null <<'EOF_SERVICE'
    [Unit]
    Description=SmartIR-Net Suricata WSL2 Sensor
    After=network-online.target

    [Service]
    Type=simple
    User=smartir-sensor
    Group=smartir-sensor
    WorkingDirectory=/var/lib/smartir-sensor
    RuntimeDirectory=smartir-suricata
    RuntimeDirectoryMode=0750
    ExecStartPre=/usr/bin/python3 /opt/smartir/tools/suricata_alerts_config.py --check /etc/smartir-lab/suricata.yaml
    ExecStartPre=/usr/bin/suricata -T --init-errors-fatal -c /etc/smartir-lab/suricata.yaml -S /etc/smartir-lab/local.rules -l /var/log/smartir-suricata
    ExecStart=/usr/bin/suricata --pcap=eth0 --set unix-command.filename=/run/smartir-suricata/suricata-command.socket --init-errors-fatal -c /etc/smartir-lab/suricata.yaml -S /etc/smartir-lab/local.rules -l /var/log/smartir-suricata
    Restart=no
    KillSignal=SIGINT
    TimeoutStopSec=60
    AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
    CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN
    NoNewPrivileges=true
    UMask=0077

    [Install]
    WantedBy=multi-user.target
    EOF_SERVICE

    sudo systemd-analyze verify /etc/systemd/system/smartir-suricata.service
    sudo systemctl daemon-reload
    sudo systemctl start smartir-suricata.service
    sleep 3
    systemctl is-active smartir-suricata.service
    sudo ss -xlpn | grep smartir-suricata

Esperado: `active` y socket `/run/smartir-suricata/suricata-command.socket`. Si el motor sale, consultar `sudo journalctl -u smartir-suricata.service -n 80 --no-pager -o cat`.

Dar al **usuario Linux actual** el permiso mínimo para iniciar y detener esa unidad desde Windows:

    printf '%s\n' "$USER ALL=(root) NOPASSWD: /usr/bin/systemctl start smartir-suricata.service, /usr/bin/systemctl stop smartir-suricata.service" > /tmp/smartir-lab-sudoers
    sudo visudo -cf /tmp/smartir-lab-sudoers
    sudo install -o root -g root -m 440 /tmp/smartir-lab-sudoers /etc/sudoers.d/smartir-lab
    sudo visudo -c
    sudo -n /usr/bin/systemctl start smartir-suricata.service

Los archivos ejecutables, reglas y unidad Linux deben permanecer propiedad de root y no ser editables por el operador.

## 7. Prueba de alertas de laboratorio

En Ubuntu, y solo con permiso de la red donde se encuentre:

    ping -c 3 -W 2 1.1.1.1
    systemctl is-active smartir-suricata.service

En Windows PowerShell, comprobar el tamaño y contenido de `smartir-alerts.json`. Deben aparecer líneas JSON con `event_type: alert` y firma `SMARTIR WSL2 LAB ICMP TEST`. **La regla ICMP de ejemplo no detecta por sí sola todas las amenazas.**

## 8. Iniciar el supervisor y verificar transmisión

Desde PowerShell, carpeta raíz del proyecto, con Docker Desktop abierto:

    .\automation\start.ps1
    Start-Sleep -Seconds 15
    .\automation\status.ps1

Esperado: `suricata_unit_active: true`, `supervisor_lock_held: true`, `api_health: true`, `web_http: true`, `eve_exists: true`, `code: running` y `agent_alive: true`. `start.ps1` **solo pide el arranque**; verificar siempre `status.ps1`.

Verificar tráfico nuevo y aceptación automática:

    wsl -d Ubuntu --exec ping -c 3 -W 2 1.1.1.1
    Start-Sleep -Seconds 12
    $cfg = Get-Content .\automation\lab.local.json -Raw | ConvertFrom-Json
    Get-Content (Join-Path $cfg.runtime 'agent-current.log') -Tail 20

Debe existir un evento `accepted`; los conteos importados pueden variar y algunos eventos pueden ser duplicados. Iniciar sesión como administrador o analista en http://127.0.0.1:5173 y localizar el incidente o alerta por firma, fuente y hora de laboratorio. Los timestamps se almacenan en UTC y se muestran en la zona de México.

Probar apagado y reinicio controlados:

    .\automation\stop.ps1
    Start-Sleep -Seconds 15
    .\automation\status.ps1
    .\automation\start.ps1
    Start-Sleep -Seconds 15
    .\automation\status.ps1

No borrar `estado-auto` ni reiniciar la base de datos para forzar el resultado.

## 9. Recuperación de fallos (sin destruir datos)

| Síntoma | Comprobación | Corrección |
|---|---|---|
| `docker_engine` / pipe inaccesible | `docker info` | Abrir Docker Desktop, esperar motor y usar contenedores Linux. |
| API no responde | `docker compose logs --tail 80 api db` | Revisar `.env`, salud DB y migraciones; no borrar volumen. |
| Bootstrap rechaza | Usuarios ya existentes | Usar cuenta administrativa actual; no reinicializar PostgreSQL. |
| `smartir-suricata` falla | `journalctl -u smartir-suricata.service` | Revisar interfaz, regla, caché y socket; usar `--set unix-command.filename=...`. |
| Mensaje `Address already in use` | `sudo ss -xlpn | grep suricata` | No borrar socket ajeno: usar el socket exclusivo de la unidad SmartIR. |
| `Could not chmod ... 600` | Archivo EVE en NTFS | Revisar ACL y acceso de escritura; aviso aislado puede no ser fatal. |
| EVE sigue vacío | `suricata.log`, regla y `eth0` | Verificar motor, ping controlado y fichero configurado. |
| `degraded` persistente | `supervisor.log`, salud API y WSL | Esperar, revisar etapa y no crear otro lector. |
| Agente `401`/`403` | Cuenta EVE | Rol analista, `eve_only=true`, misma contraseña en API y archivo privado. |
| Checkpoint bloqueado | `agent-current.log` y estado | Conservar estado y revisar causa; no editar offset ni borrarlo. |

En una instalación ya existente **conservar siempre**: `.env`, `automation/lab.local.json`, contraseña privada del sensor, base y volumen PostgreSQL, archivo EVE y checkpoint. **No ejecutar** `docker compose down -v`, `docker volume prune`, `DROP DATABASE`, `TRUNCATE` ni borrar checkpoints. Para respaldos, usar `pg_dump` dentro del contenedor y `docker compose cp` para extraer un archivo privado, verificándolo en otra base aislada.

## 10. Criterios de aceptación

- [ ] Ubuntu WSL2, Docker Desktop y Python Windows están disponibles.
- [ ] Docker Compose arranca `db`, `api` y `web` y Alembic indica `0009`.
- [ ] Un administrador puede iniciar sesión y el usuario EVE restringido existe.
- [ ] El archivo de contraseña se mantiene privado.
- [ ] Suricata está activo con su socket exclusivo y la regla ICMP.
- [ ] El EVE dedicado contiene alertas JSON de una prueba de red autorizada.
- [ ] El supervisor indica `running` y `agent_alive: true`.
- [ ] El agente registra al menos un lote `accepted` tras nueva actividad.
- [ ] Los datos aparecen en la interfaz con el horario esperado.
- [ ] El ciclo `stop.ps1` → `start.ps1` funciona sin borrar estado.

**Alcance:** este éxito acredita la operación de extremo a extremo para el entorno y pruebas realizados; no certifica 100 % de disponibilidad, seguridad ni detección universal. Las cinco prácticas Packet Tracer se documentan por separado en [su guía](PRACTICAS_PACKET_TRACER.md); no se consideran implementadas por instalar SmartIR-Net.
