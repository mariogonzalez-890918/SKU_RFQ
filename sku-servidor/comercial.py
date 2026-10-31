from fechas import iso_date
"""Ventas institucionales y Expendios: compañías, precios finales, documentos y caja."""
import base64,collections,copy,decimal,hashlib,json,re,uuid
from permissions import require_module
from requisiciones import BRANCHES,Conflict,now,text

D=decimal.Decimal
CENT=D('.01')
ADMINS={'superadmin','auxti'}
SUPERVISORS=ADMINS|{'gerente'}
CHANNELS={'ventasins','expendios'}
LISTS={'PUBLICO':'Público institucional','RUTA':'Expendio ruta','DESPACHO':'Expendio despacho'}
CAPS=['ventasins.clientes','ventasins.pedidos','ventasins.reportes','expendios.clientes','expendios.caja','expendios.reportes','maestro','precios','configurar']

def dumps(v):return json.dumps(v,ensure_ascii=False,allow_nan=False)
def amount(v,positive=False):
 try:
  if isinstance(v,bool):raise ValueError()
  q=D(str(v))
  if not q.is_finite() or q<0 or q>D('999999999') or q.as_tuple().exponent < -6 or positive and not q:raise ValueError()
  return q
 except (decimal.InvalidOperation,TypeError,ValueError):raise ValueError('Cantidad o importe inválido; máximo 999999999 y seis decimales.')
def money(v):return format(D(v).quantize(CENT,rounding=decimal.ROUND_HALF_UP),'f')
def fingerprint(data):return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def tax_name(rate):return 'PENDIENTE' if rate is None else 'IEPS' if D(str(rate))==8 else 'IVA' if D(str(rate))==16 else 'SIN IVA'

def tax_line(quantity,price,rate,discount='0'):
 q=amount(quantity,True);p=amount(price);r=amount(rate);d=amount(discount)
 if r not in (D(0),D(8),D(16)) or d>100:raise ValueError('Impuesto permitido: 0% sin IVA, 8% IEPS o 16% IVA. Descuento de 0 a 100 %.')
 gross=(q*p*(1-d/100)).quantize(CENT,rounding=decimal.ROUND_HALF_UP)
 net=(gross/(1+r/100)).quantize(CENT,rounding=decimal.ROUND_HALF_UP)
 return {'cantidad':format(q,'f'),'precio':format(p,'f'),'iva':format(r,'f'),'descuento':format(d,'f'),'base':money(net),'impuesto':money(gross-net),'total':money(gross),'incluyeIva':r==16,'incluyeImpuestos':True,'tipoImpuesto':tax_name(r)}

