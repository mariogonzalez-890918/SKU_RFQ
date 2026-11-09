# PT · Producto terminado — GMP ERP 3.2.0

## Uso

Sistemas habilita PT por perfil y crea usuarios con perfil PT, contraseña y sucursales asignadas: EJIDOS, SAN PABLO y/o CUAUTITLAN. No se crea ninguna cuenta con contraseña predeterminada. EJE 8 no participa. PT no ve precios/costos ni modifica maestros, etiquetas o configuración. Gerencia y AUXTI reciben acceso al nuevo módulo, que Sistemas puede retirar desde Accesos por perfil.

Las etiquetas se generan desde el maestro de ventas activo (comercial o catálogo SKU Ventas), conservando el SKU validado. PDF con QR y barras Code 128, SKU y descripción. En PT se escanea el código con Enter, se abre cámara por HTTPS o se toma/selecciona una foto. La foto se decodifica localmente y no se sube. Cámara de video requiere permiso del navegador y HTTPS; una IP con HTTP permite usar lector externo o la foto cuando el navegador/dispositivo ofrezca esa opción.

El usuario elige sucursal, identifica el producto y registra cantidad. Piezas enteras; otras unidades permiten hasta tres decimales. La fecha, folio, descripción y unidad los resuelve el servidor. La confirmación tiene clave única para que reintentar por problemas de red no duplique registros. Una captura pendiente debe verificarse o reenviarse antes de continuar. Los códigos por producto identifican el pan, no cuentan piezas ni identifican por sí solos un carro físico.

Historial: PT solo ve sus propios ingresos de las sucursales asignadas; Gerencia, AUXTI y Superadministrador ven las tres sucursales. Las cancelaciones de estos tres perfiles conservan la cantidad original y reenvían la exportación del mes original. El resumen muestra ingresos netos, no existencias posteriores a ventas. Esta etapa no envía movimientos a Odoo ni modifica el inventario de materias primas; el ID_MOVIMIENTO estable permitirá mapear una integración posterior.

## OneDrive personal: configuración guiada

El vínculo compartido de un Excel no concede autorización de escritura a GMP. El archivo de ejemplo corresponde a EJIDOS. Esta etapa genera archivos nuevos y no altera ese libro compartido: `GMP_PT/EJIDOS/PT_EJIDOS_2026-11.xlsx`, `GMP_PT/SAN_PABLO/PT_SAN_PABLO_2026-11.xlsx` y `GMP_PT/CUAUTITLAN/PT_CUAUTITLAN_2026-11.xlsx`. Al cambiar de mes se usa otro archivo; no se reemplaza el mes anterior. Los Excel contienen hojas INGRESOS_PT y RESUMEN_PT. El histórico oficial queda en SQLite; cada publicación actualiza el contenido del archivo mensual desde ese histórico.

1. Superadministrador abre PT → OneDrive por sucursal → Conectar OneDrive personal.
2. Registrar una aplicación propia en https://entra.microsoft.com/ → Registros de aplicaciones, para cuentas personales Microsoft (o cuentas organizativas y personales). Microsoft exige acceso a un tenant para registrar aplicaciones; puede ser necesario habilitar ese acceso con la cuenta administradora de Microsoft.
3. En Autenticación habilitar flujos de cliente público. Permisos delegados Microsoft Graph: User.Read y Files.ReadWrite; la conexión solicita offline_access para renovar sesión. No generar secreto de cliente ni proporcionar contraseña a GMP.
4. Copiar el Client ID en GMP y configurar el propietario `soportetecnico@grupomipan.com`, así como una carpeta diferente para cada sucursal. Guardar, pulsar Conectar con Microsoft y autorizar la cuenta propietaria con el código en el sitio oficial. Activar Publicar automáticamente y guardar.
5. Compartir las carpetas mensuales desde OneDrive como solo lectura para usuarios de consulta; quitar enlaces de edición previos sobre esas carpetas si existen. GMP no cambia automáticamente las invitaciones ni garantiza que quienes ya tienen edición no puedan modificar el archivo.
6. Consultar estado por sucursal/mes y usar Publicar pendientes ahora para reintentos. La captura se guarda aunque OneDrive falle. Ocho fallos consecutivos requieren reintento manual; se conservan los ingresos pendientes. Si el archivo cambió fuera de GMP, la publicación se detiene para evitar sobrescribir cambios; Sistemas debe revisar y conciliar ese caso.

