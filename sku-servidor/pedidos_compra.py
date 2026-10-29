"""GMP ERP: compras, recepción y registro de compra con trazabilidad de requisiciones."""
import base64,copy,json,re,threading,uuid
from decimal import Decimal,ROUND_HALF_UP
from comercial import ADMINS,dumps,fingerprint,money,tax_name
from fechas import iso_date
from permissions import require_module
from requisiciones import BRANCHES,Conflict,now,text,parse_master
from reportes import infer_factor,dec,unit,dimension
from productos_comerciales import optional_price

CAPTURERS={'compras','gerente','superadmin','auxti','almacenista'}
SERIES_EDITORS={'compras','gerente'}|ADMINS
RECEIVERS=SERIES_EDITORS|{'almacenista'}
STATES=('BORRADOR','ENVIADO','PEDIDO','RECEPCION_PARCIAL','RECIBIDO','COMPRADO','CANCELADO')
TABLES=('po_vendors','po_templates','po_sequences','po_series_registry','po_numbers','po_orders','po_moves','po_access','po_audit','po_mail')

def number(v,positive=False):
 q=dec(v,positive)
 if q>Decimal('999999999') or q.as_tuple().exponent < -6:raise ValueError('Máximo 999999999 y seis decimales.')
 return q

def rate(v):
 if v is None or str(v).strip()=='':return None
 s=str(v).strip().replace('%','').replace(',','.');n=Decimal(s)
 if n in (Decimal('.08'),Decimal('.16')):n*=100
 if n not in (0,8,16):raise ValueError('Impuesto: 0% sin IVA, 8% IEPS o 16% IVA.')
 return str(int(n))

def delivery_in(quantity,source,target):
 if unit(source)==unit(target):return quantity
 a=dimension(source);b=dimension(target)
 if not a or not b or a[0]!=b[0]:raise ValueError('Cambió la unidad de entrega y falta una equivalencia con la requisición original.')
 return quantity*a[1]/b[1]

def email(v):
 value=text(v or '',200)
 if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):raise ValueError('Correo inválido.')
 return value

