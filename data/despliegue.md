# Proceso de despliegue de Colibrí

> Documentación ficticia creada para la Pre-entrega 3.

## Ramas y revisiones

La rama `main` está protegida: nadie puede hacer push directo. Todo cambio entra por un pull request desde una rama `feature/*` o `fix/*`, y necesita **dos aprobaciones** de personas del equipo dueño del servicio antes de poder mergearse.

Cada pull request dispara el pipeline de integración continua, que corre los tests unitarios y de integración, los linters y un escaneo de dependencias. El pull request no se puede mergear si la cobertura de tests del servicio baja del **80%** o si el escaneo encuentra una vulnerabilidad crítica.

Los mensajes de commit siguen el formato de Conventional Commits (`feat:`, `fix:`, `chore:`), porque a partir de ellos se genera automáticamente el changelog de cada versión.

## Ventanas de despliegue

Los despliegues a producción se hacen los **martes y jueves de 10:00 a 16:00** (hora de Buenos Aires). Nunca se despliega los viernes, ni en vísperas de feriado, porque si algo sale mal no hay suficiente gente disponible para resolverlo.

Hay un **congelamiento de despliegues (freeze)** desde el **15 de diciembre hasta el 7 de enero**, y también durante los días de eventos comerciales grandes como Hot Sale y Cyber Monday. Durante un freeze solo se pueden desplegar arreglos de incidentes SEV1, con la aprobación del líder de guardia.

## Despliegue canary

Ninguna versión nueva llega a todos los usuarios de golpe. Primero se despliega como **canary**: la versión nueva recibe el **5% del tráfico durante 30 minutos**, mientras el 95% restante sigue en la versión anterior.

Durante esos 30 minutos se comparan las métricas de las dos versiones. La versión canary se promueve al 100% del tráfico solo si cumple las dos condiciones:

- La tasa de errores es menor al **1%**.
- La latencia p95 es menor a **800 milisegundos**.

Si alguna de las dos condiciones no se cumple, el sistema hace un **rollback automático** y avisa en el canal del equipo.

## Rollback manual

Si un problema aparece después de promover la versión, el rollback manual se hace con:

```
colibri-ops rollback <servicio> --a-version <tag>
```

El objetivo es que un rollback completo tarde **menos de 10 minutos**. Por eso las imágenes de las últimas 10 versiones de cada servicio se mantienen siempre disponibles en el registro de contenedores.

## Feature flags

Las funcionalidades nuevas se activan con feature flags, gestionados con Unleash. Esto permite desplegar código desactivado y encenderlo después, primero para un grupo chico de usuarios y luego para todos, sin hacer un nuevo deploy.

Los flags temporales (los que se usan para lanzar una funcionalidad) se tienen que borrar a los **60 días** de estar activos al 100%. Un flag olvidado es deuda técnica: agrega caminos al código que nadie prueba. El flag `pagos_modo_cola` es una excepción: es un flag operativo permanente que se usa en incidentes.

## Migraciones de base de datos

Las migraciones siguen el patrón **expand/contract** y nunca se despliegan en el mismo deploy que el código que las usa:

1. **Expand**: se agregan las columnas o tablas nuevas sin borrar nada. El código viejo sigue funcionando.
2. Se despliega el código nuevo, que escribe en la estructura nueva y en la vieja a la vez.
3. **Contract**: cuando ningún código usa la estructura vieja, se borra en una migración aparte.

Así, cualquier deploy se puede revertir sin perder datos. Las migraciones que bloquean una tabla grande durante más de 5 segundos requieren la aprobación del equipo de datos.
