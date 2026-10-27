# RFQ_SKU_GMP · Versión 1.3.1

Aplicación para Windows y servidor local con generadores de SKU de compras y ventas, requisiciones de materiales, reportes de costos y autorizaciones. Interfaz con menú lateral, inicio con tarjetas y vistas adaptables a celular.

aplicación soportada y gestionada por Ing. Mario González, sistemas@grupomipan.com 2026

## Imágenes y navegación

Las opciones de cada módulo se eligen en submenús del menú izquierdo. En celular y tablet (hasta 1024 px), el botón de tres líneas abre el menú desplegable; se conserva abierto cuando cambia la altura visible del navegador. Reportes separa consulta, configuración y costos; Respaldos separa descarga, restauración y reinicio.

En Requisiciones → Imágenes por SKU puedes cargar archivos de imagen válidos (PNG, JPEG, WebP, GIF, BMP, TIFF y otros formatos compatibles con el servidor), sin mínimo de dimensiones ni límite de peso por archivo configurado en el módulo. Para carga masiva, nombra cada archivo como `SKU.png`, `SKU.jpg`, etc.; el SKU debe existir y ser único. También puedes filtrar **Sin imagen** y pulsar **Cargar imagen**. Superadministrador y AUXTI son los únicos perfiles que pueden cargar, cambiar y quitar fotos; pueden hacerlo sin aprobación. Las miniaturas solo aparecen al buscar materiales de una nueva requisición; si faltan fotos, se muestra el logo GMP. El respaldo de requisiciones incluye las imágenes y acepta respaldos anteriores sin fotos.

El perfil **AUXTI** tiene acceso administrativo y puede descargar respaldos. Las bajas de SKU, desactivaciones de usuarios, cancelaciones o eliminación de partidas de requisiciones, vaciado y restauración de módulos requieren autorización de `sistemas@grupomipan.com`. Las solicitudes se revisan en **Autorizaciones → Autorizaciones de AUXTI**; los cambios de requisiciones se revisan en su pestaña correspondiente. Hasta aprobar, los datos se conservan. Se valida que los datos no hayan cambiado y se registra la decisión. AUXTI no puede asignarse Superadministrador, cambiar las cuentas de Superadministrador ni modificar accesos por perfil.

**Accesos por perfil** permite controlar por separado SKU Ventas, SKU Compras, Requisiciones, Imágenes y Cargar maestros. Cargar un maestro requiere tanto acceso al módulo correspondiente como a Cargar maestros. Habilitar Imágenes a otro perfil permite consultar su sección, pero la modificación de fotos permanece reservada a Superadministrador y AUXTI.

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

