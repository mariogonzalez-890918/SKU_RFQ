> Documento de diseño previo. El alcance implementado y las decisiones posteriores del usuario se encuentran en [IMPLEMENTACION.md](IMPLEMENTACION.md). Razones sociales dinámicas: solo AUXTI y Superadministrador administran sus vínculos con las cuatro sucursales.

# Ampliación: razones sociales, clientes, IVA, folios y cancelaciones

Requisitos incorporados el **28 de octubre de 2026**. Este documento amplía el diseño de v2.0; no representa funciones ya instaladas. **VentasIns se considera el canal de pedidos institucionales** conforme a la precisión del usuario.

## 1. Tres razones sociales capturadas por el usuario

Se contemplan **tres razones sociales emisoras**, válidas tanto en pedidos institucionales como en Expendios. En Configuración → Razones sociales se presentan tres espacios sin datos empresariales precargados. El usuario llena denominación, nombre comercial, RFC si corresponde a su configuración, domicilio, contacto, moneda, logo y textos de impresión. Superadministrador captura/autoriza inicialmente esos datos; su administración podrá asignarse como capacidad separada, sin conceder gestión de perfiles.

**Razón social emisora, empresa cliente, sucursal y caja son entidades diferentes.** EJIDOS, SAN PABLO, CUAUTITLAN y EJE 8 siguen siendo ubicaciones. Una ubicación puede operar para más de una razón social mediante cajas separadas. No se identifica una empresa por la sucursal ni por el módulo de producto A01–A22.

| Elemento | Regla de separación propuesta |
| --- | --- |
| Usuario | Razones sociales permitidas, razón predeterminada y sucursales/cajas asignadas. |
| Presupuesto/pedido | Una sola razón social emisora, visible en formulario y documento impreso. |
| Caja y sesión | Cada caja pertenece a una razón social; la sesión hereda y fija esa pertenencia. No mezcla fondos de empresas. |
| Listas, impuestos y pagos | Configuración y alcance por razón social; no usar una lista de otra empresa como fallback. |
| Clientes | Identidad y contactos, con asociación comercial explícita a cada razón social autorizada. |
| Producto | SKU global conservado; disponibilidad, unidad comercial y precios habilitados por razón social/canal. |
| Folios | Series/contadores por razón social y tipo de documento; cajas con numeración propia donde corresponda. |
| Reporte | Una razón social o consolidado de las autorizadas, con columna y agrupación por emisor. |
| Historial e impresión | Snapshot del emisor, logo/datos relevantes y condiciones usados al confirmar. Editar la empresa después no cambia documentos anteriores. |

### Selector y permisos

El encabezado muestra la **razón social activa**. Se elige una para crear/cobrar y varias únicamente para consulta consolidada. Solo aparecen las asignadas al usuario. El servidor verifica módulo + acción + razón social + sucursal/caja + cartera; no acepta un `company_id` por estar incluido en el formulario.

Cambiar de razón social no mueve un carrito ni un presupuesto entre empresas: guardar borrador en la original o descartarlo explícitamente. Un documento confirmado o pagado no cambia de emisor. Las devoluciones, cancelaciones y reimpresiones conservan la empresa de origen. No hay ventas intercompañía, traspasos de caja o facturación cruzada implícitos.

La migración desde 1.8.0 no asigna datos históricos a una empresa inventada. El catálogo SKU puede seguir compartido; cualquier asignación empresarial de documentos anteriores exige un mapeo aprobado. Las requisiciones actuales conservan su funcionamiento y sus reglas de autorización.

## 2. Alta y gestión de clientes

VentasIns → Pedidos → Clientes y Expendios → Pedidos → Clientes utilizarán un mismo servicio autorizado. El alta sigue el patrón de formulario de contactos de Odoo 14: identificación, contactos/direcciones y condiciones comerciales, separando la entidad cliente de la empresa emisora. Referencia: [formulario oficial de contactos 14.0](https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/views/res_partner_views.xml).

