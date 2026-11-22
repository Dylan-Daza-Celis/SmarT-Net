# Cinco prácticas progresivas de Cisco Packet Tracer

Todos los escenarios pertenecen a una **red académica ficticia** y solo deben ejecutarse en Packet Tracer o un laboratorio autorizado. Los archivos `.pkt` se crearán y guardarán mediante la aplicación Packet Tracer (no se incluyen porque requieren el simulador).

## Infraestructura común propuesta
- VLAN 10 Estudiantes: `192.168.10.0/24`, gateway `192.168.10.1`.
- VLAN 20 Docentes: `192.168.20.0/24`, gateway `192.168.20.1`.
- VLAN 30 Administración: `192.168.30.0/24`, gateway `192.168.30.1`.
- VLAN 40 Servidores/monitoreo: `192.168.40.0/24`, gateway `192.168.40.1`.
- VLAN 99 Gestión: `192.168.99.0/24`, gateway `192.168.99.1`.
- Equipo de referencia: un switch 2960, un router con subinterfaces 802.1Q, cuatro PC y un servidor. Se agregan dispositivos cuando una práctica lo requiere.
- La tabla de IP y puertos debe adaptarse a los modelos concretos disponibles.

## P01 — Segmentación y conectividad
**Objetivo:** configurar VLAN y rutas inter-VLAN.
1. Conectar PCs al switch y éste al router.
2. Configurar VLAN 10/20/30/40/99, asignar puertos de acceso, enlace trunk.
3. Configurar subinterfaces 802.1Q y gateways .1 en el router.
4. Configurar direcciones IP estáticas en hosts.
5. Validar pings intra/inter VLAN y `show vlan brief`, `show interfaces trunk`, `show ip interface brief`.
**Evidencia:** topología, tablas IP, configuración, pings y comandos show.

## P02 — ACL y accesos no autorizados
**Objetivo:** restringir acceso desde Estudiantes a Administración manteniendo acceso a servicios autorizados.
1. Recuperar P01 y guardar copia como `P02_ACL.pkt`.
2. Crear ACL extendida que deniegue tráfico originado en `192.168.10.0/24` hacia `192.168.30.0/24` y permita el resto del tráfico pertinente.
3. Aplicar la ACL en dirección de entrada a la subinterfaz VLAN 10.
4. Probar ping/HTTP desde Estudiantes a Administración (denegado), y hacia servidor permitido.
5. Registrar `show access-lists` y pruebas antes/después.
**Evidencia:** reglas, contadores, comunicaciones permitidas/denegadas.

## P03 — Administración segura y AAA
**Objetivo:** impedir acceso administrativo inseguro y comprobar controles de autenticación.
1. Recuperar P02, guardar `P03_AAA_SSH.pkt`.
2. Definir hostname, dominio y usuario administrativo local; habilitar SSH y VTY solo SSH.
3. Activar `aaa new-model` y `aaa authentication login default local` cuando la imagen/modelo los soporte.
4. Comprobar acceso remoto SSH correcto e intento inválido; documentar limitaciones de simulador.
**Evidencia:** configuración VTY/AAA, pruebas correctas e inválidas. Evitar exponer contraseñas reales en capturas.

## P04 — Monitoreo con Syslog
**Objetivo:** centralizar logs y evidenciar cambios de estado/seguridad.
1. Recuperar P03 y guardar `P04_Syslog.pkt`.
2. Configurar un Server-PT en VLAN 40, por ejemplo `192.168.40.10`, habilitar servicio SYSLOG disponible.
3. Configurar `logging host 192.168.40.10` y mensajes de nivel apropiado en router/switch según soporte.
4. Generar eventos de interfaz o autenticación soportados por el simulador.
5. Verificar los mensajes realmente recibidos en el servidor.
**Evidencia:** interfaz de Syslog, mensaje con fecha/fuente, comandos pertinentes.

## P05 — Análisis de incidentes integrado con SmartIR-Net
**Objetivo:** documentar eventos observados y analizarlos en el dashboard.
1. Recuperar P04 y guardar `P05_Incidentes.pkt`.
2. Ejecutar pruebas de acceso denegado por ACL y autenticación SSH inválida, exclusivamente simuladas.
3. Registrar hora, origen, destino, tipo, resultado y evidencia capturada.
4. Traducir los hechos observados al esquema JSON de SmartIR-Net. Indicar explícitamente qué campos fueron medidos y cuáles estimados (por ejemplo severidad/criticidad).
5. Importar los registros a SmartIR-Net y comparar niveles de prioridad calculados.
**Evidencia:** archivo pkt, resultados de simulación, JSON preparado y dashboard.

## Matriz de trazabilidad
| Práctica | Requisitos relacionados |
|---|---|
| P01 | RPT-01, RPT-02, RPT-08 |
| P02 | RPT-03, RPT-06, RPT-08 |
| P03 | RPT-05, RPT-06, RPT-08 |
| P04 | RPT-04, RPT-06, RPT-07, RPT-08 |
| P05 | RPT-06, RPT-07, RPT-08; RF-07, RF-09, RF-18 a RF-21 |

## Advertencia metodológica
Packet Tracer no reproduce íntegramente Suricata ni todos los comportamientos reales de ataques (malware, DoS, exfiltración). Los seis escenarios experimentales de la investigación requieren datasets sintéticos o un laboratorio separado apropiado. No presentar simulaciones ficticias como capturas de un IDS real.
