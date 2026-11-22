# Cinco prácticas progresivas de Cisco Packet Tracer

**Iteración 10: las cinco prácticas están DISEÑADAS, ninguna IMPLEMENTADA ni VALIDADA.** El bosquejo histórico siguiente se conserva; la especificación ampliada al final prevalece. No existen `.pkt` ni capturas de ejecución verificadas en el repositorio.

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

## Especificación ampliada de implementación — iteración 10

### B01. Material, topología y tabla común obligatoria

Red académica ficticia, sin Internet ni conexiones a infraestructura real. Material: Packet Tracer, router **2911 R1**, switch **2960-24TT S1**, cinco PC-PT (E1, E2, D1, A1, G1), Server-PT SRV, siete cables de cobre directo. Registrar versión del simulador, modelos y nombres reales de interfaces. Las variantes de IOS simuladas deben comprobarse con `?`; no se presume soporte completo de IOS real.

```text
E1 Fa0 ─ S1 Fa0/1     E2 Fa0 ─ S1 Fa0/2     D1 Fa0 ─ S1 Fa0/3
A1 Fa0 ─ S1 Fa0/4     SRV Fa0 ─ S1 Fa0/5    G1 Fa0 ─ S1 Fa0/6
                          S1 Gi0/1 ═ R1 Gi0/0 (trunk 802.1Q)
```

Direcciones estáticas en Desktop → IP Configuration. Sin DHCP, NAT ni WAN. Máscara de todas las subredes: **255.255.255.0 (/24)**.

| Dispositivo/interfaz | IPv4 | Máscara | Gateway | VLAN/puerto |
|---|---|---|---|---|
| E1 Fa0 | 192.168.10.11 | 255.255.255.0 | 192.168.10.1 | 10 / Fa0/1 |
| E2 Fa0 | 192.168.10.12 | 255.255.255.0 | 192.168.10.1 | 10 / Fa0/2 |
| D1 Fa0 | 192.168.20.11 | 255.255.255.0 | 192.168.20.1 | 20 / Fa0/3 |
| A1 Fa0 | 192.168.30.11 | 255.255.255.0 | 192.168.30.1 | 30 / Fa0/4 |
| SRV Fa0 | 192.168.40.10 | 255.255.255.0 | 192.168.40.1 | 40 / Fa0/5 |
| G1 Fa0 | 192.168.99.10 | 255.255.255.0 | 192.168.99.1 | 99 / Fa0/6 |
| S1 Vlan99 | 192.168.99.2 | 255.255.255.0 | 192.168.99.1 | Gestión |
| R1 Gi0/0.10 | 192.168.10.1 | 255.255.255.0 | No aplica | 10 |
| R1 Gi0/0.20 | 192.168.20.1 | 255.255.255.0 | No aplica | 20 |
| R1 Gi0/0.30 | 192.168.30.1 | 255.255.255.0 | No aplica | 30 |
| R1 Gi0/0.40 | 192.168.40.1 | 255.255.255.0 | No aplica | 40 |
| R1 Gi0/0.99 | 192.168.99.1 | 255.255.255.0 | No aplica | 99 |
| R1 Gi0/0.999 | Sin IP | No aplica | No aplica | 999 nativa, sin hosts |

VLAN10 estudiantes, 20 docentes, 30 administración, 40 servicios, 99 gestión; 999 nativa sin usuarios. Servicios por etapa: P01 ICMP/ARP/802.1Q; P02 HTTP TCP80 y DNS UDP53; P03 SSH TCP22/AAA local; P04 Syslog UDP514; P05 conserva los anteriores.

Para **cada prueba** registrar ID, fecha real, versión PT, configuración inicial, origen/destino, protocolo, resultado esperado, observado y archivo/captura. Guardar copias nuevas P01…P05 cuando se construyan realmente. DISEÑADA = procedimiento; IMPLEMENTADA = `.pkt` y configuración disponibles; VALIDADA = matriz positiva/negativa con evidencias revisadas. Un `.pkt` por sí solo no valida resultados. Los marcadores `<SECRETO_LOCAL>` deben sustituirse solo en el laboratorio; ocultar contraseñas y hashes en evidencias.

### P01 ampliada — Segmentación por VLAN

**DISEÑADA.** Objetivo general: construir dominios de broadcast separados y routing explícito. Objetivos específicos: asignar puertos, transportar etiquetas y configurar gateways; distinguir conectividad L2/L3. Fundamento: una VLAN separa broadcasts, pero el router habilita comunicación entre redes; la seguridad entre VLAN requiere políticas adicionales.

