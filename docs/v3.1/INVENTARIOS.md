# GMP ERP 3.1.0 · Almacenes

Se crea un almacén por razón social y sucursal vinculada: EJIDOS, SAN PABLO, CUAUTITLAN y EJE 8. La razón social se administra en la configuración comercial. Sistemas y AUXTI asignan empresas y sucursales en Compras → Accesos; Inventarios respeta esa misma asignación y los almacenes autorizados del usuario. El módulo se habilita inicialmente para Compras, Gerencia, Almacenista, AUXTI y Superadministrador; Sistemas puede cambiar los accesos por perfil. Requisición nunca recibe acceso a costos.

## Puesta en marcha

1. En Almacenes e inventarios selecciona la razón social y sucursal.
2. Descarga el layout desde Inventario inicial y ajustes. La hoja INVENTARIO_INICIAL contiene exactamente SKU, DESCRIPCION, UNIDAD_ENTREGA y FISICO. Se precargan los productos del maestro de requisiciones; FISICO queda vacío.
3. Captura el conteo. Una celda vacía se omite, un cero explícito significa cero físico. Se validan SKU únicos, descripción y unidad del maestro. Para incrementar existencias se exige costo de entrega válido del maestro; no se inventan costos faltantes.
4. Revisa la vista previa y envía la solicitud. Gerencia, Superadministrador o AUXTI autorizan o rechazan. Almacenista solicita; no autoriza ajustes. Los conteos quedan invalidados si otro movimiento alteró el almacén desde su revisión.

La integración de existencias comienza al autorizar el inventario inicial. No se contabilizan automáticamente recepciones ni surtidos históricos anteriores a esa activación: el conteo inicial ya representa el físico real. Si existen varias razones sociales activas en una sucursal, selecciona el almacén al surtir la requisición.

## Operación

- Recepción de compra: aumenta existencias con su equivalencia UM_ENTREGA, usando el precio antes de impuestos del pedido. Se registra en la misma transacción SQLite que la recepción.
- Surtido real: descuenta únicamente cantidadSurtida, conserva lo solicitado y rechaza existencias negativas. Correcciones/cancelaciones autorizadas revierten la diferencia cuando el surtido pertenece al mismo ciclo del almacén. Un cambio antiguo no modifica un ciclo posterior a un restablecimiento.
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
