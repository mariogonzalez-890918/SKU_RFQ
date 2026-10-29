# GMP ERP · Versión 3.1.6

Compras integrado con Requisiciones, Pedidos institucionales y Expendios. Incluye proveedores, solicitudes de cotización, pedidos de compra, recepciones parciales y registro interno de compras. Consulta [versión 3](docs/v3.0/IMPLEMENTACION.md).

Versión 2.1.1 con Pedidos institucionales y Expendios/TPV: pantallas y flujos separados, acceso por IP/HTTP y respaldo comercial. Consulta [instalación y alcance de v2](docs/v2.0/IMPLEMENTACION.md).

Aplicación para Windows y servidor local con generadores de SKU de compras y ventas, requisiciones de materiales, reportes de costos y autorizaciones. Interfaz con menú lateral, inicio con tarjetas y vistas adaptables a celular.

aplicación soportada y gestionada por Ing. Mario González, sistemas@grupomipan.com 2026

## Cambios 3.1.6

La barra lateral contraída muestra solo iconos, con nombre accesible y tooltip; se corrige el texto recortado de Almacenes, Pedidos, Expendios y Compras. Desplegada conserva nombres completos, incluidos celular y tablet.

Recepciones de compra incluye devolución al proveedor parcial o completa del remanente. Valida cantidades contra la recepción y devoluciones anteriores, conserva el original y registra la salida en Kárdex. Almacenista solicita; Gerencia, AUXTI y Superadministrador autorizan. Se muestran cantidades recibidas, devueltas y netas; las compras/facturas originales se conservan y la devolución física se registra por separado. El reporte Excel incluye devuelto y recibido neto.

Traspasos permite armar solicitudes aunque falte conteo o el físico sea cero/negativo. Enviar sin suficiente stock requiere autorización explícita de Gerencia, AUXTI o Superadministrador; no se exige activar el inventario inicial. El destino aumenta solo al confirmar cantidades recibidas. Kárdex tiene columna propia Concepto de movimiento y mantiene costos ocultos para Almacenista en pantalla y exportaciones.

Resumen de existencias tiene su propio botón; Kárdex conserva el detalle. Las observaciones de cancelación y surtido son opcionales. Surtir por encima de lo solicitado requiere autorización de Gerencia, AUXTI o Superadministrador antes de modificar documento, costos o inventario. Se conserva la cantidad solicitada original y el surtido real autorizado.

El Kárdex permite imprimir el resumen y detalle con los filtros actuales, descargar el reporte en PDF o exportar XML estructurado. Los costos se excluyen para Compras y Almacenista.

Movimiento de almacén agrupa entradas y salidas manuales y acceso a ajustes; su uso es exclusivo de Gerencia, AUXTI y Superadministrador. Las recepciones y surtidos registran Kárdex aunque falte el conteo inicial. Los surtidos pasan directamente, incluso si exceden el saldo, y muestran una alerta de negativo. Las correcciones y cancelaciones conservan sus autorizaciones. Las salidas históricas faltantes se concilian una vez, verificando antes que el conteo físico no las haya descontado ya. El saldo previo al conteo se identifica como provisional.

Compras incluye filtros propios y reportes detallados por pedido, partida, proveedor y sucursal, con cantidades pedidas, recibidas, pendientes y compradas, y exportación Excel de cinco hojas y PDF.

## Imágenes y navegación

Las opciones de cada módulo se eligen en submenús del menú izquierdo. En celular y tablet (hasta 1024 px), el botón de tres líneas abre el menú desplegable; se conserva abierto cuando cambia la altura visible del navegador. Reportes separa consulta, configuración y costos; Respaldos separa descarga, restauración y reinicio.

En Requisiciones → Imágenes por SKU puedes cargar archivos de imagen válidos (PNG, JPEG, WebP, GIF, BMP, TIFF y otros formatos compatibles con el servidor), sin mínimo de dimensiones ni límite de peso por archivo configurado en el módulo. Para carga masiva, nombra cada archivo como `SKU.png`, `SKU.jpg`, etc.; el SKU debe existir y ser único. También puedes filtrar **Sin imagen** y pulsar **Cargar imagen**. Superadministrador y AUXTI son los únicos perfiles que pueden cargar, cambiar y quitar fotos; pueden hacerlo sin aprobación. Las miniaturas solo aparecen al buscar materiales de una nueva requisición; si faltan fotos, se muestra el logo GMP. El respaldo de requisiciones incluye las imágenes y acepta respaldos anteriores sin fotos.