Material, conexiones y direccionamiento: **B01 completa**. Procedimiento:

1. Crear y cablear B01; configurar los seis hosts con su tabla.
2. En consola S1:

```ios
enable
configure terminal
hostname S1
vlan 10
 name ESTUDIANTES
vlan 20
 name DOCENTES
vlan 30
 name ADMINISTRACION
vlan 40
 name SERVICIOS
vlan 99
 name GESTION
vlan 999
 name NATIVA_SIN_HOSTS
interface range FastEthernet0/1-2
 switchport mode access
 switchport access vlan 10
 spanning-tree portfast
interface FastEthernet0/3
 switchport mode access
 switchport access vlan 20
 spanning-tree portfast
interface FastEthernet0/4
 switchport mode access
 switchport access vlan 30
 spanning-tree portfast
interface FastEthernet0/5
 switchport mode access
 switchport access vlan 40
 spanning-tree portfast
interface FastEthernet0/6
 switchport mode access
 switchport access vlan 99
 spanning-tree portfast
interface GigabitEthernet0/1
 switchport mode trunk
 switchport trunk native vlan 999
 switchport trunk allowed vlan 10,20,30,40,99,999
 no shutdown
interface Vlan99
 ip address 192.168.99.2 255.255.255.0
 no shutdown
exit
ip default-gateway 192.168.99.1
interface range FastEthernet0/7-24
 shutdown
interface GigabitEthernet0/2
 shutdown
end
copy running-config startup-config
```

3. **Antes de configurar R1**, E1→E2 debe responder y E1→D1 fallar. Repetir tras ARP/convergencia; un primer ping perdido no demuestra aislamiento.
4. En R1:

```ios
enable
configure terminal
hostname R1
interface GigabitEthernet0/0
 no ip address
 no shutdown
interface GigabitEthernet0/0.10
 encapsulation dot1Q 10
 ip address 192.168.10.1 255.255.255.0
interface GigabitEthernet0/0.20
 encapsulation dot1Q 20
 ip address 192.168.20.1 255.255.255.0
interface GigabitEthernet0/0.30
 encapsulation dot1Q 30
 ip address 192.168.30.1 255.255.255.0
interface GigabitEthernet0/0.40
 encapsulation dot1Q 40
 ip address 192.168.40.1 255.255.255.0
interface GigabitEthernet0/0.99
 encapsulation dot1Q 99
 ip address 192.168.99.1 255.255.255.0
interface GigabitEthernet0/0.999
 encapsulation dot1Q 999 native
 no ip address
end
copy running-config startup-config
```

5. Verificar S1: `show vlan brief`, `show interfaces trunk`, `show interfaces FastEthernet0/1 switchport`, `show mac address-table`. R1: `show ip interface brief`, `show ip route`, `show running-config`. Hosts: `ipconfig` y `ping` al gateway/otras VLAN. Simulation: filtrar ARP/ICMP y seguir broadcasts.

Positivas/criterios: E1↔E2, E1→D1/A1/SRV tras routing, G1→192.168.99.2; al menos cuatro pings por par tras ARP. Negativas: inter-VLAN antes de R1 y puerto Fa0/7 apagado. No esperar aislamiento inter-VLAN después del routing: P02 lo añade.

Errores: VLAN/puerto incorrectos, trunk sin VLAN permitida, interfaz padre apagada, máscara/gateway incorrectos o SVI99 sin enlace activo. Diagnosticar en ese orden con los `show`. En 2960 no exigir `switchport trunk encapsulation dot1q`: utiliza dot1Q sin ese comando.

Evidencias: topología/IP/puertos, VLAN/trunk/rutas, pings antes/después y broadcast simulado. Relación: intercomunicación L2/L3, segmentación y superficie de exposición; SmartIR relaciona IP pero no configura VLAN. Limitación específica: PT simula protocolos, no rendimiento o aislamiento físico real.

### P02 ampliada — ACL extendida

**DISEÑADA.** Objetivo general: imponer y verificar una política a estudiantes. Específicos: ordenar reglas, aplicar dirección y demostrar permitidos/denegados. Fundamento: ACL evalúa primera coincidencia y denegación implícita; no es firewall con estado ni IDS.

Material/topología/IPv4/puertos: **P01/B01 sin cambios**. SRV activa HTTP y DNS en Services; registro A `www.lab.invalid → 192.168.40.10`, DNS de E1 .40.10. Política: estudiantes sin administración/gestión; hacia servidores solo DNS UDP y HTTP; demás comunicación de laboratorio permitida.

