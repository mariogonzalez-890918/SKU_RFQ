# Generador de SKU GMP

GENERADOR DE SKU GMP - WINDOWS DE 64 BITS

1. Copia la carpeta a una ruta fija del servidor, por ejemplo C:\SKU-JAD.
2. Abre SKU-JAD-Servidor.exe. No necesitas instalar Python.
3. Inicia sesión con sistemas@grupomipan.com y la contraseña que configuraste.
4. Ejecuta ABRIR-PUERTO.bat y acepta la solicitud de administrador de Windows.
5. Desde otra computadora abre http://IP-DEL-SERVIDOR:8080
   Usa la IP local, la de Radmin VPN o la de ZeroTier, según tu conexión.

El EXE incluye compras (774 artículos) y ventas (625 artículos) y el logo GMP.
Incluye Requisición de materiales con 700 artículos de la pestaña PRODUCTOS,
áreas solicitantes, series por sucursal y fecha asignada por el servidor.
Consulta REQUISICIONES.txt para cargar maestros, emitir e imprimir solicitudes.
Consulta REPORTES-Y-ACCESOS.txt para habilitar módulos por perfil y armar
reportes con costo de compra, equivalencias e impuestos configurables.
Los cambios de todos los usuarios se guardan en la misma base de datos.
Los SKU tienen 14 caracteres. Compras usa verificador Luhn base36; ventas
conserva los SKU históricos y usa sufijo 0-9, A-Z para los nuevos repetidos.
Las bajas no reutilizan códigos. En ventas la columna A histórica nunca cambia.
Las cargas de maestros agregan artículos sin sobrescribir los existentes.

Para que arranque al encender Windows:
Ejecuta INSTALAR-INICIO-AUTOMATICO.bat, acepta el permiso de administrador,
cierra la ventana manual y reinicia el servidor. También puedes arrancar
la tarea SKU-JAD-Servidor desde el Programador de tareas.

La carpeta data y config.json se crean JUNTO al EXE, fuera de sus archivos
temporales. Guarda respaldos de esos archivos; al actualizar el EXE,
conserva data y config.json. No ejecutes el EXE directamente desde el ZIP.

Para administrar usuarios, perfiles y contraseñas, abre Administrar usuarios
y perfiles con la cuenta de sistemas. Para cambiar el puerto, detén la app,
edita port en config.json y reinicia. El puerto predeterminado es TCP 8080.

Para Radmin VPN o ZeroTier, ambos equipos deben pertenecer a la misma red
y el servidor debe estar encendido. La tarea o ventana debe estar activa.

Los perfiles son visualizador, ventas, compras, superadministrador, alta de
productos, gerente y almacenista. El gerente consulta solo requisiciones en
las cuatro sucursales. El almacenista consulta los almacenes asignados desde
Administrar usuarios y perfiles. Alta de productos no tiene acceso a respaldos.
Los respaldos son
exclusivos del superadministrador.

Consulta ACTUALIZAR-GMP.txt para sustituir el EXE anterior sin perder datos.

Consulta AUTORIZACIONES-Y-DESCARGAS.txt para Excel, PDF y cambios autorizados.


NUEVA INTERFAZ: consulta INTERFAZ-Y-MENU.txt para el menú lateral y las vistas.



GENERADOR DE SKU GMP - REQUISICION DE MATERIALES

MAESTRO INICIAL
Se cargan exclusivamente los 700 artículos de la pestaña PRODUCTOS del archivo
3.0.1.0 Maestro de productos de compra 2026 (2).xlsx suministrado.
No se importan SISTEMAS ni las demás pestañas. Se conservan SKU, descripción,
proveedor y unidades. La unidad utiliza UM_ENTREGA SUCURSALES cuando está
informada; en otro caso UM_ENTREGA o UM_COMPRA. Los indicadores SI, NO y N/A
no se usan como unidades: se consulta la siguiente columna disponible.
No se calculan conversiones.
Hay 64 artículos sin SKU y tres códigos repetidos en la fuente: cada material
tiene un ID interno independiente que permite distinguirlo sin cambiar su SKU.
Los artículos inactivos se consultan en el maestro pero no se pueden solicitar.