| Bloque | Datos propuestos |
| --- | --- |
| Identificación | Código estable, persona/empresa, nombre, nombre comercial, identificador fiscal cuando se capture y estado activo. |
| Contacto | Correo, teléfonos, contacto principal y notas comerciales. |
| Direcciones | Dirección principal y direcciones de entrega/cobro relacionadas; contacto específico por dirección. |
| Condiciones por emisor | Razón social autorizada, lista de precios, moneda, condiciones de pago, vendedor/cartera y referencias del cliente. |
| Control | Usuario/fecha de alta, revisiones, archivos de importación y trazabilidad de cambios. |

**VentasIns:** alta/edición de clientes de su cartera con capacidad habilitada. **Expendios:** alta rápida de nombre/contacto/dirección si se habilita; puede vender al cliente configurado de mostrador sin inventar datos. Límites de crédito, cambios de cartera y condiciones especiales son capacidades aparte. El diseño no activa crédito por el mero hecho de crear un cliente.

Un cliente puede operar con las tres razones sociales sin duplicar necesariamente su identidad, pero sus listas, condiciones y saldos se mantienen por emisor. La asociación compartida es explícita; no expone automáticamente toda la cartera a otros usuarios. Direcciones y contactos hijos heredan las restricciones. Datos fiscales parecidos producen aviso de posible duplicado, no una fusión automática. Códigos/IDs estables determinan identidad; no usar solo nombre o RFC para sobrescribir registros.

Baja lógica, sin borrar pedidos ni tickets históricos. Importación y exportación de clientes requieren permisos propios y conservan el alcance del usuario. La impresión usa los datos congelados en el documento, no la ficha modificada meses después.

## 3. IVA: 0 %, 8 % y 16 %

Se incluyen las **tres tasas indicadas por el usuario**, asignables por producto/partida y razón social. No se determina la tasa por nombre, sucursal o ubicación. Los administradores autorizados configuran cuál corresponde a cada producto; una tasa faltante bloquea la confirmación/cobro, en vez de convertirse silenciosamente en cero.

- Cero es una tasa explícita, distinta de dato ausente o de una categoría exenta no definida en este alcance.
- Cada lista declara si sus precios incluyen IVA. Se congela en la línea tasa, modalidad, base, descuento, IVA y total.
- Descuento autorizado aplicado antes del impuesto; cálculo decimal y redondeo por línea a dos decimales para MXN. Precios/cantidades pueden requerir más decimales antes del redondeo monetario.
- Precio sin IVA: base redondeada de cantidad × precio × (1 − descuento); IVA = base × tasa, redondeado; total = base + IVA.
- Precio con IVA: calcular el importe con descuento, obtener base = importe / (1 + tasa) y determinar IVA como diferencia. No sumar nuevamente el impuesto incluido.
- Documento, ticket y reporte agrupan bases e impuestos por tasa y concilian contra las mismas líneas guardadas por el servidor.

Ejemplo sin descuento, importes en MXN:

| Base | IVA | Impuesto | Total |
| --- | --- | --- | --- |
| 100.00 | 0 % | 0.00 | 100.00 |
| 100.00 | 8 % | 8.00 | 108.00 |
| 100.00 | 16 % | 16.00 | 116.00 |
| **300.00** | Mixto | **24.00** | **324.00** |

Con precio incluido de 108.00 al 8 %, la base debe ser 100.00 y el IVA 8.00; con 116.00 al 16 %, 100.00 y 16.00. Un descuento de 10 % sobre base 100.00 al 16 % produce base 90.00, IVA 14.40 y total 104.40. Son casos de prueba de cálculo, no una determinación de qué tasa corresponde legalmente a un producto. No se incluye emisión fiscal en esta etapa.

## 4. Folio inicial de pedidos institucionales

