> Estado del conector implementado: programación de 12 horas, ejecución manual y carga XLSX. La descarga directa debe estar autorizada; el flujo OAuth de Microsoft Graph descrito como alternativa todavía no está implementado. No se publica la liga privada del usuario.

# Maestro SUGERIDO y actualización automática desde OneDrive

## Fuente y estado de la revisión

El usuario proporcionó una liga compartida y un embed de su maestro de venta. El libro se abrió en el navegador y se comprobaron los encabezados de **SUGERIDO**, incluida la unidad de medida en O y el impuesto de N mostrado como porcentaje. No se modificaron celdas. El servidor no descargó una copia verificable: la petición directa devolvió 403 y la descarga de interfaz no entregó un archivo local verificable. Por tanto, la lectura automática sin intervención todavía requiere prueba de conexión y autorización.

El mapeo siguiente reemplaza la propuesta genérica de PRODUCTOS_VENTA para este maestro. Se usa la estructura existente, sin pedir al usuario que reconstruya el archivo. Solo se procesa **SUGERIDO**; las otras pestañas no alimentan el catálogo comercial por omisión.

La liga compartida, el embed, identificadores de cuenta y credenciales se conservarán en configuración privada del servidor. **No se publican en este repositorio ni dentro del EXE público.** Este documento incluye estructura, no registros ni precios empresariales.

## 1. Columnas y uso en el sistema

| Columna | Encabezado comprobado / instrucción del usuario | Uso comercial |
| --- | --- | --- |
| A | SKU | Identidad del producto; conservar los SKU validados y sus ceros. No regenerarlos al sincronizar. |
| B | PRODUCTOS Y SERVICIOS | Tipo de producto/servicio; resolver PP/PT y etiquetas existentes sin modificar A. |
| C | CATEGORIA | Categoría de venta; admite las etiquetas del maestro y se vincula al catálogo actual. |
| D | SUBCATEGORÍA | Subcategoría; preservar claves e identidad. |
| E | LINEA | Línea para pasteles; no convertirla en otra categoría ni exigirla en productos a los que no aplica. |
| F | MODULO ID PDV | Categoría/módulo de navegación del TPV. Resolver nombres o A01–A22; no usarlo como sucursal, caja ni emisor. |
| G | EXPENDIO | Indicador adicional de disponibilidad para Expendios. Definir valores admitidos, por ejemplo SI/NO; vacíos/desconocidos se revisan al habilitar el conector, no causan borrado de artículos. |
| H | DESCRIPCION | Descripción comercial del producto. |
| I | PRECIO DE VENTA PUERTA | El usuario lo define como **precio público base para pedidos institucionales**. Conservar el encabezado original, aunque la etiqueta del sistema sea “Institucional público”. |
| J | PRECIO DE VENTA EXPENDIO RUTA | Lista base **Ruta** en Expendios/TPV. |
| K | PRECIO DE VENTA EXPENDIO DESPACHO | Lista base **Despacho** en Expendios/TPV. |
| L | PRECIO DE VENTA MERMA | Conservar en la referencia/exportación del maestro; no habilitar como lista de venta sin solicitud expresa. |
| M | RAYA | Campo de referencia sin regla comercial solicitada; no usar para precios, impuestos o caja. |
| N | IMPUESTO | IVA de 0 %, 8 % o 16 %, aplicado al producto/partida. |
| O | UOM | Unidad de venta del maestro; no sustituirla por UM_ENTREGA de compras/requisiciones. |
| P / Q / R | EMPACADO / EMPACADO PROD / INV EMPACADO | Metadatos fuera de la venta solicitada. No deducir stock real ni movimientos de inventario a partir de estas celdas. |
| S | ESTATUS | Estado comercial; mapear valores reconocidos de forma explícita. Cambiar disponibilidad no borra ventas históricas. |

Antes de activar, validar posición **y encabezado**, tipos y valores de clasificación. Si alguien inserta columnas, renombra la hoja o introduce un esquema incompatible, detener ese lote y conservar la última carga válida. Cambiar la descripción o clasificación no autoriza modificar un SKU validado.

## 2. Las tres listas tienen IVA incluido

**I, J y K son precios finales con impuesto incluido**, según instrucción expresa del usuario. El sistema extrae base e IVA usando N; no suma el IVA nuevamente al precio del maestro.

Ejemplo de cálculo, sin datos del libro: precio final 108.00 con IVA 8 % → base 100.00 e IVA 8.00; precio final 116.00 con IVA 16 % → base 100.00 e IVA 16.00. Tasa cero mantiene base = precio final. En todas las salidas se concilian los importes con decimales y el mismo criterio de redondeo.

