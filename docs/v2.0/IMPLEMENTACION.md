# RFQ_SKU_GMP 2.0.0-rc1

Integración candidata para revisión, sin sustituir automáticamente el servicio instalado. Los módulos comerciales comparten usuarios, sesión y SQLite con RFQ_SKU_GMP. Los catálogos SKU y las requisiciones mantienen sus rutas y reglas.

## Razones sociales y sucursales

En el módulo comercial, **Configuración → Razones sociales** permite agregar tantas razones sociales como se requieran, editar sus datos y eliminarlas. Cada una se vincula explícitamente con una o varias de **EJIDOS, SAN PABLO, CUAUTITLAN y EJE 8**. **Solo Superadministrador y AUXTI** pueden realizar estas operaciones. Gerente y operadores no pueden hacerlo aunque modifiquen una petición HTTP.

En **Configuración → Expendios y sucursales** se muestran siempre esas cuatro sucursales y se seleccionan sus razones sociales. En TPV se elige primero el expendio, después una razón social vinculada y finalmente su caja. Se respetan además los permisos de empresas, sucursales y cajas del usuario. No se asigna una empresa automáticamente a las cuatro sucursales.

Eliminar conserva el registro inactivo y las copias históricas en documentos. No permite nuevas operaciones. Deben cerrarse primero las cajas abiertas; para desvincular una sucursal hay que reasignar sus cajas activas. La configuración usa revisiones para evitar sobrescribir cambios simultáneos.

## Activación y uso

1. Conservar una copia de `data` y `config.json` de la instalación antes de probar la candidata. El EXE público arranca vacío y no incluye credenciales, maestros, información fiscal ni la liga privada de OneDrive.
2. Superadministrador habilita **Pedidos institucionales** y/o **Expendios / Punto de venta** en los accesos por perfil. Existen los roles nuevos **VentasIns** y **Expendios**. Los perfiles existentes conservan sus accesos guardados.
3. Entrar al módulo desde el menú de la aplicación. AUXTI necesita que el módulo esté habilitado; una vez habilitado puede administrar las razones sociales.
4. Capturar razones sociales y sucursales, importar el Excel de prueba en **Maestro de ventas** y revisar antes de aplicar. En **Accesos por usuario**, Superadministrador asigna empresas, sucursales y cajas a los operadores.
5. Para TPV, crear una caja, elegir RUTA o DESPACHO y abrir sesión con fondo inicial. El pedido se cobra una sola vez, aunque se repita el envío.

## Implementado

- Ventas institucionales: clientes, presupuestos, conversión a pedido, edición de cantidades/precios/descuentos, eliminación de partidas, cancelación directa con motivo, plantillas por cliente, precios específicos y folios iniciales por razón social.
- Expendios: productos por categoría/módulo PDV, eliminación de partidas antes de cobrar, listas RUTA/DESPACHO, efectivo/tarjeta/transferencia, cambio, sesiones y cierre con diferencia de efectivo.
- Solicitudes de cancelación del TPV con folio propio: solo AUXTI y Superadministrador resuelven. Cancelar no registra por sí solo una salida de dinero; el reembolso real se confirma aparte y queda auditado.
- IVA 0%, 8% y 16% extraído de precios finales con `Decimal`. El precio enviado por el navegador se ignora en TPV. Se conservan precios, impuestos y datos del emisor del documento emitido.
- Ticket Bixolon de 80 mm: encabezado con logo Mi Pan y/o sucursal, ambos opcionales por caja. No imprime razón social, RFC, domicilio fiscal ni campos fiscales del cliente. Documento institucional imprimible por separado.
- Reportes por razón social, fechas y estado, presupuestos/pedidos separados en indicadores, selección de filas y columnas, configuraciones guardadas por usuario, exportación XLSX/CSV/PDF. Cancelaciones excluidas del total exportado.
- Menús comerciales con composición inspirada en Odoo 14, diferentes de los módulos actuales. Menú adaptable para celular y tablet. Implementación propia, sin dependencias del código Enterprise.

## Maestro y actualización

Solo **SUGERIDO**. A SKU; B tipo; C categoría; D subcategoría; E línea; F módulo PDV; G expendio; H descripción; I público institucional; J ruta; K despacho; N impuesto; O UOM; S estado. Se valida el encabezado y se interpreta el formato porcentual de Excel. Los SKU históricos de A se conservan; los vacíos/duplicados/incorrectos se rechazan para corregir la fuente.

La importación es transaccional: un error conserva la versión anterior. No borra artículos ausentes ni sobrescribe precios manuales o negociados por cliente. El maestro comercial no regenera ni reemplaza los catálogos históricos SKU.

**Actualización automática cada 12 horas**, ejecutada por el servidor, y botón **Sincronizar ahora**. La liga se configura únicamente en la base privada. La fuente proporcionada inicialmente permite ver el libro en navegador, pero la descarga directa devolvió acceso denegado. Se requiere una liga que entregue el XLSX sin una sesión de navegador. El inicio OAuth/renovación de tokens de Graph no se incluye en esta candidata; no se afirma que la liga de vista previa ya sincronice. Ante error permanece el último maestro válido.

## Límites de esta candidata

Se entrega para probar la integración y revisar sus pantallas antes de reemplazar el servicio operativo. Los respaldos/restauraciones por módulo de la versión anterior siguen disponibles para SKU y requisiciones; no incluyen las tablas comerciales nuevas. Para preservar toda la candidata, detener el servicio y copiar completa la carpeta `data`. La restauración comercial selectiva y reportes dinámicos avanzados de agrupación quedan pendientes antes de considerar la v2 estable.

No se incluyen contabilidad, CFDI, conciliación bancaria, funcionamiento sin conexión ni control de existencias físicas. Las operaciones comerciales registran cantidades y cobros; no representan movimientos del inventario de requisiciones.

## Verificación

Pruebas HTTP con base temporal y productos ficticios en `tests/test_commercial.py`: permisos por empresa/sucursal, gestión exclusiva de razones sociales, revisión concurrente, precios negociados, folios, idempotencia, IVA, cancelaciones, reembolsos, impresión sin datos fiscales, exportación y programación de 12 horas. Se ejecuta también la batería previa y la regresión del menú móvil.
