"""Respaldo/restauración por módulo con revisión, detección de concurrencia y copia previa."""
import base64,copy,hashlib,hmac,json,pathlib,re,uuid,zipfile,io
from requisiciones import BRANCHES,AREAS,Conflict,now
from areas import default_catalog,validate_catalog
MODULES={'compras':'SKU Compras','ventas':'SKU Ventas','requisiciones':'Requisición de compras / materiales','comercial':'Pedidos institucionales y Expendios'}
TABLES=('req_materials','req_masters','req_branches','req_series_registry','req_documents','req_costs','req_reports','req_report_features','req_changes','req_document_versions','req_images','req_areas')
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def check(condition,message):
 if not condition:raise ValueError(message)
def workbook(master):
 try:
  raw=base64.b64decode(master,validate=True)
  check(len(raw)<=15*1024*1024,'El maestro supera 15 MB.')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:check('xl/workbook.xml' in z.namelist() and sum(i.file_size for i in z.infolist())<=100*1024*1024,'Maestro Excel inválido o demasiado grande.')
 except (TypeError,zipfile.BadZipFile):raise ValueError('Maestro Excel inválido.')

def blank_master(sheet):
 from xml.sax.saxutils import escape
 headers={'A':'CLAVE PROVEEDOR','B':'SKU','C':'STATUS DE COMPRA','D':'SKU NUEVO','E':'PRODUCTO','F':'CATEGORÍA','G':'SUBCATEGORÍA','H':'DESCRIPCIÓN','I':'PRECIO DE COMPRA','K':'COSTO','L':'U_M','M':'UM_COMPRA','N':'UM_ENTREGA','O':'PROVEEDOR PRINCIPAL'}
 if sheet=='SUGERIDO':headers={**headers,'A':'SKU','B':'PRODUCTOS Y SERVICIOS','C':'CATEGORÍA','D':'SUBCATEGORÍA','F':'MODULO ID PDV','S':'ESTADO'}
 ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="'+sheet+'" sheetId="1" r:id="rId1"/></sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
  row=''.join('<c r="'+col+'1" t="inlineStr"><is><t>'+escape(value)+'</t></is></c>' for col,value in headers.items());z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="'+ns+'"><sheetData><row r="1">'+row+'</row></sheetData></worksheet>')
 return base64.b64encode(out.getvalue()).decode()