SOLICITUDES
La confirmación se muestra cuando termina el guardado. Las consultas del
historial y los folios se actualizan en paralelo, en segundo plano, sin
retrasar la apertura de la solicitud emitida. Si esa actualización falla,
la solicitud sigue guardada: usa Actualizar requisiciones para verla en la lista.
Se conserva la protección contra duplicados al reintentar un envío.

1. Inicia sesión y abre Requisición de materiales.
2. Selecciona sucursal, área y solicitante.
3. Busca materiales por descripción, SKU, proveedor o ID interno.
4. Captura cantidad y observaciones; agrega las partidas a la solicitud.
5. Pulsa Emitir solicitud. El servidor confirma fecha, serie y folio.
6. Consulta el historial para ver, imprimir/guardar PDF o descargar cada
   solicitud en CSV. La vista imprimible incluye espacios para firmas.

La fecha y hora se asignan en el servidor en horario de Ciudad de México
(UTC-06:00). No hay edición de la fecha ni de solicitudes ya emitidas.
Las cantidades admiten hasta seis decimales y conservan la unidad del maestro.
Las solicitudes guardan una copia de sus materiales, unidades y descripciones.
Se registran como SOLICITADA; no se registra automáticamente una entrega ni
se descuentan existencias. Se admiten hasta 200 partidas por solicitud.

SERIES INICIALES
EJIDOS: REQ-EJI-000001
SAN PABLO: REQ-SP-000001
CUAUTITLAN: REQ-CUA-000001
EJE 8: REQ-E8-000001
Cada sucursal tiene un consecutivo independiente. Dos usuarios no pueden
recibir el mismo folio y reintentar un envío no genera otra solicitud.
El folio mostrado en el formulario es una vista previa; al emitir se asigna
el consecutivo vigente. Los números no se reinician al actualizar el EXE.

PERSONALIZAR
El superadministrador puede configurar la serie y aumentar el siguiente folio
en Personalizar series y folios por sucursal. No puede disminuirlo ni usar
una serie reservada por otra sucursal. Las solicitudes anteriores conservan
su serie, folio y fecha originales.

CARGAR DATOS MAESTROS
Compras, alta de productos y superadministrador pueden revisar y confirmar
una carga. El archivo XLSX debe tener una pestaña llamada PRODUCTOS.
También se admite CSV/TSV con SKU, DESCRIPCION, UNIDAD y PROVEEDOR.
Los registros nuevos se agregan; los ya existentes se conservan. Una misma
carga no duplica artículos. Si cambian descripción, proveedor o unidad,
se considera otra referencia y no se altera el historial anterior.
Descargar catálogo vigente CSV incluye todos los materiales acumulados.
Descargar archivo maestro original entrega el último archivo cargado.

ACCESOS
Superadministrador: solicitudes, maestros, series y folios.
Compras y alta de productos: solicitudes y carga de maestros.
Ventas: emitir y consultar solicitudes, sin cargar maestros ni configurar.
Visualizador: consulta y descarga, sin emitir ni configurar.
Gerente: consulta requisiciones de EJIDOS, SAN PABLO, CUAUTITLAN y EJE 8.
Puede crear y editar reportes, impuestos, costos y equivalencias del reporte.
No modifica requisiciones emitidas ni administra usuarios o respaldos.
Almacenista: solo consulta de requisiciones en los almacenes que seleccione
el superadministrador. Los almacenes son las cuatro sucursales actuales.
La restricción se aplica al historial, detalle, impresión y descarga de cada
solicitud. Un enlace directo de otra sucursal no concede acceso.
Se mantienen las restricciones de respaldos de los perfiles anteriores.
Superadministrador puede habilitar o bloquear los tres módulos por perfil.
Consulta REPORTES-Y-ACCESOS.txt para permisos y el generador de reportes.