class CommercialStore:
 def __init__(self,store):
  self.store=store
  with store.connect() as db:
   db.executescript('''
    CREATE TABLE IF NOT EXISTS cm_companies(id INTEGER PRIMARY KEY AUTOINCREMENT,revision INTEGER NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cm_access(email TEXT PRIMARY KEY,payload TEXT NOT NULL,revision INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS cm_products(sku TEXT PRIMARY KEY,payload TEXT NOT NULL,revision INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS cm_prices(company INTEGER NOT NULL,list TEXT NOT NULL,sku TEXT NOT NULL,customer TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(company,list,sku,customer));
    CREATE TABLE IF NOT EXISTS cm_customers(id TEXT PRIMARY KEY,company INTEGER NOT NULL,code TEXT NOT NULL,creator TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,UNIQUE(company,code));
    CREATE TABLE IF NOT EXISTS cm_templates(id TEXT PRIMARY KEY,company INTEGER NOT NULL,creator TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cm_reports(id TEXT PRIMARY KEY,company INTEGER NOT NULL,channel TEXT NOT NULL,creator TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cm_boxes(id TEXT PRIMARY KEY,company INTEGER NOT NULL,branch TEXT NOT NULL,code TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,UNIQUE(company,code));
    CREATE TABLE IF NOT EXISTS cm_sessions(id TEXT PRIMARY KEY,company INTEGER NOT NULL,box TEXT NOT NULL,operator TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS cm_open_box ON cm_sessions(box) WHERE state='ABIERTA';
    CREATE TABLE IF NOT EXISTS cm_sequences(company INTEGER NOT NULL,kind TEXT NOT NULL,series TEXT NOT NULL,next INTEGER NOT NULL,width INTEGER NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(company,kind));
    CREATE TABLE IF NOT EXISTS cm_sequence_registry(company INTEGER NOT NULL,series TEXT NOT NULL,kind TEXT NOT NULL,PRIMARY KEY(company,series));
    CREATE TABLE IF NOT EXISTS cm_documents(id TEXT PRIMARY KEY,company INTEGER NOT NULL,channel TEXT NOT NULL,creator TEXT NOT NULL,box TEXT NOT NULL,session TEXT NOT NULL,state TEXT NOT NULL,number TEXT NOT NULL,created TEXT NOT NULL,client_key TEXT NOT NULL,fingerprint TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,UNIQUE(company,number),UNIQUE(creator,channel,client_key));
    CREATE INDEX IF NOT EXISTS cm_document_scope ON cm_documents(company,channel,created);
    CREATE TABLE IF NOT EXISTS cm_versions(document TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(document,revision));
    CREATE TABLE IF NOT EXISTS cm_cancellations(id TEXT PRIMARY KEY,company INTEGER NOT NULL,document TEXT NOT NULL,requester TEXT NOT NULL,state TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL);
    CREATE UNIQUE INDEX IF NOT EXISTS cm_cancel_pending ON cm_cancellations(document) WHERE state='PENDIENTE';
    CREATE TABLE IF NOT EXISTS cm_cash_moves(id TEXT PRIMARY KEY,company INTEGER NOT NULL,session TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cm_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,company INTEGER NOT NULL,actor TEXT NOT NULL,created TEXT NOT NULL,action TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS cm_revision(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL);
    INSERT OR IGNORE INTO cm_revision VALUES(1,1);
   ''')
 def audit(self,db,actor,company,action,data):
  db.execute('INSERT INTO cm_audit(company,actor,created,action,payload) VALUES(?,?,?,?,?)',(company,actor['email'],now(),action,dumps(data)))
  db.execute('UPDATE cm_revision SET revision=revision+1 WHERE id=1')
 def access(self,actor):
  with self.store.connect() as db:row=db.execute('SELECT payload,revision FROM cm_access WHERE email=?',(actor['email'],)).fetchone()
  return {**(json.loads(row[0]) if row else {'empresas':[],'sucursales':[],'cajas':[],'acciones':[]}), 'revision':row[1] if row else 0}
 def module(self,actor,channel):
  if channel not in CHANNELS:raise ValueError('Módulo comercial inválido.')
  require_module(actor,channel)
 def action(self,actor,channel,action):
  self.module(actor,channel)
  if actor['role'] in ADMINS:return
  default=(actor['role']=='ventaspasteleria' and channel=='ventasins' and action=='pedidos') or (actor['role']==channel and action in ('clientes','pedidos','caja','reportes')) or actor['role']=='gerente' and action in ('reportes','clientes')
  if not default and channel+'.'+action not in self.access(actor)['acciones'] and action not in self.access(actor)['acciones']:raise PermissionError('Tu perfil permite consulta; esta acción requiere un permiso adicional.')
 def admin(self,actor):
  if actor['role'] not in ADMINS:raise PermissionError('Solo AUXTI y Superadministrador administran razones sociales y configuración comercial.')
  if not any(m in actor.get('modulos',[]) for m in CHANNELS|{'pedidoscompra'}):raise PermissionError('No tienes un módulo comercial habilitado.')
 def company(self,id,actor,active=False,db=None):
  if type(id) is not int:raise ValueError('Selecciona una razón social.')
  if actor['role'] not in ADMINS and id not in self.access(actor)['empresas']:raise PermissionError('No tienes acceso a esta razón social.')
  if db is None:
   with self.store.connect() as conn:row=conn.execute('SELECT revision,payload FROM cm_companies WHERE id=?',(id,)).fetchone()
  else:row=db.execute('SELECT revision,payload FROM cm_companies WHERE id=?',(id,)).fetchone()
  if not row:raise ValueError('Razón social no disponible.')
  value={'id':id,'revision':row[0],**json.loads(row[1])}
  if active and (value.get('eliminada') or not value.get('activa')):raise ValueError('La razón social no está activa para nuevas operaciones.')
  return value
 def branch(self,company,branch,actor):
  if branch not in company['sucursales']:raise PermissionError('La sucursal no está vinculada a esta razón social.')
  if actor['role'] not in ADMINS and branch not in self.access(actor)['sucursales']:raise PermissionError('No tienes asignada esta sucursal.')
 def metadata(self,actor,channel):
  self.module(actor,channel);access=self.access(actor)
  with self.store.connect() as db:
   companies=[{'id':id,'revision':rev,**json.loads(p)} for id,rev,p in db.execute('SELECT id,revision,payload FROM cm_companies ORDER BY id') if actor['role'] in ADMINS or id in access['empresas']]
   revision=db.execute('SELECT revision FROM cm_revision WHERE id=1').fetchone()[0]
  return {'empresas':companies,'acceso':access,'sucursales':list(BRANCHES),'listas':LISTS,'iva':['0','8','16'],'revision':revision,'puedeConfigurar':actor['role'] in ADMINS,'puedeCancelarExpendios':actor['role'] in ADMINS,'puedeGestionarPlantillas':actor['role'] in ADMINS|{'gerente'},'puedeAutorizarCancelacionInstitucional':actor['role'] in ADMINS|{'gerente'},'soloCaptura':actor['role']=='ventaspasteleria','puedeDesbloquear':actor['role'] in {'ventasins','gerente','auxti','superadmin'},'puedeOperar':actor['role']=='ventaspasteleria' or actor['role'] in ADMINS or actor['role']==channel or channel+'.'+('caja' if channel=='expendios' else 'pedidos') in access['acciones'],'puedeImportar':actor['role'] in ADMINS or 'maestro' in access['acciones']}
 def save_company(self,data,actor,remove=False):
  self.admin(actor);id=data.get('id');rev=data.get('revision',0)
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT revision,payload FROM cm_companies WHERE id=?',(id,)).fetchone() if id else None
   if id and not old:raise ValueError('Razón social no encontrada.')
   if (old[0] if old else 0)!=rev:raise Conflict('La razón social cambió. Actualiza la pantalla.')
   if id and actor['role'] not in ADMINS:self.company(id,actor,db=db)
   if remove:
    if not old:raise ValueError('Selecciona una razón social existente.')
    if db.execute("SELECT 1 FROM cm_sessions WHERE company=? AND state='ABIERTA'",(id,)).fetchone():raise ValueError('Cierra las cajas antes de eliminar la razón social.')
    value=json.loads(old[1]);value.update({'activa':False,'eliminada':True})
   else:
    name=text(data.get('nombre',''),200);branches=data.get('sucursales',[])
    if not name or not isinstance(branches,list) or not branches or any(b not in BRANCHES for b in branches) or len(set(branches))!=len(branches):raise ValueError('Indica nombre y al menos una de las cuatro sucursales.')
    value={'nombre':name,'rfc':text(data.get('rfc',''),30),'domicilio':text(data.get('domicilio',''),700),'contacto':text(data.get('contacto',''),200),'sucursales':branches,'activa':data.get('activa',True) is True,'eliminada':False}
    if old:
     for branch,payload in db.execute('SELECT branch,payload FROM cm_boxes WHERE company=?',(id,)):
      if branch not in branches and json.loads(payload).get('activa'):raise ValueError('Reasigna primero las cajas activas de la sucursal que deseas desvincular.')
     if not value['activa'] and db.execute("SELECT 1 FROM cm_sessions WHERE company=? AND state='ABIERTA'",(id,)).fetchone():raise ValueError('Cierra las cajas antes de desactivar la razón social.')
   if id:db.execute('UPDATE cm_companies SET revision=revision+1,payload=? WHERE id=?',(dumps(value),id))
   else:id=db.execute('INSERT INTO cm_companies VALUES(NULL,1,?)',(dumps(value),)).lastrowid
   self.audit(db,actor,id,'empresa_eliminada' if remove else 'empresa_guardada',{'id':id})
  return {'ok':True,'id':id}
 def save_access(self,data,actor):
  if actor['role']!='superadmin':raise PermissionError('Solo Superadministrador asigna accesos comerciales por usuario.')
  email=str(data.get('email','')).strip().lower();companies=data.get('empresas',[]);branches=data.get('sucursales',[]);boxes=data.get('cajas',[]);caps=data.get('acciones',[])
  if not all(isinstance(v,list) for v in (companies,branches,boxes,caps)) or any(type(c) is not int for c in companies) or any(b not in BRANCHES for b in branches) or any(c not in CAPS for c in caps):raise ValueError('Asignación comercial inválida.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   user=db.execute('SELECT role FROM users WHERE email=?',(email,)).fetchone()
   if not user or user[0]=='superadmin':raise ValueError('Selecciona un usuario distinto del Superadministrador.')
   for c in companies:
    if not db.execute('SELECT 1 FROM cm_companies WHERE id=?',(c,)).fetchone():raise ValueError('Razón social inválida.')
   for b in boxes:
    row=db.execute('SELECT company,branch FROM cm_boxes WHERE id=?',(b,)).fetchone()
    if not row or row[0] not in companies or row[1] not in branches:raise ValueError('La caja no coincide con las empresas/sucursales asignadas.')
   old=db.execute('SELECT revision FROM cm_access WHERE email=?',(email,)).fetchone()
   if data.get('revision',0)!=(old[0] if old else 0):raise Conflict('La asignación cambió. Actualiza antes de guardar.')
   value={'empresas':list(dict.fromkeys(companies)),'sucursales':list(dict.fromkeys(branches)),'cajas':list(dict.fromkeys(boxes)),'acciones':list(dict.fromkeys(caps))}
   db.execute('INSERT INTO cm_access VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET payload=excluded.payload,revision=excluded.revision',(email,dumps(value),(old[0] if old else 0)+1));self.audit(db,actor,0,'acceso_comercial',{'email':email})
  return {'ok':True}
 def save_branch_companies(self,data,actor):
  self.admin(actor);branch=data.get('sucursal');selected=data.get('empresas');revisions=data.get('revisiones',{})
  if branch not in BRANCHES or not isinstance(selected,list) or any(type(id) is not int for id in selected) or len(set(selected))!=len(selected) or not isinstance(revisions,dict):raise ValueError('Selecciona una de las cuatro sucursales y sus razones sociales.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');rows=[(id,rev,json.loads(p)) for id,rev,p in db.execute('SELECT id,revision,payload FROM cm_companies') if not json.loads(p).get('eliminada')]
   if set(selected)-{id for id,_,_ in rows}:raise ValueError('Razón social no disponible.')
   if any(revisions.get(str(id))!=rev for id,rev,_ in rows):raise Conflict('Cambió una razón social. Actualiza las asignaciones.')
   for id,rev,value in rows:
    before=branch in value['sucursales'];after=id in selected
    if before==after:continue
    if before:
     boxes=db.execute('SELECT payload FROM cm_boxes WHERE company=? AND branch=?',(id,branch)).fetchall()
     if any(json.loads(p).get('activa') for p, in boxes):raise ValueError('Reasigna o desactiva las cajas de esta razón social antes de desvincular la sucursal.')
    value['sucursales']=[b for b in BRANCHES if (b in value['sucursales'] and b!=branch) or b==branch and after]
    db.execute('UPDATE cm_companies SET revision=revision+1,payload=? WHERE id=?',(dumps(value),id));self.audit(db,actor,id,'razon_social_asignada_a_sucursal',{'sucursal':branch,'vinculada':after})
  return {'ok':True}
 def access_list(self,actor):
  self.admin(actor)
  with self.store.connect() as db:rows=db.execute('SELECT u.email,u.name,u.role,a.payload,a.revision FROM users u LEFT JOIN cm_access a ON a.email=u.email ORDER BY email').fetchall()
  return {'usuarios':[{'email':r[0],'nombre':r[1],'perfil':r[2],**(json.loads(r[3]) if r[3] else {'empresas':[],'sucursales':[],'cajas':[],'acciones':[]}), 'revision':r[4] or 0} for r in rows],'acciones':CAPS}
 def products(self,company,actor,channel,query='',customer=''):
  self.module(actor,channel);self.company(company,actor)
  with self.store.connect() as db:
   rows=db.execute('SELECT sku,payload,revision FROM cm_products ORDER BY sku').fetchall();prices=db.execute('SELECT list,sku,revision,payload FROM cm_prices WHERE company=? AND customer=?',(company,'')).fetchall()
   if customer and channel=='ventasins':
    self.customer(db,customer,company,actor);prices+=db.execute('SELECT list,sku,revision,payload FROM cm_prices WHERE company=? AND customer=?',(company,customer)).fetchall()
  pmap={(l,sku):{'revision':rev,**json.loads(p)} for l,sku,rev,p in prices}
  q=query.strip().upper();result=[]
  for sku,p,rev in rows:
   product={'sku':sku,'revision':rev,**json.loads(p)}
   if channel=='ventasins' and not product.get('institucional',True) or channel=='expendios' and not product.get('expendio'):continue
   if q and q not in (sku+' '+product['nombre']).upper():continue
   if not any((key,sku) in pmap for key in LISTS):continue
   product['precios']={key:pmap[(key,sku)]['precio'] for key in (('PUBLICO',) if channel=='ventasins' else ('RUTA','DESPACHO')) if (key,sku) in pmap};result.append(product)
  return {'productos':result}
 def report_definitions(self,company,actor,channel):
  self.module(actor,channel);self.company(company,actor)
  with self.store.connect() as db:rows=db.execute('SELECT id,revision,payload FROM cm_reports WHERE company=? AND channel=? AND creator=?',(company,channel,actor['email'])).fetchall()
  return {'reportes':[{'id':id,'revision':rev,**json.loads(p)} for id,rev,p in rows]}
 def save_report(self,data,actor,channel):
  from comercial_print import COLUMNS
  self.action(actor,channel,'reportes');company=data.get('empresa');self.company(company,actor);name=text(data.get('nombre',''),100);columns=data.get('columnas');filters=data.get('filtros',{})
  if not name or not isinstance(columns,list) or not columns or any(c not in COLUMNS for c in columns) or not isinstance(filters,dict):raise ValueError('Indica nombre, columnas y filtros del reporte.')
  id=data.get('id');value={'nombre':name,'columnas':list(dict.fromkeys(columns)),'filtros':{k:text(filters.get(k,''),100) for k in ('desde','hasta','estado','sucursal','cliente','caja','producto','campoFecha')}}
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT company,channel,creator,revision FROM cm_reports WHERE id=?',(id,)).fetchone() if id else None
   if id and (not row or row[:3]!=(company,channel,actor['email'])):raise PermissionError('Reporte no disponible.')
   if data.get('revision',0)!=(row[3] if row else 0):raise Conflict('El reporte cambió.')
   if row:db.execute('UPDATE cm_reports SET revision=revision+1,payload=? WHERE id=?',(dumps(value),id))
   else:id=uuid.uuid4().hex;db.execute('INSERT INTO cm_reports VALUES(?,?,?,?,1,?)',(id,company,channel,actor['email'],dumps(value)))
   self.audit(db,actor,company,'reporte_comercial_guardado',{'id':id})
  return {'ok':True,'id':id}
 def customers(self,company,actor,channel):
  self.module(actor,channel);self.company(company,actor)
  with self.store.connect() as db:rows=db.execute('SELECT id,revision,payload,creator FROM cm_customers WHERE company=? ORDER BY code',(company,)).fetchall()
  return {'clientes':[{'id':id,'revision':rev,**json.loads(p)} for id,rev,p,creator in rows if channel in json.loads(p).get('canales',['ventasins','expendios'])]}
 def save_customer(self,data,actor,channel):
  self.action(actor,channel,'clientes');company=data.get('empresa');self.company(company,actor,True)
  name=text(data.get('nombre',''),200);code=text(data.get('codigo',''),50).upper();id=data.get('id');rev=data.get('revision',0)
  if not name:raise ValueError('Indica el nombre del cliente. Su código se asigna automáticamente.')
  value={k:text(data.get(k,''),700 if k in ('domicilio','entrega') else 200) for k in ('nombre','rfc','correo','telefono','domicilio','entrega','condiciones')};value.update({'codigo':code,'activo':data.get('activo',True) is True})
  if value['correo'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value['correo']):raise ValueError('Correo de cliente inválido.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT company,creator,revision,payload,code FROM cm_customers WHERE id=?',(id,)).fetchone() if id else None
   if id and (not old or old[0]!=company):raise PermissionError('Cliente no disponible en esta razón social.')
   if (old[2] if old else 0)!=rev:raise Conflict('El cliente cambió.')
   if old:
    if code and code!=old[4]:raise ValueError('El código asignado al cliente no se modifica.')
    code=old[4]
   else:
    identity=lambda v:tuple(' '.join(str(v.get(k,'')).upper().split()) for k in ('nombre','rfc','correo','telefono','domicilio'))
    for p, in db.execute('SELECT payload FROM cm_customers WHERE company=?',(company,)):
     if identity(json.loads(p))==identity(value):raise Conflict('El cliente ya existe. Abre Editar cliente para actualizarlo.')
    code=self.next_customer_code(db,company)
   value['codigo']=code
   channels=data.get('canales',(json.loads(old[3]).get('canales',['ventasins','expendios']) if old else [channel]))
   if not isinstance(channels,list) or not channels or set(channels)-CHANNELS:raise ValueError('Selecciona uno o ambos canales del cliente.')
   previous_channels=set(json.loads(old[3]).get('canales',['ventasins','expendios'])) if old else set()
   for ch in set(channels)^previous_channels:self.action(actor,ch,'clientes')
   value['canales']=list(dict.fromkeys(channels))
   if id:db.execute('UPDATE cm_customers SET code=?,revision=revision+1,payload=? WHERE id=?',(code,dumps(value),id))
   else:id=uuid.uuid4().hex;db.execute('INSERT INTO cm_customers VALUES(?,?,?,?,1,?)',(id,company,code,actor['email'],dumps(value)))
   self.audit(db,actor,company,'cliente_guardado',{'id':id})
  return {'ok':True,'id':id}
 def next_customer_code(self,db,company):
  db.execute("INSERT OR IGNORE INTO cm_sequences VALUES(?,'CLIENTE','CLIENTES',1,6,1)",(company,));number=db.execute("SELECT next FROM cm_sequences WHERE company=? AND kind='CLIENTE'",(company,)).fetchone()[0]
  while True:
   if number>999999999:raise ValueError('Se agotó el consecutivo de clientes.')
   code='CLI'+str(company).zfill(2)+'-'+str(number).zfill(6);number+=1
   if not db.execute('SELECT 1 FROM cm_customers WHERE company=? AND code=?',(company,code)).fetchone():break
  db.execute("UPDATE cm_sequences SET next=?,revision=revision+1 WHERE company=? AND kind='CLIENTE'",(number,company));return code
 def customer(self,db,id,company,actor,channel='ventasins'):
  if not id:return None
  row=db.execute('SELECT payload,company,creator FROM cm_customers WHERE id=?',(id,)).fetchone()
  if not row or row[1]!=company:raise PermissionError('Cliente no disponible en esta razón social.')
  value=json.loads(row[0])
  if channel not in value.get('canales',['ventasins','expendios']):raise ValueError('El cliente no está habilitado para este canal.')
  if not value.get('activo'):raise ValueError('Cliente inactivo.')
  return {'id':id,**value}
 def save_price(self,data,actor):
  self.admin(actor);company=data.get('empresa');self.company(company,actor,True);sku=data.get('sku');list=data.get('lista');customer=data.get('cliente') or '';price=amount(data.get('precio'));rev=data.get('revision',0)
  if list not in LISTS or customer and list!='PUBLICO':raise ValueError('Lista inválida. Tarifas por cliente: institucional público.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if not db.execute('SELECT 1 FROM cm_products WHERE sku=?',(sku,)).fetchone():raise ValueError('SKU no disponible.')
   if customer:self.customer(db,customer,company,actor)
   old=db.execute('SELECT revision FROM cm_prices WHERE company=? AND list=? AND sku=? AND customer=?',(company,list,sku,customer)).fetchone()
   if (old[0] if old else 0)!=rev:raise Conflict('El precio cambió. Actualiza los precios.')
   db.execute('INSERT INTO cm_prices VALUES(?,?,?,?,?,?) ON CONFLICT(company,list,sku,customer) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(company,list,sku,customer,(old[0] if old else 0)+1,dumps({'precio':format(price,'f'),'origen':'CLIENTE' if customer else 'MANUAL','fecha':now()})))
   self.audit(db,actor,company,'precio_guardado',{'sku':sku,'lista':list,'cliente':customer})
  return {'ok':True}
 def prices(self,company,actor):
  self.admin(actor);self.company(company,actor)
  with self.store.connect() as db:rows=db.execute('SELECT list,sku,customer,revision,payload FROM cm_prices WHERE company=? ORDER BY list,sku',(company,)).fetchall()
  return {'precios':[{'lista':l,'sku':s,'cliente':c,'revision':r,**json.loads(p)} for l,s,c,r,p in rows]}
 def templates(self,company,actor):
  self.module(actor,'ventasins');self.company(company,actor)
  with self.store.connect() as db:rows=db.execute('SELECT id,creator,revision,payload FROM cm_templates WHERE company=?',(company,)).fetchall()
  return {'plantillas':[{'id':id,'revision':rev,**json.loads(p)} for id,creator,rev,p in rows if actor['role'] in SUPERVISORS|{'ventasins'} or creator==actor['email']]}
 def save_template(self,data,actor):
  self.module(actor,'ventasins')
  if actor['role'] not in ADMINS|{'gerente'}:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador administran plantillas.')
  company=data.get('empresa');self.company(company,actor,True);name=text(data.get('nombre',''),160);lines=data.get('partidas');id=data.get('id');customer=data.get('cliente') or ''
  if not name or not isinstance(lines,list) or not 1<=len(lines)<=200:raise ValueError('Indica nombre y partidas de la plantilla.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');self.customer(db,customer,company,actor);prepared=[]
   for line in lines:
    product=db.execute('SELECT payload FROM cm_products WHERE sku=?',(line.get('sku'),)).fetchone()
    if not product or not json.loads(product[0]).get('institucional',True):raise ValueError('SKU inválido para una plantilla institucional.')
    prepared.append({'sku':line['sku'],'cantidad':format(amount(line.get('cantidad'),True),'f'),'observaciones':text(line.get('observaciones',''),500)})
   value={'nombre':name,'cliente':customer,'partidas':prepared,'condiciones':text(data.get('condiciones',''),1000)}
   old=db.execute('SELECT company,creator,revision FROM cm_templates WHERE id=?',(id,)).fetchone() if id else None
   if id and (not old or old[0]!=company or actor['role'] not in SUPERVISORS and old[1]!=actor['email']):raise PermissionError('Plantilla no disponible.')
   if data.get('revision',0)!=(old[2] if old else 0):raise Conflict('La plantilla cambió.')
   if id:db.execute('UPDATE cm_templates SET revision=revision+1,payload=? WHERE id=?',(dumps(value),id))
   else:id=uuid.uuid4().hex;db.execute('INSERT INTO cm_templates VALUES(?,?,?,1,?)',(id,company,actor['email'],dumps(value)))
   self.audit(db,actor,company,'plantilla_guardada',{'id':id})
  return {'ok':True,'id':id}
 def sequence(self,db,company,kind):
  default=('PED' if kind=='PEDIDO' else 'COT' if kind=='PRESUPUESTO' else 'INT' if kind.startswith('INT') else 'CAN' if kind=='CANCELACION' else 'TPV')+'-RS'+str(company).zfill(2)
  if kind.startswith(('TPV:','INT:')):default+='-'+kind.split(':')[1][:6].upper()
  db.execute('INSERT OR IGNORE INTO cm_sequences VALUES(?,?,?,1,6,1)',(company,kind,default));row=db.execute('SELECT series,next,width,revision FROM cm_sequences WHERE company=? AND kind=?',(company,kind)).fetchone()
  db.execute('INSERT OR IGNORE INTO cm_sequence_registry VALUES(?,?,?)',(company,row[0],kind))
  return dict(zip(('serie','siguiente','ancho','revision'),row))
 def next_number(self,db,company,kind):
  s=self.sequence(db,company,kind)
  if s['siguiente']>999999999:raise ValueError('Se agotaron los folios. Configura otra serie.')
  db.execute('UPDATE cm_sequences SET next=next+1,revision=revision+1 WHERE company=? AND kind=?',(company,kind))
  return s['serie']+'-'+str(s['siguiente']).zfill(s['ancho'])
 def sequences(self,company,actor):
  self.admin(actor);self.company(company,actor)
  with self.store.connect() as db:
   values=[{'tipo':kind,**self.sequence(db,company,kind)} for kind in ('PRESUPUESTO','PEDIDO')]
  return {'series':values}
 def save_sequence(self,data,actor):
  self.admin(actor);company=data.get('empresa');self.company(company,actor,True);kind=data.get('tipo');series=text(data.get('serie',''),35).upper();n=data.get('siguiente');width=data.get('ancho',6)
  if kind not in ('PEDIDO','PRESUPUESTO') or not re.fullmatch('[A-Z0-9][A-Z0-9-]{1,34}',series) or type(n) is not int or not 1<=n<=999999999 or type(width) is not int or not 1<=width<=12:raise ValueError('Serie, inicial o ancho inválidos.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=self.sequence(db,company,kind)
   if data.get('revision')!=old['revision']:raise Conflict('Se emitió un folio o cambió la serie. Actualiza.')
   if n<old['siguiente']:raise ValueError('El siguiente folio no puede retroceder ni reutilizar números.')
   registered=db.execute('SELECT kind FROM cm_sequence_registry WHERE company=? AND series=?',(company,series)).fetchone()
   if registered and (registered[0]!=kind or series!=old['serie']):raise ValueError('Esa serie está reservada; utiliza una nueva.')
   db.execute('INSERT OR IGNORE INTO cm_sequence_registry VALUES(?,?,?)',(company,series,kind));db.execute('UPDATE cm_sequences SET series=?,next=?,width=?,revision=revision+1 WHERE company=? AND kind=?',(series,n,width,company,kind));self.audit(db,actor,company,'serie_guardada',data)
  return {'ok':True}
 def boxes(self,company,actor):
  self.module(actor,'expendios');co=self.company(company,actor);access=self.access(actor)
  with self.store.connect() as db:rows=db.execute('SELECT id,branch,revision,payload FROM cm_boxes WHERE company=? ORDER BY code',(company,)).fetchall();sessions={r[0]:{'id':r[1],'operador':r[2],'revision':r[3],**json.loads(r[4])} for r in db.execute("SELECT box,id,operator,revision,payload FROM cm_sessions WHERE company=? AND state='ABIERTA'",(company,))}
  return {'cajas':[{'id':id,'revision':rev,**json.loads(p),'sesion':sessions.get(id)} for id,branch,rev,p in rows if actor['role'] in ADMINS or id in access['cajas'] and branch in access['sucursales']]}
 def box(self,db,id,company,actor,active=False):
  row=db.execute('SELECT company,branch,revision,payload FROM cm_boxes WHERE id=?',(id,)).fetchone()
  if not row or row[0]!=company:raise PermissionError('Caja no disponible para esta razón social.')
  if actor['role'] not in ADMINS and id not in self.access(actor)['cajas']:raise PermissionError('No tienes acceso a esta caja.')
  co=self.company(company,actor,active,db);self.branch(co,row[1],actor);box={'id':id,'revision':row[2],**json.loads(row[3])}
  if active and not box['activa']:raise ValueError('Caja inactiva.')
  return box
 def save_box(self,data,actor):
  self.admin(actor);company=data.get('empresa');co=self.company(company,actor,True);branch=data.get('sucursal');self.branch(co,branch,actor);id=data.get('id');code=text(data.get('codigo',''),24).upper();name=text(data.get('nombre',''),160);listing=data.get('lista','DESPACHO')
  if not re.fullmatch('[A-Z0-9][A-Z0-9-]{0,23}',code) or not name or listing not in ('RUTA','DESPACHO'):raise ValueError('Código, nombre o lista de caja inválidos.')
  settings={'mostrarLogo':data.get('mostrarLogo',True) is True,'mostrarSucursal':data.get('mostrarSucursal',True) is True}
  value={'codigo':code,'nombre':name,'sucursal':branch,'lista':listing,'activa':data.get('activa',True) is True,'ticket':settings}
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT company,revision FROM cm_boxes WHERE id=?',(id,)).fetchone() if id else None
   if id and (not old or old[0]!=company):raise PermissionError('Caja de otra razón social.')
   if data.get('revision',0)!=(old[1] if old else 0):raise Conflict('La caja cambió.')
   if id and db.execute("SELECT 1 FROM cm_sessions WHERE box=? AND state='ABIERTA'",(id,)).fetchone():
    previous=json.loads(db.execute('SELECT payload FROM cm_boxes WHERE id=?',(id,)).fetchone()[0])
    if previous['sucursal']!=branch:raise ValueError('Cierra la sesión antes de cambiar la sucursal de una caja.')
    if not value['activa']:raise ValueError('Cierra la sesión antes de desactivar la caja.')
   if id:db.execute('UPDATE cm_boxes SET branch=?,code=?,revision=revision+1,payload=? WHERE id=?',(branch,code,dumps(value),id))
   else:id=uuid.uuid4().hex;db.execute('INSERT INTO cm_boxes VALUES(?,?,?,?,1,?)',(id,company,branch,code,dumps(value)))
   self.audit(db,actor,company,'caja_guardada',{'id':id})
  return {'ok':True,'id':id}
 def open_session(self,data,actor):
  self.action(actor,'expendios','caja');company=data.get('empresa');mode='TICKETS' if data.get('modo')=='TICKETS' else 'CAJA';fund=D(0) if mode=='TICKETS' else amount(data.get('fondo','0'))
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');box=self.box(db,data.get('caja'),company,actor,True)
   old=db.execute("SELECT id,operator,payload,revision FROM cm_sessions WHERE box=? AND state='ABIERTA'",(box['id'],)).fetchone()
   if old:
    if old[1]!=actor['email'] and actor['role'] not in SUPERVISORS:raise PermissionError('La caja está abierta por otro usuario.')
    return {'id':old[0],'revision':old[3],**json.loads(old[2])}
   id=uuid.uuid4().hex;value={'caja':box['id'],'sucursal':box['sucursal'],'operador':actor['email'],'fechaApertura':now(),'fondo':money(fund),'estado':'ABIERTA','modo':mode}
   db.execute('INSERT INTO cm_sessions VALUES(?,?,?,?,?,1,?)',(id,company,box['id'],actor['email'],'ABIERTA',dumps(value)));self.audit(db,actor,company,'apertura_caja',{'sesion':id,'fondo':money(fund)})
  return {'id':id,'revision':1,**value}
 def session(self,db,id,company,actor,active=True):
  row=db.execute('SELECT box,operator,state,revision,payload,company FROM cm_sessions WHERE id=?',(id,)).fetchone()
  if not row or row[5]!=company:raise PermissionError('Sesión de caja inválida.')
  box=self.box(db,row[0],company,actor,active)
  if row[1]!=actor['email'] and actor['role'] not in SUPERVISORS:raise PermissionError('No puedes operar la sesión de otro usuario.')
  if active and row[2]!='ABIERTA':raise Conflict('La sesión ya está cerrada.')
  return {'id':id,'revision':row[3],**json.loads(row[4])},box
 def cash_summary(self,db,id):
  session=json.loads(db.execute('SELECT payload FROM cm_sessions WHERE id=?',(id,)).fetchone()[0]);expected=amount(session['fondo']);paid=D(0);refund=D(0)
  for p, in db.execute('SELECT payload FROM cm_documents WHERE session=?',(id,)):
   doc=json.loads(p)
   if doc.get('modo')=='TICKETS':continue
   paid+=amount(doc['total'])
   if doc['pago']['metodo']=='EFECTIVO':expected+=amount(doc['total'])
  for p, in db.execute('SELECT payload FROM cm_cash_moves WHERE session=?',(id,)):
   move=json.loads(p);refund+=amount(move['importe'])
   if move['metodo']=='EFECTIVO':expected-=amount(move['importe'])
  return {'fondo':session['fondo'],'cobrado':money(paid),'reembolsado':money(refund),'efectivoEsperado':money(expected)}
 def close_session(self,data,actor):
  self.action(actor,'expendios','caja');company=data.get('empresa');note=text(data.get('observaciones',''),1000)
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');session,box=self.session(db,data.get('sesion'),company,actor)
   count=D(0) if session.get('modo')=='TICKETS' else amount(data.get('contado'))
   if data.get('revision')!=session['revision']:raise Conflict('La caja cambió. Actualiza para cerrar.')
   summary=self.cash_summary(db,session['id']);value={**session,**summary,'estado':'CERRADA','fechaCierre':now(),'cerradoPor':actor['email'],'contado':money(count),'diferencia':money(count-D(summary['efectivoEsperado'])),'observaciones':note}
   value.pop('id',None);value.pop('revision',None)
   db.execute('UPDATE cm_sessions SET state=?,revision=revision+1,payload=? WHERE id=?',('CERRADA',dumps(value),session['id']));self.audit(db,actor,company,'cierre_caja',{'sesion':session['id'],**summary,'contado':money(count)})
  return {'ok':True,**value}
 def sessions(self,company,actor):
  self.module(actor,'expendios');self.company(company,actor)
  with self.store.connect() as db:
   rows=db.execute('SELECT id,box,operator,revision,payload FROM cm_sessions WHERE company=? ORDER BY rowid DESC LIMIT 300',(company,)).fetchall();result=[]
   for id,box,operator,rev,p in rows:
    try:self.box(db,box,company,actor)
    except PermissionError:continue
    if operator!=actor['email'] and actor['role'] not in SUPERVISORS:continue
    result.append({'id':id,'revision':rev,**json.loads(p),**self.cash_summary(db,id)})
  return {'sesiones':result}

 def prepare(self,db,data,actor,channel,company,box=None):
  issuer=self.company(company,actor,True,db);branch=box['sucursal'] if box else data.get('sucursal');self.branch(issuer,branch,actor)
  customer=self.customer(db,data.get('cliente'),company,actor,channel);lines=data.get('partidas');listing=box['lista'] if box else 'PUBLICO'
  if not isinstance(lines,list) or not 1<=len(lines)<=200:raise ValueError('Agrega de 1 a 200 partidas.')
  result=[]
  for line in lines:
   sku=line.get('sku');row=db.execute('SELECT payload,revision FROM cm_products WHERE sku=?',(sku,)).fetchone()
   if not row:raise ValueError('SKU no encontrado: '+str(sku))
   product=json.loads(row[0])
   if not product.get('activo') or channel=='expendios' and not product.get('expendio') or channel=='ventasins' and not product.get('institucional',True):raise ValueError('Producto no disponible para este canal: '+sku)
   if product.get('iva') is None:raise ValueError('Completa el IVA pendiente del producto '+sku+' antes de venderlo.')
   price=db.execute('SELECT payload,revision FROM cm_prices WHERE company=? AND list=? AND sku=? AND customer=?',(company,listing,sku,customer['id'] if customer and channel=='ventasins' else '')).fetchone()
   if not price:price=db.execute('SELECT payload,revision FROM cm_prices WHERE company=? AND list=? AND sku=? AND customer=?',(company,listing,sku,'')).fetchone()
   if not price:raise ValueError('El SKU no tiene precio en la lista de esta razón social: '+sku)
   price_value=json.loads(price[0]);unit_price=line.get('precio',price_value['precio']) if channel=='ventasins' and actor['role']!='ventaspasteleria' else price_value['precio']
   if channel=='expendios' and (line.get('precioVisto') is not None and amount(line['precioVisto'])!=amount(unit_price) or line.get('ivaVisto') is not None and amount(line['ivaVisto'])!=amount(product['iva'])):raise Conflict('Cambió el precio o IVA de '+sku+'. Actualiza los productos y revisa el total antes de cobrar.')
   value=tax_line(line.get('cantidad'),unit_price,product['iva'],line.get('descuento','0') if channel=='ventasins' and actor['role']!='ventaspasteleria' else '0')
   result.append({'sku':sku,'nombre':product['nombre'],'unidad':product['unidad'],'nota':text(line.get('nota',''),500),'revisionProducto':row[1],'revisionPrecio':price[1],**value})
  return {'empresa':company,'emisor':issuer,'sucursal':branch,'cliente':customer,'lista':listing,'partidas':result,'observaciones':text(data.get('observaciones',''),10000),'condiciones':text(data.get('condiciones',''),2000),'base':money(sum(D(r['base']) for r in result)),'impuesto':money(sum(D(r['impuesto']) for r in result)),'total':money(sum(D(r['total']) for r in result))}
 def document(self,db,id,actor,channel):
  self.module(actor,channel);row=db.execute('SELECT company,channel,creator,box,revision,payload FROM cm_documents WHERE id=?',(id,)).fetchone()
  if not row or row[1]!=channel:raise ValueError('Documento no encontrado.')
  self.company(row[0],actor);value=json.loads(row[5]);self.branch(value['emisor'],value['sucursal'],actor)
  if channel=='ventasins':value.setdefault('bloqueado',value.get('tipo')=='PEDIDO')
  if channel=='expendios':
   box=self.box(db,row[3],row[0],actor);value.setdefault('cajaNombre',box['nombre']);value.setdefault('cajaCodigo',box['codigo'])
  if actor['role'] not in SUPERVISORS and row[2]!=actor['email']:raise PermissionError('Solo puedes consultar tus documentos.')
  return {'id':id,'revision':row[4],**value}
 def get_document(self,id,actor,channel):
  with self.store.connect() as db:return self.document(db,id,actor,channel)
 def documents(self,company,actor,channel,filters=None):
  self.module(actor,channel);self.company(company,actor);f=filters or {};result=[]
  start=iso_date(f.get('desde'));end=iso_date(f.get('hasta'))
  if start and end and start>end:raise ValueError('La fecha inicial no puede ser posterior a la final.')
  if f.get('campoFecha','emision') not in ('','emision','pedido','entrega'):raise ValueError('Filtro de fecha inválido.')
  with self.store.connect() as db:
   for id, in db.execute('SELECT id FROM cm_documents WHERE company=? AND channel=? ORDER BY created DESC',(company,channel)):
    try:value=self.document(db,id,actor,channel)
    except PermissionError:continue
    date_value=value.get('fechaEntrega','') if f.get('campoFecha')=='entrega' else value.get('fechaPedido',value['fecha'][:10]) if f.get('campoFecha')=='pedido' else value['fecha'][:10]
    if (start or end) and not date_value or start and date_value<start or end and date_value>end:continue
    if f.get('producto') and not any(f['producto'].upper() in (line['sku']+' '+line['nombre']).upper() for line in value['partidas']):continue
    if f.get('estado') and value['estado']!=f['estado'] or f.get('sucursal') and value['sucursal']!=f['sucursal']:continue
    if f.get('caja') and value.get('caja')!=f['caja']:continue
    if f.get('cliente') and (value.get('cliente') or {}).get('id')!=f['cliente']:continue
    result.append(value)
  totals={k:money(sum(D(v[k]) for v in result if v['estado']!='CANCELADO')) for k in ('base','impuesto','total')}
  return {'documentos':result,'totales':totals,'cantidad':len(result)}
 def persist(self,db,value,actor,channel,key,hash,old=None):
  id=old['id'] if old else uuid.uuid4().hex;revision=old['revision']+1 if old else 1
  payload={k:v for k,v in value.items() if k not in ('id','revision')}
  if old:
   db.execute('INSERT INTO cm_versions VALUES(?,?,?)',(id,old['revision'],dumps(old)))
   db.execute('UPDATE cm_documents SET state=?,number=?,revision=?,payload=? WHERE id=?',(value['estado'],value['folio'],revision,dumps(payload),id))
  else:db.execute('INSERT INTO cm_documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(id,value['empresa'],channel,actor['email'],value.get('caja',''),value.get('sesion',''),value['estado'],value['folio'],value['fecha'],key,hash,revision,dumps(payload)))
  self.audit(db,actor,value['empresa'],'documento_guardado',{'id':id,'canal':channel,'estado':value['estado']})
  return {'ok':True,'documento':{'id':id,'revision':revision,**payload}}
 def save_order(self,data,actor):
  self.action(actor,'ventasins','pedidos');company=data.get('empresa');key=str(data.get('clave',''));id=data.get('id')
  if not id and not re.fullmatch('[a-zA-Z0-9_-]{16,100}',key):raise ValueError('Falta la clave única del envío.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=self.document(db,id,actor,'ventasins') if id else None;hash=fingerprint(data)
   if old and (old['empresa']!=company or data.get('revision')!=old['revision']):raise Conflict('El pedido cambió. Actualiza antes de guardar.')
   if old and actor['role']=='ventaspasteleria':raise PermissionError('VENTASPASTELERIA solo captura nuevos documentos y consulta su historial.')
   if old and old.get('bloqueado'):raise ValueError('El pedido está bloqueado. Solicita el desbloqueo antes de modificarlo.')
   if old and old['estado']=='CANCELADO':raise ValueError('Un documento cancelado conserva su historial y no puede modificarse.')
   if not old:
    repeat=db.execute("SELECT id,fingerprint FROM cm_documents WHERE creator=? AND channel='ventasins' AND client_key=?",(actor['email'],key)).fetchone()
    if repeat:
     if repeat[1]!=hash:raise Conflict('La clave del envío ya se usó con otro contenido.')
     return {'ok':True,'repetido':True,'documento':self.document(db,repeat[0],actor,'ventasins')}
   value=self.prepare(db,data,actor,'ventasins',company);kind=data.get('tipo','PRESUPUESTO')
   if kind not in ('PRESUPUESTO','PEDIDO'):raise ValueError('Selecciona presupuesto o pedido.')
   if old and old['tipo']=='PEDIDO' and kind!='PEDIDO':raise ValueError('Un pedido no puede volver a presupuesto.')
   pedido=iso_date(data.get('fechaPedido',(old or {}).get('fechaPedido',(old or {}).get('fecha',now())[:10])))
   entrega=iso_date(data.get('fechaEntrega',(old or {}).get('fechaEntrega','')))
   value.update({'fechaPedido':pedido or now()[:10],'fechaEntrega':entrega,'clienteOpcional':text(data.get('clienteOpcional',(old or {}).get('clienteOpcional','')),300)})
   number=old['folio'] if old and kind==old['tipo'] else self.next_number(db,company,kind)
   value.update({'bloqueado':True if kind=='PEDIDO' and (not old or old['tipo']!='PEDIDO') else (old or {}).get('bloqueado',False),'tipo':kind,'folio':number,'presupuestoOrigen':old['folio'] if old and old['tipo']=='PRESUPUESTO' and kind=='PEDIDO' else (old or {}).get('presupuestoOrigen',''),'estado':'PEDIDO' if kind=='PEDIDO' else 'PRESUPUESTO','fecha':old['fecha'] if old else now(),'modificado':now(),'creador':old['creador'] if old else actor['email']})
   return self.persist(db,value,actor,'ventasins',key,hash,old)
 def toggle_order_lock(self,data,actor):
  self.module(actor,'ventasins')
  if actor['role'] not in {'ventasins','gerente','auxti','superadmin'}:raise PermissionError('Tu perfil no puede bloquear o desbloquear pedidos.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');doc=self.document(db,data.get('id'),actor,'ventasins')
   if doc['revision']!=data.get('revision'):raise Conflict('El documento cambió. Actualiza.')
   if doc['estado']=='CANCELADO' or type(data.get('bloqueado')) is not bool:raise ValueError('No se puede cambiar el bloqueo de este documento.')
   before=copy.deepcopy(doc);doc['bloqueado']=data['bloqueado'];doc['bloqueo']={'actor':actor['email'],'fecha':now(),'bloqueado':doc['bloqueado']};self.audit(db,actor,doc['empresa'],'bloqueo_pedido',{'id':doc['id'],'bloqueado':doc['bloqueado']});return self.persist(db,doc,actor,'ventasins','','',before)
 def cancel_order(self,data,actor):
  self.action(actor,'ventasins','pedidos');reason=text(data.get('motivo',''),1000)
  if not reason:raise ValueError('Indica el motivo de cancelación.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=self.document(db,data.get('id'),actor,'ventasins')
   if data.get('revision')!=old['revision']:raise Conflict('El documento cambió.')
   if old.get('bloqueado'):raise ValueError('Desbloquea el pedido antes de cancelarlo.')
   if old['estado']=='CANCELADO':raise ValueError('El documento ya está cancelado.')
   return self.persist(db,{**old,'estado':'CANCELADO','cancelacion':{'motivo':reason,'autor':actor['email'],'fecha':now()}},actor,'ventasins','','',old)
 def checkout(self,data,actor):
  self.action(actor,'expendios','caja');company=data.get('empresa');key=str(data.get('clave',''));hash=fingerprint(data)
  if not re.fullmatch('[a-zA-Z0-9_-]{16,100}',key):raise ValueError('Falta la clave única del cobro.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');repeat=db.execute("SELECT id,fingerprint FROM cm_documents WHERE creator=? AND channel='expendios' AND client_key=?",(actor['email'],key)).fetchone()
   if repeat:
    if repeat[1]!=hash:raise Conflict('La clave del cobro ya fue utilizada con otro contenido.')
    return {'ok':True,'repetido':True,'documento':self.document(db,repeat[0],actor,'expendios')}
   session,box=self.session(db,data.get('sesion'),company,actor);value=self.prepare(db,data,actor,'expendios',company,box);ticket_only=session.get('modo')=='TICKETS' or data.get('soloTicket') is True;method='TICKET' if ticket_only else data.get('metodo');received=D(0) if ticket_only else amount(data.get('recibido','0'));total=D(value['total'])
   if method not in (('TICKET',) if ticket_only else ('EFECTIVO','TARJETA','TRANSFERENCIA')):raise ValueError('Método de pago inválido.')
   if method=='EFECTIVO' and received<total:raise ValueError('El efectivo recibido es menor al total.')
   value.update({'tipo':'VENTA','folio':self.next_number(db,company,'TPV:'+box['id']),'folioInterno':self.next_number(db,company,'INT:'+box['id']),'estado':'EMITIDA' if ticket_only else 'PAGADA','modo':'TICKETS' if ticket_only else 'COBRO','fecha':now(),'creador':actor['email'],'caja':box['id'],'cajaNombre':box['nombre'],'cajaCodigo':box['codigo'],'sesion':session['id'],'ticket':box['ticket'],'pago':{'metodo':method,'recibido':'0.00' if ticket_only else money(received) if method=='EFECTIVO' else value['total'],'cambio':money(received-total) if method=='EFECTIVO' else '0.00'},'reembolso':'NO APLICA'})
   db.execute('UPDATE cm_sessions SET revision=revision+1 WHERE id=?',(session['id'],))
   return self.persist(db,value,actor,'expendios',key,hash)
 def request_cancel(self,data,actor):
  self.action(actor,'expendios','caja');reason=text(data.get('motivo',''),1000)
  if not reason:raise ValueError('Indica el motivo de cancelación.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');doc=self.document(db,data.get('id'),actor,'expendios')
   if doc['estado'] not in ('PAGADA','EMITIDA'):raise ValueError('Solo se puede solicitar cancelación de ventas o tickets emitidos.')
   if doc['revision']!=data.get('revision'):raise Conflict('La venta cambió.')
   id=uuid.uuid4().hex;value={'folio':self.next_number(db,doc['empresa'],'CANCELACION'),'documento':doc['id'],'folioVenta':doc['folio'],'motivo':reason,'solicitante':actor['email'],'fecha':now(),'revisionDocumento':doc['revision']}
   db.execute('INSERT INTO cm_cancellations VALUES(?,?,?,?,?,1,?)',(id,doc['empresa'],doc['id'],actor['email'],'PENDIENTE',dumps(value)));self.audit(db,actor,doc['empresa'],'cancelacion_solicitada',value)
   return {'ok':True,'solicitud':{'id':id,'estado':'PENDIENTE','revision':1,**value}}
 def cancellations(self,company,actor):
  self.module(actor,'expendios');self.company(company,actor);result=[]
  with self.store.connect() as db:
   for id,doc,requester,state,rev,p in db.execute("SELECT c.id,c.document,c.requester,c.state,c.revision,c.payload FROM cm_cancellations c JOIN cm_documents d ON d.id=c.document WHERE c.company=? AND d.channel='expendios' ORDER BY c.rowid DESC",(company,)):
    if actor['role'] not in ADMINS and requester!=actor['email']:continue
    try:self.document(db,doc,actor,'expendios')
    except PermissionError:continue
    result.append({'id':id,'estado':state,'revision':rev,**json.loads(p)})
  return {'solicitudes':result}
 def decide_cancel(self,data,actor):
  self.admin(actor);self.module(actor,'expendios');approve=data.get('aprobar')
  if type(approve) is not bool:raise ValueError('Indica aprobar o rechazar.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT company,document,state,revision,payload FROM cm_cancellations WHERE id=?',(data.get('id'),)).fetchone()
   if not row:raise ValueError('Solicitud no encontrada.')
   if row[2]!='PENDIENTE' or row[3]!=data.get('revision'):raise Conflict('La solicitud ya cambió.')
   value=json.loads(row[4]);doc=self.document(db,row[1],actor,'expendios')
   if doc['revision']!=value['revisionDocumento'] or doc['estado'] not in ('PAGADA','EMITIDA'):raise Conflict('La venta cambió. Revisa la solicitud.')
   if approve:self.persist(db,{**doc,'estado':'CANCELADO','cancelacion':{'autor':actor['email'],'fecha':now(),'motivo':value['motivo'],'solicitud':data['id']},'reembolso':'NO APLICA' if doc.get('modo')=='TICKETS' else 'PENDIENTE'},actor,'expendios','','',doc)
   value.update({'resueltoPor':actor['email'],'resuelto':now(),'observaciones':text(data.get('observaciones',''),1000)})
   db.execute('UPDATE cm_cancellations SET state=?,revision=revision+1,payload=? WHERE id=?',('APROBADA' if approve else 'RECHAZADA',dumps(value),data['id']));self.audit(db,actor,row[0],'cancelacion_resuelta',{'id':data['id'],'aprobada':approve})
  return {'ok':True}
 def refund(self,data,actor):
  self.admin(actor);self.module(actor,'expendios')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');doc=self.document(db,data.get('id'),actor,'expendios')
   if data.get('revision')!=doc['revision']:raise Conflict('La venta cambió.')
   if doc['estado']!='CANCELADO' or doc['reembolso']!='PENDIENTE':raise ValueError('Esta venta no tiene reembolso pendiente.')
   session,box=self.session(db,data.get('sesion'),doc['empresa'],actor)
   if box['id']!=doc['caja']:raise ValueError('Registra el reembolso en una sesión abierta de la misma caja.')
   value={'documento':doc['id'],'importe':doc['total'],'metodo':doc['pago']['metodo'],'fecha':now(),'autor':actor['email']}
   db.execute('INSERT INTO cm_cash_moves VALUES(?,?,?,?)',(uuid.uuid4().hex,doc['empresa'],session['id'],dumps(value)));db.execute('UPDATE cm_sessions SET revision=revision+1 WHERE id=?',(session['id'],))
   return self.persist(db,{**doc,'reembolso':'REALIZADO','devolucion':value},actor,'expendios','','',doc)

 def institutional_cancel_requests(self,company,actor):
  self.module(actor,'ventasins');self.company(company,actor);result=[]
  with self.store.connect() as db:
   for id,doc,who,state,revision,payload in db.execute("SELECT c.id,c.document,c.requester,c.state,c.revision,c.payload FROM cm_cancellations c JOIN cm_documents d ON d.id=c.document WHERE c.company=? AND d.channel='ventasins' ORDER BY c.rowid DESC",(company,)):
    try:self.document(db,doc,actor,'ventasins')
    except PermissionError:continue
    result.append({'id':id,'estado':state,'revision':revision,**json.loads(payload)})
  return {'solicitudes':result}
 def request_institutional_cancel(self,data,actor):
  self.action(actor,'ventasins','pedidos');reason=text(data.get('motivo',''),3000)
  if not reason:raise ValueError('Indica el motivo de la cancelación solicitada.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');doc=self.document(db,data.get('id'),actor,'ventasins')
   if doc['estado']=='CANCELADO':raise ValueError('El documento ya está cancelado.')
   if doc['revision']!=data.get('revision'):raise Conflict('El documento cambió. Actualiza antes de solicitar.')
   old=db.execute("SELECT id,revision,payload FROM cm_cancellations WHERE document=? AND state='PENDIENTE'",(doc['id'],)).fetchone()
   if old:return {'ok':True,'repetido':True,'solicitud':{'id':old[0],'revision':old[1],'estado':'PENDIENTE',**json.loads(old[2])}}
   id=uuid.uuid4().hex;value={'folio':self.next_number(db,doc['empresa'],'CANCELACION'),'canal':'ventasins','documento':doc['id'],'folioVenta':doc['folio'],'motivo':reason,'solicitante':actor['email'],'fecha':now(),'revisionDocumento':doc['revision']};db.execute('INSERT INTO cm_cancellations VALUES(?,?,?,?,?,1,?)',(id,doc['empresa'],doc['id'],actor['email'],'PENDIENTE',dumps(value)));self.audit(db,actor,doc['empresa'],'cancelacion_institucional_solicitada',value);return {'ok':True,'solicitud':{'id':id,'revision':1,'estado':'PENDIENTE',**value}}
 def decide_institutional_cancel(self,data,actor):
  self.module(actor,'ventasins')
  if actor['role'] not in ADMINS|{'gerente'}:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador autorizan cancelaciones institucionales.')
  approve=data.get('aprobar')
  if type(approve) is not bool:raise ValueError('Selecciona aprobar o rechazar.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT company,document,state,revision,payload FROM cm_cancellations WHERE id=?',(data.get('id'),)).fetchone()
   if not row or row[2]!='PENDIENTE' or row[3]!=data.get('revision'):raise Conflict('La solicitud no está pendiente o cambió.')
   doc=self.document(db,row[1],actor,'ventasins');value=json.loads(row[4]);value.update({'resueltoPor':actor['email'],'fechaResolucion':now(),'comentario':text(data.get('comentario',''),3000)})
   if approve:
    if doc['revision']!=value['revisionDocumento'] or doc['estado']=='CANCELADO':raise Conflict('El documento cambió. Rechaza esta solicitud y pide una nueva.')
    before=copy.deepcopy(doc);doc['estado']='CANCELADO';doc['cancelacion']={'motivo':value['motivo'],'autor':actor['email'],'solicitadoPor':value['solicitante'],'fecha':now(),'solicitud':data['id']};self.persist(db,doc,actor,'ventasins','','',before)
   db.execute('UPDATE cm_cancellations SET state=?,revision=revision+1,payload=? WHERE id=?',('APROBADA' if approve else 'RECHAZADA',dumps(value),data['id']));self.audit(db,actor,row[0],'cancelacion_institucional_resuelta',{'id':data['id'],'aprobada':approve})
  return {'ok':True}
