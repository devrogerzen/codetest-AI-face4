# Políticas de seguridad de Colibrí

> Documentación ficticia creada para la Pre-entrega 3.

## Gestión de secretos

Las contraseñas, API keys y certificados se guardan únicamente en **HashiCorp Vault**. Está prohibido guardar secretos en el código, en archivos de configuración versionados o en variables de entorno escritas a mano en los servidores. El pipeline de integración continua escanea cada commit y bloquea el merge si detecta algo que parece un secreto.

Los secretos se rotan automáticamente cada **90 días**. Las credenciales del proveedor de pagos son la excepción: se rotan cada **30 días**, por ser las más sensibles. Si un secreto se filtra (por ejemplo, alguien lo pega en un chat), se considera comprometido y se rota de inmediato, aunque no haya señales de que alguien lo usó.

## Acceso a producción

Nadie entra a los servidores de producción de forma directa. El acceso es solo a través de un **bastión** que exige autenticación de dos factores (MFA), y cada sesión queda grabada.

El acceso de emergencia, llamado **break-glass**, permite permisos de administrador durante un incidente. Requiere la aprobación de **dos personas**: el líder de guardia y alguien del equipo de seguridad. Los permisos de break-glass expiran solos a las **4 horas** y cada uso se revisa en la reunión semanal de seguridad.

Los permisos se otorgan con el principio de mínimo privilegio: cada persona tiene acceso solo a los servicios de su equipo. Los accesos se revisan cada trimestre y se quitan los que ya no se usan.

## Datos personales

Colibrí guarda datos personales de los clientes: nombre, email, teléfono y direcciones de entrega. Estos datos se cifran en reposo con **AES-256** y en tránsito con TLS 1.3.

Los números de tarjeta **nunca** se guardan en Colibrí: el proveedor de pagos los tokeniza y Colibrí guarda solo el token. Ningún servicio, log o base de datos de Colibrí puede contener un número de tarjeta completo.

Cuando un cliente pide la baja de su cuenta, sus datos personales se eliminan dentro de los **30 días**, salvo los que la ley obliga a conservar, como los datos de facturación.

## Logs

Los logs no pueden contener datos personales. Antes de enviarse a Loki, cada log pasa por un filtro que enmascara emails, teléfonos y documentos de identidad. Si aparece un dato personal sin enmascarar, se trata como un incidente de seguridad SEV2.

Los logs de aplicación se retienen **30 días** en Loki. Los logs de auditoría, que registran quién accedió a qué y cuándo, se retienen **1 año** en almacenamiento de solo lectura.

## Vulnerabilidades

Las dependencias de todos los servicios se escanean de forma automática **una vez por semana**. Los plazos para corregir una vulnerabilidad dependen de su gravedad:

- **Crítica**: se parchea en un máximo de **72 horas**.
- **Alta**: se parchea en un máximo de **14 días**.
- **Media o baja**: se incluye en el plan de trabajo del siguiente mes.

Si una vulnerabilidad crítica no tiene parche disponible, el equipo de seguridad define una mitigación temporal, como desactivar la funcionalidad afectada o bloquear el patrón de ataque en el api-gateway.

## Reporte de incidentes de seguridad

Cualquier persona que detecte un posible problema de seguridad tiene que reportarlo enseguida a **seguridad@colibri.example**, aunque no esté segura de que sea grave. Reportar un falso positivo no tiene ninguna consecuencia; demorar el reporte de un problema real sí. Los incidentes de seguridad siguen la misma guía de severidades que los incidentes operativos, pero el comandante de incidente es siempre una persona del equipo de seguridad.