class BackupStore:
 def __init__(self,store,validate_purchase,reports):self.store=store;self.validate_purchase=validate_purchase;self.reports=reports
 def authorize(self,actor,module):
  if actor['role'] not in ('superadmin','auxti'):raise PermissionError('Solo administración puede consultar respaldos.')
  if module not in MODULES:raise ValueError('Selecciona SKU Compras, SKU Ventas o Requisiciones.')
 def snapshot(self,db,module):
  if module in ('compras','ventas'):
   table='catalog' if module=='compras' else 'sales_catalog';revision,payload=db.execute('SELECT revision,payload FROM '+table+' WHERE id=1').fetchone();return {'revision':revision,'catalogo':json.loads(payload)}
  tables={}
  selected=TABLES
  if module=='comercial':
   from respaldo_comercial import TABLES as selected
  for table in selected:
   info=db.execute('PRAGMA table_info('+table+')').fetchall();columns=[r[1] for r in info];primary=[name for _,name in sorted((r[5],r[1]) for r in info if r[5])];order=','.join(primary) if primary else 'rowid'
   tables[table]={'columnas':columns,'filas':[list(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY '+order)]}
  return {'tablas':tables}
 def envelope(self,module,payload,actor):
  value={'formato':'GMP-RESPALDO','version':1,'modulo':module,'creado':now(),'creadoPor':actor['email'],'datos':payload};return {**value,'checksum':digest(value)}
 def create(self,module,actor):
  self.authorize(actor,module)
  with self.store.connect() as db:
   db.execute('BEGIN');return self.envelope(module,self.snapshot(db,module),actor)
 def unpack(self,module,backup):
  check(isinstance(backup,dict),'Archivo de respaldo inválido.')
  if backup.get('formato') is None and module in ('compras','ventas') and 'state' in backup and 'master' in backup:
   check(backup['state'].get('version')==(3 if module=='compras' else 1),'El respaldo antiguo pertenece a otro módulo.');return {'revision':backup.get('revision',0),'catalogo':{k:v for k,v in backup.items() if k not in ('revision','catalogos')}},True
  check(backup.get('formato')=='GMP-RESPALDO' and backup.get('version')==1,'Formato o versión de respaldo no compatibles.')
  check(backup.get('modulo')==module,'El archivo pertenece a otro módulo; cambia la selección.')
  expected=backup.get('checksum');check(isinstance(expected,str) and hmac.compare_digest(expected,digest({k:v for k,v in backup.items() if k!='checksum'})),'El archivo está incompleto o su comprobación de integridad no coincide.')
  check(isinstance(backup.get('datos'),dict),'Faltan los datos del respaldo.');return copy.deepcopy(backup['datos']),False
 def validate(self,db,module,data):
  if module=='comercial':
   from respaldo_comercial import validate
   return validate(db,data)
  if module in ('compras','ventas'):
   catalog=data.get('catalogo');check(isinstance(catalog,dict),'Falta el catálogo del respaldo.')
   if module=='compras':self.validate_purchase(catalog,self.store.catalogs)
   else:
    from ventas import validate
    validate(catalog)
   workbook(catalog['master']);return
  tables=data.get('tablas')
  if isinstance(tables,dict) and 'req_images' not in tables:tables['req_images']={'columnas':['material_id','image_id','payload','contenido'],'filas':[]}
  if isinstance(tables,dict) and 'req_areas' not in tables:tables['req_areas']={'columnas':['id','revision','payload'],'filas':[[1,1,json.dumps(default_catalog(AREAS),ensure_ascii=False)]]}
  check(isinstance(tables,dict) and set(tables)==set(TABLES),'El respaldo de requisiciones debe incluir maestro, solicitudes, series, costos, reportes y autorizaciones.')
  unpacked={}
  for table in TABLES:
   value=tables[table];columns=[r[1] for r in db.execute('PRAGMA table_info('+table+')')];check(isinstance(value,dict) and value.get('columnas')==columns and isinstance(value.get('filas'),list),'Estructura incompatible: '+table)
   rows=value['filas'];check(len(rows)<=200000,'El respaldo excede el límite de registros por tabla.')
   check(all(isinstance(row,list) and len(row)==len(columns) and all(v is None or type(v) in (str,int,float) for v in row) for row in rows),'Filas inválidas: '+table)
   info=db.execute('PRAGMA table_info('+table+')').fetchall();unique_keys=[[r[1] for r in sorted(info,key=lambda r:r[5]) if r[5]]]
   for index in db.execute('PRAGMA index_list('+table+')'):
    if index[2]:unique_keys.append([r[2] for r in db.execute('PRAGMA index_info('+index[1]+')')])
   for keys in unique_keys:
    if not keys or None in keys:continue
    positions=[columns.index(key) for key in keys];seen_keys=set()
    for row in rows:
     value=tuple(row[p] for p in positions)
     if None in value:continue
     check(value not in seen_keys,'Identificadores o claves repetidas en '+table+'.');seen_keys.add(value)
   unpacked[table]=[dict(zip(columns,row)) for row in rows]
  area_rows=unpacked['req_areas'];check(len(area_rows)==1 and area_rows[0]['id']==1 and type(area_rows[0]['revision']) is int and area_rows[0]['revision']>=1,'Falta un catálogo de áreas válido.');area_names=validate_catalog(json.loads(area_rows[0]['payload']))
  materials={}
  for row in unpacked['req_materials']:
   item=json.loads(row['payload']);check(type(row['id']) is int and row['id']>0 and row['id'] not in materials and item.get('source_key')==row['source_key'] and isinstance(item.get('nombre'),str) and isinstance(item.get('sku'),str) and isinstance(item.get('unidad'),str) and isinstance(item.get('proveedor'),str) and item.get('estado') in ('ACTIVO','INACTIVO'),'Material inválido o repetido.');materials[row['id']]=item
  from imagenes import validate_png
  for row in unpacked['req_images']:
   image=json.loads(row['payload']);check(row['material_id'] in materials and bool(re.fullmatch('[a-f0-9]{32}',row['image_id'])) and isinstance(image,dict),'Imagen sin material o identificador válido.')
   raw=base64.b64decode(row.get('contenido',''),validate=True);width,height=validate_png(raw,image.get('archivo',''))
   check(image.get('ancho')==width and image.get('alto')==height and image.get('bytes')==len(raw) and all(isinstance(image.get(k),str) for k in ('skuAlCargar','actualizado','cargadoPor')),'Metadatos de imagen inválidos.')
  branches=unpacked['req_branches'];check({r['branch'] for r in branches}==set(BRANCHES) and len(branches)==len(BRANCHES),'Deben existir las cuatro sucursales.')
  for row in branches:check(re.fullmatch('[A-Z0-9][A-Z0-9-]{1,19}',row['series']) and type(row['next_folio']) is int and 1<=row['next_folio']<=1000000000 and type(row['revision']) is int and row['revision']>=1,'Serie o folio inválido.')
  registry={}
  for row in unpacked['req_series_registry']:
   check(row['branch'] in BRANCHES and re.fullmatch('[A-Z0-9][A-Z0-9-]{1,19}',row['series']) and row['series'] not in registry,'Registro de series inválido.');registry[row['series']]=row['branch']
  for row in branches:check(registry.get(row['series'])==row['branch'],'La serie no pertenece a su sucursal.')
  def document(doc):
   check(isinstance(doc,dict) and re.fullmatch('[a-f0-9]{32}',doc.get('id','')) and doc.get('sucursal') in BRANCHES and doc.get('area') in area_names and doc.get('estado') in ('SOLICITADA','APROBADA','SURTIDA','SURTIDO','CANCELADA') and type(doc.get('folio')) is int and doc['folio']>=1 and doc.get('numero')==doc.get('serie','')+'-'+str(doc['folio']).zfill(6),'Requisición inválida.')
   check(isinstance(doc.get('fechaHora'),str) and doc.get('fecha')==doc['fechaHora'][:10] and isinstance(doc.get('solicitante'),str) and isinstance(doc.get('observaciones'),str),'Fecha o texto de requisición inválido.')
   lines=doc.get('partidas');check(isinstance(lines,list) and 1<=len(lines)<=200,'Partidas inválidas.');seen=set()
   from reportes import dec
   for line in lines:
    check(isinstance(line,dict) and type(line.get('materialId')) is int and line['materialId'] in materials and line['materialId'] not in seen and all(isinstance(line.get(k),str) for k in ('sku','nombre','unidad','proveedor','observaciones')),'Referencia de material inválida.');dec(line.get('cantidad'),True);seen.add(line['materialId'])
    if 'cantidadSurtida' in line:check(0<=dec(line['cantidadSurtida'])<=dec(line['cantidad']),'Cantidad surtida inválida.')
    if doc['estado'] in ('SURTIDA','SURTIDO'):check('cantidadSurtida' in line,'Falta cantidad surtida.')
  docs={}
  for row in unpacked['req_documents']:
   doc=json.loads(row['payload']);document(doc);check(row['id']==doc['id'] and row['branch']==doc['sucursal'] and row['series']==doc['serie'] and row['folio']==doc['folio'] and row['number']==doc['numero'] and row['created_at']==doc['fechaHora'] and row['id'] not in docs,'El índice de solicitudes no coincide con los documentos.');check(registry.get(doc['serie'])==doc['sucursal'],'Serie histórica de otra sucursal.');docs[doc['id']]=doc
  for row in unpacked['req_document_versions']:doc=json.loads(row['payload']);document(doc);check(row['document_id'] in docs and doc['id']==row['document_id'] and type(row['revision']) is int and row['revision']>=1,'Historial de revisiones inválido.')
  from reportes import dec
  for row in unpacked['req_costs']:
   c=json.loads(row['payload']);check(row['material_id'] in materials and type(row['revision']) is int and row['revision']>=1 and all(isinstance(c.get(k),str) for k in ('unidadCompra','unidadSolicitud','motivo','origen','actualizado')),'Costo sin material o estructura válida.')
   if c.get('precioCompra') not in ('',None):dec(c['precioCompra'])
   if c.get('costoEntrega') not in ('',None):dec(c['costoEntrega'])
   if c.get('factor') is not None:dec(c['factor'])
  for row in unpacked['req_reports']:
   c=json.loads(row['payload']);check(c.get('id')==row['id'] and re.fullmatch('[A-Za-z0-9_-]{1,64}',row['id']) and type(row['revision']) is int and row['revision']>=1,'Reporte inválido.');self.reports.config(c,area_names=area_names)
  for row in unpacked['req_changes']:
   c=json.loads(row['payload']);check(c.get('objetivo') in docs and c.get('id')==row['id'] and c.get('sucursal')==row['branch'] and c.get('solicitadoPor')==row['requester'] and c.get('estado')==row['status'] and c.get('estado') in ('PENDIENTE','APROBADA','RECHAZADA') and c.get('tipo') in ('cancelar','modificar','aprobar','surtir','corregir_surtido') and type(c.get('revision')) is int,'Autorización inválida.')
   if c['tipo']=='modificar':
    values=c.get('datos');check(isinstance(values,dict) and set(values)=={'area','solicitante','observaciones','partidas'},'Campos de corrección inválidos.');document({**docs[c['objetivo']],**values})
   if c['tipo'] in ('surtir','corregir_surtido'):
    values=c.get('datos');check(isinstance(values,dict) and not set(values)-{'partidas','area','solicitante','observaciones','almacenInventario'} and isinstance(values.get('partidas'),list),'Datos de surtido inválidos.')
    if values.get('almacenInventario') is not None:check(isinstance(values['almacenInventario'],str) and len(values['almacenInventario'])<100,'Almacén de surtido inválido.')
    base=docs[c['objetivo']];parts={p['materialId']:p for p in base['partidas']};seen=set()
    for line in values['partidas']:
     check(isinstance(line,dict) and set(line)=={'materialId','cantidadSurtida'} and type(line['materialId']) is int and line['materialId'] in parts and line['materialId'] not in seen,'Partidas de surtido inválidas.');seen.add(line['materialId']);check(0<=dec(line['cantidadSurtida'])<=dec(parts[line['materialId']]['cantidad']),'Cantidad surtida inválida.')
    check(seen==set(parts),'Faltan partidas de surtido.')
    if 'area' in values:check(values['area'] in area_names,'Área de surtido inválida.')
    if 'solicitante' in values:check(isinstance(values['solicitante'],str) and bool(values['solicitante'].strip()),'Solicitante de surtido inválido.')
    if 'observaciones' in values:check(isinstance(values['observaciones'],str),'Observaciones de surtido inválidas.')
  check(bool(unpacked['req_masters']),'Falta el maestro de materiales.')
  for row in unpacked['req_masters']:check(isinstance(row['filename'],str) and row['filename'].lower().endswith(('.xlsx','.csv','.tsv','.txt')),'Archivo de maestro inválido.');base64.b64decode(row['content'],validate=True);json.loads(row['report'])
 def summary(self,module,data):
  if module=='comercial':
   from respaldo_comercial import summary
   return summary(data)
  if module in ('compras','ventas'):
   state=data['catalogo']['state'];return {'articulos':len(state['registros']),'activos':sum(not r['eliminado'] for r in state['registros']),'consecutivo':state['maxId'],'skuReservados':len(state['reservados'])}
  tables=data['tablas'];return {'materiales':len(tables['req_materials']['filas']),'requisiciones':len(tables['req_documents']['filas']),'reportes':len(tables['req_reports']['filas']),'autorizaciones':len(tables['req_changes']['filas']),'versionesHistoricas':len(tables['req_document_versions']['filas']),'imagenes':len(tables['req_images']['filas']),'areas':len(json.loads(tables['req_areas']['filas'][0][2])['areas'])}
 def review(self,data,actor,apply=False):
  if apply and actor['role']!='superadmin':raise PermissionError('AUXTI necesita aprobación de sistemas para reemplazar o vaciar datos.')
  module=data.get('modulo');self.authorize(actor,module);incoming,legacy=self.unpack(module,data.get('respaldo'))
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE' if apply else 'BEGIN');current=self.snapshot(db,module);current_hash=digest(current);self.validate(db,module,incoming)
   result={'modulo':module,'nombre':MODULES[module],'actual':self.summary(module,current),'respaldo':self.summary(module,incoming),'huellaActual':current_hash,'legado':legacy,'nota':'Se reemplaza únicamente el módulo elegido. Se conservan los máximos de folios e identificadores para evitar reutilizarlos.'}
   if not apply:return result
   if module in ('requisiciones','comercial') and db.execute("SELECT 1 FROM sqlite_master WHERE name='inv_ledger'").fetchone() and db.execute('SELECT 1 FROM inv_ledger LIMIT 1').fetchone():raise Conflict('Existen movimientos de inventario integrados. Conserva el historial y recupera una copia completa de data para no desajustar las existencias.')
   check(data.get('confirmar') is True,'Confirma que deseas reemplazar los datos del módulo seleccionado.')
   if data.get('huellaActual')!=current_hash:raise Conflict('El módulo cambió después de la revisión. Revisa el respaldo otra vez antes de restaurar.')
   backup_id=uuid.uuid4().hex;directory=self.store.directory/'respaldos';directory.mkdir(exist_ok=True);previous=self.envelope(module,current,actor);target=directory/('antes-'+backup_id+'.json');target.write_text(json.dumps(previous,ensure_ascii=False),encoding='utf8')
   if module in ('compras','ventas'):
    table='catalog' if module=='compras' else 'sales_catalog';history='history' if module=='compras' else 'sales_history';catalog=incoming['catalogo'];state=catalog['state'];current_state=current['catalogo']['state'];state['maxId']=max(state['maxId'],current_state['maxId']);active={r['sku'] for r in state['registros'] if not r['eliminado'] and r.get('sku')};known=set(current_state['reservados'])|{r['sku'] for r in current_state['registros'] if r.get('sku')};state['reservados']=sorted((set(state['reservados'])|known)-active)
    if module=='compras':self.validate_purchase(catalog,self.store.catalogs)
    else:
     from ventas import validate
     validate(catalog)
    db.execute('INSERT INTO '+history+' VALUES(?,?,?)',(current['revision'],now(),json.dumps(current['catalogo'],ensure_ascii=False)));db.execute('UPDATE '+table+' SET revision=?,payload=? WHERE id=1',(current['revision']+1,json.dumps(catalog,ensure_ascii=False)))
   elif module=='comercial':
    from respaldo_comercial import restore
    restore(db,incoming,current)
   else:
    old_branches={r[0]:(r[2],r[3]) for r in current['tablas']['req_branches']['filas']};old_registry=dict(db.execute('SELECT series,branch FROM req_series_registry'))
    for table in reversed(TABLES):db.execute('DELETE FROM '+table)
    for table in TABLES:
     t=incoming['tablas'][table];columns=t['columnas'];db.executemany('INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',t['filas'])
    db.execute("UPDATE req_documents SET payload=json_set(payload,'$.estado','SURTIDO') WHERE json_extract(payload,'$.estado')='SURTIDA'")
    db.execute('UPDATE req_areas SET revision=MAX(revision,?)+1 WHERE id=1',(current['tablas']['req_areas']['filas'][0][1],))
    for branch,(floor,rev) in old_branches.items():db.execute('UPDATE req_branches SET next_folio=MAX(next_folio,?),revision=MAX(revision,?)+1 WHERE branch=?',(floor,rev,branch))
    for branch in BRANCHES:
     floor=db.execute('SELECT COALESCE(MAX(folio),0)+1 FROM req_documents WHERE branch=?',(branch,)).fetchone()[0];db.execute('UPDATE req_branches SET next_folio=MAX(next_folio,?) WHERE branch=?',(floor,branch))
    for series,branch in old_registry.items():
     restored=db.execute('SELECT branch FROM req_series_registry WHERE series=?',(series,)).fetchone()
     check(not restored or restored[0]==branch,'La serie histórica pertenece a otra sucursal; no se puede restaurar.');db.execute('INSERT OR IGNORE INTO req_series_registry VALUES(?,?)',(series,branch))
   result.update({'ok':True,'respaldoPrevio':backup_id})
  return result
 def previous(self,id,actor):
  self.authorize(actor,'compras');check(bool(re.fullmatch('[a-f0-9]{32}',id)),'Identificador inválido.');path=self.store.directory/'respaldos'/('antes-'+id+'.json');check(path.is_file(),'No se encuentra la copia de seguridad previa.');return path.read_bytes()
 def reset(self,data,actor,apply=False):
  if data.get('modulo')=='comercial':raise ValueError('Las ventas y movimientos comerciales no se vacían. Usa respaldos y restauración para recuperar una instalación, conservando el historial.')
  if apply and actor['role']!='superadmin':raise PermissionError('AUXTI necesita aprobación de sistemas para vaciar datos.')
  module=data.get('modulo');self.authorize(actor,module)
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE' if apply else 'BEGIN');current=self.snapshot(db,module);fingerprint=digest(current);result={'modulo':module,'nombre':MODULES[module],'actual':self.summary(module,current),'huellaActual':fingerprint,'nota':'Se vacían los datos del módulo elegido. Usuarios, otros módulos y máximos de consecutivos/folios se conservan. Se crea una copia automática antes de vaciar.'}
   if not apply:return result
   if module in ('requisiciones','comercial') and db.execute("SELECT 1 FROM sqlite_master WHERE name='inv_ledger'").fetchone() and db.execute('SELECT 1 FROM inv_ledger LIMIT 1').fetchone():raise Conflict('Existen movimientos de inventario integrados. Conserva el historial y recupera una copia completa de data para no desajustar las existencias.')
   check(data.get('confirmar') is True and data.get('texto')=='VACIAR','Escribe VACIAR para confirmar el reinicio del módulo.')
   if data.get('huellaActual')!=fingerprint:raise Conflict('El módulo cambió; vuelve a revisar antes de vaciar.')
   id=uuid.uuid4().hex;folder=self.store.directory/'respaldos';folder.mkdir(exist_ok=True);(folder/('antes-'+id+'.json')).write_text(json.dumps(self.envelope(module,current,actor),ensure_ascii=False),encoding='utf8')
   if module in ('compras','ventas'):
    table='catalog' if module=='compras' else 'sales_catalog';history='history' if module=='compras' else 'sales_history';catalog=current['catalogo'];old=json.dumps(catalog,ensure_ascii=False);state=catalog['state'];state['reservados']=sorted(set(state['reservados'])|{r['sku'] for r in state['registros'] if r.get('sku')});state['registros']=[];catalog['master']=blank_master('PRODUCTOS' if module=='compras' else 'SUGERIDO')
    if module=='compras':catalog.update({'formatoMaestro':'PRODUCTOS','archivoMaestro':'CATALOGO VACIO.xlsx'})
    else:
     from ventas import row_identity
     catalog['sheet']='SUGERIDO';catalog['historicosReinicio']={**catalog.get('historicosReinicio',{}),**{r['sku']:list(row_identity(r)) for r in json.loads(old)['state']['registros'] if r.get('validado') and not r['eliminado']}}
    db.execute('INSERT INTO '+history+' VALUES(?,?,?)',(current['revision'],now(),old));db.execute('UPDATE '+table+' SET revision=?,payload=? WHERE id=1',(current['revision']+1,json.dumps(catalog,ensure_ascii=False)))
   else:
    for table in TABLES:
     if table not in ('req_branches','req_series_registry','req_areas'):db.execute('DELETE FROM '+table)
    db.execute('UPDATE req_branches SET revision=revision+1')
    report={'archivo':'PRODUCTOS VACIO.xlsx','hoja':'PRODUCTOS','total':0,'sinSku':0,'sinUnidad':0,'skuRepetidos':0,'inactivos':0};db.execute('INSERT INTO req_masters(filename,created_at,actor,content,report) VALUES(?,?,?,?,?)',(report['archivo'],now(),actor['email'],blank_master('PRODUCTOS'),json.dumps(report)))
    config=self.reports.config({'nombre':'Reporte general de requisiciones'});config.update({'id':'general','editor':actor['email'],'actualizado':now()});db.execute('INSERT INTO req_reports VALUES(?,1,?)',('general',json.dumps(config,ensure_ascii=False)))
    for key in ('costos-compra-v1','um-entrega-prioridad-v2','costos-um-entrega-v2','costos-um-entrega-v3-costo'):db.execute('INSERT INTO req_report_features VALUES(?)',(key,))
   result.update({'ok':True,'respaldoPrevio':id})
  return result

