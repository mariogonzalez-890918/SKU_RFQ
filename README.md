# Generador de SKU GMP · SKU_RFQ

Aplicación para Windows y servidor local con generadores de SKU de compras y ventas, requisiciones de materiales, reportes de costos y autorizaciones. Interfaz con menú lateral, inicio con tarjetas y vistas adaptables a celular.

## Funciones

- SKU de 14 caracteres. Conserva los SKU históricos de ventas.
- Carga de maestros sin sobrescribir los artículos existentes.
- Requisiciones con fecha del servidor y serie/folio por sucursal.
- Roles y acceso configurable a cada módulo; almacenistas limitados a sus almacenes.
- Reportes con filtros, unidades, costo de compra, impuestos configurables y descargas XLSX, PDF y CSV.
- Cambios o cancelaciones propuestos por almacenistas, con aprobación de Gerente o Superadministrador e historial. Las canceladas se excluyen del costeo.

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