Los tokens se almacenan con DPAPI, vinculados a la cuenta de Windows del servidor. Mantener esa cuenta al reiniciar el EXE; si se cambia de equipo/cuenta, reconectar Microsoft. No se incluyen tokens en el repositorio o distribución. Resguardar toda la carpeta data para conservar ingresos y estado de publicación; las descargas de respaldos por módulo anteriores no incluyen aún el nuevo módulo PT.

## Fuentes técnicas

- Microsoft Excel API y limitación de OneDrive personal: https://learn.microsoft.com/en-us/graph/api/resources/excel
- Carga de archivos en cuentas personales: https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession
- Autorización por código de dispositivo: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code
- Registro de aplicación: https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app
- Lector local ZXing JS Library 0.21.3, licencia Apache 2.0: https://github.com/zxing-js/library (SHA256 del bundle: d7cc8f69dd70bdcf3ac00c9ae572bf2acb9f4132ba379c72df842e4db918652d).

## Cámara de video por HTTPS

El servidor acepta `tls_cert` y `tls_key` en config.json (rutas absolutas o relativas al EXE), o `--tls-cert` y `--tls-key`. El certificado debe ser válido y confiable para el nombre usado en los teléfonos. No se crea un certificado autofirmado ni se altera el firewall automáticamente. Alternativa: publicar GMP detrás de un proxy HTTPS administrado. Un certificado rechazado o una IP que no coincida con su nombre no habilita la cámara. El lector externo funciona en HTTP; la foto usa el selector de imágenes del navegador.

## Corrección móvil 3.2.1

En Etiquetas QR / barras, Dirección de GMP se rellena con la dirección actual (local o ZeroTier) y puede cambiarse antes de generar el PDF. El QR contiene un enlace a `/pt?sku=...` para la cámara normal del teléfono; Code128 conserva el SKU. El teléfono debe poder alcanzar esa dirección y puerto. Un QR impreso tiene una dirección fija; no cambia automáticamente entre redes. El lector dentro de PT acepta ambos formatos y las etiquetas anteriores con SKU solo.

Abrir el QR sin sesión muestra el inicio de sesión y conserva el producto. No registra cantidades ni publica datos hasta confirmar el ingreso. Si hay una captura pendiente de confirmar, se verifica antes de abrir otro producto. HTTP permite abrir el enlace desde la cámara del teléfono; el video dentro del navegador sigue requiriendo HTTPS.

El estado OneDrive NO conectado es explícito. La liga del libro de ejemplo no autoriza escritura ni lo convierte en destino. Se mantiene el esquema acordado de nuevos Excel mensuales por sucursal, después de completar la autorización Microsoft. No se ha validado una conexión real mientras esa autorización siga pendiente.

## Lectura de fotos 3.2.2

Se separan Tomar foto del código y Elegir foto o imagen. La lectura se realiza localmente, admite hasta 25 MB/40 megapíxeles y prueba orientación, resolución y recortes con límite de 20 segundos. Muestra la imagen seleccionada y el avance; se permite volver a elegir la misma foto. No se puede recuperar información perdida por desenfoque o barras reducidas a muy pocos píxeles. Los errores del maestro o del servidor se muestran por separado del fallo de lectura. Las fotos no se envían al servidor.

Validado con la etiqueta facilitada por el usuario en fotos JPEG de 3000×4000, giros de 0/90/180/270 grados, código Code128 girado, foto vacía, reintento de la misma imagen y error de SKU inexistente. Leer una foto no genera ingresos.

## Alternativa Familia sin Client ID — 3.2.3

Se agregó publicación en carpeta local/SMB de una PC Windows compatible con OneDrive. Consulta [Configuración de PC puente](CARPETA_PUENTE.md). El modo Microsoft Graph anterior sigue disponible. La cuenta Microsoft solo se inicia en OneDrive en la PC puente; GMP no solicita su contraseña. El guardado en carpeta y la sincronización en la nube son estados distintos.