El perfil **AUXTI** tiene acceso administrativo y puede descargar respaldos. Las bajas de SKU, desactivaciones de usuarios, cancelaciones o eliminación de partidas de requisiciones, vaciado y restauración de módulos requieren autorización de `sistemas@grupomipan.com`. Las solicitudes se revisan en **Autorizaciones → Autorizaciones de AUXTI**; los cambios de requisiciones se revisan en su pestaña correspondiente. Hasta aprobar, los datos se conservan. Se valida que los datos no hayan cambiado y se registra la decisión. AUXTI no puede asignarse Superadministrador, cambiar las cuentas de Superadministrador ni modificar accesos por perfil.

**Accesos por perfil** permite controlar por separado SKU Ventas, SKU Compras, Requisiciones, Imágenes y Cargar maestros. Cargar un maestro requiere tanto acceso al módulo correspondiente como a Cargar maestros. Habilitar Imágenes a otro perfil permite consultar su sección, pero la modificación de fotos permanece reservada a Superadministrador y AUXTI.

El perfil **Gerente** puede emitir requisiciones, cargar el maestro de materiales, configurar series y folios de las cuatro sucursales, gestionar reportes y autorizar cambios. No puede retroceder folios ni reutilizar series de otra sucursal. La actualización habilita Cargar maestros para las cuentas de Gerente existentes; Sistemas puede ajustar luego sus accesos.

El perfil **Requisición** permite crear solicitudes y consultar exclusivamente las registradas por la propia cuenta en las sucursales asignadas en Usuarios, con impresión de esas solicitudes y propuestas de corrección que requieren aprobación de Gerente o Superadministrador. Las propuestas no cambian la solicitud hasta autorizarse. El alcance se comprueba también en el servidor y se basa en la cuenta que capturó, no en el nombre escrito en Solicitante. No tiene acceso a costos, reportes, maestros, series, autorizaciones de otras cuentas ni administración; tampoco puede cancelar solicitudes. Sus únicos submenús son Nueva solicitud y Mis requisiciones. En Usuarios puedes asignar el perfil a nuevas cuentas; no se crea una cuenta con contraseña predeterminada.

Las contraseñas nuevas requieren de 4 a 200 caracteres. En el acceso y en Usuarios está la casilla **Mostrar contraseña** para revisarla antes de enviar el formulario.

En Requisiciones → **Áreas solicitantes**, Superadministrador, AUXTI y Gerente pueden agregar y editar áreas. Los nombres anteriores se conservan para las requisiciones emitidas, correcciones y filtros de reportes. El catálogo se incluye en el respaldo de requisiciones.

Cada requisición ofrece dos opciones de impresión: el formato actual y **Ticket Bixolon 80 mm**, con contenido de 72 mm y firmas de Solicita, Entrega y Recibe al final. El ticket no muestra costos ni fotos de productos. En la vista previa pulsa Imprimir / Guardar PDF y selecciona la BIXOLON (por ejemplo, `bixo`), rollo de 80 mm, escala 100 %, sin márgenes ni encabezados/pies del navegador. La impresión conserva los mismos permisos de acceso de la requisición.

## Descargar EXE

