# Layouts propuestos — revisión, no importadores implementados

Formato objetivo: Excel `.xlsx` y CSV UTF-8 para datos tabulares. Descargar una plantilla versionada desde cada módulo, seleccionar archivo, mapear encabezados, validar, previsualizar altas/cambios/errores y confirmar. No se mezclan productos, reglas de precios y asignación a cajas en una sola hoja implícita.

El maestro histórico actual usa **SUGERIDO**, SKU en **A**, descripción en **H** y módulo PDV en **F**. Se conserva ese importador. El layout comercial nuevo usa encabezados; no se interpreta automáticamente como la misma hoja ni actualiza los SKU validados de A.

## 1. PRODUCTOS_VENTA, versión propuesta 1

| Campo | Obligatorio | Regla |
| --- | --- | --- |
| SKU | Sí | Texto, 14 caracteres alfanuméricos; conserva ceros e identidad. Debe enlazar un SKU activo existente. Si falta, enviar a alta/generación de SKU antes de habilitar venta. |
| DESCRIPCION_VENTA | Sí | Texto comercial; no cambia automáticamente la descripción histórica del catálogo SKU. |
| TIPO | Sí | PP o PT; clasificación validada contra el catálogo existente. |
| CATEGORIA | Sí | Clave existente, por ejemplo PB. No crear categorías por errores de escritura. |
| SUBCATEGORIA | Sí | Clave de dos caracteres, texto. |
| MODULO_ID_PDV | Sí | A01–A22; `000` conserva “sin clasificar” y genera aviso antes de publicar en TPV. |
| UNIDAD_VENTA | Sí | Clave de unidad registrada; cantidad/presentación explícita. |
| CODIGO_BARRAS | No | Texto; unicidad dentro del catálogo activo; no se interpreta como SKU necesariamente. |
| ACTIVO | Sí | SI/NO. La baja comercial conserva documentos históricos. |
| VENDIBLE_VENTASINS | Sí | SI/NO; autoriza publicación en ese canal, no permisos de usuarios. |
| VENDIBLE_EXPENDIOS | Sí | SI/NO; requiere además asignación a sucursal/caja y precio válido. |
| IMPUESTO_VENTA | Sí | Clave de un impuesto configurado, incluso tasa cero explícita; no inferir un impuesto por nombre de producto. |

Ejemplo **ficticio**: `PTPB07BOL0000A`, BOLILLO DEMO, PT, PB, 07, A11, PIEZA, código de barras vacío, SI, SI, SI, IVA_DEMO. El precio no se toma de UM_COMPRA ni del costo de requisiciones.

## 2. LISTAS_PRECIOS, versión propuesta 1

| Campo | Regla |
| --- | --- |
| LISTA_CLAVE / NOMBRE_LISTA | Identidad estable y nombre legible. |
| CANAL | VENTASINS o EXPENDIOS. Una lista compartida se asigna explícitamente a ambos; no se comparte por coincidencia de nombre. |
| SUCURSAL | EJIDOS, SAN PABLO, CUAUTITLAN o EJE 8; permitir generalidad solo mediante opción explícita del layout. |
| CLIENTE_CLAVE | Opcional; referencia a cliente existente. |
| SKU / UNIDAD_VENTA | Producto y presentación exactos. |
| CANTIDAD_MINIMA / CANTIDAD_MAXIMA | Rango de tramo; máximo vacío significa sin tope. Rechazar solapamientos de igual prioridad. |
| PRECIO / MONEDA | Decimal no negativo y moneda configurada. Cero solo autorizado expresamente. |
| INCLUYE_IMPUESTOS | SI/NO obligatorio y coherente con configuración de lista. |
| VIGENTE_DESDE / VIGENTE_HASTA | Fechas ISO; hasta vacío significa vigencia abierta. |
| ACTIVA | SI/NO; no elimina versiones utilizadas. |

