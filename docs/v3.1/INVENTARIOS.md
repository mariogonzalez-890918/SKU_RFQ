# GMP ERP 3.1.4 · Almacenes

Se crea un almacén por razón social y sucursal vinculada: EJIDOS, SAN PABLO, CUAUTITLAN y EJE 8. La razón social se administra en la configuración comercial. Sistemas y AUXTI asignan empresas y sucursales en Compras → Accesos; Inventarios respeta esa misma asignación y los almacenes autorizados del usuario. El módulo se habilita inicialmente para Compras, Gerencia, Almacenista, AUXTI y Superadministrador; Sistemas puede cambiar los accesos por perfil. Requisición nunca recibe acceso a costos.

## Puesta en marcha

1. En Almacenes e inventarios selecciona la razón social y sucursal.
2. Descarga el layout desde Inventario inicial y ajustes. La hoja INVENTARIO_INICIAL contiene exactamente SKU, DESCRIPCION, UNIDAD_ENTREGA y FISICO. Se precargan los productos del maestro de requisiciones; FISICO queda vacío.
3. Captura el conteo. Una celda vacía se omite, un cero explícito significa cero físico. Se validan SKU únicos, descripción y unidad del maestro. Para incrementar existencias se exige costo de entrega válido del maestro; no se inventan costos faltantes.
4. Revisa la vista previa y envía la solicitud. Gerencia, Superadministrador o AUXTI autorizan o rechazan. Almacenista solicita; no autoriza ajustes. Los conteos quedan invalidados si otro movimiento alteró el almacén desde su revisión.

Las nuevas recepciones y surtidos contabilizan existencias aunque el conteo inicial esté pendiente; el saldo se identifica como provisional. Por indicación operativa, los nuevos surtidos se registran directamente aunque excedan el saldo; se conserva una alerta y el saldo negativo. Las correcciones, cancelaciones y movimientos manuales conservan las autorizaciones. Si existen varias razones sociales en una sucursal, selecciona el almacén al surtir. Las entregas históricas faltantes se concilian una sola vez desde Movimiento de almacén; verifica que el conteo no las haya descontado ya. El inventario inicial fija el físico contado y conserva los movimientos anteriores.

## Operación

- Recepción de compra: aumenta existencias con su equivalencia UM_ENTREGA, usando el precio antes de impuestos del pedido. Se registra en la misma transacción SQLite que la recepción.
- Surtido real: descuenta únicamente cantidadSurtida, conserva lo solicitado y permite saldo negativo directo con alerta. Correcciones/cancelaciones autorizadas revierten la diferencia cuando el surtido pertenece al mismo ciclo del almacén. Un cambio antiguo no modifica un ciclo posterior a un restablecimiento.
- Entradas/salidas extraordinarias: Gerencia, AUXTI o Superadministrador, con motivo. Almacén solicita el ajuste mediante conteo físico.
- Traspaso: solicitud → salida → tránsito → recepción parcial/total. El envío descuenta origen; el destino aumenta solo con cantidades confirmadas a su llegada. Se conserva quién entrega, quién recibe, usuarios, fechas, costos transportados y saldos pendientes. Un usuario de origen puede solicitar salida a otro destino configurado; solo una cuenta asignada al destino puede confirmar su llegada. Devolver tránsito al origen requiere uno de los tres autorizadores.
- Costeo: promedio ponderado en unidad de entrega, sin impuestos. El costo del material transportado se congela al enviarse. Es control operativo, sin pólizas fiscales ni CFDI intercompañía.
- Consultas: existencias en Excel/PDF y diario en Excel. El diario muestra los últimos 1000 movimientos; la base conserva todo el historial.

## Restablecimiento

Solo Superadministrador. Primero revisa el almacén, escribe RESTABLECER y proporciona motivo. Se generan movimientos compensatorios a cero, se conserva el diario inmutable, se invalidan conteos pendientes y se abre un nuevo ciclo para cargar inventario inicial. Se impide restablecer si existe material en tránsito, incluso en recepciones parciales.

Para actualizar el servidor, detén el EXE anterior, conserva y respalda la carpeta data y config.json, reemplaza el ejecutable y reinicia. Las tablas nuevas se crean sin borrar datos existentes. Una vez integrados movimientos de inventario, la recuperación de Compras, Requisiciones o razones sociales requiere una copia completa y consistente de data; se impide restaurar aisladamente documentos que pudieran duplicar entradas o desajustar existencias. Las descargas de respaldos se conservan.

## Referencia del flujo