1. Guardar copia P02 y registrar E1→A1 y HTTP SRV antes de aplicar reglas.
2. R1:

```ios
configure terminal
ip access-list extended ESTUDIANTES_IN
 deny ip 192.168.10.0 0.0.0.255 192.168.30.0 0.0.0.255
 deny ip 192.168.10.0 0.0.0.255 192.168.99.0 0.0.0.255
 permit udp 192.168.10.0 0.0.0.255 host 192.168.40.10 eq 53
 permit tcp 192.168.10.0 0.0.0.255 host 192.168.40.10 eq 80
 deny ip 192.168.10.0 0.0.0.255 192.168.40.0 0.0.0.255
 permit ip 192.168.10.0 0.0.0.255 any
interface GigabitEthernet0/0.10
 ip access-group ESTUDIANTES_IN in
end
copy running-config startup-config
```

3. S1 conserva P01, sin ACL L3 en el 2960. Hosts conservan B01; SRV mantiene gateway .40.1. En R1: `show access-lists`, `show ip interface GigabitEthernet0/0.10`, `show running-config`. Seguir paquetes con Simulation.
4. Positivas: E1→E2 y D1 ping; HTTP por IP y nombre al SRV; G1→A1. Negativas: E1→A1/G1 ping; E1→SRV ICMP y TCP443 (PDU complejo si disponible). Un servicio apagado también produce fallo: demostrar descarte en R1 y no atribuirlo al ACL sin evidencia.

Criterio: todas las permitidas llegan y denegadas se descartan por la regla prevista. Contadores solo si la versión los implementa. Diagnóstico: wildcard vs máscara, dirección `in`, permiso prematuro, DNS incorrecto/HTTP apagado. Probar IP antes del nombre. `log` no es requisito porque el simulador puede no generar mensajes ACL.

Evidencias: tabla antes/después, ACL/aplicación, PDU descartado, HTTP/DNS permitido. Relación: seguridad de la intercomunicación por política; una denegación de prueba no demuestra un ataque. SmartIR admite una anotación manual de laboratorio, sin importar ACL automáticamente. Limitación: simulación sin estado, contadores/logs parciales, ninguna medición de capacidad ante ataques.

### P03 ampliada — SSH y AAA local

**DISEÑADA.** Objetivo general: restringir gestión remota a G1 con autenticación local. Específicos: configurar SSHv2, AAA y acceso VTY; probar credenciales erróneas y Telnet. Fundamento: cifrado, autenticación y autorización son controles distintos; AAA local no implica servidor central ni MFA.

Material/topología/tabla: **P02/B01 completos**. G1 .99.10 administra R1 .99.1 y S1 .99.2 por TCP22; ACL anterior vigente. Mantener consola abierta como recuperación segura del laboratorio.

1. En R1, desde consola:

```ios
configure terminal
ip domain-name laboratorio.invalid
username labadmin privilege 15 secret <SECRETO_LOCAL>
enable secret <OTRO_SECRETO_LOCAL>
aaa new-model
aaa authentication login default local
access-list 10 permit host 192.168.99.10
access-list 10 deny any
crypto key generate rsa
```

Responder **2048** cuando solicite tamaño RSA (entrada interactiva, no comando global). Registrar si no lo admite. Un fallback1024 solo demuestra un simulador antiguo: **obsoleto de laboratorio, no recomendación de producción**.

```ios
ip ssh version 2
line vty 0 4
 login authentication default
 transport input ssh
 access-class 10 in
 exec-timeout 5 0
end
copy running-config startup-config
```

2. En **S1**, ejecutar el mismo bloque global/RSA con hostname S1 existente y configurar **`line vty 0 15`** con las cuatro instrucciones anteriores. Conservar SVI/gateway B01. Verificar `show running-config`: todas las VTY existentes deben quedar protegidas; si R1 también ofrece5–15 aplicar allí la misma política.
3. Desde G1: `ssh -l labadmin 192.168.99.1` y .99.2; introducir secretos solo en prompt y salir con `exit`. Probar una contraseña inválida, `telnet 192.168.99.1` y SSH desde D1 (denegado por VTY, sin depender del ACL de estudiantes).
4. Verificar `show ip ssh`, `show users`, `show access-lists` y configuración **saneada**. `show aaa sessions` solo si la ayuda lo ofrece.

Criterios: dos SSH positivos, credencial errónea rechazada, Telnet rechazado, D1 rechazado. Si no existe `aaa new-model`, registrar AAA pendiente; `login local` con SSH es una alternativa parcial que no valida el bloque AAA.