Descarga **RFQ_SKU_GMP.exe** o el ZIP desde [Releases](https://github.com/mariogonzalez-890918/SKU_RFQ/releases/latest). La distribución pública no requiere Python e incluye catálogos vacíos. En el primer inicio solicita crear una contraseña; no lleva credenciales incorporadas. Para actualizar un servidor existente, conserva `data/` y `config.json` junto al EXE.

El flujo de GitHub Actions compila y publica los ejecutables automáticamente. También puedes generar una distribución pública local con `python tools/build_public.py --output-dir dist-public` después de instalar `requirements-dev.txt`.

## Funciones

- SKU de 14 caracteres. Conserva los SKU históricos de ventas.
- Maestro de compras desde `PRODUCTOS`: revisión previa, actualización por lote y recálculo de SKU cuando cambia la clasificación. Los SKU anteriores quedan reservados; las filas ambiguas se muestran para revisión.
- Requisiciones con fecha del servidor y serie/folio por sucursal.
- Roles y acceso configurable a cada módulo; almacenistas limitados a sus almacenes.
- Reportes con filtros, costo por **UM_ENTREGA**, impuestos configurables y descargas XLSX, PDF y CSV. Importe = cantidad solicitada × costo por unidad de entrega; se convierte desde UM_COMPRA mediante una equivalencia válida.
- Cambios o cancelaciones propuestos por almacenistas, con aprobación de Gerente o Superadministrador e historial. Las canceladas se excluyen del costeo.
- Respaldo y restauración por módulo (SKU Compras, SKU Ventas o Requisiciones), exclusivos de Superadministrador, con revisión de integridad, copia automática previa y conservación de máximos de folios/identificadores.
- **Vaciar módulo y cargar desde cero**: revisa, escribe `VACIAR` y confirma. Se guarda copia previa y se conservan usuarios, otros módulos y máximos de identificadores/folios. Luego carga `PRODUCTOS` y descarga el maestro con los SKU nuevos en D.

El reporte reconoce `UM_ENTREGA` y `UOM_ENTREGA`. Usa `COSTO` como costo unitario de entrega; cuando está vacío calcula precio de compra/equivalencia. Una equivalencia cero sigue pendiente de revisión. Se distinguen artículos con el mismo nombre cuando tienen presentación o clave de proveedor distintas.

## Ejecutar desde el código

Requiere Python 3.10 o posterior. En PowerShell, desde la carpeta del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/inicializar.py
.\.venv\Scripts\python.exe sku-servidor/server.py --host 0.0.0.0 --port 8080
```

El inicializador solicita una **contraseña nueva**, crea catálogos vacíos y se niega a sobrescribir archivos existentes. La cuenta inicial es `sistemas@grupomipan.com`. Abre `http://127.0.0.1:8080` o `http://IP-DEL-SERVIDOR:8080` desde tu red autorizada (LAN, Radmin o ZeroTier). El inicio de sesión usa HTTP local; para exponer el servicio a Internet configura HTTPS y acceso restringido.

Este repositorio público contiene código; **no incluye maestros empresariales, contraseñas, hashes de la instalación existente, bases de datos ni ejecutables con datos precargados**. Una instalación nueva debe cargar sus maestros desde la interfaz. En requisiciones se usa exclusivamente la pestaña `PRODUCTOS`; ventas utiliza `SUGERIDO` y conserva los SKU en A. Los archivos locales `initial*.json`, `data/` y `config.json` están excluidos de Git.

## Desarrollo de la interfaz

Los archivos publicados en `sku-servidor/public/` permiten ejecutar el servidor sin Node. Los fuentes de la interfaz están en `sku/`. Para regenerarlos, después de inicializar los archivos locales, instala Node.js y ejecuta:

```powershell
node sku/build-server.mjs
```

El generador utiliza los archivos iniciales locales y no requiere una ruta de Excel particular. Los datos de una instalación existente se mantienen en su base de datos, no en los archivos HTML/JS.

## Compilar EXE para Windows

Después de inicializar y, si corresponde, regenerar la interfaz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm sku/SKU-JAD-Servidor.spec --distpath dist --workpath build
```

El EXE incluye los archivos iniciales **locales** que tengas al compilarlo. Distribúyelo solo a los destinatarios autorizados. Para actualizar una instalación, detén el EXE anterior, respalda y conserva `data/` y `config.json`, y reemplaza el ejecutable. El código y el EXE conservan las mismas funciones; los catálogos empresariales se gestionan fuera de Git.

## Prueba de instalación limpia

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Esta prueba utiliza datos vacíos y credenciales aleatorias temporales. Las guías detalladas de operación están en [sku-servidor/LEEME.md](sku-servidor/LEEME.md); las cifras de materiales que mencionan describen la instalación original y no los catálogos vacíos de este repositorio.

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `sku-servidor/` | Servidor HTTP, SQLite, permisos, SKU, requisiciones, reportes y autorizaciones |
| `sku-servidor/public/` | Interfaz compilada, inicio de sesión y logo |
| `sku/` | Fuentes de HTML/CSS/JavaScript y definición de PyInstaller |
| `tools/` | Inicialización local sin datos empresariales |
| `tests/` | Verificación de instalación limpia |


Requisición y Almacenista solicitan aprobación o cancelación desde el detalle. Superadministrador, AUXTI y Gerente autorizan; se conserva el folio y el historial. Almacenista y los perfiles administrativos aprueban capturando cantidades realmente surtidas en UM_ENTREGA y la marca SURTIDO. Solicitado y surtido se muestran por separado, también en ambas impresiones, sin mostrar costos al perfil Requisición. El costeo usa lo realmente surtido y compara su total contra lo requisitado; las canceladas siguen excluidas.

Versión 1.8.0: Almacenista, Superadministrador, Gerencia y AUXTI aprueban capturando las cantidades realmente surtidas y el estado SURTIDO. El almacenista solicita correcciones de surtidos con autorización; los administradores y gerencia las aplican directamente. Reportes y descargas comparan total requisitado y total surtido; el costeo usa el surtido real y las cantidades se agrupan por unidad, sin sumar unidades incompatibles. Sin captura de entrega, el surtido es cero.

Inventarios 3.1: carga inicial, ajustes autorizados, surtido real, recepciones y traspasos con confirmación. Consulta [puesta en marcha de almacenes](docs/v3.1/INVENTARIOS.md).