El usuario podrá capturar **serie, folio inicial y ancho de presentación** desde Configuración → Pedidos institucionales → Series y folios, para cada razón social. Ejemplo ficticio: serie `PED-RS01`, inicial `500`, ancho `6` → `PED-RS01-000500`. La fecha sigue siendo del servidor.

- Primera configuración: permitir el entero positivo elegido dentro del rango técnico aprobado; no imponer comenzar en uno.
- Después de emitir: el siguiente no retrocede por debajo de los usados/reservados. Permitir incrementarlo o crear otra serie sin reutilizar números.
- Índice único por empresa/tipo/serie/folio y asignación atómica. El identificador interno global sigue siendo independiente del texto visible.
- Vista previa, revisión concurrente y auditoría de quién configuró el contador. Restaurar respaldo conserva los máximos, incluso si el respaldo tenía un siguiente menor.
- Configuración inicialmente de Superadministrador; delegación explícita de `configurar_folios_institucionales`. Operadores de ventas no cambian el contador por tener permiso para confirmar pedidos.

## 5. Folio interno y solicitudes de cancelación en Expendios

Cada venta tendrá **ID técnico**, **folio interno de operación** legible y **folio de ticket**. El interno se asigna por el servidor y permanece aun si la venta se cancela. Además, cada solicitud de cancelación tendrá un folio propio, vinculado al interno y al ticket. No son SKU ni folios de requisición.

Flujo propuesto:

```text
Venta registrada → Solicitar cancelación con motivo
                → Solicitud PENDIENTE con folio
                → Revisión por AUXTI o Superadministrador
                → RECHAZADA: venta intacta
                → APROBADA: operación CANCELADA y movimientos vinculados
```

**Solo AUXTI y Superadministrador cancelan/autorizarán la cancelación de Expendios. Gerencia no puede hacerlo.** Esta condición se comprueba en el servidor, incluso si otro perfil tiene acceso al módulo, a reportes o a excepciones generales. No basta un checkbox de visibilidad para conceder cancelación. El solicitante no resuelve su propia solicitud; cualquier ampliación de esa política se revisará expresamente.

Expendios solicita sobre sus operaciones/cajas autorizadas y consulta el estado. Se registra emisor, sucursal, caja, sesión, cajero, folios, importe, motivo, solicitante, revisor, fecha y decisión. La solicitud pendiente no altera ventas, cobros ni arqueo. Revisar la versión de la venta antes de autorizar y bloquear doble cancelación/reembolso.

Una venta cobrada **no se borra**. La autorización genera la anulación comercial y su trazabilidad. El reembolso de dinero se registra por separado con importe, medio y estado: cancelar no demuestra que se haya devuelto efectivo. Reportes distinguirán venta anulada, importe a reembolsar y reembolso efectuado; la caja solo descuenta salidas reales de efectivo. Reimpresiones se marcan CANCELADO/COPIA conservando el documento original y el folio de autorización.

Esta regla es exclusiva de **Expendios**. No elimina la facultad de Gerente para autorizar cancelaciones de requisiciones en la versión actual.

## 6. Reportes y exportación con referencia Odoo 14