ASIGNAR ALMACENES A UN USUARIO
1. Entra como sistemas y abre Administrar usuarios y perfiles.
2. Crea un usuario o pulsa Editar usuario sobre una cuenta existente.
3. Selecciona ALMACENISTA y marca los almacenes autorizados (al menos uno).
4. Guarda el usuario. Si es una cuenta existente, deja su contraseña vacía
   para conservarla. Los cambios se aplican a las siguientes consultas,
   incluso cuando el almacenista ya tiene una sesión abierta.
Para GERENTE, las cuatro sucursales se asignan automáticamente.

ACTUALIZAR EL SERVIDOR
Detén la ventana o tarea SKU-JAD-Servidor. Respalda data con la aplicación
detenida. Sustituye el EXE en su misma carpeta y conserva data y config.json.
Al iniciar se agregan las tablas de requisiciones sin reemplazar los catálogos,
usuarios ni contraseñas existentes. No copies carpetas de pruebas al servidor.
El acceso continúa en http://IP-DEL-SERVIDOR:8080 por LAN, Radmin o ZeroTier.


GENERADOR DE SKU GMP - ACCESOS POR PERFIL Y REPORTES DE COSTO

MODULOS POR PERFIL
Superadministrador dispone de Acceso a módulos por perfil, arriba de las pestañas.
Puede habilitar o bloquear SKU Ventas, SKU Compras y Requisición de materiales
para cada uno de los otros perfiles. Guarda los accesos de la fila editada.
El bloqueo se aplica en el servidor de inmediato, incluso a sesiones abiertas.
Actualiza la página de la cuenta afectada para mostrar u ocultar sus pestañas.
Superadministrador conserva siempre los tres módulos y la administración.
Habilitar un módulo no convierte un perfil de consulta en un perfil de edición.
Las asignaciones de almacenes del Almacenista siguen restringiendo sus solicitudes.

GENERADOR DE REPORTES
Abre Reportes de requisición desde el menú lateral izquierdo.
Solo Gerente y Superadministrador pueden crear o modificar configuraciones,
impuestos, costos de compra y equivalencias. Los otros perfiles con acceso
al módulo pueden consultar reportes guardados y descargar su detalle CSV.
Cada consulta se limita a las sucursales/almacenes autorizados del usuario.

ARMAR UN REPORTE
1. Pulsa Armar reporte nuevo y escribe el nombre.
2. Selecciona fechas, sucursales y áreas. Sin selección incluye todas las
   ubicaciones autorizadas. Puedes filtrar por solicitante, material/SKU y folio.
3. Elige agrupación: general, sucursal, área, requisición, material o unidad.
4. Agrega los impuestos deseados con nombre y porcentaje, o deja la lista vacía.
5. Consulta Vista previa y Guarda el reporte para que los demás lo puedan ver.
6. Usa Ver requisiciones sobre un grupo y pulsa el folio para abrir la solicitud.
7. Descarga el detalle CSV. La pantalla pagina el detalle de 200 en 200;
   la descarga incluye todas las partidas del resultado.

COSTOS POR UNIDAD
La carga inicial utiliza PRECIO DE COMPRA y UM_COMPRA de PRODUCTOS.
La cantidad solicitada utiliza la unidad de entrega del material.
Costo unitario solicitado = precio por unidad de compra / equivalencia.
Ejemplo: una CAJA de 12 piezas con precio 120 y equivalencia 12 PIEZAS
por CAJA tiene costo unitario 10 por PIEZA; solicitar 3 PIEZAS cuesta 30.
Las unidades iguales y equivalencias inequívocas se reconocen automáticamente.
Presentaciones contradictorias con U_M, unidades sin equivalencia o precios
faltantes quedan PENDIENTES. No se consideran cero: el total se marca parcial.
La carga inicial contiene 700 materiales y 160 requieren revisión de costo
o equivalencia. La cifra disminuye conforme se confirman las equivalencias.

