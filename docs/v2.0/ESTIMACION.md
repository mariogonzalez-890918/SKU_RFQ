> Documento de diseño previo. El alcance implementado y las decisiones posteriores del usuario se encuentran en [IMPLEMENTACION.md](IMPLEMENTACION.md). Razones sociales dinámicas: solo AUXTI y Superadministrador administran sus vínculos con las cuatro sucursales.

# Presupuesto preliminar de tiempo — v2.0 completa

**Fecha:** 28 de octubre de 2026. Estimación de planificación basada en el código 1.8.0 inspeccionado y el alcance de este PR; no es una fecha comprometida ni una medición de funciones ya desarrolladas. El análisis y el prototipo existentes no son una implementación comercial funcional.

## Rango propuesto

**200–320 horas de trabajo efectivo**, equivalentes a **25–40 jornadas de 8 horas**, o **5–8 semanas de 40 horas**, para integrar y validar el alcance completo siguiente. El calendario real depende de disponibilidad para revisar entregas y hacer pruebas en servidor, cajas e impresora.

| Etapa | Alcance incluido | Horas |
| --- | --- | ---: |
| 1. Base multirrazón y accesos | Tres emisores capturados por el usuario, permisos y alcances, selector, esquema/migración y folios iniciales institucionales. | 28–44 |
| 2. Catálogo y clientes | Alta de clientes, direcciones y condiciones por emisor; layouts, listas de precios y configuración de IVA 0/8/16 %, incluido/excluido. | 32–48 |
| 3. Ventas institucionales | Presupuestos, plantillas, pedidos, precios históricos, condiciones, folios e impresión documento/ticket. | 32–48 |
| 4. Expendios/TPV | Caja/sesiones, pagos registrados, folio interno, cierres, solicitudes de cancelación exclusivas AUXTI/Superadministrador y reembolsos vinculados. | 44–72 |
| 5. Reportes y exportaciones | Dashboard, filtros/agrupación, consolidado por emisor, IVA por tasa, selección de columnas y plantillas, CSV/XLSX/PDF. | 28–44 |
| 6. Validación y publicación | Cotejo visual Enterprise 14, pruebas de permisos/cobros/concurrencia, migración/respaldos, regresión 1.8.0, Bixolon en equipo cliente, piloto y EXE. | 36–64 |
| **Total** | **Implementación integrada y validada** | **200–320** |

Las etapas incluyen desarrollo y sus verificaciones locales; la última agrega pruebas integrales y piloto. El rango no suma nuevamente las horas del análisis ya realizado. No representa horas continuas de ejecución autónoma del asistente ni garantiza una duración idéntica de sesión: debe revisarse conforme se implementa y se mide la primera entrega.

## Primera entrega utilizable propuesta

**Etapas 1–3: 92–140 horas efectivas** (aproximadamente 2.3–3.5 semanas a 40 h/semana). Objetivo: tres razones sociales, clientes/productos/precios/IVA, presupuestos y pedidos institucionales con impresión y folio inicial configurable.

Es una entrega para **piloto controlado de VentasIns**, con pruebas locales y sus migraciones. No incluye el TPV completo ni todos los reportes, ni sustituye la aceptación integral de la etapa 6 para producción general. Para operar caja se entrega la etapa 4 y se realiza su validación física correspondiente.

## Supuestos del rango

- Se mantiene un servidor Windows, una aplicación/base SQLite y acceso LAN/VPN; no hay sincronización multiserver ni TPV sin conexión.
- Tres razones sociales, las cuatro sucursales actuales y cajas asignadas; cantidad de terminales, tamaño del catálogo y volumen de operaciones deben medirse en el piloto.
- El usuario captura datos reales de empresas y entrega maestros/layouts claros; no se incluye depuración masiva de históricos sin correspondencias.
- MXN inicialmente, IVA 0 %, 8 % y 16 %, listas fijas y tramos acordados; sin un motor ilimitado de promociones o reglas fiscales automáticas.
- Pago en efectivo y registro manual de otros medios autorizados; sin conexión bancaria/terminal, emisión fiscal, contabilidad general ni pasarela.
- Bixolon de 80 mm instalada en el equipo cliente e impresión con diálogo del navegador; sin agente de impresión silenciosa.
- La interfaz busca cercanía a Odoo Enterprise 14 en las pantallas acordadas. Se cotejará con referencias autorizadas; no se implementa todo el ERP ni se garantiza cada personalización de una instalación desconocida.
- Sin inventario completo, producción, lotes, caducidades, contabilidad de costos o traspasos intercompañía en esta entrega.

## Qué puede ampliar el tiempo

Calca visual de pantallas adicionales, migración de ventas históricas, muchas cajas concurrentes, reglas de crédito o anticipos no definidas, cambios de empresa en operaciones emitidas, operación offline, stock en tiempo real, facturación fiscal o dispositivos con protocolos adicionales. Estos puntos se estiman aparte si se incorporan; no se asume que el rango los absorbe.

## Seguimiento del presupuesto

Al comenzar la etapa 1 se fija el backlog de aceptación y el conjunto de datos piloto. Al terminar esa etapa se compara avance real contra el rango y se actualiza la previsión restante. Cada entrega indica: alcance terminado, pruebas realizadas, pendientes y esfuerzo restante estimado. La fecha de arranque se acuerda al autorizar la implementación; este PR sigue siendo de análisis.