La referencia es la experiencia de filtros/listados y Acción → Exportar: selección de campos y plantillas de exportación. La documentación 14 menciona CSV y XLS; RFQ propone **CSV y XLSX**, además de PDF para el reporte impreso, manteniendo su formato moderno actual. No se promete compatibilidad binaria con todos los archivos o acciones de Odoo. Fuente: [exportación oficial 14.0](https://github.com/odoo/documentation/blob/14.0/content/applications/general/export_import_data.rst).

### Reportes de la entrega 2.0

| Familia | Detalle y agrupación |
| --- | --- |
| Presupuestos y pedidos | Emisor, cliente, vendedor, estado, aceptación, vencimiento, importes y documento de origen. |
| Ventas | Razón social → canal → sucursal → cliente/producto/vendedor → documento. |
| Expendios | Caja, sesión, cajero, tickets, medios de pago, anulaciones y reembolsos. |
| IVA | Bases, IVA y totales separados en 0 %, 8 % y 16 %, con devoluciones/anulaciones vinculadas. |
| Caja | Fondo, entradas, efectivo esperado/contado, salidas reales, diferencias y responsable del cierre. |
| Clientes | Altas, actividad, pedidos y cobros por cliente y razón social; no exponer cartera ajena. |
| Metas/dashboard | Indicadores comerciales y metas definidas, sin duplicar presupuesto/pedido/ticket/cobro. |

Filtros por período, razón social activa o varias autorizadas, sucursal, canal, cliente, vendedor, producto, caja, sesión, estado y tasa. Guardar favoritos; agrupar y abrir el detalle desde un total. Vistas lista, gráfico y tabla dinámica propuestas sobre el mismo conjunto de datos autorizado. No se incluye contabilidad general, conciliación bancaria o todos los reportes del ERP Odoo.

### Acción → Exportar

Elegir filas seleccionadas **o todas las del filtro**, seleccionar/ordenar columnas autorizadas y guardar una plantilla de exportación. Mostrar conteo y alcance antes de generar. Descargar todo el resultado aunque la pantalla esté paginada; totales del detalle/grupo coherentes con el filtro seleccionado. XLSX con cantidades/importes numéricos y códigos como texto; CSV UTF-8; PDF con encabezados repetidos y fecha/filtros/emisor identificados.

La plantilla guarda nombres de campos de una lista permitida, no expresiones SQL ni datos. Al reutilizarla se recalculan permisos, filtros y razones sociales; un favorito no recupera acceso revocado. Separar exportación de clientes y de importes comerciales. Nunca exportar contraseñas, sesiones, tokens o costos a perfiles no autorizados.

Un consolidado agrupa por razón social y moneda, identifica las incluidas y permite abrir cada documento. No suma monedas distintas ni unidades incompatibles. Distinguir fecha de pedido, cobro, cancelación, reembolso y cierre; seleccionar cuál usa el indicador. Los reportes existentes de requisiciones conservan sus reglas de IVA/exportación y no se cambian automáticamente por este diseño comercial.

## 7. Impacto técnico y aceptación adicional

- Añadir `companies` y asignaciones de usuario; `company_id` obligatorio en documentos, caja, pagos, reglas de precio, secuencias, autorizaciones y metas. Índices/restricciones compuestas que impidan unir líneas/pagos de emisores distintos.
- Clientes con identidad estable y relación `customer_company`; condiciones y cartera por emisor. Productos comerciales con disponibilidad por empresa/canal, conservando SKU global.
- Folio interno y solicitud de cancelación con secuencias propias; historial inmutable y reembolsos vinculados. Tasa y modalidad de IVA congeladas por línea.
- Respaldar las tres razones sociales con todas sus dependencias. Cualquier restauración parcial necesita validación de referencias, alcances y contadores; no restaurar una empresa encima de pagos de otra.
- Probar aislamiento entre empresas en API, impresión, exportaciones, búsquedas y favoritos; al cambiar razón social no reaprovechar un carrito anterior.
- Probar IVA mixto y precios incluidos/excluidos, descuentos, redondeos y devoluciones. Los mismos datos deben producir totales idénticos en pedido, ticket, dashboard, CSV, XLSX y PDF.
- Probar folio inicial elegido, concurrencia, salto de serie y restauración sin reutilización; gerencia intentando cancelar Expendios debe recibir denegación.
- Probar solicitud pendiente sin impacto, rechazo, autorización por AUXTI/Superadministrador, doble clic, venta modificada y reembolso pendiente/efectuado.

El prototipo adjunto al PR ilustra la navegación inicial, perfiles y formatos; **aún no simula** estos nuevos formularios multirrazón, alta completa de clientes, IVA mixto, selector de columnas ni solicitudes de cancelación. La especificación anterior define lo que deberá añadirse antes de aceptarlos como implementados.