Clave de actualización: lista + canal + alcance + SKU + unidad + rango + vigencia, con identificador de regla estable al exportar. Actualizar una regla crea revisión y conserva la anterior. Filas ambiguas se reportan, no se resuelven por posición en Excel. El modo “solo agregar” omite existentes; “actualizar seleccionados” requiere permiso de precios y confirmación de diferencias.

## 3. EXPENDIOS_LAYOUT, versión propuesta 1

| Campo | Regla |
| --- | --- |
| SUCURSAL / CAJA_CLAVE | Sucursal existente y caja registrada; no crea cajas ni asigna usuarios de forma silenciosa. |
| SKU | Debe ser vendible en Expendios y estar activo. |
| CATEGORIA_TPV | Categoría visual de navegación del expendio; puede mapear MODULO_ID_PDV. |
| ORDEN_CATEGORIA / ORDEN_PRODUCTO | Enteros para ordenar pestañas y tarjetas. |
| VISIBLE | SI/NO; ocultar no elimina el producto ni tickets anteriores. |
| LISTA_PREDETERMINADA | Lista autorizada para la caja; evitar listas predeterminadas contradictorias en distintas filas de una misma caja. |

Este layout organiza qué se ve en la caja. No carga ventas pagadas, efectivo, existencias ni asignaciones de acceso. Cargarlo exige **Expendios habilitado + importar layout + Cargar maestros**, y alcance autorizado sobre las cajas incluidas.

## 4. PLANTILLAS_PRESUPUESTO y METAS_VENTAS

Plantilla de presupuesto: `PLANTILLA_CLAVE`, `NOMBRE`, `CANAL`, `ORDEN`, `TIPO_LINEA` (PRODUCTO/SECCION/NOTA), `SKU`, `CANTIDAD`, `UNIDAD_VENTA`, `TEXTO`, `VIGENCIA_DIAS`, `CONDICIONES_CLAVE`. Precio resuelto al usar la plantilla, no fijado por una celda vieja salvo regla explícita autorizada. Productos opcionales quedan identificados como opcionales.

Meta comercial: `PERIODO_DESDE`, `PERIODO_HASTA`, `CANAL`, `SUCURSAL`, `VENDEDOR_CLAVE` opcional, `METRICA` (PEDIDOS_CONFIRMADOS/VENTA_TPV_NETA/COBRADO), `IMPORTE_META`, `MONEDA`, `INCLUYE_IMPUESTOS`. Se rechazan metas duplicadas para el mismo alcance y período; no son cotizaciones a clientes. Esta hoja es propuesta por la ambigüedad de “presupuestar dashboard” y requiere validación de alcance.

## Reglas comunes de importación

- Verificar tipo, tamaño, expansión del ZIP, hoja y versión del layout antes de procesar. Los límites actuales del servidor y maestro se respetan hasta medir una ampliación.
- Tratar SKU, códigos y claves como texto. No quitar ceros, convertir códigos a flotantes ni aceptar fechas numéricas ambiguas. Celdas obligatorias con fórmula sin valor validado se reportan; no ejecutar fórmulas/macros.
- Vista previa con número de fila, campo, valor, error y acción propuesta. Errores de referencia o permisos bloquean confirmar; no aplicar silenciosamente solo una parte del archivo.
- Huella del archivo + revisión del destino + confirmación de usuario. Revisar de nuevo permisos y revisiones dentro de la transacción. Si cambió el maestro/precio mientras se revisaba, generar otra vista previa.
- Registrar archivo, fecha, actor, revisión y resumen. Repetir la misma importación no duplica productos, precios ni asignaciones. Exportar solo el alcance autorizado; proteger exportaciones de texto frente a fórmulas inyectadas en hojas de cálculo.
- Nunca borrar filas comerciales por faltar en el archivo cargado. Desactivar, no eliminar, y solo con permiso correspondiente. Rechazar cualquier intento de cambiar un SKU validado.
