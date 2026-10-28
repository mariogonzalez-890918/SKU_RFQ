# Referencia Odoo Enterprise 14

Consulta: **2026-10-28**. Se revisó primero 19.0 y, al precisar el usuario la versión, se sustituyó por **14.0** como referencia final. Las observaciones y rutas siguientes provienen de archivos oficiales de Odoo 14.0; no se reutiliza código de Odoo en el prototipo.

## Fuentes primarias

| ID | Fuente oficial 14.0 | Qué se verificó |
| --- | --- | --- |
| O1 | [Ventas: vistas y menús](https://github.com/odoo/odoo/blob/14.0/addons/sale/views/sale_views.xml) | Jerarquía Pedidos, Productos, Informes y Configuración; clientes y equipos; vistas y permisos de grupo. |
| O2 | [Plantillas de presupuestos](https://github.com/odoo/documentation/blob/14.0/content/applications/sales/sales/send_quotations/quote_template.rst) | Plantillas reutilizables con líneas, secciones, notas y opciones de confirmación. |
| O3 | [Listas de precios](https://github.com/odoo/documentation/blob/14.0/content/applications/sales/sales/products_prices/prices/pricing.rst) | Precios/listas por segmento, cliente y reglas. La precedencia GMP propuesta se especifica aparte. |
| O4 | [Menús de Punto de Venta](https://github.com/odoo/odoo/blob/14.0/addons/point_of_sale/views/point_of_sale_view.xml) | Pedidos, Clientes, Informes y Configuración, con grupos de usuario/gerente. |
| O5 | [Configuración y entrada al dashboard TPV](https://github.com/odoo/odoo/blob/14.0/addons/point_of_sale/views/pos_config_view.xml), [tarjetas del dashboard](https://github.com/odoo/odoo/blob/14.0/addons/point_of_sale/views/point_of_sale_dashboard.xml) | Entrada Dashboard y cajas/sesiones representadas con tarjetas. |
| O6 | [Productos TPV](https://github.com/odoo/odoo/blob/14.0/addons/point_of_sale/views/product_view.xml), [sesiones](https://github.com/odoo/odoo/blob/14.0/addons/point_of_sale/views/pos_session_view.xml), [pedidos TPV](https://github.com/odoo/odoo/blob/14.0/addons/point_of_sale/views/pos_order_view.xml) | Catálogo/listas, sesiones y consulta de operaciones; algunas opciones dependen de grupos/configuración. |
| O7 | [Documento de presupuesto/pedido](https://github.com/odoo/odoo/blob/14.0/addons/sale/report/sale_report_templates.xml) | Encabezado, cliente/direcciones, folio, fechas, vendedor, tabla de líneas, totales, términos y firma. |
| O8 | [Recibos e impresión TPV](https://github.com/odoo/documentation/blob/14.0/content/applications/sales/point_of_sale/receipts_invoices.rst) | Reimpresión y configuración de recibos. |
| O9 | [Reportes TPV](https://github.com/odoo/documentation/blob/14.0/content/applications/sales/point_of_sale/reporting.rst) | Acceso a análisis desde Informes y desde el dashboard. |
| O10 | [Referencia visual pública del TPV](https://github.com/odoo/documentation/blob/14.0/content/applications/sales/point_of_sale/pos-interface.png) | Imagen de interfaz incluida en la documentación 14.0; para cotejo de distribución de caja y productos. |

| O11 | [Formulario de empresas](https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/views/res_company_views.xml), [contactos](https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/views/res_partner_views.xml) | Campos de empresa/contacto y separación de entidades en la base 14.0. El aislamiento y asignaciones de tres emisores son diseño GMP. |
| O12 | [Exportación/importación 14.0](https://github.com/odoo/documentation/blob/14.0/content/applications/general/export_import_data.rst) | Acción Exportar, selección de campos y plantillas. La referencia describe CSV/XLS; RFQ propone CSV/XLSX y PDF para informes. |

## Qué significa «casi como calca» en este diseño

El objetivo visual es Odoo **Enterprise 14**. Se propone conservar sus patrones de navegación y composición en los módulos nuevos: selector de aplicaciones, barra superior, controles de listado, formulario con estados, pestañas y TPV con pedido y catálogo.

La evidencia pública consultada documenta la base 14.0 y funcionalidades compartidas. No se tuvo acceso a una instalación Enterprise 14 del usuario ni a su tema, personalizaciones o módulos privados. Por ello, el prototipo es una propuesta cercana para revisión; no una reproducción exacta verificada de esa instalación. Antes de cerrar el diseño visual se cotejarán capturas de referencia autorizadas en las mismas resoluciones.

Las decisiones propias de GMP —Expendios como contenedor del TPV, asignación por perfil, precedencia de precios, alcances por sucursal, reglas de autorización y base de datos compartida— son propuestas de integración, no afirmaciones sobre comportamientos predeterminados de Odoo.