En Costos de compra y equivalencias por unidad, Gerente o Superadministrador
puede buscar el producto, editar su precio/unidad de compra y confirmar cuántas
unidades solicitadas contiene una unidad de compra. Guarda y vuelve a generar
el reporte. Esto no modifica los SKU, el archivo Excel ni las solicitudes emitidas.
Los precios válidos de cero se conservan como cero; no se confunden con faltantes.

BASE DE VALUACION E IMPUESTOS
El reporte usa el costo de compra CONFIGURADO VIGENTE al momento de generarlo,
también para solicitudes anteriores. No es una reconstrucción del costo histórico
de emisión: las versiones anteriores no guardaban precios en las solicitudes.
Cambiar la configuración de costos puede cambiar el importe de reportes futuros.
Los impuestos son los que el editor guarde en cada reporte. Cada impuesto se
calcula sobre el costo de compra sin impuestos; no hay impuestos sobre impuestos.
Importes e impuestos se redondean a centavos por partida y se suman en el reporte.
No se mezclan cantidades de unidades diferentes. En resúmenes generales se
muestran importes; las cantidades solo se suman por unidad o material/unidad.

ACTUALIZAR
Detén el EXE anterior, respalda data y reemplaza el EXE en su misma carpeta.
Conserva data y config.json. Al iniciar se crean configuraciones de perfiles,
costos y reportes sin reiniciar folios ni reemplazar usuarios o requisiciones.

ACTUALIZACIÓN: ahora puedes descargar XLSX y PDF, guardar copias de reportes
y cancelar/corregir solicitudes con autorización. Consulta
AUTORIZACIONES-Y-DESCARGAS.txt. Las canceladas se excluyen del costeo.
Una equivalencia cero queda pendiente, sin división entre cero ni costo gratuito.




GENERADOR DE SKU GMP - REPORTES Y CAMBIOS AUTORIZADOS

VARIOS REPORTES Y DESCARGAS
En el menú izquierdo > Reportes de requisición:
- Armar reporte nuevo permite guardar un reporte independiente con su nombre,
  filtros, agrupación e impuestos. Puedes guardar varios y elegirlos en la lista.
- Guardar como otro reporte duplica la configuración sin cambiar el original.
- Descargar Excel genera un archivo XLSX con Resumen, Grupos y Detalle.
- Descargar PDF genera un PDF con resumen, filtros, impuestos y detalle paginado.
- Las descargas incluyen todas las partidas del filtro, no solo la página visible.
- El servidor recalcula con costos, permisos y estados vigentes al descargar.
- Para PDF se admiten hasta 10,000 partidas. Reduce filtros si supera ese límite;
  Excel y CSV permiten el detalle completo dentro del límite del reporte.
- Solo Gerente y Superadministrador editan reportes, impuestos, costos y
  equivalencias. Los demás usuarios habilitados consultan y descargan los
  reportes guardados, limitados a sus sucursales/almacenes autorizados.

CANCELAR Y MODIFICAR REQUISICIONES
Abre Ver solicitud en el historial o desde el detalle del reporte.
Gerente y Superadministrador pueden aplicar una corrección o cancelación
directa, con motivo obligatorio. La cancelación es definitiva y conserva el folio.

El Almacenista puede solicitar modificar o cancelar requisiciones de los
almacenes que le asignó el Superadministrador. Escribe el motivo y envía la
propuesta. NO cambia la solicitud ni el costeo hasta que se apruebe.
No puede cambiar costos, equivalencias, impuestos ni reportes.

