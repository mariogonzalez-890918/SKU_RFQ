from fechas import display_date
from permissions import require_module
"""Solicitudes inmutables, maestro independiente y folios atómicos por sucursal."""
import base64,collections,csv,datetime,decimal,hashlib,html,io,json,pathlib,re,sqlite3,unicodedata,uuid,zipfile,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parent
MX=datetime.timezone(datetime.timedelta(hours=-6))
AREAS=['Produccion','Produccion Barra congelada','Produccion Batidos Galletas','Produccion Bizcochero','Produccion Donas','Produccion Franceseros','Produccion Gelatinas','Produccion Limpieza','Produccion Pasteleros','Produccion Punto de Venta San Pablo','Produccion Reposteria','Produccion Rosticeria','Salida Cuautitlan','Salida Ejidos','Almacen rosticeria','Produccion Pan Molido','Produccion Pesadas','Produccion Condimix','Produccion Empacado','Produccion Empacado Armado','Produccion Empacado Congelado','Expendio']
BRANCHES={'EJIDOS':'REQ-EJI','SAN PABLO':'REQ-SP','CUAUTITLAN':'REQ-CUA','EJE 8':'REQ-E8'}
MANAGERS={'superadmin','auxti','compras','alta'}
SCOPED_ROLES={'gerente','almacenista','requisicion'}
READ_ONLY_ROLES={'visualizador','almacenista'}
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def visible_branches(actor=None):
 if actor is None or actor['role'] not in SCOPED_ROLES:return list(BRANCHES)
 field='sucursales' if actor['role'] in ('gerente','requisicion') else 'almacenes'
 return [value for value in actor.get(field,[]) if value in BRANCHES]
def now():return datetime.datetime.now(datetime.timezone.utc).astimezone(MX).isoformat(timespec='seconds')
def norm(value):return ' '.join(re.sub('[^A-Z0-9 ]',' ',''.join(c for c in unicodedata.normalize('NFD',str(value or '')) if not unicodedata.combining(c)).upper()).split())
def text(value,limit=300):
 if not isinstance(value,str) or len(value)>limit:raise ValueError('Texto inválido o demasiado largo.')
 return value.strip()
def csv_bytes(rows):
 stream=io.StringIO();writer=csv.writer(stream)
 for row in rows:writer.writerow([("'"+str(x) if re.match(r'^[\s]*[=+@-]',str(x)) else str(x)) for x in row])
 return ('\ufeff'+stream.getvalue()).encode('utf8')
