# Microsoft 365 Familia sin Client ID · GMP ERP 3.2.4

GMP genera los archivos de PT en una carpeta local o compartida. La aplicación OneDrive de una PC compatible sincroniza esa carpeta con la cuenta personal. No se necesita registrar una aplicación, obtener Client ID ni comprar Microsoft 365 empresarial para este modo.

## Preparar la PC puente

1. Utiliza una PC con Windows 11 y acceso tanto al servidor GMP como a Internet. El servidor actual fue identificado anteriormente como Windows Server 2016; esta solución mantiene OneDrive en la PC puente.
2. Inicia OneDrive en esa PC con la cuenta propietaria de los archivos. Esta sesión se hace directamente en Microsoft, no en GMP.
3. Dentro de la carpeta de OneDrive crea `GMP_PT`. En el Explorador, márcala como **Mantener siempre en este dispositivo**.
4. En las propiedades de esa carpeta, configura un recurso compartido de Windows llamado `GMP_PT`. Concede lectura/escritura en el recurso compartido y en Seguridad al usuario de Windows con el que se ejecuta GMP en el servidor. No es necesario conceder acceso de modificación a los usuarios que solo consultan los Excel.
5. Desde el servidor y con esa misma cuenta de Windows abre `\\PC-PUENTE\GMP_PT`, sustituyendo PC-PUENTE por el nombre o IP real de la PC. Debe poder escribir allí. Si Windows pide credenciales de la PC puente, establece ese acceso en Windows; GMP no almacena contraseñas de SMB ni de Microsoft.

Mantén la PC encendida, con su sesión de Windows iniciada y OneDrive funcionando. Puedes bloquear la pantalla. Comprueba el acceso después de reiniciar ambos equipos; el acceso de una sesión de administrador puede ser distinto al de la cuenta que inicia GMP automáticamente.

## Configurar GMP

1. Actualiza conservando `data` y `config.json`; reinicia y recarga el navegador.
2. Con Superadministrador abre **PT → OneDrive por sucursal → Configurar publicación**.
3. En Método selecciona **Carpeta sincronizada / PC puente · Sin Client ID**.
4. En Carpeta accesible desde el servidor indica `\\PC-PUENTE\GMP_PT`. Si GMP y OneDrive se ejecutan en la misma PC compatible, también se admite la ruta local de una carpeta ya existente.
5. Usa las subcarpetas `EJIDOS`, `SAN_PABLO` y `CUAUTITLAN`, una diferente para cada sucursal. Confirma el correo propietario y guarda.
6. Pulsa **Probar carpeta**. La prueba se ejecuta en segundo plano; Actualizar estado mostrará si el servidor pudo escribir. Esta prueba no confirma sincronización en la nube.
7. Activa **Publicar automáticamente** y guarda. Los ingresos previos que estén pendientes se incluyen en el archivo mensual.

Ejemplos dentro de la carpeta compartida:

- `EJIDOS/PT_EJIDOS_2026-11.xlsx`
- `SAN_PABLO/PT_SAN_PABLO_2026-11.xlsx`
- `CUAUTITLAN/PT_CUAUTITLAN_2026-11.xlsx`

Cada archivo nuevo contiene REGISTRO ENTRADA, con D producto, E cantidad y F UOM, una fila por captura. El detalle y resumen de consulta permanecen en GMP. Cambia de archivo al comenzar otro mes; las cancelaciones actualizan el mes original. Para usar un inventario mensual ya preparado y conservar sus otras pestañas, activa Usar libro de inventario preparado del mes y colócalo con el nombre indicado antes de publicar. Se valida el mes y se conserva el original para descargarlo desde Superadministrador. Los informes dinámicos pueden requerir Actualizar en Excel.

## Confirmación y problemas

**GUARDADO_EN_CARPETA** significa que GMP guardó el Excel en el destino. OneDrive realiza la transferencia después: confirma su icono de sincronización y abre el archivo en OneDrive web. GMP no puede certificar la llegada a la nube mediante este modo.

Si la PC está apagada, la red falla o Excel bloquea el archivo, las capturas siguen en GMP y la publicación queda pendiente. Hay reintentos automáticos; después de ocho fallos utiliza **Publicar pendientes ahora** cuando el destino esté disponible. Evita editar los archivos generados; las modificaciones de cantidades o identidad de filas publicadas por GMP se detectan y detienen la sustitución. Las actualizaciones de cálculo de Excel se conservan. Comparte las carpetas en OneDrive como solo lectura para quienes consultan. No se cambia de carpeta dentro del mismo método después de publicar para evitar separar el histórico. Para migrar a Microsoft directo, desactiva la publicación automática, cambia de método, autoriza la cuenta y selecciona los libros; los archivos anteriores se conservan.

La configuración de la ruta es exclusiva del Superadministrador. PT no recibe rutas del servidor, contraseñas ni configuración. Gerencia y AUXTI pueden revisar publicaciones y solicitar reintentos.

Pruebas: escritura en carpeta Windows, Excel mensual por sucursal, cancelaciones, recuperación, bloqueo y edición externa; simulación de destino no disponible. La PC puente y su sincronización real requieren completar la preparación anterior; no se instalaron ni configuraron automáticamente.

Referencias: [requisitos de OneDrive](https://support.microsoft.com/es-es/onedrive/onedrive-system-requirements), [sincronización con OneDrive](https://support.microsoft.com/es-es/onedrive/sync-your-computer-s-files-and-folders-with-onedrive).
