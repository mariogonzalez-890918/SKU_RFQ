"""Importación transaccional del layout SUGERIDO; precios finales y SKU históricos."""
import base64,io,json,re,zipfile,xml.etree.ElementTree as ET
from ventas import read_master,norm,N,NS
from comercial import ADMINS,amount,dumps,now
from productos_comerciales import optional_price

def parse_master(content):
 raw,path,xml,rows=read_master(content)
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  styles=ET.fromstring(z.read('xl/styles.xml')) if 'xl/styles.xml' in z.namelist() else None
  formats={int(f.get('numFmtId')):f.get('formatCode','') for f in styles.findall('m:numFmts/m:numFmt',N)} if styles is not None else {}
  percent=set()
  if styles is not None:
   for i,xf in enumerate(styles.findall('m:cellXfs/m:xf',N)):
    code=int(xf.get('numFmtId','0'))
    if code in (9,10) or '%' in formats.get(code,''):percent.add(i)
  cells={c.get('r'):c for c in ET.fromstring(xml).findall('m:sheetData/m:row/m:c',N)}
  strings=[''.join(t.text or '' for t in si.iter('{'+NS+'}t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
  def value(c):
   if c is None:return ''
   v=c.findtext('m:v','',N)
   return strings[int(v)] if c.get('t')=='s' and v else ''.join(t.text or '' for t in c.iter('{'+NS+'}t')) if c.get('t')=='inlineStr' else v
  for col,word in {'A':'SKU','H':'DESCRIPCION','I':'PRECIO','J':'RUTA','K':'DESPACHO','N':'IMPUESTO','O':'UOM'}.items():
   if word not in norm(value(cells.get(col+'1'))):raise ValueError(f'Encabezado {col} incorrecto: se esperaba {word}. Solo se procesa SUGERIDO.')
  products=[];seen=set()
  for row in rows:
   sku=norm(row.get('A'));n=row['fila'];name=row['H'].strip()
   if not re.fullmatch('[A-Z0-9]{14}',sku) or sku in seen:raise ValueError(f'Fila {n}: SKU de A inválido o repetido. Corrige el maestro; no se regeneran SKU validados.')
   seen.add(sku);cell=cells.get('N'+str(n));rate_value=str(row.get('N','')).strip();is_percent='%' in rate_value or cell is not None and int(cell.get('s','0')) in percent
   rate=amount(rate_value.replace('%','').strip()) if rate_value.upper() not in ('','NULL','N/A','NA') else None
   if rate is not None and is_percent and '%' not in rate_value:rate*=100
   if rate is not None and rate not in (0,8,16):raise ValueError(f'Fila {n}: impuesto inválido, se permite 0%, 8% o 16%.')
   prices={key:optional_price(row.get(col,'')) for key,col in [('PUBLICO','I'),('RUTA','J'),('DESPACHO','K')]}
   channel=norm(row.get('W',''))
   if channel and channel not in ('INSTITUCIONALES','EXPENDIOS','AMBOS'):raise ValueError(f'Fila {n}: CANAL en W debe ser INSTITUCIONALES, EXPENDIOS o AMBOS.')
   institutional=channel!='EXPENDIOS';expendio=channel in ('EXPENDIOS','AMBOS') if channel else norm(row.get('G')) in ('SI','S','1','TRUE','VERDADERO','X')
   unit=str(row.get('O','')).strip()
   if not unit or len(name)>300:raise ValueError(f'Fila {n}: revisa descripción y UOM en O.')
   products.append({'sku':sku,'nombre':name,'tipo':row.get('B',''),'categoria':row.get('C',''),'subcategoria':row.get('D',''),'linea':row.get('E',''),'modulo':row.get('F',''),'institucional':institutional,'expendio':expendio,'unidad':unit,'iva':format(rate,'f') if rate is not None else None,'activo':norm(row.get('S','ACTIVO')) not in ('BAJA','INACTIVO','NO','0'),'origen':'MAESTRO','precios':prices})
 if not products:raise ValueError('SUGERIDO no contiene productos.')
 return products

def import_master(cm,data,actor):
 if actor['role'] not in ADMINS:
  if 'maestro' not in cm.access(actor)['acciones']:raise PermissionError('No tienes permiso para cargar el maestro comercial.')
  from permissions import require_module
  require_module(actor,'cargar_maestro')
 if not any(m in actor.get('modulos',[]) for m in ('ventasins','expendios')):raise PermissionError('No tienes módulos comerciales habilitados.')
 companies=data.get('empresas',[])
 if not isinstance(companies,list) or not companies or len(companies)!=len(set(companies)):raise ValueError('Selecciona al menos una razón social.')
 for company in companies:cm.company(company,actor,True)
 products=parse_master(data.get('contenido',''));added=updated=preserved=manual=0;pending=[]
 with cm.store.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  if '_source_revision' in data and db.execute('SELECT revision FROM cm_source WHERE id=1').fetchone()[0]!=data['_source_revision']:raise ValueError('Cambió la configuración mientras se descargaba; sincroniza nuevamente.')
  for product in products:
   row=db.execute('SELECT revision,payload FROM cm_products WHERE sku=?',(product['sku'],)).fetchone();added+=not bool(row);updated+=bool(row);prices=product['precios'];payload={k:v for k,v in product.items() if k!='precios'}
   if row and json.loads(row[1]).get('origen')=='MANUAL':manual+=1
   else:db.execute('INSERT INTO cm_products VALUES(?,?,?) ON CONFLICT(sku) DO UPDATE SET payload=excluded.payload,revision=excluded.revision',(product['sku'],dumps(payload),(row[0] if row else 0)+1))
   missing=(['IVA'] if product['iva'] is None else [])+(['PRECIO PUBLICO'] if product['institucional'] and prices['PUBLICO'] is None else [])+(['PRECIO EXPENDIO'] if product['expendio'] and prices['RUTA'] is None and prices['DESPACHO'] is None else [])
   if missing:pending.append({'sku':product['sku'],'descripcion':product['nombre'],'faltantes':missing})
   for company in companies:
    for listing,price in prices.items():
     old=db.execute("SELECT revision,payload FROM cm_prices WHERE company=? AND list=? AND sku=? AND customer=''",(company,listing,product['sku'])).fetchone()
     if old and json.loads(old[1]).get('origen')!='MAESTRO':preserved+=1;continue
     if price is None:
      db.execute("DELETE FROM cm_prices WHERE company=? AND list=? AND sku=? AND customer=''",(company,listing,product['sku']));continue
     db.execute("INSERT INTO cm_prices VALUES(?,?,?,'',?,?) ON CONFLICT(company,list,sku,customer) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",(company,listing,product['sku'],(old[0] if old else 0)+1,dumps({'precio':price,'origen':'MAESTRO','fecha':now()})))
  for company in companies:cm.audit(db,actor,company,'maestro_comercial',{'productos':len(products),'archivo':str(data.get('archivo','SUGERIDO.xlsx'))[:200]})
  if data.get('revisar'):db.rollback()
 return {'ok':True,'revisionPrevia':bool(data.get('revisar')),'productos':len(products),'nuevos':added,'actualizados':updated,'preciosManualesConservados':preserved,'productosManualesConservados':manual,'skuValidadosConservados':True,'totalPendientes':len(pending),'pendientes':pending}
