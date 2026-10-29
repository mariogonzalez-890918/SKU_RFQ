# GMP ERP 3.0.0

El flujo de Compras toma como referencia el [modelo de Odoo 14](https://github.com/odoo/odoo/blob/14.0/addons/purchase/models/purchase.py): cotización, pedido confirmado, recepción y registro de compra/factura del proveedor. Es una implementación propia integrada en este servidor; el registro de compra es operativo, sin timbrado CFDI ni contabilización automática.

Compras comparte las razones sociales de Institucionales y Expendios. Utiliza el maestro PRODUCTOS cargado en Requisiciones y sus costos/unidades. Permite COMPRA o ENTREGA con equivalencia validada; una equivalencia desconocida o impuesto vacío requiere corrección, sin inventar cero. Los precios de Compras se capturan antes de impuesto. Los documentos conservan sus unidades, costos y equivalencia al confirmarse.

Solo Compras y Gerencia capturan/confirmar pedidos y registran compras. Almacenista puede recibir según acceso. Compras, Gerencia, AUXTI y Sistemas configuran series por razón social, sucursal y tipo de documento. Los números ya emitidos permanecen reservados incluso después de cancelación o restauración. Sistemas/AUXTI asignan alcance de empresas/sucursales desde Compras → Accesos; habilitar un perfil por sí solo no asigna datos de una razón social.

Una requisición puede originar cotizaciones/pedidos; se comprueba el saldo ya vinculado para no duplicar cantidades. La requisición muestra las referencias y avance sin exponer costos a solicitantes. Recibir al proveedor no marca una requisición como surtida a su área.

Recepciones y compras admiten cantidades parciales e idempotencia de envío. No se recibe más de lo pedido ni se registra compra de más de lo recibido. Cancelar pedidos con recepciones/compras está bloqueado para conservar trazabilidad. Los reportes incluyen estados y conteos por sucursal; importes de borradores y cancelaciones no se suman a pedidos confirmados.

Proveedores tienen códigos automáticos y layout PROVEEDORES con revisión antes de aplicar. Plantillas por cliente y proveedor tienen layouts separados y edición en su módulo. Solo Gerencia, AUXTI y Superadministrador administran y cargan plantillas. Excel agrupa partidas por nombre y cliente/proveedor y detecta claves repetidas, ambigüedad y cambios concurrentes.

Pedidos institucionales incluyen bloqueo/desbloqueo. Al confirmar se bloquea el pedido; pueden desbloquear Pedidos institucionales, Gerencia, AUXTI y Superadministrador dentro de su alcance. VENTASPASTELERIA solo captura y consulta sus documentos, sin maestros, precios administrativos, plantillas ni historial de terceros. Sus cancelaciones requieren autorización de Gerencia/AUXTI/Sistemas; hasta aprobarse el documento sigue vigente.

Compras imprime solo en A4 y PDF. Observaciones: 100,000 caracteres; condiciones: 20,000. El PDF pagina los textos largos. Se retiró la leyenda personal de formatos y reportes. Las fechas mantienen presentación dd/mm/yyyy y calendario de selección. Los accesos de Inicio se muestran con iconos en la cuadrícula común.

Correo: Sistemas/AUXTI configuran SMTP TLS privado; solo el botón explícito de envío envía un PDF real al destinatario revisado. Un envío no confirmado queda REVISAR, sin reintentos automáticos. El respaldo de Compras no contiene contraseñas SMTP. No se envían correos de prueba a proveedores durante el desarrollo.

Actualización: detener el EXE anterior, conservar data y config.json y ejecutar GMP_ERP.exe en la misma carpeta. El EXE público no contiene maestros, datos empresariales ni credenciales. El primer inicio de una instalación nueva solicita crear contraseña. Los respaldos de Compras se descargan en su módulo; solo Sistemas restaura y se conserva una copia previa.
