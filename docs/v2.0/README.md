# RFQ_SKU_GMP v2.0 — revisión de integración

**Estado:** análisis para revisión, 28 de octubre de 2026. No implementa módulos ni cambia el EXE 1.8.0.

Se integrarán **VentasIns** y **Expendios** en el mismo RFQ_SKU_GMP, con sus usuarios, catálogo de venta, presupuestos, pedidos, listas de precios y dashboard. El **Punto de Venta pertenece a Expendios**; su visibilidad se asignará en Accesos por perfil. La referencia visual final solicitada es **Odoo Enterprise 14**, que sustituye a Odoo 19 como objetivo de estos módulos.

## Qué revisar

1. [Diseño funcional, menús y permisos](DISENO_FUNCIONAL.md).
2. [Layouts propuestos de carga](LAYOUTS.md).
3. [Integración, etapas y criterios de aceptación](INTEGRACION_Y_PRUEBAS.md).
4. [Prototipo navegable](prototipo.html): abrir el archivo local en el navegador. Simula perfiles, visibilidad de Expendios, presupuestos, caja y formatos de impresión. Usa datos ficticios, no guarda operaciones y no se conecta al servidor. Los botones de impresión muestran la propuesta; imprimir exige pulsar el botón correspondiente.
5. [Fuentes y alcance de la comparación con Odoo 14](FUENTES.md).

## Decisiones propuestas

| Tema | Propuesta para v2.0 |
| --- | --- |
| Integración | Una aplicación, autenticación y base de datos compartidas; módulos comerciales separados de los generadores SKU. |
| Perfiles nuevos | Etiquetas **Expendios** y **VentasIns**, claves internas `expendios` y `ventasins`. No se crean cuentas ni contraseñas en este análisis. |
| Acceso al TPV | Superadministrador asigna **Ver Expendios / Punto de Venta** por perfil. Ver no concede operar caja ni modificar precios. |
| Apariencia | Reproducir de cerca la estructura y composición de Odoo Enterprise 14 en los módulos nuevos: selector de aplicaciones, barra superior, listas, formularios, estados y caja. Mantener la identidad GMP. |
| Presupuestos | Plantillas reutilizables, conversión trazable a pedido y versiones de precios. |
| Precios | Listas por canal, sucursal, cliente y vigencia, con una selección explícita y reproducible. |
| Expendios | Cajas y sesiones por sucursal, cobros, tickets y cierre; permisos para cambios, cancelaciones y devoluciones. |
| Impresión | Documento comercial con composición de Odoo 14 y ticket Bixolon de 80 mm. No modificar los formatos actuales de requisiciones. |
| Implantación | Por etapas y con módulos inicialmente deshabilitados para perfiles existentes hasta asignación de Sistemas. |

## Pendiente de confirmar durante la revisión

- Significado comercial de **VentasIns**: se conserva literalmente el nombre solicitado, sin asumir “insumos” o “institucional”.
- Referencia visual de la instalación Enterprise 14 utilizada: tema, personalizaciones y capturas de lista, formulario, TPV y documento impreso. Las fuentes públicas verifican la base 14.0; no prueban equivalencia exacta con una instalación Enterprise personalizada.
- Layout empresarial real: hojas, encabezados, campos obligatorios y datos de muestra anonimizados. Los esquemas adjuntos son una propuesta, no una plantilla ya compatible con el importador actual.
- Listas autorizadas, impuestos/precios incluidos, descuentos máximos, pagos, cajas, tratamiento de anticipos y responsables de cierres.
- Tamaño documental predeterminado (Carta propuesto, A4 alternativo), condiciones comerciales, logo y textos de firma/pie.

Estas decisiones no bloquean la revisión del diseño. Ninguna se considera aprobada por el mero hecho de abrir este PR. El siguiente paso será incorporar los comentarios y después implementar por etapas; este PR no despliega v2.0.

## Validación del análisis

- Prototipo comprobado en Edge a 1440×900, 1024×768 y 390×844: selector, menús, búsqueda, formulario, caja, pago simulado y vistas de impresión.
- Verificado el acceso de consulta sin posibilidad de operar caja y la ocultación de Expendios al retirar su checkbox. Esta es validación de la simulación visual; la autorización real del servidor queda definida para la implementación.
- Documento y ticket comercial muestran el mismo importe; el presupuesto no aparece como cobrado. No se enviaron impresiones físicas ni se registraron cobros.
- Sin llamadas HTTP/API, recursos externos ni persistencia en el prototipo. Enlaces relativos y diff documental revisados. La aplicación y su EXE permanecen en 1.8.0.