N debe normalizarse conservando tipo y formato de Excel: un valor porcentual mostrado como 8 % puede almacenarse como 0.08; no interpretarlo como 0.08 %. Admitir las representaciones explícitas de 0/8/16 %; valores numéricos ambiguos, vacíos, errores de fórmula u otras tasas no se convierten automáticamente en cero. Probar también fórmulas con valor calculado y el formato porcentual. El lector actual conserva tipos básicos pero debe ampliarse para esta normalización comercial.

La razón social no aparece en estas columnas. En la configuración del conector se asigna a qué emisores/listas autorizados alimenta el maestro; no compartirlo automáticamente entre las tres empresas. I, J y K crean/revisan listas base independientes por razón social y canal, con `incluye_iva = true`.

## 3. Precios y plantillas por cliente

En pedidos institucionales se podrán mantener **plantillas por cliente** y **precios pactados por cliente**, además del precio público I. Son conceptos distintos:

1. Una plantilla por cliente propone productos, cantidades, secciones, notas y condiciones al crear un presupuesto; no conserva un precio viejo como tarifa automática.
2. Una regla de precio por cliente, SKU, unidad, razón social y vigencia tiene prioridad sobre la lista pública I si está autorizada y activa.
3. Si no existe precio pactado aplicable, se utiliza I del maestro para la lista institucional autorizada. Si tampoco hay precio válido, bloquear confirmación, no usar J/K por accidente.
4. En Expendios se usa Ruta J o Despacho K según la lista asignada a caja/operación y permisos. El operador no obtiene todas las listas por visualizar el módulo.
5. Las reglas registran origen **MAESTRO_ONEDRIVE**, **CLIENTE** o **MANUAL_AUTORIZADO**. La sincronización modifica únicamente los campos y reglas cuya fuente es el maestro. No sobrescribe precios pactados ni plantillas de clientes.

Un cambio de I/J/K o de N crea una nueva revisión para operaciones futuras. Documentos confirmados, cobros y tickets conservan precio/IVA/condiciones de su snapshot. Presupuestos ya guardados informan que hay una nueva tarifa y permiten recalcular con revisión visible; no cambian silenciosamente. Un precio pactado final conserva su importe autorizado y desglosa la tasa aplicable de la nueva operación, salvo una configuración de impuestos expresamente aprobada.

## 4. Embed frente a sincronización

El embed suministrado sirve para una **vista de referencia** del archivo y expone un botón Descargar. No es un canal de integración de datos: el contenido está en un iframe de Office y no existe un contrato estable para obtener sus filas desde la aplicación. Sus parámetros de interactividad/presentación no autorizan ni garantizan descarga automática en el servidor.

Si se habilita la vista incrustada, se limita a administración/usuarios con permiso de maestro. El libro completo puede mostrar listas o campos no autorizados para un cajero o vendedor; el TPV normal utiliza el catálogo filtrado del sistema, no el iframe completo. No se publica el código embed real en el prototipo público.

### Conexión recomendada

**Microsoft Graph con lectura autorizada** del archivo y descarga del contenido XLSX. Resolver la referencia compartida o un identificador estable según la cuenta y permisos disponibles. Microsoft documenta la descarga autenticada de `driveItem` y el uso de `If-None-Match` con eTag/cTag para omitir archivos sin cambios [M1]. No almacenar como enlace permanente una URL temporal de descarga.

La autorización inicial se realiza para la cuenta y archivo correctos, con permisos mínimos de lectura compatibles con el método escogido. El método `/shares` de metadatos tiene requisitos distintos a la descarga [M2]; no pedir permisos amplios de escritura solo para inspeccionar el maestro. Confirmar si la cuenta es personal o de trabajo y el flujo delegado/aplicación admitido; no suponer que credenciales de servicio de un tenant funcionarán en OneDrive personal.

Alternativa si el entorno ya dispone de una copia OneDrive sincronizada y soportada en el servidor: importar esa copia local completa, con las mismas validaciones. Depende del cliente OneDrive, la sesión/identidad de ejecución y la disponibilidad real del archivo. Un CSV exportado manualmente no reemplaza la actualización de la liga solicitada. El conector no escribe en el Excel fuente.

## 5. Ciclo automático propuesto