En el menú Autorizaciones, Gerente o Superadministrador abre Revisar
autorización, compara los cambios, escribe un comentario y aprueba o rechaza.
Las propuestas desactualizadas no se aprueban: se rechazan y se solicita una
nueva propuesta sobre la versión vigente. Si el almacenista perdió el acceso
al almacén o está inactivo, tampoco se puede aplicar la propuesta.

Se pueden corregir área, solicitante, observaciones y partidas (cantidades,
agregar o quitar materiales). No cambian fecha de emisión, sucursal, serie,
folio ni SKU originales. Se guardan las versiones anteriores, motivos,
solicitante, fecha y autorizador. Ver historial de cambios permite consultarlos.

Las solicitudes CANCELADAS siguen visibles en el historial, impresión y CSV,
con su estado. Se EXCLUYEN totalmente del reporte de costeo, de sus impuestos
y descargas. El reporte muestra cuántas canceladas se excluyeron. Vuelve a
generarlo después de un cambio para actualizar los resultados en pantalla.

EQUIVALENCIA CERO
Una equivalencia cero significa pendiente de corregir. No se divide entre
cero ni se muestra costo cero: esa partida queda sin valorizar y el total
se identifica como PARCIAL. Esto es independiente de cancelar una solicitud.
Cancelar no modifica las equivalencias del producto ni afecta otros folios.
Gerente o Superadministrador pueden corregir la equivalencia y recalcular.

ACTUALIZAR EL SERVIDOR
Detén el EXE anterior, respalda la carpeta data y reemplaza el ejecutable
en su carpeta habitual. Conserva data y config.json. La actualización agrega
tablas de autorizaciones e historial sin reiniciar usuarios, SKU o folios.
No ejecutes dos versiones contra la misma base de datos al mismo tiempo.



GENERADOR DE SKU GMP - NUEVA NAVEGACIÓN

INICIO
Al iniciar sesión verás las tarjetas de las herramientas permitidas para tu
perfil. Los accesos rápidos permiten comenzar una requisición o crear un SKU.
Los indicadores respetan las sucursales y almacenes autorizados de tu cuenta.

MENÚ IZQUIERDO
- SKU Compras: Catálogo, Nuevo artículo, Cargar listas, Ayuda y códigos.
- SKU Ventas: Catálogo, Nuevo artículo, Cargar listas, Ayuda y códigos.
- Requisición de materiales: Nueva solicitud, Historial, Maestro de materiales
  y Series y folios. Solo aparecen las opciones permitidas por tu perfil.
- Reportes de requisición: selecciona el reporte y pulsa Ver reporte. Desde
  aquí descargas Excel, PDF o CSV. Los filtros e impuestos están en Configurar
  filtros e impuestos; solo los pueden editar Gerente y Superadministrador.
- Autorizaciones: propuestas de corrección o cancelación y sus resoluciones.
  El almacenista consulta sus propuestas; Gerente/Superadministrador resuelven.
- Usuarios y Accesos por perfil: administración exclusiva de Superadministrador.

Para modificar o cancelar, entra a Requisición > Historial > Ver solicitud.
Se conserva el flujo de autorización y el historial. Las canceladas se excluyen
del costeo. Los costos y equivalencias siguen en Reportes de requisición.

El botón de tres líneas contrae el menú en computadora y lo despliega en
pantallas pequeñas. En computadora puedes usar el botón Atrás del navegador
para volver a la pantalla anterior. Los formularios conservan los datos
mientras navegas entre las vistas de la misma sesión/página.

La ayuda de los SKU se encuentra en Ayuda y códigos, separada de la captura.
Los maestros de requisiciones se cargan/descargan en Maestro de materiales.
No se necesitan fuentes, imágenes ni librerías de un sitio externo para usar
la nueva interfaz en tu red local, Radmin o ZeroTier.

ACTUALIZAR
Detén la versión anterior y respalda data antes de reemplazar el EXE.
Conserva data y config.json. Esta actualización reorganiza la interfaz;
no reinicia usuarios, catálogos, solicitudes, permisos ni folios.

