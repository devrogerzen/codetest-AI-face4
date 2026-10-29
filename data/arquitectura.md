# Arquitectura de la plataforma Colibrí

> Documentación ficticia creada para la Pre-entrega 3. Colibrí es la plataforma de comercio electrónico de la empresa imaginaria Mercado Austral.

## Visión general

Colibrí está dividida en microservicios que se comunican por HTTP dentro del cluster y por mensajes asíncronos a través de RabbitMQ. Todo el tráfico externo entra por un único punto, el **api-gateway**, que se encarga de la autenticación, el rate limiting y el ruteo hacia los servicios internos. Ningún servicio interno está expuesto directamente a internet.

La plataforma corre en Kubernetes, en dos clusters de producción: **colibri-prod-sa** (São Paulo) y **colibri-prod-scl** (Santiago de Chile). El esquema es activo-pasivo: São Paulo atiende todo el tráfico y Santiago se mantiene sincronizado para tomar el control si la región principal falla. El cambio de región se hace con un failover de DNS que tarda alrededor de 5 minutos en propagarse.

## Servicios

| Servicio | Tecnología | Puerto interno | Responsabilidad |
|---|---|---|---|
| api-gateway | Go 1.22 | 8080 | Entrada única, autenticación con JWT, rate limiting |
| catalogo | Python 3.12 + FastAPI | 8001 | Productos, precios y stock |
| carrito | Node.js 20 | 8002 | Carritos de compra y cupones |
| pagos | Java 21 + Spring Boot | 8443 | Cobros con el proveedor de pagos y reintegros |
| notificaciones | Python 3.12 (worker) | sin puerto | Emails y notificaciones push |

El servicio de **pagos** es el único que usa TLS mutuo (mTLS) también dentro del cluster, porque maneja información sensible. Los demás servicios se comunican por HTTP interno sin cifrado, protegidos por las políticas de red de Kubernetes.

El **api-gateway** aplica un límite de **120 requests por minuto por IP**. Las requests que superan el límite reciben HTTP 429. El timeout del gateway hacia cualquier servicio interno es de **45 segundos**; si un servicio no responde en ese tiempo, el gateway devuelve HTTP 504 al cliente.

## Datos

- **PostgreSQL 16**: base de datos principal. Cada servicio tiene su propia base (catalogo_db, carrito_db, pagos_db) y ningún servicio puede leer la base de otro: si necesita esos datos, los pide por API. Hay una réplica de lectura que usa el servicio de catálogo para las búsquedas.
- **Redis 7**: se usa para dos cosas. Como caché del catálogo, con un TTL de **300 segundos** por producto, y para guardar las sesiones de carrito, que expiran a los **7 días** sin actividad. Redis corre con un límite de memoria de 4 GiB y una réplica.
- **RabbitMQ 3.13**: colas de mensajes entre servicios. Las principales son `pedidos.confirmados`, que publica el servicio de pagos cuando un cobro se aprueba, y `notificaciones.email`, que consume el worker de notificaciones.
- **MinIO**: almacenamiento de objetos compatible con S3, donde se guardan las imágenes de los productos. Las imágenes se sirven a los usuarios a través de una CDN.

## Flujo de una compra

1. El cliente arma el carrito; cada cambio se guarda en Redis a través del servicio carrito.
2. Al confirmar, el gateway envía la orden al servicio de pagos.
3. Pagos cobra con el proveedor externo y, si el cobro se aprueba, publica un mensaje en la cola `pedidos.confirmados`.
4. El servicio de catálogo consume ese mensaje y descuenta el stock.
5. El worker de notificaciones envía el email de confirmación de compra al cliente.

Si el paso 3 falla por un problema del proveedor externo, la orden queda en estado PENDIENTE y se reintenta automáticamente durante 15 minutos antes de marcarse como RECHAZADA.

## Observabilidad

Las métricas se recolectan con Prometheus y se visualizan en Grafana. Los logs de todos los servicios se centralizan en Loki y las trazas distribuidas en Tempo, de modo que una misma compra se puede seguir de punta a punta a través de todos los servicios. Cada request recibe un encabezado `X-Colibri-Trace-Id` en el gateway, y todos los servicios lo propagan a sus llamadas internas y lo incluyen en sus logs.

El tablero principal de Grafana se llama "Colibrí - Salud general" y muestra la tasa de errores, la latencia p95 de cada servicio y la profundidad de las colas de RabbitMQ.