class PurchaseStore:
 def __init__(self,store,cm,requisitions,reports):
  self.store=store;self.cm=cm;self.req=requisitions;self.reports=reports;self.cache=None;self.lock=threading.Lock()
  with store.connect() as db:
   db.executescript('''
   CREATE TABLE IF NOT EXISTS po_vendors(id TEXT PRIMARY KEY,company INTEGER NOT NULL,code TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,UNIQUE(company,code));
   CREATE TABLE IF NOT EXISTS po_templates(id TEXT PRIMARY KEY,company INTEGER NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS po_sequences(company INTEGER NOT NULL,branch TEXT NOT NULL,kind TEXT NOT NULL,series TEXT NOT NULL,next INTEGER NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(company,branch,kind));
   CREATE TABLE IF NOT EXISTS po_series_registry(company INTEGER NOT NULL,series TEXT NOT NULL,branch TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(company,series));
   CREATE TABLE IF NOT EXISTS po_numbers(company INTEGER NOT NULL,series TEXT NOT NULL,number INTEGER NOT NULL,document TEXT NOT NULL,PRIMARY KEY(company,series,number));
   CREATE TABLE IF NOT EXISTS po_orders(id TEXT PRIMARY KEY,company INTEGER NOT NULL,branch TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL,creator TEXT NOT NULL,client_key TEXT NOT NULL UNIQUE,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS po_moves(id TEXT PRIMARY KEY,order_id TEXT NOT NULL,kind TEXT NOT NULL,client_key TEXT NOT NULL UNIQUE,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS po_access(email TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS po_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,created TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS po_settings(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL);
   INSERT OR IGNORE INTO po_settings VALUES(1,1,'{}');
   CREATE TABLE IF NOT EXISTS po_mail(id TEXT PRIMARY KEY,order_id TEXT NOT NULL,client_key TEXT NOT NULL UNIQUE,state TEXT NOT NULL,payload TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS po_features(key TEXT PRIMARY KEY);
   ''')
   if not db.execute("SELECT 1 FROM po_features WHERE key='almacen-captura-v301'").fetchone():
    row=db.execute("SELECT modules FROM role_modules WHERE role='almacenista'").fetchone()
    if row:db.execute("UPDATE role_modules SET modules=?,revision=revision+1 WHERE role='almacenista'",(dumps(list(dict.fromkeys(json.loads(row[0])+['pedidoscompra']))),))
    db.execute("INSERT INTO po_features VALUES('almacen-captura-v301')")
   if not db.execute("SELECT 1 FROM po_features WHERE key='institucional-managers-v3'").fetchone():
    for role in ('gerente','auxti'):
     row=db.execute('SELECT modules FROM role_modules WHERE role=?',(role,)).fetchone()
     if row:db.execute('UPDATE role_modules SET modules=?,revision=revision+1 WHERE role=?',(dumps(list(dict.fromkeys(json.loads(row[0])+['ventasins']))),role))
    db.execute("INSERT INTO po_features VALUES('institucional-managers-v3')")
   if not db.execute("SELECT 1 FROM po_features WHERE key='compras-v3'").fetchone():
    for role in ('superadmin','auxti','gerente','compras'):
     r=db.execute('SELECT modules FROM role_modules WHERE role=?',(role,)).fetchone()
     if r:db.execute('UPDATE role_modules SET modules=?,revision=revision+1 WHERE role=?',(dumps(list(dict.fromkeys(json.loads(r[0])+['pedidoscompra']))),role))
    db.execute("INSERT INTO po_features VALUES('compras-v3')")
 def audit(self,db,actor,action,data):db.execute('INSERT INTO po_audit(created,actor,action,payload) VALUES(?,?,?,?)',(now(),actor['email'],action,dumps(data)))
 def access(self,actor,db=None):
  if db is None:
   with self.store.connect() as conn:return self.access(actor,conn)
  r=db.execute('SELECT revision,payload FROM po_access WHERE email=?',(actor['email'],)).fetchone()
  return {'revision':r[0] if r else 0,**(json.loads(r[1]) if r else {'empresas':[],'sucursales':[]})}
 def scope(self,actor,company=None,branch=None,capture=False,receive=False,db=None):
  require_module(actor,'pedidoscompra')
  if capture and actor['role'] not in CAPTURERS:raise PermissionError('Solo Compras, Gerencia, Superadministrador, AUXTI y Almacenista pueden capturar, confirmar y registrar compras.')
  if receive and actor['role'] not in RECEIVERS:raise PermissionError('Este perfil no puede recibir compras.')
  access=self.access(actor,db)
  if company is not None:
   if type(company) is not int:raise ValueError('Selecciona razón social.')
   if actor['role'] not in ADMINS and company not in access['empresas']:raise PermissionError('Razón social no asignada para Compras.')
   if db is None:
    with self.store.connect() as conn:row=conn.execute('SELECT payload FROM cm_companies WHERE id=?',(company,)).fetchone()
   else:row=db.execute('SELECT payload FROM cm_companies WHERE id=?',(company,)).fetchone()
   if not row:raise ValueError('Razón social inexistente.')
   co=json.loads(row[0])
   if branch is not None:
    if branch not in co['sucursales'] or actor['role'] not in ADMINS and branch not in access['sucursales']:raise PermissionError('Sucursal no vinculada o no asignada.')
   return {'id':company,**co}
  return access
 def metadata(self,actor):
  self.scope(actor);access=self.access(actor)
  with self.store.connect() as db:companies=[{'id':i,'revision':r,**json.loads(p)} for i,r,p in db.execute('SELECT id,revision,payload FROM cm_companies') if actor['role'] in ADMINS or i in access['empresas']]
  return {'empresas':companies,'sucursales':list(BRANCHES) if actor['role'] in ADMINS else access['sucursales'],'estados':list(STATES),'puedePlantillas':actor['role'] in ADMINS|{'gerente'},'puedeCapturar':actor['role'] in CAPTURERS,'puedeRecibir':actor['role'] in RECEIVERS,'puedeSeries':actor['role'] in SERIES_EDITORS,'puedeAdministrar':actor['role'] in ADMINS,'acceso':access}
 def save_access(self,data,actor):
  self.scope(actor)
  if actor['role'] not in ADMINS:raise PermissionError('Solo Sistemas y AUXTI asignan accesos de Compras.')
  who=email(data.get('email'));companies=data.get('empresas',[]);branches=data.get('sucursales',[])
  if not isinstance(companies,list) or not isinstance(branches,list) or any(type(i) is not int for i in companies) or set(branches)-set(BRANCHES):raise ValueError('Alcance inválido.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if not db.execute('SELECT 1 FROM users WHERE email=? AND active=1',(who,)).fetchone():raise ValueError('Usuario no disponible.')
   if any(not db.execute('SELECT 1 FROM cm_companies WHERE id=?',(i,)).fetchone() for i in companies):raise ValueError('Razón social inexistente.')
   old=self.access({'email':who},db)
   if old['revision']!=data.get('revision',0):raise Conflict('Cambió el acceso. Actualiza.')
   db.execute('INSERT INTO po_access VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(who,old['revision']+1,dumps({'empresas':sorted(set(companies)),'sucursales':sorted(set(branches))})));self.audit(db,actor,'acceso',{'email':who})
  return {'ok':True}
 def access_list(self,actor):
  self.scope(actor)
  if actor['role'] not in ADMINS:raise PermissionError('Solo administración.')
  with self.store.connect() as db:return {'usuarios':[{'email':e,'nombre':n,'perfil':r,**self.access({'email':e},db)} for e,n,r in db.execute('SELECT email,name,role FROM users WHERE active=1 ORDER BY email')]}
 def vendors(self,company,actor):
  self.scope(actor,company)
  with self.store.connect() as db:return {'proveedores':[{'id':i,'codigo':c,'revision':r,**json.loads(p)} for i,c,r,p in db.execute('SELECT id,code,revision,payload FROM po_vendors WHERE company=? ORDER BY code',(company,))]}
 def save_vendor(self,data,actor,db=None):
  company=data.get('empresa');self.scope(actor,company)
  if actor['role'] not in SERIES_EDITORS:raise PermissionError('No puedes editar proveedores.')
  if db is None:
   with self.store.connect() as conn:
    conn.execute('BEGIN IMMEDIATE');return self.save_vendor(data,actor,conn)
  name=text(data.get('nombre',''),300)
  if not name:raise ValueError('Nombre del proveedor obligatorio.')
  id=data.get('id') or uuid.uuid4().hex;old=db.execute('SELECT company,code,revision FROM po_vendors WHERE id=?',(id,)).fetchone()
  if old and old[0]!=company:raise PermissionError('Proveedor de otra razón social.')
  if data.get('revision',0)!=(old[2] if old else 0):raise Conflict('El proveedor cambió.')
  rfc=text(data.get('rfc',''),20).upper()
  if rfc and db.execute('SELECT 1 FROM po_vendors WHERE company=? AND id<>? AND json_extract(payload,\'$.rfc\')=?',(company,id,rfc)).fetchone():raise ValueError('El RFC del proveedor ya está registrado.')
  code=old[1] if old else 'PRO'+str(company).zfill(2)+'-'+str(1+max([int(r[0].split('-')[-1]) for r in db.execute('SELECT code FROM po_vendors WHERE company=?',(company,)) if re.fullmatch(r'PRO[0-9]+-[0-9]+',r[0])]+[0])).zfill(6)
  value={'nombre':name,'rfc':rfc,'correo':email(data.get('correo','')),'telefono':text(data.get('telefono',''),100),'contacto':text(data.get('contacto',''),200),'domicilio':text(data.get('domicilio',''),1000),'referencia':text(data.get('referencia',''),300),'condiciones':text(data.get('condiciones',''),20000),'activo':data.get('activo',True) is True}
  db.execute('INSERT INTO po_vendors VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(id,company,code,(old[2] if old else 0)+1,dumps(value)));self.audit(db,actor,'proveedor_guardado',{'id':id,'codigo':code});return {'ok':True,'id':id,'codigo':code}
 def materials(self,actor):
  self.scope(actor)
  with self.store.connect() as db:
   stamp=(fingerprint([list(r) for r in db.execute('SELECT id,payload FROM req_materials ORDER BY id')]),db.execute('SELECT MAX(id) FROM req_masters').fetchone(),db.execute('SELECT COALESCE(SUM(revision),0) FROM req_costs').fetchone())
   if self.cache and self.cache[0]==stamp:return {'materiales':copy.deepcopy(self.cache[1])}
   rows=[{'id':i,**json.loads(p)} for i,p in db.execute('SELECT id,payload FROM req_materials')];latest=db.execute('SELECT filename,content FROM req_masters ORDER BY id DESC LIMIT 1').fetchone();taxes={}
   if latest:
    try:taxes={r['source_key']:r.get('impuestoCompra') for r in parse_master(base64.b64decode(latest[1]),latest[0])['materiales']}
    except ValueError:pass
   costs={i:json.loads(p) for i,p in db.execute('SELECT material_id,payload FROM req_costs')}
  result=[]
  for r in rows:
   c=costs.get(r['id'],{});factor=c.get('factor') or infer_factor(r)[0]
   try:tax=rate(r.get('impuestoCompra') or taxes.get(r.get('source_key')))
   except (ValueError,ArithmeticError):tax=None
   result.append({'materialId':r['id'],'sku':r.get('sku',''),'nombre':r['nombre'],'activo':r.get('estado')!='INACTIVO','unidadCompra':r.get('unidadCompra') or c.get('unidadCompra') or r['unidad'],'unidadEntrega':r['unidad'],'factor':factor,'precioCompra':c.get('precioCompra') or r.get('precioCompra') or None,'costoEntrega':c.get('costoEntrega') or r.get('costoBaseMaestro') or None,'impuesto':tax,'proveedor':r.get('proveedor','')})
  self.cache=(stamp,result);return {'materiales':copy.deepcopy(result)}
 def sequence(self,db,company,branch,kind):
  if kind not in ('COTIZACION','PEDIDO','RECEPCION','COMPRA'):raise ValueError('Tipo de serie inválido.')
  defaults={'COTIZACION':'SC','PEDIDO':'OC','RECEPCION':'REC','COMPRA':'CMP'};suffix={'EJIDOS':'EJI','SAN PABLO':'SP','CUAUTITLAN':'CUA','EJE 8':'E8'}[branch]
  db.execute('INSERT OR IGNORE INTO po_sequences VALUES(?,?,?,?,1,1)',(company,branch,kind,defaults[kind]+'-'+str(company).zfill(2)+'-'+suffix));db.execute('INSERT OR IGNORE INTO po_series_registry SELECT company,series,branch,kind FROM po_sequences');row=db.execute('SELECT series,next,revision FROM po_sequences WHERE company=? AND branch=? AND kind=?',(company,branch,kind)).fetchone();used=db.execute('SELECT MAX(number) FROM po_numbers WHERE company=? AND series=?',(company,row[0])).fetchone()[0] or 0
  if used>=row[1]:db.execute('UPDATE po_sequences SET next=?,revision=revision+1 WHERE company=? AND branch=? AND kind=?',(used+1,company,branch,kind));row=(row[0],used+1,row[2]+1)
  return {'serie':row[0],'siguiente':row[1],'revision':row[2]}
 def sequences(self,company,branch,actor):
  self.scope(actor,company,branch)
  with self.store.connect() as db:return {'series':[{'tipo':kind,**self.sequence(db,company,branch,kind)} for kind in ('COTIZACION','PEDIDO','RECEPCION','COMPRA')]}
 def save_sequence(self,data,actor):
  company=data.get('empresa');branch=data.get('sucursal');self.scope(actor,company,branch)
  if actor['role'] not in SERIES_EDITORS:raise PermissionError('Solo Compras, Gerencia, AUXTI y Sistemas configuran series.')
  series=text(data.get('serie',''),30).upper();next=data.get('siguiente');kind=data.get('tipo')
  if not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,29}',series) or type(next) is not int or not 1<=next<=999999999:raise ValueError('Serie o folio inválido.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=self.sequence(db,company,branch,kind)
   if old['revision']!=data.get('revision'):raise Conflict('La serie cambió o se emitió un documento.')
   used=db.execute('SELECT MAX(number) FROM po_numbers WHERE company=? AND series=?',(company,series)).fetchone()[0] or 0
   owner=db.execute('SELECT branch,kind FROM po_series_registry WHERE company=? AND series=? AND (branch<>? OR kind<>?)',(company,series,branch,kind)).fetchone()
   if owner:raise ValueError('Esta serie pertenece a otro tipo de documento o sucursal.')
   if next<=used or series==old['serie'] and next<old['siguiente']:raise ValueError('No se pueden reutilizar ni retroceder folios.')
   db.execute('INSERT OR IGNORE INTO po_series_registry VALUES(?,?,?,?)',(company,series,branch,kind))
   db.execute('UPDATE po_sequences SET series=?,next=?,revision=revision+1 WHERE company=? AND branch=? AND kind=?',(series,next,company,branch,kind));self.audit(db,actor,'serie_configurada',{'empresa':company,'sucursal':branch,'tipo':kind,'serie':series,'siguiente':next})
  return {'ok':True}
 def next_number(self,db,company,branch,kind,id):
  seq=self.sequence(db,company,branch,kind)
  if seq['siguiente']>999999999:raise ValueError('Serie agotada.')
  db.execute('INSERT INTO po_numbers VALUES(?,?,?,?)',(company,seq['serie'],seq['siguiente'],id));db.execute('UPDATE po_sequences SET next=next+1,revision=revision+1 WHERE company=? AND branch=? AND kind=?',(company,branch,kind));return seq['serie']+'-'+str(seq['siguiente']).zfill(6)
 def document(self,db,id,actor):
  row=db.execute('SELECT company,branch,state,revision,payload FROM po_orders WHERE id=?',(id,)).fetchone()
  if not row:raise ValueError('Pedido de compra inexistente.')
  self.scope(actor,row[0],row[1],db=db);return {'id':id,'revision':row[3],**json.loads(row[4])}
 def get_document(self,id,actor):
  with self.store.connect() as db:
   doc=self.document(db,id,actor);doc['movimientos']=[json.loads(p) for p, in db.execute('SELECT payload FROM po_moves WHERE order_id=? ORDER BY rowid',(id,))];doc['correos']=[{'id':i,'estado':s,**json.loads(p)} for i,s,p in db.execute('SELECT id,state,payload FROM po_mail WHERE order_id=?',(id,))];return doc
 def orders(self,actor,company=None,filters=None):
  self.scope(actor);filters=filters or {};start=iso_date(filters.get('desde'));end=iso_date(filters.get('hasta'));result=[]
  if start and end and start>end:raise ValueError('Rango de fechas inválido.')
  with self.store.connect() as db:
   for id, in db.execute('SELECT id FROM po_orders ORDER BY rowid DESC'):
    try:d=self.document(db,id,actor)
    except PermissionError:continue
    if company and d['empresa']!=company or filters.get('sucursal') and d['sucursal']!=filters['sucursal'] or filters.get('estado') and d['estado']!=filters['estado'] or filters.get('proveedor') and d['proveedor']['id']!=filters['proveedor']:continue
    if start and d['fechaPedido']<start or end and d['fechaPedido']>end:continue
    if filters.get('requisicion') and not any(l.get('requisicionId')==filters['requisicion'] for l in d['partidas']):continue
    result.append(d)
  groups=[]
  for branch in BRANCHES:
   docs=[d for d in result if d['sucursal']==branch];valid=[d for d in docs if d['estado'] not in ('BORRADOR','ENVIADO','CANCELADO')];groups.append({'sucursal':branch,'emitidas':sum(d['estado'] not in ('BORRADOR','CANCELADO') for d in docs),'borradores':sum(d['estado']=='BORRADOR' for d in docs),'canceladas':sum(d['estado']=='CANCELADO' for d in docs),'total':money(sum((Decimal(d['total']) for d in valid),Decimal(0)))})
  return {'pedidos':result,'sucursales':groups}
 def request_document(self,id,actor):
  doc=self.req.get(id,actor)
  if doc is None:raise PermissionError('Requisición no disponible en tu alcance.')
  return doc
 def req_sources(self,company,branch,actor):
  self.scope(actor,company,branch);docs=[]
  with self.store.connect() as db:
   for id,p in db.execute('SELECT id,payload FROM req_documents'):
    d=json.loads(p)
    if d['sucursal']!=branch or d['estado']=='CANCELADO':continue
    try:self.request_document(id,actor)
    except (PermissionError,ValueError):continue
    used={}
    for oid,op in db.execute("SELECT id,payload FROM po_orders WHERE state<>'CANCELADO'"):
     for line in json.loads(op)['partidas']:
      if line.get('requisicionId')==id:source_unit=next((r['unidad'] for r in d['partidas'] if r['materialId']==line['materialId']),line['unidadEntrega']);used[line['materialId']]=used.get(line['materialId'],Decimal(0))+delivery_in(Decimal(line['cantidadEntrega']),line['unidadEntrega'],source_unit)
    parts=[{**line,'saldoCompraEntrega':format(max(Decimal(0),Decimal(line['cantidad'])-used.get(line['materialId'],Decimal(0))),'f')} for line in d['partidas']]
    docs.append({'id':id,'numero':d['numero'],'fecha':d['fecha'],'area':d['area'],'partidas':parts})
  return {'requisiciones':docs}
 def request_detail(self,company,branch,id,actor):
  self.scope(actor,company,branch);doc=self.request_document(id,actor)
  if doc['sucursal']!=branch:raise PermissionError('La requisición no pertenece a la sucursal seleccionada.')
  source=next((r for r in self.req_sources(company,branch,actor)['requisiciones'] if r['id']==id),None)
  if source is None:source={'partidas':[{**l,'saldoCompraEntrega':'0'} for l in doc['partidas']]}
  safe={k:doc.get(k,'') for k in ('id','numero','fecha','sucursal','area','solicitante','observaciones','estado')};safe['partidas']=source['partidas']
  linked=self.orders(actor,company,{'requisicion':id})['pedidos'];return {'requisicion':safe,'pedidos':[{'id':p['id'],'folio':p['folio'],'estado':p['estado'],'proveedor':p['proveedor']['nombre']} for p in linked]}
 def validate_source(self,db,line,branch,actor,unit_factor,quantity,exclude=None):
  id=line.get('requisicionId')
  if not id:return None
  doc=self.request_document(id,actor)
  if doc['sucursal']!=branch or doc['estado']=='CANCELADO':raise ValueError('La requisición no corresponde a la sucursal o está cancelada.')
  material=line['materialId'];source=next((l for l in doc['partidas'] if l['materialId']==material),None)
  if source is None:raise ValueError('El material no pertenece a la requisición.')
  used=Decimal(0)
  for oid,p in db.execute("SELECT id,payload FROM po_orders WHERE state<>'CANCELADO'"):
   if oid==exclude:continue
   for l in json.loads(p)['partidas']:
    if l.get('requisicionId')==id and l['materialId']==material:used+=delivery_in(Decimal(l['cantidadEntrega']),l['unidadEntrega'],source['unidad'])
  if used+delivery_in(quantity*unit_factor,line.get('unidadEntrega',source['unidad']),source['unidad'])>Decimal(source['cantidad']):raise ValueError('La cantidad excede el saldo de la requisición ya vinculado a pedidos de compra.')
  return doc['numero']
 def save_order(self,data,actor):
  company=data.get('empresa');branch=data.get('sucursal');self.scope(actor,company,branch,capture=True);materials={m['materialId']:m for m in self.materials(actor)['materiales']};lines=data.get('partidas');key=str(data.get('clave',''));id=data.get('id') or uuid.uuid4().hex
  if not re.fullmatch('[A-Za-z0-9_-]{16,100}',key) or not isinstance(lines,list) or not 1<=len(lines)<=200:raise ValueError('Faltan partidas o clave de envío.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=self.document(db,id,actor) if data.get('id') else None
   previous=db.execute('SELECT id,payload FROM po_orders WHERE client_key=?',(key,)).fetchone()
   if previous and not old:
    if json.loads(previous[1]).get('huellaEnvio')!=fingerprint(data):raise Conflict('Clave de envío utilizada con otros datos.')
    return {'ok':True,'repetido':True,'documento':self.document(db,previous[0],actor)}
   if old and (old['empresa']!=company or old['sucursal']!=branch or old['revision']!=data.get('revision')):raise Conflict('El pedido cambió o pertenece a otro alcance.')
   if old and old['estado'] not in ('BORRADOR','ENVIADO'):raise ValueError('Solo se edita la solicitud de cotización antes de confirmar el pedido.')
   vendor=db.execute('SELECT code,payload FROM po_vendors WHERE id=? AND company=?',(data.get('proveedor'),company)).fetchone()
   if not vendor or not json.loads(vendor[1])['activo']:raise ValueError('Selecciona un proveedor activo de esta razón social.')
   prepared=[];seen=set()
   for l in lines:
    material=materials.get(l.get('materialId'));kind=l.get('tipoUnidad','COMPRA');qty=number(l.get('cantidad'),True)
    if material is None or not material['activo'] or kind not in ('COMPRA','ENTREGA'):raise ValueError('Material o unidad no disponible en el maestro de Requisiciones.')
    identity=(l['materialId'],l.get('requisicionId',''))
    if identity in seen:raise ValueError('Material repetido para la misma requisición. Agrupa su cantidad.')
    seen.add(identity);factor=number(material['factor'],True) if material.get('factor') else Decimal(1) if material['unidadCompra']==material['unidadEntrega'] else None
    if factor is None:raise ValueError('Falta equivalencia validada de compra/entrega. Corrígela en costos de Requisiciones.')
    conversion=factor if kind=='COMPRA' else Decimal(1);source_number=self.validate_source(db,{**l,'unidadEntrega':material['unidadEntrega']},branch,actor,conversion,qty,id if old else None);tax=rate(l.get('impuesto',material.get('impuesto')))
    if tax is None:raise ValueError('Completa el impuesto del producto; una celda vacía no es impuesto cero.')
    default=material.get('precioCompra') if kind=='COMPRA' else material.get('costoEntrega') or (format(Decimal(material['precioCompra'])/factor,'f') if material.get('precioCompra') else None)
    default=optional_price(default);price=number(l.get('precio',default));base=qty*price;tax_amount=base*Decimal(tax)/100;due=iso_date(l.get('fechaRequerida') or data.get('fechaEntrega',''))
    prepared.append({'linea':str(len(prepared)+1),'materialId':material['materialId'],'sku':material['sku'],'nombre':material['nombre'],'tipoUnidad':kind,'unidad':material['unidadCompra'] if kind=='COMPRA' else material['unidadEntrega'],'unidadCompra':material['unidadCompra'],'unidadEntrega':material['unidadEntrega'],'factor':format(factor,'f'),'factorEntrega':format(conversion,'f'),'cantidad':format(qty,'f'),'cantidadEntrega':format(qty*conversion,'f'),'precio':format(price,'f'),'impuesto':tax,'tipoImpuesto':tax_name(tax),'base':money(base),'importeImpuesto':money(tax_amount),'total':money(base+tax_amount),'fechaRequerida':due,'requisicionId':l.get('requisicionId',''),'requisicionNumero':source_number or '','observaciones':text(l.get('observaciones',''),3000),'recibido':'0','comprado':'0'})
   issuer=self.scope(actor,company,branch,db=db)
   if not issuer.get('activa') or issuer.get('eliminada'):raise ValueError('La razón social no está activa.')
   value={'empresa':company,'emisor':issuer,'sucursal':branch,'proveedor':{'id':data['proveedor'],'codigo':vendor[0],**json.loads(vendor[1])},'referenciaProveedor':text(data.get('referenciaProveedor',''),300),'fechaPedido':iso_date(data.get('fechaPedido')) or now()[:10],'fechaEntrega':iso_date(data.get('fechaEntrega')),'observaciones':text(data.get('observaciones',''),100000),'condiciones':text(data.get('condiciones',''),20000),'partidas':prepared,'estado':old['estado'] if old else 'BORRADOR','creado':old['creado'] if old else now(),'creador':old['creador'] if old else actor['email'],'actualizado':now(),'folio':old['folio'] if old else self.next_number(db,company,branch,'COTIZACION',id),'huellaEnvio':fingerprint(data)}
   for k in ('base','importeImpuesto','total'):value[k]=money(sum((Decimal(l[k]) for l in prepared),Decimal(0)))
   if old:db.execute('UPDATE po_orders SET revision=revision+1,payload=? WHERE id=?',(dumps(value),id))
   else:db.execute('INSERT INTO po_orders VALUES(?,?,?,?,1,?,?,?)',(id,company,branch,value['estado'],actor['email'],key,dumps(value)))
   self.audit(db,actor,'cotizacion_guardada',{'id':id,'folio':value['folio']});return {'ok':True,'documento':self.document(db,id,actor)}
 def update_doc(self,db,doc,actor,action):
  id=doc['id'];payload={k:v for k,v in doc.items() if k not in ('id','revision','movimientos','correos')};payload['actualizado']=now();db.execute('UPDATE po_orders SET state=?,revision=revision+1,payload=? WHERE id=?',(doc['estado'],dumps(payload),id));self.audit(db,actor,action,{'id':id,'folio':doc['folio']})
 def transition(self,data,actor):
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');doc=self.document(db,data.get('id'),actor);self.scope(actor,doc['empresa'],doc['sucursal'],capture=True,db=db)
   if doc['revision']!=data.get('revision'):raise Conflict('El pedido cambió. Actualiza.')
   action=data.get('accion')
   if action=='confirmar':
    if doc['estado'] not in ('BORRADOR','ENVIADO'):raise ValueError('Solo puedes confirmar una cotización pendiente.')
    for l in doc['partidas']:self.validate_source(db,l,doc['sucursal'],actor,Decimal(l['factorEntrega']),Decimal(l['cantidad']),doc['id'])
    issuer=self.scope(actor,doc['empresa'],doc['sucursal'],db=db)
    if not issuer.get('activa') or issuer.get('eliminada'):raise ValueError('La razón social ya no está activa.')
    if not db.execute("SELECT 1 FROM po_vendors WHERE id=? AND company=? AND json_extract(payload,'$.activo')=1",(doc['proveedor']['id'],doc['empresa'])).fetchone():raise ValueError('El proveedor ya no está activo.')
    doc['cotizacionOrigen']=doc['folio'];doc['folio']=self.next_number(db,doc['empresa'],doc['sucursal'],'PEDIDO',doc['id']);doc['estado']='PEDIDO';doc['confirmado']=now()
   elif action=='cancelar':
    if doc['estado']=='CANCELADO' or any(Decimal(l['recibido']) or Decimal(l['comprado']) for l in doc['partidas']):raise ValueError('No se cancela un pedido que ya tiene recepciones o compras; requiere devolución documentada.')
    reason=text(data.get('motivo',''),3000)
    if not reason:raise ValueError('Indica motivo de cancelación.')
    doc['estado']='CANCELADO';doc['cancelacion']={'motivo':reason,'fecha':now(),'actor':actor['email']}
   else:raise ValueError('Acción inválida.')
   self.update_doc(db,doc,actor,action);return {'ok':True,'documento':self.document(db,doc['id'],actor)}
 def movement(self,data,actor,kind):
  key=str(data.get('clave',''))
  if not re.fullmatch('[A-Za-z0-9_-]{16,100}',key):raise ValueError('Falta clave del movimiento.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');doc=self.document(db,data.get('id'),actor);self.scope(actor,doc['empresa'],doc['sucursal'],capture=kind=='COMPRA',receive=kind=='RECEPCION',db=db);repeat=db.execute('SELECT payload FROM po_moves WHERE client_key=?',(key,)).fetchone()
   if repeat:
    old=json.loads(repeat[0])
    if old.get('huella')!=fingerprint(data):raise Conflict('Clave utilizada con otro movimiento.')
    return {'ok':True,'movimiento':old,'documento':doc,'repetido':True}
   if doc['revision']!=data.get('revision'):raise Conflict('Cambió el pedido o su recepción.')
   if doc['estado'] not in ('PEDIDO','RECEPCION_PARCIAL','RECIBIDO'):raise ValueError('El pedido no permite este movimiento.')
   lines=data.get('partidas');prepared=[];seen=set()
   if not isinstance(lines,list) or not lines:raise ValueError('Indica las cantidades realmente recibidas o compradas.')
   for requested in lines:
    line=next((l for l in doc['partidas'] if l['linea']==requested.get('linea')),None);quantity=number(requested.get('cantidad'),True)
    if line is None or line['linea'] in seen:raise ValueError('Partida inválida o repetida.')
    seen.add(line['linea']);field='recibido' if kind=='RECEPCION' else 'comprado';maximum=Decimal(line['cantidad']) if kind=='RECEPCION' else Decimal(line['recibido'])
    if Decimal(line[field])+quantity>maximum:raise ValueError('No se puede recibir más de lo pedido ni comprar/facturar más de lo recibido.')
    received_unit=requested.get('tipoUnidad',line['tipoUnidad'])
    if received_unit!=line['tipoUnidad']:raise ValueError('Registra la cantidad en la unidad capturada del pedido; la equivalencia de entrega se muestra al lado.')
    line[field]=format(Decimal(line[field])+quantity,'f');prepared.append({'linea':line['linea'],'materialId':line['materialId'],'sku':line['sku'],'nombre':line['nombre'],'cantidad':format(quantity,'f'),'unidad':line['unidad'],'cantidadEntrega':format(quantity*Decimal(line['factorEntrega']),'f'),'unidadEntrega':line['unidadEntrega'],'base':money(quantity*Decimal(line['precio'])),'impuestos':money(quantity*Decimal(line['precio'])*Decimal(line['impuesto'])/100)})
   reference=text(data.get('referencia',''),300)
   if kind=='COMPRA' and reference:
    if db.execute("SELECT 1 FROM po_moves WHERE kind='COMPRA' AND json_extract(payload,'$.empresa')=? AND json_extract(payload,'$.proveedorId')=? AND json_extract(payload,'$.referencia')=?",(doc['empresa'],doc['proveedor']['id'],reference)).fetchone():raise ValueError('La referencia de compra/factura ya fue registrada para este proveedor.')
   id=uuid.uuid4().hex;value={'id':id,'pedidoId':doc['id'],'empresa':doc['empresa'],'proveedorId':doc['proveedor']['id'],'tipo':kind,'folio':self.next_number(db,doc['empresa'],doc['sucursal'],kind,id),'fecha':iso_date(data.get('fecha')) or now()[:10],'creado':now(),'actor':actor['email'],'referencia':reference,'observaciones':text(data.get('observaciones',''),100000),'partidas':prepared,'huella':fingerprint(data)};value['total']=money(sum((Decimal(l['base'])+Decimal(l['impuestos']) for l in prepared),Decimal(0)))
   if kind=='RECEPCION' and hasattr(self,'inventory'):self.inventory.receipt(db,doc,value,actor)
   db.execute('INSERT INTO po_moves VALUES(?,?,?,?,?)',(id,doc['id'],kind,key,dumps(value)));doc['estado']='COMPRADO' if all(Decimal(l['comprado'])==Decimal(l['cantidad']) for l in doc['partidas']) else 'RECIBIDO' if all(Decimal(l['recibido'])==Decimal(l['cantidad']) for l in doc['partidas']) else 'RECEPCION_PARCIAL';self.update_doc(db,doc,actor,kind);return {'ok':True,'movimiento':value,'documento':self.document(db,doc['id'],actor)}
 def links_for_requisition(self,id,actor):
  require_module(actor,'requisiciones');self.request_document(id,actor);result=[]
  with self.store.connect() as db:
   for oid,p in db.execute('SELECT id,payload FROM po_orders ORDER BY rowid DESC'):
    doc=json.loads(p);lines=[{'materialId':l['materialId'],'sku':l['sku'],'nombre':l['nombre'],'cantidadEntrega':l['cantidadEntrega'],'unidadEntrega':l['unidadEntrega'],'recibidoEntrega':format(Decimal(l['recibido'])*Decimal(l['factorEntrega']),'f')} for l in doc['partidas'] if l.get('requisicionId')==id]
    if lines:result.append({'id':oid,'folio':doc['folio'],'estado':doc['estado'],'sucursal':doc['sucursal'],'partidas':lines})
  return {'pedidos':result}
 def backup(self,actor,db=None):
  self.scope(actor)
  if actor['role'] not in ADMINS:raise PermissionError('Solo Sistemas y AUXTI descargan respaldos de Compras.')
  if db is None:
   with self.store.connect() as conn:return self.backup(actor,conn)
  tables={}
  for name in TABLES:
   columns=[r[1] for r in db.execute('PRAGMA table_info('+name+')')];tables[name]={'columnas':columns,'filas':[list(r) for r in db.execute('SELECT * FROM '+name)]}
  content={'formato':'GMP_ERP_COMPRAS_3','tablas':tables};return {**content,'checksum':fingerprint(content)}
 def restore(self,data,actor):
  self.scope(actor)
  if actor['role']!='superadmin':raise PermissionError('Solo Sistemas puede restaurar datos de Compras.')
  payload=data.get('respaldo');apply=data.get('aplicar') is True
  if apply:
   with self.store.connect() as guard:
    if guard.execute("SELECT 1 FROM sqlite_master WHERE name='inv_ledger'").fetchone() and guard.execute("SELECT 1 FROM inv_ledger WHERE json_extract(payload,'$.tipo')='RECEPCION_COMPRA' LIMIT 1").fetchone():raise Conflict('Hay recepciones integradas al inventario. Recupera una copia completa de data; restaurar solo Compras desajustaría las existencias.')
  if not isinstance(payload,dict) or payload.get('formato')!='GMP_ERP_COMPRAS_3' or payload.get('checksum')!=fingerprint({k:v for k,v in payload.items() if k!='checksum'}) or set(payload.get('tablas',{}))!=set(TABLES):raise ValueError('Respaldo de Compras inválido o dañado.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');current=self.backup(actor,db)
   if db.execute("SELECT 1 FROM po_mail WHERE state='ENVIANDO'").fetchone():raise ValueError('Hay un correo en proceso. Espera antes de restaurar.')
   if apply and data.get('huellaActual')!=current['checksum']:raise Conflict('Compras cambió desde la revisión del respaldo.')
   for name in TABLES:
    target=payload['tablas'][name];columns=[r[1] for r in db.execute('PRAGMA table_info('+name+')')]
    if target.get('columnas')!=columns or not isinstance(target.get('filas'),list) or len(target['filas'])>100000 or any(not isinstance(row,list) or len(row)!=len(columns) for row in target['filas']):raise ValueError('Tabla de respaldo inválida: '+name)
   companies={r[0] for r in db.execute('SELECT id FROM cm_companies')};vendors={r[0]:r[1] for r in payload['tablas']['po_vendors']['filas']};orders={r[0] for r in payload['tablas']['po_orders']['filas']}
   for row in payload['tablas']['po_vendors']['filas']:
    if row[1] not in companies or type(row[3]) is not int or row[3]<1:raise ValueError('Proveedor con razón social o revisión inexistente.')
    v=json.loads(row[4]);text(v['nombre'],300);email(v.get('correo',''))
   for row in payload['tablas']['po_orders']['filas']:
    d=json.loads(row[7])
    if row[1] not in companies or row[2] not in BRANCHES or row[3] not in STATES or d['proveedor']['id'] not in vendors or vendors[d['proveedor']['id']]!=row[1] or d['empresa']!=row[1] or d['estado']!=row[3] or d['sucursal']!=row[2]:raise ValueError('Pedido incoherente en el respaldo.')
    for line in d['partidas']:
     if not 0<=number(line['comprado'])<=number(line['recibido'])<=number(line['cantidad'],True) or not db.execute('SELECT 1 FROM req_materials WHERE id=?',(line['materialId'],)).fetchone():raise ValueError('Cantidad o material inválido en respaldo.')
     if line.get('requisicionId') and not db.execute('SELECT 1 FROM req_documents WHERE id=?',(line['requisicionId'],)).fetchone():raise ValueError('Falta la requisición vinculada. Restaura primero su módulo.')
   for row in payload['tablas']['po_moves']['filas']:
    if row[1] not in orders:raise ValueError('Movimiento sin pedido de compra.')
   result={'ok':True,'huellaActual':current['checksum'],'proveedores':len(vendors),'pedidos':len(orders),'movimientos':len(payload['tablas']['po_moves']['filas'])}
   if not apply:return result
   target=self.store.directory/'backups-compras';target.mkdir(exist_ok=True);(target/('antes-restauracion-'+uuid.uuid4().hex+'.json')).write_text(dumps(current),encoding='utf8')
   for name in reversed(TABLES):db.execute('DELETE FROM '+name)
   for name in TABLES:
    content=payload['tablas'][name];columns=content['columnas'];db.executemany('INSERT INTO '+name+' VALUES('+','.join('?' for _ in columns)+')',content['filas'])
   # Los folios ya usados siguen reservados aun al recuperar una copia anterior.
   for row in current['tablas']['po_numbers']['filas']:db.execute('INSERT OR IGNORE INTO po_numbers VALUES(?,?,?,?)',row)
   for row in current['tablas']['po_series_registry']['filas']:db.execute('INSERT OR IGNORE INTO po_series_registry VALUES(?,?,?,?)',row)
   for company,branch,kind,series,next,rev in db.execute('SELECT * FROM po_sequences').fetchall():
    used=db.execute('SELECT MAX(number) FROM po_numbers WHERE company=? AND series=?',(company,series)).fetchone()[0] or 0;db.execute('UPDATE po_sequences SET next=MAX(next,?),revision=revision+1 WHERE company=? AND branch=? AND kind=?',(used+1,company,branch,kind))
   self.audit(db,actor,'respaldo_restaurado',result);return {**result,'restaurado':True}
 def templates(self,company,actor):
  self.scope(actor,company)
  with self.store.connect() as db:return {'plantillas':[{'id':i,'revision':r,**json.loads(p)} for i,r,p in db.execute('SELECT id,revision,payload FROM po_templates WHERE company=? ORDER BY id',(company,))]}
 def save_template(self,data,actor,db=None):
  company=data.get('empresa');self.scope(actor,company)
  if actor['role'] not in ADMINS|{'gerente'}:raise PermissionError('Tu perfil no puede editar plantillas de proveedor.')
  if db is None:
   with self.store.connect() as conn:
    conn.execute('BEGIN IMMEDIATE');return self.save_template(data,actor,conn)
  name=text(data.get('nombre',''),160);vendor=data.get('proveedor');lines=data.get('partidas');id=data.get('id') or uuid.uuid4().hex
  if not name or not isinstance(lines,list) or not 1<=len(lines)<=200:raise ValueError('Indica nombre y entre 1 y 200 partidas de la plantilla.')
  if not db.execute("SELECT 1 FROM po_vendors WHERE id=? AND company=? AND json_extract(payload,'$.activo')=1",(vendor,company)).fetchone():raise ValueError('Proveedor no disponible para esta razón social.')
  old=db.execute('SELECT company,revision FROM po_templates WHERE id=?',(id,)).fetchone()
  if old and old[0]!=company:raise PermissionError('Plantilla de otra razón social.')
  if data.get('revision',0)!=(old[1] if old else 0):raise Conflict('La plantilla cambió. Actualiza.')
  prepared=[];seen=set()
  for line in lines:
   mid=line.get('materialId');unit=line.get('tipoUnidad','COMPRA')
   if mid in seen or not db.execute('SELECT 1 FROM req_materials WHERE id=?',(mid,)).fetchone() or unit not in ('COMPRA','ENTREGA'):raise ValueError('Material repetido, inexistente o unidad inválida.')
   seen.add(mid);prepared.append({'materialId':mid,'cantidad':format(number(line.get('cantidad'),True),'f'),'tipoUnidad':unit,'precio':optional_price(line.get('precio')),'impuesto':rate(line.get('impuesto')),'observaciones':text(line.get('observaciones',''),3000)})
  value={'nombre':name,'proveedor':vendor,'partidas':prepared,'observaciones':text(data.get('observaciones',''),100000),'condiciones':text(data.get('condiciones',''),20000)};db.execute('INSERT INTO po_templates VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(id,company,(old[1] if old else 0)+1,dumps(value)));self.audit(db,actor,'plantilla_proveedor_guardada',{'id':id});return {'ok':True,'id':id}