Diagnóstico: claves requieren hostname/dominio; SVI/gateway impiden llegar a S1; método AAA ausente bloquea login. Verificar usuario antes de restringir VTY; recuperar desde consola en la copia, sin borrar configuraciones. Evidencias: VTY/AAA saneadas, estado SSH, sesión exitosa y tres negativas, sin contraseña/hashes.

Relación: seguridad del plano de gestión; SmartIR usa JWT/Argon2id y no administra dispositivos por SSH ni conecta AAA IOS. Limitaciones: subset AAA/SSH según PT y cifrado simulado sin validación criptográfica real.

### P04 ampliada — Centralización Syslog

**DISEÑADA.** Objetivo general: centralizar mensajes realmente soportados. Específicos: habilitar receptor/severidad, identificar emisor y separar ausencia de entrega/evento. Fundamento: Syslog UDP514 no garantiza entrega ni confidencialidad; un reloj no verificado no constituye UTC confiable.

Material/topología/IPv4: **P03/B01**; mismo SRV .40.10 gateway .40.1 Fa0/5 VLAN40, HTTP/DNS conservados. Services → SYSLOG → On; ningún Suricata u otro servidor necesario.

1. Guardar P04. Anotar reloj del simulador y `show clock` de ambos dispositivos. Si se ajusta, en EXEC: `clock set 12:00:00 22 Nov 2026`, declarando hora manual de laboratorio, sin precisión NTP acreditada.
2. En **R1 y S1**:

```ios
configure terminal
service timestamps log datetime msec
logging host 192.168.40.10
logging trap informational
logging on
end
copy running-config startup-config
```

Si la ayuda solo ofrece `logging 192.168.40.10`, usar esa forma y documentar. No exigir TLS/source-interface/login logging no soportados. S1 llega por gateway; R1 está conectado a VLAN40.
3. En S1, `interface FastEthernet0/1`, `shutdown`, `no shutdown`, `end`: comprobar caída/restauración de E1. Mantener trunk y servidor arriba. Salir de configuración también puede generar mensaje según PT; un fallo SSH no es estímulo garantizado.
4. Consultar `show logging`, `show clock`, `show ip interface brief`, Services SYSLOG y Simulation UDP hacia514.
5. Negativa: apagar **solo servicio SYSLOG** en SRV, generar otro cambio Fa0/1, comprobar que ese nuevo mensaje no se recibe; reactivar y generar uno nuevo. No borrar historial ni esperar retransmisión UDP.

Criterios: al menos un mensaje de cada dispositivo si realmente se emite en esa versión, identificando fuente/texto/hora; positiva y negativa documentadas. Si solo S1 emite, R1 queda pendiente. Diagnóstico: servicio/IP/gateway, ping R1/S1→SRV, trunk/VLAN40, nivel y estímulo compatible; distinguir transporte de logger simulado.

Evidencias: servicio On, configuración, mensajes reales, paquete UDP y negativa. Relación: observabilidad y procedencia en redes segmentadas. **SmartIR no tiene receptor Syslog ni adaptador IOS**: no existe importación automática o conversión a EVE auténtico. Limitaciones: reloj/logger parciales, UDP sin garantías y ninguna medición de pérdida real.

### P05 ampliada — Escenario integrado y correlación documental

**DISEÑADA.** Objetivo general: unir controles de red, evidencia y análisis sin atribuir integración automática. Específicos: ejecutar pruebas controladas, anotar procedencia, preparar JSON manual y comprobar riesgo/ventanas. Fundamento: observación, anotación y priorización son capas diferentes; un score no demuestra ataque.

Material, conexiones, tabla IPv4 y servicios: **P04/B01 sin cambios**, más editor UTF-8 y SmartIR **en instancia aislada**. R1 conserva subinterfaces/ACL/SSH/Syslog; S1 VLAN/trunk/SSH/Syslog; SRV HTTP/DNS/Syslog. Para construir desde cero aplicar bloques por dispositivo P01→P04. No hay comandos ofensivos adicionales.

1. Guardar P05 y verificar VLAN/trunk/rutas/ACL/SSH/logging con los `show` anteriores. Registrar configuración saneada.
2. Positivos: E1→HTTP SRV, G1→SSH R1/S1, E1→E2. Negativos: E1→A1, D1→SSH, credencial SSH inválida desde G1. Registrar captura real por prueba. Si ACL/AAA no genera Syslog, usar PDU/pantalla real, sin inventar log.
3. Bitácora: PT-P05-01…, origen, destino, protocolo, resultado, reloj/zona y limitación. No llamar DoS a un cable apagado ni malware/exfiltración a un ping; esos tipos requieren otro laboratorio. Los seis ejemplos sintéticos existentes no proceden de PT.
4. Preparar manualmente JSON SmartIR. Plantilla **SINTÉTICA DE DISEÑO, NO OBSERVADA**:

```json
{"events":[{"source":"packet-tracer-manual-SYNTHETIC","event_timestamp":"2026-11-22T12:01:00Z","source_ip":"192.168.10.11","destination_ip":"192.168.30.11","event_type":"acceso_no_autorizado","severity":40,"asset_criticality":50,"message":"PLANTILLA NO OBSERVADA; intento autorizado; severidad y criticidad por política; referencia PT-P05-01"}]}
```

Al implementar, enlazar cada hecho con su captura. Solo declarar timestamp UTC observado si se justifica conversión y reloj; de lo contrario mantener escenario sintético con hora programada. Severidad40/criticidad50 son supuestos. No introducir etiqueta de referencia como score ni fabricar alerta IDS.
5. Como analista en SmartIR aislado importar y repetir exactamente el archivo: duplicado, no evento nuevo. La evidencia PT permanece en bitácora externa/referencia del mensaje; no existe adaptador de evidencia Packet Tracer.
6. Crear copias **explícitamente sintéticas** a12:02 y12:16 UTC, mismo tipo/IP y distinto mensaje/fecha. Primeras dos en `[12:00,12:15)`, última en `[12:15,12:30)`: esperar dos incidentes. Para un evento: `.35*40+.25*50+.15*20+.15*75+.10*50=45.75→46 Media`; con dos:48.75→49 Media. No atribuirlo a eficacia de ACL.
7. Revisar weighted-v2/contexto desconocido, responsables, estados y No calculable. Exportar snapshot JSON/CSV/PDF con eje evento `[12:00,12:30)` y verificar hash. Separar capturas PT, anotaciones y evidencias SmartIR.

Criterios: positivos/negativos atribuibles al control correcto; bitácora enlazada, idempotencia, dos ventanas y fórmula comprobadas **cuando se ejecute**. Diagnóstico: fecha sin zona422, permiso403, cuota429/Retry-After, revisión409; tipo/IP/ventana distintos separan incidentes. No ajustar parámetros para forzar prioridades.

Evidencias requeridas: `.pkt`, versión, tabla IPv4, configuraciones saneadas, matriz con al menos seis pruebas de red, capturas/bitácora, JSON manual/SHA-256, repetición de importación y snapshot verificable. Relación: intercomunicación, política, gestión y monitoreo con análisis documental. Limitaciones: **sin Suricata en PT, captura EVE, streaming Syslog a SmartIR ni eficacia real demostrada**; ventanas/ingestión no equivalen a MTTD/MTTR humano.

### Estado y referencias verificables

| Práctica | Diseño | Implementación | Validación actual |
|---|---|---|---|
| P01 VLAN | B01/P01 completos | Pendiente | Sin ejecución/capturas |
| P02 ACL | B01/P02 completos | Pendiente | Sin ejecución/capturas |
| P03 SSH/AAA | B01/P03 completos | Pendiente | Confirmar subset IOS |
| P04 Syslog | B01/P04 completos | Pendiente | Confirmar mensajes/reloj |
| P05 Integrada | B01/P05 completos | Pendiente | Traducción manual diseñada |

Referencias primarias consultadas el22-11-2026; no certifican ejecución del simulador:

- [Cisco: routing entre VLAN/dot1Q](https://www.cisco.com/c/en/us/td/docs/routers/ios-xe/lan-wan/lan-wan/m_lsw-conf-rout-vlan.html).
- [Cisco: puertos access/trunk/VLAN nativa](https://www.cisco.com/en/US/docs/ios/lanswitch/configuration/guide/lsw_enet_switch_net.html).
- [Cisco: SSH y AAA local](https://www.cisco.com/c/en/us/td/docs/routers/ir8340/software/configuration/b_ir8340_cg_17_7/m_ssh.pdf) (IOS XE real: contrastar subset PT).
- [Cisco NetAcad: Logging from Multiple Sources](https://contenthub.netacad.com/courses/cyberops/_common/25.3.11-packet-tracer---logging-from-multiple-sources.pdf): localizado en búsqueda; descarga503 en esta revisión. No se atribuye lectura íntegra.

La matriz histórica RPT/RF se conserva arriba; no se declara cumplimiento de un catálogo externo no aportado. La matriz ampliada se basa en controles y procedimientos identificables de este archivo.
