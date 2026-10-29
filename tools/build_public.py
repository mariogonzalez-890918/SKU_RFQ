"""Compila una distribución pública con catálogos vacíos y sin credenciales incorporadas."""
import argparse,pathlib,runpy,secrets,shutil,subprocess,sys,tempfile,zipfile
ROOT=pathlib.Path(__file__).resolve().parent.parent
SERVER_FILES=('inventarios_operaciones.py','inventarios.py','inventarios_routes.py','plantillas_import.py','pedidos_compra.py','pedidos_compra_routes.py','pedidos_compra_vendors.py','pedidos_compra_output.py','precios_masivos.py','fechas.py','productos_comerciales.py','clientes_comerciales.py','respaldo_comercial.py','comercial.py','comercial_routes.py','comercial_print.py','comercial_sync.py','maestro_comercial.py','server.py','ventas.py','requisiciones.py','permissions.py','reportes.py','reporte_export.py','autorizaciones.py','compras.py','respaldos.py','app_info.py','imagenes.py','aprobaciones_admin.py','areas.py','ticket.py','catalogos.json')
GUIDE='''GMP ERP v3.1.2 - DISTRIBUCIÓN PÚBLICA

1. Extrae el ZIP en una carpeta fija, por ejemplo C:\\SKU-GMP.
2. Ejecuta GMP_ERP.exe. No necesitas instalar Python.
3. En una instalación nueva, la consola solicitará definir y confirmar una
   contraseña para sistemas@grupomipan.com. No existe contraseña predeterminada.
4. Abre http://127.0.0.1:8080. Desde tu red autorizada usa http://IP:8080.
5. Carga tus maestros desde la aplicación. Esta distribución contiene catálogos
   vacíos y no incluye información de productos de una empresa.

ACTUALIZAR UNA INSTALACIÓN EXISTENTE
Detén el EXE anterior, respalda y conserva data y config.json y reemplaza
el ejecutable. Se conservan los usuarios, sus contraseñas, los catálogos,
las requisiciones, los reportes y los folios existentes.

Antes de instalar el inicio automático, completa el primer inicio interactivo.
El puerto 8080 debe estar permitido en el firewall de tu red local/VPN.
Para exponer el servicio a Internet utiliza HTTPS y acceso restringido.
'''
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=pathlib.Path,default=ROOT/'dist-public');args=parser.parse_args();target=args.output_dir.resolve();target.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='gmp-public-') as folder:
  clean=pathlib.Path(folder);server=clean/'sku-servidor';server.mkdir();(clean/'sku').mkdir()
  for name in SERVER_FILES:shutil.copy2(ROOT/'sku-servidor'/name,server/name)
  shutil.copytree(ROOT/'sku-servidor/public',server/'public');shutil.copy2(ROOT/'sku/SKU-JAD-Servidor.spec',clean/'sku/SKU-JAD-Servidor.spec')
  initializer=runpy.run_path(str(ROOT/'tools/inicializar.py'));initializer['create_initials'](server,secrets.token_urlsafe(32));(server/'initial-admin.json').unlink()
  subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','sku/SKU-JAD-Servidor.spec','--distpath',str(target),'--workpath',str(clean/'build')],cwd=clean,check=True)
 shutil.copy2(target/'SKU-JAD-Servidor.exe',target/'RFQ_SKU_GMP.exe');shutil.copy2(target/'SKU-JAD-Servidor.exe',target/'GMP_ERP.exe')
 (target/'LEEME.txt').write_text(GUIDE,encoding='utf8')
 with zipfile.ZipFile(target.parent/'GMP_ERP_Windows.zip','w',zipfile.ZIP_DEFLATED) as archive:
  for name in ('GMP_ERP.exe','LEEME.txt'):archive.write(target/name,name)
 print('EXE público sin maestros ni credenciales:',target/'SKU-JAD-Servidor.exe')
if __name__=='__main__':main()


