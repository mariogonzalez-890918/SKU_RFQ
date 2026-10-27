"""Inicialización sin datos operativos ni contraseña predeterminada. Solo biblioteca estándar."""
import argparse,base64,getpass,hashlib,io,json,pathlib,secrets,zipfile
from xml.sax.saxutils import escape
ROOT=pathlib.Path(__file__).resolve().parent.parent

def empty_workbook(sheet,headers):
 ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';output=io.BytesIO()
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="'+sheet+'" sheetId="1" r:id="rId1"/></sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
  row=''.join('<c r="'+col+'1" t="inlineStr"><is><t>'+escape(label)+'</t></is></c>' for col,label in headers.items())
  z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="'+ns+'"><sheetData><row r="1">'+row+'</row></sheetData></worksheet>')
 return base64.b64encode(output.getvalue()).decode()

def create_initials(directory,password):
 directory=pathlib.Path(directory);names=['initial.json','initial-admin.json','initial-ventas.json','initial-requisiciones.json']
 if any((directory/name).exists() for name in names):raise ValueError('Ya existen archivos iniciales. No se sobrescriben; conserva la instalación actual.')
 if not isinstance(password,str) or not 4<=len(password)<=200:raise ValueError('La contraseña requiere entre 4 y 200 caracteres.')
 directory.mkdir(parents=True,exist_ok=True)
 purchases=empty_workbook('COMPRAS',{'A':'ID','B':'SKU ANTERIOR','C':'ESTADO','D':'SKU NUEVO','E':'PRODUCTO','F':'CATEGORÍA','G':'SUBCATEGORÍA','H':'DESCRIPCIÓN','O':'PROVEEDOR'})
 sales=empty_workbook('SUGERIDO',{'A':'SKU','B':'PRODUCTOS Y SERVICIOS','C':'CATEGORIA','D':'SUBCATEGORIA','F':'MODULO ID PDV','H':'DESCRIPCIÓN','S':'ESTADO'})
 requisitions=empty_workbook('PRODUCTOS',{'A':'SKU','B':'DESCRIPCIÓN','C':'UNIDAD','D':'PRECIO DE COMPRA','E':'UM_COMPRA','F':'PROVEEDOR'})
 salt=secrets.token_hex(16)
 files={'initial.json':{'state':{'version':3,'maxId':0,'registros':[],'reservados':[]},'master':purchases},'initial-admin.json':{'salt':salt,'password_hash':hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),310000).hex()},'initial-ventas.json':{'state':{'version':1,'maxId':0,'registros':[],'reservados':[]},'master':sales,'sheet':'SUGERIDO'},'initial-requisiciones.json':{'master':requisitions,'report':{'archivo':'MAESTRO PRODUCTOS VACIO.xlsx','hoja':'PRODUCTOS','materiales':[],'total':0,'sinSku':0,'sinUnidad':0,'skuRepetidos':0,'inactivos':0}}}
 for name,data in files.items():(directory/name).write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
 return list(files)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-dir',type=pathlib.Path,default=ROOT/'sku-servidor');args=parser.parse_args()
 if any((args.output_dir/name).exists() for name in ['initial.json','initial-admin.json','initial-ventas.json','initial-requisiciones.json']):parser.error('Esta instalación ya tiene archivos iniciales. No se sobrescribirá ninguno.')
 password=getpass.getpass('Contraseña nueva para sistemas@grupomipan.com (mínimo 4 caracteres): ')
 if password!=getpass.getpass('Confirma la contraseña: '):parser.error('Las contraseñas no coinciden.')
 try:create_initials(args.output_dir,password)
 except ValueError as error:parser.error(str(error))
 print('Archivos iniciales creados con catálogos vacíos. No los subas a Git. Carga tus maestros desde la aplicación.')
if __name__=='__main__':main()