Intervalo solicitado e implementado: **cada 12 horas**, con botón **Sincronizar ahora** para quienes tengan capacidad de carga. Es una función del servicio RFQ_SKU_GMP, no una automatización del chat ni una conexión que necesite exponer el servidor de la red local a Internet.

```text
Origen privado + alcance autorizado
  → comprobar acceso y versión
  → descargar a staging fuera de la transacción de ventas
  → validar XLSX / hoja / encabezados / SKU / IVA / precios / UOM
  → comparar SUGERIDO contra última versión válida
  → aplicar altas y revisiones del maestro en transacción corta
  → registrar resultado y avisar a pantallas de nuevas tarifas
```

- Primera carga: probar conexión, previsualizar mapeo/listas/emisores y activar el automático explícitamente. Después no pedir confirmación humana para cada actualización normal de los campos acordados.
- Registrar eTag/huella y una huella semántica de SUGERIDO. Cambios solo en otras hojas no deben alterar catálogos o precios.
- Excluir ejecuciones simultáneas. Confirmar que la revisión fuente y el destino no cambiaron durante la preparación; si cambian, reintentar con límite o pasar al siguiente ciclo, sin bloquear caja.
- SKU A válido existente: actualizar solo atributos/tarifas con origen maestro. SKU nuevo válido: dar de alta respetando unicidad. SKU vacío, duplicado o ambiguo: reportar y no generar/modificar códigos en el archivo fuente. Errores que invaliden el lote bloquean la aplicación del lote, no dejan una mezcla parcial sin avisar.
- Archivo sin filas, fuente eliminada, 403, error de red o datos inválidos: conservar catálogo y precios válidos, registrar fallo y mostrar “última sincronización correcta” y fecha. No borrar el maestro ni convertir precios en cero.
- Un artículo ausente del archivo no se elimina automáticamente. Bajas solo mediante estado reconocido/configurado o autorización; conservar referencias históricas.
- Cambiar o revocar acceso a una razón social/perfil invalida también sincronizaciones manuales. El trabajador automático usa el alcance persistido y autorizado del conector, no el rol que envía un precio desde el navegador.
- Conservar historial de archivo/revisión y resumen de altas/cambios/errores. Tokens cifrados y URL privada fuera de Git, binario y logs visibles; conexiones HTTPS a destinos Microsoft validados, con tiempos/límites de descarga.
- Si RFQ está detenido, no hay importación. Al iniciar se comprueba la fuente y se retoma el ciclo; fallar OneDrive no impide operar con la última versión válida.

## 6. Pantalla de administración y aceptación

Configuración → Maestro de venta → OneDrive: estado de conexión, hoja SUGERIDO, mapeo fijo revisable, emisores/listas destino, intervalo, última revisión, última carga correcta, errores y resumen. Acciones Probar conexión, Revisar diferencias, Sincronizar ahora, Activar/pausar automático. Mantener importación manual compatible para contingencia, sin desactivar auditoría ni protección de precios de cliente.

Pruebas necesarias antes de activarlo:

- I/J/K incluidos con N 0/8/16 %, formatos Excel porcentuales, O UOM y precios faltantes frente a cero autorizado.
- Cambio de precio o IVA que afecte nuevas operaciones, sin cambiar un presupuesto guardado ni un ticket histórico ni sobrescribir una tarifa de cliente.
- SKU y clasificación protegidos, G/ESTATUS, bajas no destructivas, línea de pasteles y módulos F.
- Archivo sin cambios, solo otra hoja cambiada, dos sincronizaciones concurrentes, edición durante descarga, token revocado, 403 y fuente vacía/corrupta.
- Caja operando mientras se descarga/aplica el lote; versiones de tarifa consistentes al confirmar pago.
- Alcance de las tres razones sociales, cuentas limitadas y ocultación del maestro completo/URL a operadores sin permiso.

La revisión en navegador confirma el acceso interactivo y encabezados, **no** una sincronización desatendida exitosa. Esa prueba de conexión forma parte de la implementación. La aplicación actual 1.8.0 sigue sin conector automático.

## Fuentes técnicas

- **M1:** [Microsoft Graph: descargar contenido de driveItem](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0).
- **M2:** [Microsoft Graph: acceso a elementos compartidos y codificación de ligas](https://learn.microsoft.com/en-us/graph/api/shares-get?view=graph-rest-1.0).

Los encabezados y usos de A–K/N fueron contrastados con las instrucciones del usuario y la interfaz del libro. O UOM, G y L–S se identificaron en la misma hoja para evitar asignaciones erróneas. No se inspeccionaron ni se publican registros de otras pestañas.