Se consultaron los modelos oficiales de Odoo 14 para validación de inventarios y operaciones de almacén: [stock_inventory.py](https://github.com/odoo/odoo/blob/14.0/addons/stock/models/stock_inventory.py) y [stock_picking.py](https://github.com/odoo/odoo/blob/14.0/addons/stock/models/stock_picking.py). La implementación de GMP ERP es propia.

## Correcciones incluidas

Captura de compras habilitada para Gerencia, Compras, Superadministrador, AUXTI y Almacenista; series editables por los cuatro primeros. Detalle real de requisiciones vinculadas; costo del maestro automático en plantillas de proveedor por unidad; observaciones generales/de partida y condiciones en exportaciones institucionales; tiempos de espera y mensajes de permisos diferenciados.

### Corrección 3.1.1

Compras toma la tasa de IMPUESTO DE COMPRA antes que el campo IMPUESTO de código SAT. Relee el Excel ya guardado, sin necesitar recargar ni reemplazar el maestro. Se respetan 0%, 8% IEPS y 16% IVA y se permite cambiar la tasa en la partida. Las plantillas muestran el impuesto automático actual del maestro y permiten personalizarlo. No se modifican pedidos históricos.

Kárdex 3.1.1: consulta cronológica por SKU, fechas y tipo, con entradas de compras recibidas, salidas de surtido real y saldo por material. El Excel usa esos mismos filtros. Existencias muestra todo el maestro; los físicos no capturados siguen pendientes. Solo Gerencia, AUXTI y Superadministrador ven valuaciones, costos y precios de inventario; se eliminan de la API y exportaciones de Compras/Almacén dentro de Inventarios. Estos accesos no cambian los permisos comerciales del módulo de pedidos de compra.

Las solicitudes de traspaso permiten seleccionar destinos pendientes de inventario inicial, pero el envío exige ambos inventarios autorizados. La ventana muestra compras realmente recibidas por SKU, cantidades surtidas netas y disponibilidad física, con detalle de recepciones. La pestaña Recepciones de compra permite consultar folios, proveedores, cantidades recibidas y su equivalencia UM_ENTREGA; las recepciones históricas previas a activación se consultan sin duplicarlas como nuevas entradas.

### Kárdex, recepciones y conceptos

El Kárdex tiene filtros Desde/Hasta, entradas/salidas, tipo de movimiento, SKU y almacén, incluyendo todos los autorizados. El resumen separa inicial del periodo, entradas, salidas, existencia al corte y existencia actual por SKU/unidad/almacén; los filtros de tipo/dirección afectan el detalle y no ocultan movimientos en los saldos generales. Descarga detalle y reporte general en Excel, o resumen en PDF.

La recepción del proveedor nace del pedido confirmado desde la cotización. La recepción entre almacenes confirma cantidades del traspaso enviado. Son operaciones distintas y se muestran separadas. La cancelación del surtido genera devolución al almacén. La cancelación/devolución de una recepción de proveedor conserva el original y registra una salida de reversa incluso antes del inventario inicial; requiere aprobación expresa si deja un saldo negativo y no puede dejar compras/facturas sin recepción. Almacén solicita y Gerencia/AUXTI/Superadministrador autorizan. Se muestran estado y motivo de cancelación en consultas y PDF del original.

Conceptos configurables por Gerencia/AUXTI/Superadministrador: devoluciones de área, recuperación, otras entradas; merma, caducidad, rotura/daño, muestras y otras salidas. Pueden agregarse, editarse o desactivarse, conservando el nombre usado en el historial. La opción Movimiento de almacén y las entradas/salidas manuales son exclusivas de Gerencia, AUXTI y Superadministrador. Almacenista puede solicitar ajustes por conteo, sujetos a autorización. Los conceptos automáticos de compra, requisición y traspaso permanecen ligados a sus documentos.

Se consultaron como referencia las operaciones de [ubicaciones y tránsito de Odoo 14](https://github.com/odoo/odoo/blob/14.0/addons/stock/models/stock_location.py), [devoluciones](https://github.com/odoo/odoo/blob/14.0/addons/stock/wizard/stock_picking_return.py) y [mermas](https://github.com/odoo/odoo/blob/14.0/addons/stock/models/stock_scrap.py). Los conceptos de GMP ERP son un catálogo configurable propio.

### Reportes de compras 3.1.2

Filtros propios por sucursal, proveedor, estado y fechas de pedido o entrega. Cantidades pedidas, recibidas, pendientes y compradas por partida; importes y agrupación por sucursal/proveedor. Excel con cinco hojas: Pedidos, Partidas, Movimientos, Por sucursal y Por proveedor. PDF detallado por pedido. Borradores, cotizaciones enviadas y cancelaciones no se suman al total confirmado.

### Exportación Kárdex 3.1.3

Imprimir Kárdex abre una vista de impresión con resumen y detalle; permite elegir impresora o Guardar PDF desde el navegador. Descargar Kárdex PDF incluye ambos apartados. Descargar Kárdex XML contiene filtros, resumen por material y movimientos. Todos respetan el alcance de almacenes y la visibilidad de costos del perfil. Las fechas se presentan dd/mm/yyyy; SKU conserva ceros iniciales.

### Surtido y navegación 3.1.4

Resumen de existencias tiene su propia pestaña, con los filtros de fechas, SKU y almacén elegidos en Kárdex. Kárdex muestra únicamente el detalle de movimientos. Las observaciones de surtido y cancelación de requisiciones son opcionales, incluida su resolución. Si se captura más de lo solicitado, se conserva el documento sin cambios y no se afecta inventario hasta la autorización de Gerencia, AUXTI o Superadministrador; aplica incluso cuando uno de estos perfiles propone el excedente. Rechazar conserva los saldos. El reporte contabiliza la cantidad real solo después de aprobar, manteniendo la solicitada original.

### Traspasos 3.1.5

Agregar partida admite físico cero, negativo o pendiente. La solicitud no mueve inventario. Ya no se exige inventario inicial activo para enviar o recibir; los saldos previos al conteo son provisionales. Si el envío deja negativo, únicamente Gerencia, AUXTI o Superadministrador pueden confirmarlo marcando la autorización expresa. Almacenista no puede forzar este permiso. La recepción confirma lo realmente recibido y aumenta destino, incluso si aún conserva saldo negativo. El concepto tiene columna propia en Kárdex y PDF/impresión. Costos exclusivos de los tres autorizadores.
