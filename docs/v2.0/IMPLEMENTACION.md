# RFQ_SKU_GMP 2.1.0

La versión 2.1.0 corrige el bloqueo de la interfaz comercial al acceder por IP mediante HTTP: las claves de envío utilizan `crypto.getRandomValues`, disponible en ese contexto, en lugar de `crypto.randomUUID`, que requiere un contexto seguro. Los dos accesos a Pedidos institucionales y Expendios/TPV aparecen al principio de Inicio y en la sección de módulos del menú. Se mantienen las restricciones por perfil, razón social, sucursal y caja.

Versión 2.1.0 para instalar en el servidor. El proceso de compilación no sustituye automáticamente el servicio instalado. Los módulos comerciales comparten usuarios, sesión y SQLite con RFQ_SKU_GMP. Los catálogos SKU y las requisiciones mantienen sus rutas y reglas.

## Razones sociales y sucursales

En el módulo comercial, **Configuración → Razones sociales** permite agregar tantas razones sociales como se requieran, editar sus datos y eliminarlas. Cada una se vincula explícitamente con una o varias de **EJIDOS, SAN PABLO, CUAUTITLAN y EJE 8**. **Solo Superadministrador y AUXTI** pueden realizar estas operaciones. Gerente y operadores no pueden hacerlo aunque modifiquen una petición HTTP.

En **Configuración → Expendios y sucursales** se muestran siempre esas cuatro sucursales y se seleccionan sus razones sociales. En TPV se elige primero el expendio, después una razón social vinculada y finalmente su caja. Se respetan además los permisos de empresas, sucursales y cajas del usuario. No se asigna una empresa automáticamente a las cuatro sucursales.

Eliminar conserva el registro inactivo y las copias históricas en documentos. No permite nuevas operaciones. Deben cerrarse primero las cajas abiertas; para desvincular una sucursal hay que reasignar sus cajas activas. La configuración usa revisiones para evitar sobrescribir cambios simultáneos.

## Activación y uso

1. Conservar una copia de `data` y `config.json` de la instalación antes de instalar la actualización. El EXE público arranca vacío y no incluye credenciales, maestros, información fiscal ni la liga privada de OneDrive.
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

## Respaldo comercial y alcance

En Respaldos se añade **Pedidos institucionales y Expendios** como bloque completo. Incluye todas las empresas, vínculos, catálogo comercial, precios, clientes, plantillas, documentos, cajas, sesiones, cobros, cancelaciones, reembolsos, auditoría, folios, permisos comerciales y la configuración privada de la fuente. Se revisa el contenido y se guarda una copia previa antes de confirmar. Solo Superadministrador restaura directamente; AUXTI conserva el flujo de aprobación existente.

Una restauración en una base con operaciones posteriores se rechaza si retrocede documentos, cierres, cancelaciones o movimientos de dinero. Para recuperar un respaldo anterior se usa una instalación vacía. Se mantienen los máximos de folios y el historial de series; la fuente automática queda desactivada para revisar su configuración tras restaurar. El módulo comercial no ofrece vaciado de ventas. SKU y requisiciones mantienen sus respaldos independientes.

Pedidos institucionales inicia en **Presupuestos**, con listas separadas de **Pedidos**, acciones Crear/Guardar/Confirmar e importes por partida en una hoja de pedido. Su búsqueda agrega productos como renglones. Expendios inicia en el **TPV**, con carrito y cobro a la izquierda, catálogo de tarjetas a la derecha y selección de expendio/razón social/caja. Ambos comparten autenticación y datos, no la pantalla de operación.

No se incluyen contabilidad, CFDI, conciliación bancaria, funcionamiento sin conexión ni control de existencias físicas. Las operaciones comerciales registran cantidades y cobros; no representan movimientos del inventario de requisiciones.

## Verificación

Pruebas HTTP con base temporal y productos ficticios en `tests/test_commercial.py`: permisos por empresa/sucursal, gestión exclusiva de razones sociales, revisión concurrente, precios negociados, folios, idempotencia, IVA, cancelaciones, reembolsos, impresión sin datos fiscales, exportación y programación de 12 horas. Se ejecuta también la batería previa y la regresión del menú móvil.

## Novedades de 2.1.0

Clientes: layouts descargables, importación con vista previa y validación, códigos automáticos por razón social, edición de datos y canales, exportación Excel. Se conservan los códigos existentes y se detectan duplicados antes de aplicar.

Productos: layout SUGERIDO con selección opcional de canal en W, alta manual con SKU automático, edición y exportación Excel. Se permite institucionales, expendios o ambos. Los precios ausentes y el IVA sin definir quedan pendientes, sin convertirlos a cero ni permitir su venta. Se conservan los SKU validados y precios manuales.

Expendios: apertura de sesión para emitir tickets sin solicitar fondo ni registrar cobros. Los tickets no muestran recibido/cambio. Los movimientos anteriores conservan su tratamiento financiero y las cancelaciones mantienen sus permisos.

El maestro puede actualizarse manualmente, desde una descarga autorizada de OneDrive o desde una ruta XLSX del servidor. La programación opcional es cada 12 horas. Una página de vista previa que requiera autorización de Microsoft no garantiza acceso de descarga.

Para activar esta versión en una instalación existente, detener el ejecutable anterior, conservar data y config.json, reemplazar el EXE y reiniciarlo. La publicación en GitHub no actualiza automáticamente el servidor.

## Reportes de cajas (2.1.1)

Expendios incluye filtro por caja y columna de código/nombre en el reporte y las exportaciones Excel, CSV y PDF. El filtro se conserva en reportes guardados y respeta la sucursal y los permisos existentes. Los tickets nuevos conservan el nombre y código de caja al emitir; documentos anteriores recuperan la identificación de su caja actual.

La versión 2.1.1 también normaliza fechas visibles y filtros como dd/mm/yyyy sin cambiar el almacenamiento ISO. La columna N del maestro define 0% sin IVA, 8% IEPS y 16% IVA, incluidos en el precio; los documentos y exportaciones distinguen tipo e importe. No se presume impuesto cero para celdas vacías.

En institucionales se capturan fecha de pedido y de entrega, con filtros por cliente, producto y rango según emisión/pedido/entrega. El perfil institucional puede editar el precio por partida, manteniendo el impuesto del maestro. Las plantillas tienen editor propio de cliente, productos, cantidades y observaciones. Se guardan con revisión para detectar ediciones simultáneas.

La impresión permite preferencia local de A4 o ticket 80 mm en institucionales; Expendios usa 80 mm. La selección de impresora física se realiza en el diálogo de Windows del navegador. No se instala un controlador ni se selecciona una impresora de forma silenciosa.

Precios por cliente incluye descarga de clientes y layout PRECIOS con código de cliente, SKU, precio con impuesto y precio antes de impuesto. Se admite uno de los importes y se calcula el otro; si están ambos se validan contra la tasa del maestro, con tolerancia de un centavo. Carga transaccional revisada: no se aplican filas parciales ni duplicados y se detectan cambios del catálogo entre revisión y confirmación. Este flujo respeta los permisos de administración de precios existentes.