def read_rows(raw,filename,sheet_name='PRODUCTOS'):
 if len(raw)>15*1024*1024:raise ValueError('El maestro supera 15 MB.')
 if filename.lower().endswith('.xlsx'):
  try:
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('El Excel descomprimido supera 100 MB.')
    wb=ET.fromstring(z.read('xl/workbook.xml'));rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'));targets={r.get('Id'):r.get('Target') for r in rels}
    sheet=next((s for s in wb.findall('m:sheets/m:sheet',NS) if s.get('name')==sheet_name),None)
    if sheet is None:raise ValueError('El archivo debe contener la pestaña PRODUCTOS. No se importan otras hojas.')
    target=targets[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];path=target.lstrip('/') if target.startswith('/') else 'xl/'+target.lstrip('./')
    strings=[''.join(t.text or '' for t in si.iter('{'+NS['m']+'}t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
    rows=[]
    for row in ET.fromstring(z.read(path)).findall('m:sheetData/m:row',NS):
     values={}
     for c in row.findall('m:c',NS):
      col=re.sub(r'\d','',c.get('r'));kind=c.get('t');v=c.findtext('m:v','',NS)
      values[col]=strings[int(v)] if kind=='s' and v else ''.join(t.text or '' for t in c.iter('{'+NS['m']+'}t')) if kind=='inlineStr' else v
     rows.append((int(row.get('r')),values))
    return rows,sheet_name
  except (zipfile.BadZipFile,ET.ParseError,KeyError,IndexError) as e:raise ValueError('El maestro Excel no es válido: '+str(e))
 if not filename.lower().endswith(('.csv','.tsv','.txt')):raise ValueError('Usa XLSX con pestaña PRODUCTOS o CSV/TSV con encabezados.')
 try:content=raw.decode('utf-8-sig')
 except UnicodeDecodeError:content=raw.decode('cp1252')
 try:dialect=csv.Sniffer().sniff(content[:4096],delimiters=',;\t')
 except csv.Error:dialect=csv.excel
 return [(i+1,{str(j):v for j,v in enumerate(row)}) for i,row in enumerate(csv.reader(io.StringIO(content),dialect))],'CSV'
def parse_master(raw,filename):
 rows,sheet=read_rows(raw,filename);header=None
 for index,(number,row) in enumerate(rows[:25]):
  h={norm(v):k for k,v in row.items() if norm(v)}
  if any(k in h for k in ('DESCRIPCION','ARTICULO','NOMBRE','PRODUCTO DESCRIPCION')) and any(k in h for k in ('SKU','SKU NUEVO','CLAVE')):header=(index,h);break
 if header is None:raise ValueError('Faltan encabezados SKU y DESCRIPCIÓN en PRODUCTOS o en el CSV.')
 index,headers=header
 def col(*labels):return next((headers[x] for x in labels if x in headers),None)
 columns={'sku':col('SKU NUEVO','SKU','CLAVE'),'nombre':col('DESCRIPCION','ARTICULO','NOMBRE','PRODUCTO DESCRIPCION'),'unidad':col('UOM ENTREGA','UM ENTREGA','UOM ENTREGA SUCURSALES','UM ENTREGA SUCURSALES','UNIDAD DE MEDIDA','UNIDAD','UOM','UOM COMPRA','UM COMPRA','UM BASE'),'proveedor':col('PROVEEDOR PRINCIPAL','PROVEEDOR'),'categoria':col('CATEGORIA'),'estado':col('STATUS DE COMPRA','ESTADO','ESTATUS','STATUS')}
 unit_columns=[headers[label] for label in ('UOM ENTREGA','UM ENTREGA','UOM ENTREGA SUCURSALES','UM ENTREGA SUCURSALES','UNIDAD DE MEDIDA','UNIDAD','UOM','UOM COMPRA','UM COMPRA','UM BASE') if label in headers]
 materials=[];occurrences=collections.Counter()
 for number,row in rows[index+1:]:
  r={k:str(row.get(c,'') or '').strip() if c is not None else '' for k,c in columns.items()}
  r['unidad']=next((str(row[c]).strip() for c in unit_columns if str(row.get(c,'') or '').strip() and norm(row[c]) not in {'SI','NO','N A','NA','TRUE','FALSE','0','1'}),'')
  for key,labels in {'impuestoCompra':('IMPUESTO DE COMPRA','IMPUESTO COMPRA','TASA IMPUESTO DE COMPRA','IMPUESTO','IMPUESTOS','IVA','TASA IMPUESTO'),'precioCompra':('PRECIO DE COMPRA','PRECIO COMPRA','COSTO DE COMPRA'),'claveProveedor':('CLAVE PROVEEDOR',),'unidadCompra':('UOM COMPRA','UM COMPRA','UNIDAD COMPRA'),'factorMaestro':('U M','FACTOR','FACTOR CONVERSION'),'costoBaseMaestro':('COSTO','COSTO UNITARIO','COSTO POR UNIDAD DE ENTREGA')}.items():
   c=col(*labels);r[key]=str(row.get(c,'') or '').strip() if c is not None else ''
  if not r['nombre']:continue
  if len(r['nombre'])>500 or len(r['sku'])>100 or len(r['unidad'])>160 or len(r['proveedor'])>500:raise ValueError(f'Fila {number}: datos demasiado largos.')
  r['estadoOriginal']=r['estado'];r['estado']='INACTIVO' if norm(r['estado']) in ('INACTIVO','BAJA','INACTIVA') else 'ACTIVO';r['fila']=number;r['hoja']=sheet
  fingerprint=json.dumps([norm(r[k]) for k in ('sku','nombre','unidad','proveedor')],ensure_ascii=False,separators=(',',':'));occurrences[fingerprint]+=1
  r['source_key']=hashlib.sha256((fingerprint+'|'+str(occurrences[fingerprint])).encode()).hexdigest();materials.append(r)
 if not materials:raise ValueError('No hay productos con descripción para importar.')
 if len(materials)>20000:raise ValueError('Se admiten hasta 20,000 artículos por carga.')
 counts=collections.Counter(r['sku'] for r in materials if r['sku'])
 return {'materiales':materials,'hoja':sheet,'archivo':filename,'total':len(materials),'sinSku':sum(not r['sku'] for r in materials),'sinUnidad':sum(not r['unidad'] for r in materials),'skuRepetidos':sum(v>1 for v in counts.values()),'inactivos':sum(r['estado']=='INACTIVO' for r in materials)}
def requester_document(document):
 """Campos operativos autorizados; excluye cualquier costo agregado por datos históricos."""
 if document is None:return None
 keys=('id','numero','serie','folio','fecha','fechaHora','sucursal','area','solicitante','observaciones','creadoPor','nombreUsuario','estado','revision')
 result={key:document[key] for key in keys if key in document}
 result['partidas']=[{key:line[key] for key in ('materialId','sku','nombre','cantidad','cantidadSurtida','unidad','proveedor','observaciones') if key in line} for line in document.get('partidas',[])]
 for key,fields in [('aprobacion',('fecha','autorizadoPor','solicitadoPor')),('surtido',('fecha','registradoPor','observaciones'))]:
  if isinstance(document.get(key),dict):result[key]={field:document[key][field] for field in fields if field in document[key]}
 if isinstance(document.get('inventario'),dict):result['inventario']={k:document['inventario'][k] for k in ('almacen','fecha','provisional') if k in document['inventario']}
 if isinstance(document.get('cancelacion'),dict):result['cancelacion']={key:document['cancelacion'][key] for key in ('motivo','fecha','autorizadoPor') if key in document['cancelacion']}
 return result

class Conflict(ValueError):pass
class RequisitionStore:
 def __init__(self,store):
  self.store=store
  from areas import AreaStore
  self.areas=AreaStore(store,AREAS)
  with store.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS req_materials(id INTEGER PRIMARY KEY AUTOINCREMENT,source_key TEXT UNIQUE NOT NULL,payload TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS req_masters(id INTEGER PRIMARY KEY AUTOINCREMENT,filename TEXT NOT NULL,created_at TEXT NOT NULL,actor TEXT NOT NULL,content TEXT NOT NULL,report TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS req_branches(branch TEXT PRIMARY KEY,series TEXT UNIQUE NOT NULL,next_folio INTEGER NOT NULL,revision INTEGER NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS req_series_registry(series TEXT PRIMARY KEY,branch TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS req_documents(id TEXT PRIMARY KEY,creator TEXT NOT NULL,client_key TEXT NOT NULL,fingerprint TEXT NOT NULL,branch TEXT NOT NULL,series TEXT NOT NULL,folio INTEGER NOT NULL,number TEXT UNIQUE NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(creator,client_key))')
   db.execute("UPDATE req_documents SET payload=json_set(payload,'$.estado','SURTIDO') WHERE json_extract(payload,'$.estado')='SURTIDA'")
   db.execute('CREATE INDEX IF NOT EXISTS req_documents_branch_date ON req_documents(branch,created_at)')
   db.execute('CREATE INDEX IF NOT EXISTS req_documents_date ON req_documents(created_at)')
   db.execute('CREATE INDEX IF NOT EXISTS req_documents_creator_date ON req_documents(creator,created_at)')
   for branch,series in BRANCHES.items():
    db.execute('INSERT OR IGNORE INTO req_branches VALUES(?,?,1,1)',(branch,series));db.execute('INSERT OR IGNORE INTO req_series_registry VALUES(?,?)',(series,branch))
   if not db.execute('SELECT 1 FROM req_masters').fetchone():
    initial=json.loads((ROOT/'initial-requisiciones.json').read_text(encoding='utf8'));report=initial['report']
    self._insert(db,report['materiales']);db.execute('INSERT INTO req_masters(filename,created_at,actor,content,report) VALUES(?,?,?,?,?)',(report['archivo'],now(),'CARGA INICIAL',initial['master'],json.dumps({k:v for k,v in report.items() if k!='materiales'},ensure_ascii=False)))
   db.execute('CREATE TABLE IF NOT EXISTS req_report_features(key TEXT PRIMARY KEY)')
   if not db.execute("SELECT 1 FROM req_report_features WHERE key='um-entrega-prioridad-v2'").fetchone():
    filename,content=db.execute('SELECT filename,content FROM req_masters ORDER BY id DESC LIMIT 1').fetchone()
    try:sources=parse_master(base64.b64decode(content),filename)['materiales']
    except ValueError:sources=[]
    by_name=collections.defaultdict(list)
    for source in sources:by_name[(norm(source['nombre']),norm(source['proveedor']))].append(source)
    for id,payload in db.execute('SELECT id,payload FROM req_materials').fetchall():
     material=json.loads(payload);candidates=by_name.get((norm(material['nombre']),norm(material['proveedor'])),[])
     if len(candidates)>1:candidates=[r for r in candidates if r['fila']==material.get('fila')]
     if len(candidates)==1 and material['unidad']!=candidates[0]['unidad']:
      material['unidad']=candidates[0]['unidad'];db.execute('UPDATE req_materials SET payload=? WHERE id=?',(json.dumps(material,ensure_ascii=False),id))
    db.execute("INSERT INTO req_report_features VALUES('um-entrega-prioridad-v2')")
 @staticmethod
 def _insert(db,materials):
  created=0
  for r in materials:
   cursor=db.execute('INSERT OR IGNORE INTO req_materials(source_key,payload) VALUES(?,?)',(r['source_key'],json.dumps(r,ensure_ascii=False)));created+=cursor.rowcount
  return created
 def metadata(self,actor=None):
  visible=visible_branches(actor)
  with self.store.connect() as db:
   branches=[dict(zip(('sucursal','serie','siguiente','revision'),r)) for r in db.execute('SELECT branch,series,next_folio,revision FROM req_branches ORDER BY rowid')]
   branches=[b for b in branches if b['sucursal'] in visible]
   for b in branches:b['vistaPrevia']=b['serie']+'-'+str(b['siguiente']).zfill(6)
   master=db.execute('SELECT filename,created_at,report FROM req_masters ORDER BY id DESC LIMIT 1').fetchone();where=' WHERE branch IN ('+','.join('?' for _ in visible)+')';params=list(visible)
   if actor and actor['role']=='requisicion':where+=' AND creator=?';params.append(actor['email'])
   count=db.execute('SELECT COUNT(*) FROM req_documents'+where,params).fetchone()[0]
  master_report=json.loads(master[2])
  if actor and actor['role']=='requisicion':master_report={key:master_report[key] for key in ('hoja','total') if key in master_report}
  return {'areas':self.areas.names(),'areasReporte':self.areas.names(historical=True) if not actor or actor['role']!='requisicion' else self.areas.names(),'sucursales':branches,'fechaServidor':now(),'zonaHoraria':'Ciudad de México (UTC-06:00)','maestro':{'archivo':master[0],'cargado':master[1],**master_report},'totalSolicitudes':count}
 def materials(self):
  with self.store.connect() as db:rows=db.execute('SELECT id,payload FROM req_materials ORDER BY id').fetchall()
  result=[{'id':id,**json.loads(payload)} for id,payload in rows];counts=collections.Counter(r['sku'] for r in result if r['sku'])
  for r in result:r['skuRepetido']=bool(r['sku'] and counts[r['sku']]>1)
  return result
 def import_master(self,data,actor):
  require_module(actor,'requisiciones');require_module(actor,'cargar_maestro')
  filename=text(data.get('archivo',''),200)
  try:raw=base64.b64decode(data.get('contenido',''),validate=True)
  except Exception:raise ValueError('Contenido del maestro inválido.')
  report=parse_master(raw,filename)
  if data.get('revisar',False):return {k:v for k,v in report.items() if k!='materiales'}
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');existing=[{'id':id,**json.loads(payload)} for id,payload in db.execute('SELECT id,payload FROM req_materials')];by_source={r['source_key']:r for r in existing};by_sku=collections.defaultdict(list);by_name=collections.defaultdict(list)
   for r in existing:
    if r['sku']:by_sku[norm(r['sku'])].append(r)
    by_name[(norm(r['nombre']),norm(r['proveedor']))].append(r)
   added=updated=skipped=0;seen=set();conflicts=[]
   for source in report['materiales']:
    candidates=[by_source[source['source_key']]] if source['source_key'] in by_source else by_sku.get(norm(source['sku']),[]) if source['sku'] else []
    if len(candidates)>1:candidates=[r for r in candidates if (norm(r['nombre']),norm(r['proveedor']))==(norm(source['nombre']),norm(source['proveedor']))]
    if not candidates:candidates=by_name.get((norm(source['nombre']),norm(source['proveedor'])),[])
    if len(candidates)>1:
     variants=[r for r in candidates if norm(r.get('claveProveedor',''))==norm(source.get('claveProveedor','')) and norm(r.get('unidadCompra',''))==norm(source.get('unidadCompra',''))]
     if len(variants)==1:candidates=variants
    if len(candidates)>1:
     matching=[r for r in candidates if norm(r['unidad'])==norm(source['unidad'])]
     if len(matching)==1:candidates=matching
    if len(candidates)==1 and candidates[0]['id'] in seen and source['sku'] and source['sku']!=candidates[0]['sku']:candidates=[]
    if len(candidates)>1 or candidates and candidates[0]['id'] in seen:
     skipped+=1;conflicts.append({'fila':source['fila'],'descripcion':source['nombre'],'motivo':'Coincidencia ambigua o fila repetida; identifica el producto con SKU.'});continue
    old=candidates[0] if candidates else None;item={**source}
    if old and not item['sku']:item['sku']=old['sku']
    if old:
     seen.add(old['id']);updated+=int(any(old.get(k)!=v for k,v in item.items()));db.execute('UPDATE req_materials SET source_key=?,payload=? WHERE id=?',(source['source_key'],json.dumps(item,ensure_ascii=False),old['id']));entry={'id':old['id'],**item}
    else:
     cursor=db.execute('INSERT INTO req_materials(source_key,payload) VALUES(?,?)',(source['source_key'],json.dumps(item,ensure_ascii=False)));added+=1;seen.add(cursor.lastrowid);entry={'id':cursor.lastrowid,**item}
    by_source[source['source_key']]=entry;by_name[(norm(item['nombre']),norm(item['proveedor']))]=[entry]
    if item['sku']:by_sku[norm(item['sku'])]=[entry]
   summary={k:v for k,v in report.items() if k!='materiales'};summary.update({'agregados':added,'actualizados':updated,'omitidos':skipped,'conflictos':conflicts,'conservados':report['total']-added-updated-skipped})
   db.execute('INSERT INTO req_masters(filename,created_at,actor,content,report) VALUES(?,?,?,?,?)',(filename,now(),actor['email'],base64.b64encode(raw).decode(),json.dumps(summary,ensure_ascii=False)))
  return summary
 def master_file(self):
  with self.store.connect() as db:name,content=db.execute('SELECT filename,content FROM req_masters ORDER BY id DESC LIMIT 1').fetchone()
  return name,base64.b64decode(content)
 def configure(self,data,actor):
  if actor['role'] not in ('superadmin','auxti','gerente'):raise PermissionError('Solo administración y Gerente pueden configurar series y folios.')
  branch=data.get('sucursal');series=text(data.get('serie',''),20).upper();number=data.get('siguiente');revision=data.get('revision')
  if branch not in BRANCHES or not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,19}',series) or type(number) is not int or not 1<=number<=999999999 or type(revision) is not int:raise ValueError('Sucursal, serie o siguiente folio inválidos.')
  if branch not in visible_branches(actor):raise PermissionError('No tienes acceso a esta sucursal.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT next_folio,revision FROM req_branches WHERE branch=?',(branch,)).fetchone()
   if old[1]!=revision:raise Conflict('La serie cambió o se emitió una solicitud. Actualiza antes de guardar.')
   if number<old[0]:raise ValueError('El folio siguiente no puede retroceder ni reutilizarse.')
   owner=db.execute('SELECT branch FROM req_series_registry WHERE series=?',(series,)).fetchone()
   if owner and owner[0]!=branch:raise ValueError('Esa serie pertenece a otra sucursal y está reservada.')
   db.execute('INSERT OR IGNORE INTO req_series_registry VALUES(?,?)',(series,branch));db.execute('UPDATE req_branches SET series=?,next_folio=?,revision=revision+1 WHERE branch=?',(series,number,branch))
  return self.metadata(actor)
 def create(self,data,actor):
  if actor['role'] in READ_ONLY_ROLES:raise PermissionError('Tu perfil solo permite consultar solicitudes.')
  allowed={'sucursal','area','solicitante','observaciones','partidas','claveCliente'}
  if set(data)-allowed:raise ValueError('Fecha, serie y folio son asignados por el servidor y no se pueden modificar.')
  branch=data.get('sucursal');area=data.get('area');requester=text(data.get('solicitante',''),160);notes=text(data.get('observaciones',''),2000);key=text(data.get('claveCliente',''),100);lines=data.get('partidas')
  if branch not in BRANCHES or area not in self.areas.names() or not requester or not re.fullmatch('[A-Za-z0-9_-]{16,100}',key) or not isinstance(lines,list) or not 1<=len(lines)<=200:raise ValueError('Selecciona sucursal, área, solicitante y entre 1 y 200 partidas.')
  if branch not in visible_branches(actor):raise PermissionError('No tienes acceso para solicitar materiales en esta sucursal.')
  canonical={'sucursal':branch,'area':area,'solicitante':requester,'observaciones':notes,'partidas':[]};seen=set()
  for line in lines:
   if not isinstance(line,dict) or set(line)-{'materialId','cantidad','observaciones'}:raise ValueError('Partida inválida; SKU y unidad provienen del maestro.')
   id=line.get('materialId');value=line.get('cantidad');line_notes=text(line.get('observaciones',''),500)
   if type(id) is not int or id<1 or id in seen or isinstance(value,bool) or not isinstance(value,(str,int,float)):raise ValueError('Material inválido o repetido en la solicitud.')
   try:q=decimal.Decimal(str(value))
   except decimal.InvalidOperation:raise ValueError('Cantidad inválida.')
   if not q.is_finite() or not 0<q<=999999999 or q.as_tuple().exponent < -6:raise ValueError('Usa cantidades positivas, con hasta 6 decimales y máximo 999999999.')
   seen.add(id);canonical['partidas'].append({'materialId':id,'cantidad':format(q,'f'),'observaciones':line_notes})
  fingerprint=hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');existing=db.execute('SELECT fingerprint,payload FROM req_documents WHERE creator=? AND client_key=?',(actor['email'],key)).fetchone()
   if existing:
    if existing[0]!=fingerprint:raise Conflict('La clave de envío ya corresponde a otra solicitud. Inicia una solicitud nueva.')
    document=json.loads(existing[1]);return {'documento':requester_document(document) if actor['role']=='requisicion' else document,'repetido':True}
   if area not in self.areas.names(db=db):raise Conflict('El área cambió mientras se preparaba la solicitud. Actualiza y selecciónala de nuevo.')
   ids=[line['materialId'] for line in canonical['partidas']]
   material_rows=dict(db.execute('SELECT id,payload FROM req_materials WHERE id IN ('+','.join('?' for _ in ids)+')',ids))
   snapshots=[]
   for line in canonical['partidas']:
    payload=material_rows.get(line['materialId'])
    if payload is None:raise ValueError('El material ya no está disponible en el maestro.')
    material=json.loads(payload)
    if material['estado']!='ACTIVO':raise ValueError('No se puede solicitar un producto inactivo: '+material['nombre'])
    if not material['unidad']:raise ValueError('El maestro no tiene unidad de entrega para '+material['nombre']+'. Carga el dato antes de solicitarlo.')
    snapshots.append({**line,**{k:material[k] for k in ('sku','nombre','unidad','proveedor')}})
   series,number=db.execute('SELECT series,next_folio FROM req_branches WHERE branch=?',(branch,)).fetchone()
   if number>999999999:raise ValueError('Se agotaron los folios de esta sucursal.')
   stamp=now();id=uuid.uuid4().hex;document={'id':id,'numero':series+'-'+str(number).zfill(6),'serie':series,'folio':number,'fecha':stamp[:10],'fechaHora':stamp,'sucursal':branch,'area':area,'solicitante':requester,'observaciones':notes,'creadoPor':actor['email'],'nombreUsuario':actor['name'],'estado':'SOLICITADA','partidas':snapshots}
   db.execute('INSERT INTO req_documents VALUES(?,?,?,?,?,?,?,?,?,?)',(id,actor['email'],key,fingerprint,branch,series,number,document['numero'],stamp,json.dumps(document,ensure_ascii=False)))
   db.execute('UPDATE req_branches SET next_folio=next_folio+1,revision=revision+1 WHERE branch=?',(branch,))
  return {'documento':document,'repetido':False}
 def list(self,branch='',page=1,actor=None):
  if branch and branch not in BRANCHES:raise ValueError('Sucursal inválida.')
  if not 1<=page<=100000:raise ValueError('Página inválida.')
  visible=visible_branches(actor)
  if branch and branch not in visible:raise PermissionError('No tienes acceso a esa sucursal o almacén.')
  where=' WHERE branch IN ('+','.join('?' for _ in visible)+')';params=tuple(visible)
  if branch:where+=' AND branch=?';params+=(branch,)
  if actor and actor['role']=='requisicion':where+=' AND creator=?';params+=(actor['email'],)
  with self.store.connect() as db:
   count=db.execute('SELECT COUNT(*) FROM req_documents'+where,params).fetchone()[0]
   rows=db.execute('SELECT d.payload FROM req_documents d JOIN (SELECT rowid AS rid FROM req_documents'+where+' ORDER BY created_at DESC,rowid DESC LIMIT 50 OFFSET ?) p ON d.rowid=p.rid ORDER BY d.created_at DESC,d.rowid DESC',(*params,(page-1)*50)).fetchall()
  docs=[json.loads(r[0]) for r in rows]
  if actor and actor['role']=='requisicion':docs=[requester_document(doc) for doc in docs]
  return {'solicitudes':[{k:v for k,v in d.items() if k!='partidas'}|{'totalPartidas':len(d['partidas'])} for d in docs],'total':count,'pagina':page,'tamano':50}
 def get(self,id,actor=None):
  with self.store.connect() as db:row=db.execute('SELECT payload,creator FROM req_documents WHERE id=?',(id,)).fetchone()
  document=json.loads(row[0]) if row else None
  own=not actor or actor['role']!='requisicion' or row and row[1]==actor['email']
  if not document or not own or document['sucursal'] not in visible_branches(actor):return None
  return requester_document(document) if actor and actor['role']=='requisicion' else document
def document_csv(doc):return csv_bytes([['FOLIO','FECHA SERVIDOR','SUCURSAL','AREA','SOLICITANTE','SKU','ID MATERIAL','DESCRIPCION','CANTIDAD SOLICITADA','CANTIDAD SURTIDA','UNIDAD','OBSERVACIONES','ESTADO','REVISION','MOTIVO CANCELACION'],*[ [doc['numero'],display_date(display_date(doc['fechaHora'])),doc['sucursal'],doc['area'],doc['solicitante'],r['sku'],r['materialId'],r['nombre'],r['cantidad'],r.get('cantidadSurtida','—'),r['unidad'],r['observaciones'],doc['estado'],doc.get('revision',1),doc.get('cancelacion',{}).get('motivo','')] for r in doc['partidas']]])
def print_document(doc,formato='actual'):
 if formato=='ticket':
  from ticket import print_ticket
  return print_ticket(doc)
 if formato!='actual':raise ValueError('Selecciona formato actual o ticket Bixolon.')
 from app_info import TITLE,VERSION,SUPPORT_LINE
 raw=_print_document_body(doc).decode('utf8');banner='<div style="font:11px Arial;margin-bottom:18px"><strong>'+html.escape(TITLE+' v'+VERSION)+'</strong><br>'+html.escape(SUPPORT_LINE)+'</div>'
 return raw.replace('<header>',banner+'<header>',1).encode('utf8')

def _print_document_body(doc):
 e=lambda x:html.escape(str(x));rows=''.join('<tr>'+''.join('<td>'+e(x)+'</td>' for x in (i+1,r['sku'] or 'SIN SKU / ID '+str(r['materialId']),r['nombre'],r['cantidad'],r.get('cantidadSurtida','—'),r['unidad'],r['observaciones']))+'</tr>' for i,r in enumerate(doc['partidas']))
 return ('<!doctype html><html lang="es"><meta charset="utf-8"><title>'+e(doc['numero'])+'</title><style>body{font:14px Arial;color:#222;margin:35px}header{display:flex;align-items:center;gap:22px;border-bottom:3px solid #284e42;padding-bottom:18px}img{width:85px}h1{font-size:23px}table{border-collapse:collapse;width:100%;margin:22px 0}td,th{padding:10px;border:1px solid #ddd;text-align:left;vertical-align:top}th{background:#f0efea}.meta{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:22px 0}.signatures{display:flex;justify-content:space-around;margin-top:80px}button{padding:12px;background:#284e42;color:white;border:0;margin-bottom:20px}@media print{button{display:none}body{margin:12mm}thead{display:table-header-group}tr{break-inside:avoid}header{break-inside:avoid}}</style><button onclick="window.print()">Imprimir / Guardar PDF</button><header><img src="/logo.png" alt="Grupo Mi Pan"><div><h1>Requisición de materiales</h1><strong>'+e(doc['numero'])+'</strong></div></header><div class="meta"><span><b>Sucursal:</b> '+e(doc['sucursal'])+'</span><span><b>Fecha del servidor:</b> '+e(display_date(doc['fechaHora']))+'</span><span><b>Área:</b> '+e(doc['area'])+'</span><span><b>Solicitante:</b> '+e(doc['solicitante'])+'</span><span><b>Capturó:</b> '+e(doc['nombreUsuario'])+' ('+e(doc['creadoPor'])+')</span><span><b>Estado:</b> '+e(doc['estado'])+'</span></div><table><thead><tr><th>#</th><th>SKU / referencia</th><th>Material solicitado</th><th>Solicitada</th><th>Surtida</th><th>Unidad</th><th>Observaciones</th></tr></thead><tbody>'+rows+'</tbody></table><p><b>Observaciones generales:</b> '+e(doc['observaciones'])+'</p><div class="signatures"><span>________________________<br>Solicita</span><span>________________________<br>Entrega</span><span>________________________<br>Recibe</span></div></html>').encode('utf8')

