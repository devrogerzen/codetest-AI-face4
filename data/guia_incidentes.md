# Guía de incidentes de Colibrí

> Documentación ficticia creada para la Pre-entrega 3.

## Niveles de severidad

Todo incidente se clasifica apenas se detecta. La severidad define qué tan rápido hay que responder y quién tiene que participar.

- **SEV1 (crítico)**: la plataforma está caída para todos los usuarios, o los pagos no funcionan. Hay que responder en **15 minutos**, se nombra un comandante de incidente de forma obligatoria y se publica una actualización de estado cada **30 minutos** hasta resolverlo.
- **SEV2 (alto)**: una funcionalidad importante está degradada o afecta solo a una parte de los usuarios, por ejemplo búsquedas muy lentas o errores intermitentes en el carrito. Hay que responder en **1 hora**.
- **SEV3 (bajo)**: errores menores que tienen una forma de evitarlos, o problemas puramente estéticos. Se atienden el **siguiente día hábil**.

Si hay dudas entre dos niveles, se elige el más grave. Bajar la severidad más tarde no tiene costo; subestimar un incidente sí.

## Guardia (on-call)

La guardia rota cada semana y el cambio de turno es los **lunes a las 10:00** (hora de Buenos Aires). Siempre hay una persona de guardia principal y una de respaldo. Si la guardia principal no confirma la alerta en 10 minutos, la alerta escala automáticamente a la persona de respaldo.

Todo incidente se coordina en el canal **#incidentes-colibri**. Las conversaciones por mensaje privado están prohibidas durante un incidente, para que quede registro de todas las decisiones.

## Runbook: Redis caído o inaccesible

**Síntomas**: la latencia del catálogo sube por encima de 2 segundos, aparecen errores `ConnectionError` de Redis en los logs, y los usuarios pierden sus carritos o no pueden agregar productos.

**Pasos**:

1. Verificar el estado de los pods con `kubectl get pods -n datos -l app=redis`.
2. Si el pod está en `CrashLoopBackOff`, revisar si se quedó sin memoria: el límite es de 4 GiB. Un pico de memoria suele deberse a claves sin TTL.
3. Si el pod principal no se recupera en 5 minutos, hacer el failover a la réplica con `colibri-ops redis failover`.
4. Mientras tanto, el catálogo sigue funcionando en **modo degradado**: lee directamente de la réplica de PostgreSQL, más lento pero sin cortar el servicio. Los carritos que estaban solo en Redis se pierden y hay que avisarlo en la comunicación del incidente.

Un Redis caído es SEV2 si el catálogo funciona en modo degradado, y SEV1 si además fallan los pagos.

## Runbook: errores 5xx en pagos

**Síntomas**: la tasa de errores 5xx del servicio de pagos supera el 2% durante 5 minutos seguidos, o la cola `pedidos.confirmados` deja de recibir mensajes.

**Pasos**:

1. Revisar en el tablero de Grafana si el problema es interno o del proveedor de pagos externo.
2. Si el problema es del proveedor, activar el feature flag **`pagos_modo_cola`**. Con ese flag activo, los pagos no se cobran en el momento: se guardan y se procesan apenas el proveedor se recupera, y el usuario ve el mensaje "Tu pago se está procesando".
3. Si el problema es interno (un deploy reciente, por ejemplo), hacer rollback del servicio de pagos a la versión anterior.

Un incidente de pagos es siempre SEV1, aunque se active `pagos_modo_cola`.

## Comunicación

Durante un SEV1, el comandante de incidente publica las actualizaciones en la página de estado pública y en el canal #incidentes-colibri. Cada actualización dice qué está afectado, qué se está haciendo y cuándo será la próxima actualización. Nunca se promete una hora de resolución que no se puede garantizar.

## Postmortem

Todo incidente **SEV1 o SEV2** requiere un postmortem escrito, que hay que presentar dentro de los **5 días hábiles** siguientes a la resolución. El formato es sin culpables (blameless): se analiza qué falló en el sistema y en los procesos, nunca quién se equivocó. Cada postmortem termina con acciones concretas, cada una con una persona responsable y una fecha límite.
