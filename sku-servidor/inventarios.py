"""Existencias por razón social/sucursal y diario inmutable en unidad de entrega."""
import copy,json,re,uuid
from decimal import Decimal,InvalidOperation
from permissions import require_module
from requisiciones import BRANCHES,Conflict,now,text,visible_branches
from comercial import dumps,fingerprint
from clientes_comerciales import read_table
from ventas import norm

APPROVERS={'gerente','superadmin','auxti'}
OPERATORS=APPROVERS|{'almacenista','compras'}
HEADERS=['SKU','DESCRIPCION','UNIDAD_ENTREGA','FISICO']

def dec(value,positive=False):
 if isinstance(value,bool) or value is None or str(value).strip()=='':raise ValueError('Cantidad/costo requerido; una celda vacía no equivale a cero.')
 try:n=Decimal(str(value))
 except InvalidOperation:raise ValueError('Cantidad o costo inválido.')
 if not n.is_finite() or n<0 or n>Decimal('999999999999') or n.as_tuple().exponent < -6 or positive and n==0:raise ValueError('Usa valores no negativos con hasta seis decimales.')
 return n
def fmt(n):return format(n.quantize(Decimal('.000001')),'f').rstrip('0').rstrip('.') if n else '0'

class InventoryStore:
 def __init__(self,store,po):
  self.store=store;self.po=po
  with store.connect() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS inv_warehouses(id TEXT PRIMARY KEY,company INTEGER NOT NULL,branch TEXT NOT NULL,cycle INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,UNIQUE(company,branch));
CREATE TABLE IF NOT EXISTS inv_balances(warehouse TEXT NOT NULL,sku TEXT NOT NULL,unit TEXT NOT NULL,qty TEXT NOT NULL,cost TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(warehouse,sku));
CREATE TABLE IF NOT EXISTS inv_ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,warehouse TEXT NOT NULL,sku TEXT NOT NULL,source TEXT NOT NULL UNIQUE,created TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS inv_ledger_scope ON inv_ledger(warehouse,id);
CREATE TABLE IF NOT EXISTS inv_requests(id TEXT PRIMARY KEY,warehouse TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inv_transfers(id TEXT PRIMARY KEY,source TEXT NOT NULL,destination TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inv_keys(key TEXT PRIMARY KEY,hash TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS inv_ledger_no_update BEFORE UPDATE ON inv_ledger BEGIN SELECT RAISE(ABORT,'El diario de inventario es inmutable'); END;
CREATE TRIGGER IF NOT EXISTS inv_ledger_no_delete BEFORE DELETE ON inv_ledger BEGIN SELECT RAISE(ABORT,'El diario de inventario es inmutable'); END;''')
   marker='inventarios-v31'
   db.execute('CREATE TABLE IF NOT EXISTS inv_features(id TEXT PRIMARY KEY)')
   if not db.execute('SELECT 1 FROM inv_features WHERE id=?',(marker,)).fetchone():
    for role in OPERATORS:
     row=db.execute('SELECT modules FROM role_modules WHERE role=?',(role,)).fetchone()
     if row:
      modules=json.loads(row[0]);modules=list(dict.fromkeys(modules+['inventarios']));db.execute('UPDATE role_modules SET modules=?,revision=revision+1 WHERE role=?',(dumps(modules),role))
    db.execute('INSERT INTO inv_features VALUES(?)',(marker,))
 def sync(self,db):
  for company,payload in db.execute('SELECT id,payload FROM cm_companies').fetchall():
   for branch in json.loads(payload).get('sucursales',[]):
    if branch in BRANCHES:db.execute('INSERT OR IGNORE INTO inv_warehouses(id,company,branch) VALUES(?,?,?)',(str(company)+':'+branch,company,branch))
 def destination(self,db,id):
  row=db.execute('SELECT company,branch,active FROM inv_warehouses WHERE id=?',(id,)).fetchone()
  if not row:raise ValueError('Almacén destino inexistente.')
  co=db.execute('SELECT payload FROM cm_companies WHERE id=?',(row[0],)).fetchone()
  if not co or row[1] not in json.loads(co[0]).get('sucursales',[]) or not row[2]:raise ValueError('El destino requiere sucursal vinculada e inventario inicial autorizado.')
  return {'id':id,'empresa':row[0],'sucursal':row[1]}
 def scope(self,actor,warehouse=None,db=None,write=False):
  require_module(actor,'inventarios')
  if actor['role'] not in OPERATORS:raise PermissionError('Este perfil no puede consultar costos ni operar inventarios.')
  if db is None:
   with self.store.connect() as conn:return self.scope(actor,warehouse,conn,write)
  if warehouse is None:return
  row=db.execute('SELECT company,branch,cycle,active,revision FROM inv_warehouses WHERE id=?',(warehouse,)).fetchone()
  if not row:raise ValueError('Almacén inexistente; actualiza las razones sociales y sucursales.')
  access=self.po.access(actor,db)
  if actor['role'] not in {'superadmin','auxti'} and (row[0] not in access['empresas'] or row[1] not in access['sucursales'] or row[1] not in visible_branches(actor)):raise PermissionError('Almacén o razón social no asignados a tu cuenta.')
  co=db.execute('SELECT payload FROM cm_companies WHERE id=?',(row[0],)).fetchone()
  if write and (not co or row[1] not in json.loads(co[0]).get('sucursales',[])):raise Conflict('La sucursal ya no está vinculada a esta razón social.')
  return {'id':warehouse,'empresa':row[0],'sucursal':row[1],'ciclo':row[2],'activo':bool(row[3]),'revision':row[4]}
 def warehouses(self,actor):
  self.scope(actor)
  with self.store.connect() as db:
   self.sync(db);result=[];companies={i:json.loads(p).get('nombre','') for i,p in db.execute('SELECT id,payload FROM cm_companies')}
   for id, in db.execute('SELECT id FROM inv_warehouses ORDER BY company,branch').fetchall():
    try:w=self.scope(actor,id,db)
    except PermissionError:continue
    result.append({**w,'razonSocial':companies.get(w['empresa'],'')})
   destinations=[{'id':i,'sucursal':b,'razonSocial':companies.get(c,''),'activo':bool(a)} for i,c,b,a in db.execute('SELECT id,company,branch,active FROM inv_warehouses') if c in companies]
  return {'almacenes':result,'destinos':destinations,'puedeAutorizar':actor['role'] in APPROVERS,'puedeRestablecer':actor['role']=='superadmin'}
 def materials(self):
  # Catálogo central, no depende del acceso del actor a la pantalla de Compras.
  mods=['pedidoscompra']
  rows=self.po.materials({'role':'superadmin','email':'sistemas@grupomipan.com','modulos':mods})['materiales'];result={}
  for m in rows:
   if not m.get('activo') or not m['sku']:continue
   sku=m['sku'].upper()
   if sku in result:raise ValueError('El maestro contiene SKU duplicados; corrige el maestro antes de mover inventario.')
   cost=m.get('costoEntrega')
   if cost is None and m.get('precioCompra') is not None and m.get('factor'):cost=fmt(dec(m['precioCompra'])/dec(m['factor'],True))
   result[sku]={**m,'sku':sku,'unidad':m['unidadEntrega'],'costo':cost}
  return result
 def balance(self,db,w,sku):
  row=db.execute('SELECT unit,qty,cost,payload FROM inv_balances WHERE warehouse=? AND sku=?',(w,sku)).fetchone()
  return {'unidad':row[0],'cantidad':row[1],'costo':row[2],**json.loads(row[3])} if row else None
 def post(self,db,w,m,delta,cost,source,kind,actor,reference='',notes='',extra=None):
  if db.execute('SELECT 1 FROM inv_ledger WHERE source=?',(source,)).fetchone():raise Conflict('Este movimiento ya fue aplicado.')
  old=self.balance(db,w,m['sku']);q=Decimal(old['cantidad']) if old else Decimal(0);avg=Decimal(old['costo']) if old else Decimal(0)
  if old and norm(old['unidad'])!=norm(m['unidad']):raise Conflict('La unidad del maestro cambió. Resuelve la equivalencia antes de mover '+m['sku']+'.')
  after=q+delta
  if after<0:raise ValueError('Existencia insuficiente para '+m['sku']+': disponible '+fmt(q)+' '+m['unidad']+'.')
  applied=cost if delta>0 else avg
  if applied is None:raise ValueError('Falta costo de entrega del maestro para '+m['sku']+'.')
  applied=dec(fmt(applied));newcost=(q*avg+delta*applied)/after if delta>0 and after else avg
  snapshot={'materialId':m.get('materialId'),'nombre':m.get('nombre','')}
  db.execute('INSERT INTO inv_balances VALUES(?,?,?,?,?,?) ON CONFLICT(warehouse,sku) DO UPDATE SET qty=excluded.qty,cost=excluded.cost,payload=excluded.payload',(w,m['sku'],m['unidad'],fmt(after),fmt(newcost),dumps(snapshot)))
  cycle=db.execute('SELECT cycle FROM inv_warehouses WHERE id=?',(w,)).fetchone()[0];created=now();value={'sku':m['sku'],'nombre':m.get('nombre',''),'unidad':m['unidad'],'cantidad':fmt(delta),'antes':fmt(q),'despues':fmt(after),'costoUnitario':fmt(applied),'importe':fmt(delta*applied),'tipo':kind,'referencia':reference,'observaciones':notes,'actor':actor['email'],'fecha':created,'ciclo':cycle,**(extra or {})}
  cursor=db.execute('INSERT INTO inv_ledger(warehouse,sku,source,created,payload) VALUES(?,?,?,?,?)',(w,m['sku'],source,created,dumps(value)));db.execute('UPDATE inv_warehouses SET revision=revision+1 WHERE id=?',(w,));return {'id':cursor.lastrowid,**value}
 def state(self,w,actor):
  with self.store.connect() as db:
   info=self.scope(actor,w,db);rows=[{'sku':sku,'unidad':unit,'cantidad':q,'costo':c,'valor':fmt(Decimal(q)*Decimal(c)),**json.loads(p)} for sku,unit,q,c,p in db.execute('SELECT sku,unit,qty,cost,payload FROM inv_balances WHERE warehouse=? ORDER BY sku',(w,))]
   return {'almacen':info,'existencias':rows,'valorTotal':fmt(sum((Decimal(r['valor']) for r in rows),Decimal(0))),'movimientos':[{'id':i,**json.loads(p)} for i,p in db.execute('SELECT id,payload FROM inv_ledger WHERE warehouse=? ORDER BY id DESC LIMIT 1000',(w,))],'solicitudes':[json.loads(p) for p, in db.execute('SELECT payload FROM inv_requests WHERE warehouse=? ORDER BY rowid DESC LIMIT 500',(w,))]}
 def stamp(self,db,w):
  return fingerprint([list(db.execute('SELECT cycle,active,revision FROM inv_warehouses WHERE id=?',(w,)).fetchone()),[list(r) for r in db.execute('SELECT sku,unit,qty,cost FROM inv_balances WHERE warehouse=? ORDER BY sku',(w,))]])
 def repeat(self,db,data):
  key=data.get('clave','')
  if not isinstance(key,str) or not re.fullmatch('[A-Za-z0-9_-]{16,100}',key):raise ValueError('Falta identificador de operación.')
  old=db.execute('SELECT hash,payload FROM inv_keys WHERE key=?',(key,)).fetchone()
  if old:
   if old[0]!=fingerprint(data):raise Conflict('Identificador usado con datos diferentes.')
   return json.loads(old[1])
 def remember(self,db,data,result):db.execute('INSERT INTO inv_keys VALUES(?,?,?)',(data['clave'],fingerprint(data),dumps(result)));return result
 def count(self,data,actor):
  self.scope(actor);w=data.get('almacen');initial=data.get('inicial') is True;materials=self.materials();rows=read_table(data,'INVENTARIO_INICIAL') if 'contenido' in data else [HEADERS]+data.get('filas',[])
  if rows[0]!=HEADERS:raise ValueError('Conserva los encabezados SKU, DESCRIPCION, UNIDAD_ENTREGA, FISICO y la pestaña INVENTARIO_INICIAL.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');info=self.scope(actor,w,db,True);stamp=self.stamp(db,w)
   if not data.get('revisar'):
    repeat=self.repeat(db,data)
    if repeat:return repeat
   if initial and info['activo']:raise Conflict('Este almacén ya tiene inventario inicial. Usa un ajuste autorizado.')
   if not initial and not info['activo']:raise ValueError('Carga primero el inventario inicial autorizado.')
   prepared=[];seen=set();skipped=0
   for n,row in enumerate(rows[1:],2):
    if not any(str(x).strip() for x in row):continue
    if len(row)>4 and any(row[4:]):raise ValueError(f'Fila {n}: sobran columnas.')
    sku=str(row[0]).strip().upper();m=materials.get(sku)
    if not m or sku in seen:raise ValueError(f'Fila {n}: SKU inexistente, inactivo o repetido.')
    seen.add(sku)
    if len(row)<4 or str(row[3]).strip()=='':skipped+=1;continue
    if norm(str(row[1]))!=norm(m['nombre']) or norm(str(row[2]))!=norm(m['unidad']):raise ValueError(f'Fila {n}: descripción o unidad de entrega no coincide con el maestro.')
    qty=dec(row[3]);old=self.balance(db,w,sku);before=Decimal(old['cantidad']) if old else Decimal(0);cost=dec(m['costo']) if m['costo'] is not None else None
    if qty>before and cost is None:raise ValueError(f'Fila {n}: falta costo de entrega en el maestro.')
    prepared.append({'sku':sku,'nombre':m['nombre'],'unidad':m['unidad'],'materialId':m['materialId'],'fisico':fmt(qty),'antes':fmt(before),'diferencia':fmt(qty-before),'costo':fmt(cost) if cost is not None else old['costo'] if old else '0'})
   if not prepared:raise ValueError('No hay conteos físicos explícitos; las celdas vacías se omiten.')
   stamp=fingerprint([stamp,prepared]);review={'huellaActual':stamp,'partidas':prepared,'omitidasSinFisico':skipped,'inicial':initial}
   if data.get('revisar'):return review
   if data.get('huellaActual')!=stamp:raise Conflict('Cambió el inventario o el maestro. Revisa de nuevo antes de solicitar.')
   reason=text(data.get('motivo',''),2000)
   if not reason:raise ValueError('Escribe el motivo del inventario o ajuste.')
   id=uuid.uuid4().hex;value={'id':id,'almacen':w,'ciclo':info['ciclo'],'inicial':initial,'partidas':prepared,'estado':'PENDIENTE','solicitadoPor':actor['email'],'fecha':now(),'motivo':reason,'revisionAlmacen':info['revision']}
   db.execute('INSERT INTO inv_requests VALUES(?,?,?,?)',(id,w,'PENDIENTE',dumps(value)));return self.remember(db,data,{'ok':True,'solicitud':value})
 def decide(self,data,actor):
  self.scope(actor)
  if actor['role'] not in APPROVERS:raise PermissionError('Solo Gerencia, Superadministrador y AUXTI autorizan ajustes.')
  if type(data.get('aprobar')) is not bool:raise ValueError('Indica aprobar o rechazar.')
  comment=text(data.get('comentario',''),2000)
  if not comment:raise ValueError('Escribe el comentario de autorización.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM inv_requests WHERE id=?',(data.get('id'),)).fetchone()
   if not row:raise ValueError('Solicitud inexistente.')
   req=json.loads(row[0]);info=self.scope(actor,req['almacen'],db,True)
   if req['estado']!='PENDIENTE':raise Conflict('La solicitud ya fue resuelta.')
   if data['aprobar']:
    if info['ciclo']!=req['ciclo'] or info['revision']!=req['revisionAlmacen']:raise Conflict('El inventario cambió desde el conteo. Rechaza esta solicitud y carga un conteo actualizado.')
    if req['inicial'] and info['activo']:raise Conflict('Ya se aplicó el inventario inicial.')
    for m in req['partidas']:
     delta=Decimal(m['diferencia'])
     if delta:self.post(db,info['id'],m,delta,Decimal(m['costo']),'conteo:'+req['id']+':'+m['sku'],'INICIAL' if req['inicial'] else 'AJUSTE',actor,req['id'],comment,{'solicitadoPor':req['solicitadoPor']})
    db.execute('UPDATE inv_warehouses SET active=1,revision=revision+1 WHERE id=?',(info['id'],))
   req.update({'estado':'APROBADA' if data['aprobar'] else 'RECHAZADA','autorizadoPor':actor['email'],'resuelto':now(),'comentario':comment});db.execute('UPDATE inv_requests SET state=?,payload=? WHERE id=?',(req['estado'],dumps(req),req['id']));return {'ok':True,'solicitud':req}
 def reset(self,data,actor):
  self.scope(actor)
  if actor['role']!='superadmin':raise PermissionError('Solo Superadministrador puede restablecer inventarios.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');w=data.get('almacen');info=self.scope(actor,w,db,True)
   if db.execute("SELECT 1 FROM inv_transfers WHERE (source=? OR destination=?) AND state IN ('EN_TRANSITO','PARCIAL')",(w,w)).fetchone():raise Conflict('Confirma o devuelve primero los materiales en tránsito de este almacén.')
   stamp=self.stamp(db,w);rows=[(s,self.balance(db,w,s)) for s, in db.execute('SELECT sku FROM inv_balances WHERE warehouse=?',(w,)).fetchall()]
   review={'huellaActual':stamp,'almacen':info,'articulos':len(rows),'valor':fmt(sum((Decimal(r['cantidad'])*Decimal(r['costo']) for s,r in rows),Decimal(0)))}
   if data.get('revisar'):return review
   repeat=self.repeat(db,data)
   if repeat:return repeat
   if data.get('huellaActual')!=stamp or data.get('confirmacion')!='RESTABLECER':raise Conflict('Revisa el almacén y escribe RESTABLECER para confirmar.')
   reason=text(data.get('motivo',''),2000)
   if not reason:raise ValueError('Escribe el motivo del restablecimiento.')
   for sku,b in rows:
    if Decimal(b['cantidad']):self.post(db,w,{'sku':sku,**b},-Decimal(b['cantidad']),None,'reset:'+data['clave']+':'+sku,'RESTABLECER',actor,w,reason)
   for id,p in db.execute("SELECT id,payload FROM inv_requests WHERE warehouse=? AND state='PENDIENTE'",(w,)).fetchall():
    r=json.loads(p);r.update({'estado':'INVALIDADA','resuelto':now(),'autorizadoPor':actor['email'],'comentario':'Restablecimiento de inventario: '+reason});db.execute("UPDATE inv_requests SET state='INVALIDADA',payload=? WHERE id=?",(dumps(r),id))
   db.execute('UPDATE inv_warehouses SET active=0,cycle=cycle+1,revision=revision+1 WHERE id=?',(w,));return self.remember(db,data,{'ok':True,'ciclo':info['ciclo']+1,'historialConservado':True})
 def manual(self,data,actor):
  self.scope(actor)
  if actor['role'] not in APPROVERS:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador registran entradas/salidas extraordinarias; Almacén solicita ajustes.')
  materials=self.materials();m=materials.get(str(data.get('sku','')).upper());qty=dec(data.get('cantidad'),True);kind=data.get('tipo');reason=text(data.get('motivo',''),2000)
  if not m or kind not in ('ENTRADA','SALIDA') or not reason:raise ValueError('Selecciona SKU, entrada/salida y motivo.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');info=self.scope(actor,data.get('almacen'),db,True);repeat=self.repeat(db,data)
   if repeat:return repeat
   if not info['activo']:raise ValueError('Autoriza primero el inventario inicial.')
   result=self.post(db,info['id'],m,qty if kind=='ENTRADA' else -qty,dec(m['costo']) if kind=='ENTRADA' and m['costo'] is not None else None,'manual:'+data['clave'],kind,actor,text(data.get('referencia',''),300),reason);return self.remember(db,data,{'ok':True,'movimiento':result})
 def transfers(self,actor):
  allowed={w['id'] for w in self.warehouses(actor)['almacenes']}
  with self.store.connect() as db:return {'traspasos':[json.loads(p) for s,d,p in db.execute('SELECT source,destination,payload FROM inv_transfers ORDER BY rowid DESC LIMIT 1000') if s in allowed or d in allowed]}
 def transfer(self,data,actor):
  self.scope(actor);action=data.get('accion');materials=self.materials()
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');repeat=self.repeat(db,data)
   if repeat:return repeat
   if action=='solicitar':
    source=data.get('origen');dest=data.get('destino');self.scope(actor,source,db,True);target=self.destination(db,dest)
    if source==dest:raise ValueError('Selecciona almacenes diferentes.')
    reason=text(data.get('motivo',''),2000);lines=data.get('partidas');prepared=[];seen=set()
    if not reason or not isinstance(lines,list) or not 1<=len(lines)<=200:raise ValueError('Indica motivo y partidas.')
    for line in lines:
     m=materials.get(str(line.get('sku','')).upper())
     if not m or m['sku'] in seen:raise ValueError('SKU inválido o repetido.')
     seen.add(m['sku']);prepared.append({k:m[k] for k in ('sku','nombre','unidad','materialId')}|{'cantidad':fmt(dec(line.get('cantidad'),True)),'recibido':'0'})
    id=uuid.uuid4().hex;num=db.execute('SELECT COUNT(*)+1 FROM inv_transfers').fetchone()[0];doc={'id':id,'folio':'TRA-'+str(num).zfill(6),'origen':source,'destino':dest,'estado':'SOLICITADA','revision':1,'fecha':now(),'solicitadoPor':actor['email'],'motivo':reason,'partidas':prepared,'intercompania':source.split(':')[0]!=dest.split(':')[0]}
    db.execute('INSERT INTO inv_transfers VALUES(?,?,?,?,?)',(id,source,dest,doc['estado'],dumps(doc)))
   else:
    row=db.execute('SELECT payload FROM inv_transfers WHERE id=?',(data.get('id'),)).fetchone()
    if not row:raise ValueError('Traspaso inexistente.')
    doc=json.loads(row[0]);w=doc['destino'] if action=='recibir' else doc['origen'];self.scope(actor,w,db,True)
    if data.get('revision')!=doc['revision']:raise Conflict('Cambió el traspaso. Ábrelo de nuevo.')
    person=text(data.get('persona',''),200)
    if action=='enviar':
     if doc['estado']!='SOLICITADA' or not person:raise ValueError('Indica quién entrega en una solicitud pendiente.')
     if not self.scope(actor,doc['origen'],db)['activo']:raise ValueError('Autoriza primero el inventario inicial de origen.')
     self.destination(db,doc['destino'])
     for m in doc['partidas']:
      move=self.post(db,doc['origen'],m,-Decimal(m['cantidad']),None,'envio:'+doc['id']+':'+m['sku'],'TRASPASO_SALIDA',actor,doc['folio'],doc['motivo'],{'entrega':person,'destino':doc['destino']});m['costo']=move['costoUnitario'];m['importe']=fmt(Decimal(m['cantidad'])*Decimal(m['costo']))
     doc.update({'estado':'EN_TRANSITO','entrega':person,'enviadoPor':actor['email'],'fechaEnvio':now(),'costoTransportado':fmt(sum((Decimal(m['importe']) for m in doc['partidas']),Decimal(0)))})
    elif action in ('recibir','devolver'):
     if doc['estado'] not in ('EN_TRANSITO','PARCIAL') or not person:raise ValueError('Indica quién recibe y un traspaso en tránsito.')
     if action=='devolver' and actor['role'] not in APPROVERS:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador autorizan la devolución del tránsito al origen.')
     lines=data.get('partidas');seen=set();received=[]
     if not isinstance(lines,list) or not lines:raise ValueError('Indica las cantidades realmente recibidas.')
     for line in lines:
      m=next((m for m in doc['partidas'] if m['sku']==line.get('sku')),None);q=dec(line.get('cantidad'),True)
      if not m or m['sku'] in seen or q>Decimal(m['cantidad'])-Decimal(m['recibido'])-Decimal(m.get('devuelto','0')):raise ValueError('Cantidad supera el tránsito pendiente o SKU repetido.')
      seen.add(m['sku']);destination=doc['destino'] if action=='recibir' else doc['origen'];self.post(db,destination,m,q,Decimal(m['costo']),data['clave']+':'+m['sku'],'TRASPASO_ENTRADA' if action=='recibir' else 'TRASPASO_DEVOLUCION',actor,doc['folio'],text(data.get('motivo',''),2000),{'recibe':person,'origen':doc['origen']});field='recibido' if action=='recibir' else 'devuelto';m[field]=fmt(Decimal(m.get(field,'0'))+q);received.append({'sku':m['sku'],'cantidad':fmt(q)})
     doc.setdefault('recepciones',[]).append({'fecha':now(),'actor':actor['email'],'recibe':person,'tipo':action,'partidas':received});doc['estado']=('CERRADA_CON_DEVOLUCION' if any(Decimal(m.get('devuelto','0')) for m in doc['partidas']) else 'RECIBIDA') if all(Decimal(m['cantidad'])==Decimal(m['recibido'])+Decimal(m.get('devuelto','0')) for m in doc['partidas']) else 'PARCIAL'
    elif action=='cancelar':
     if doc['estado']!='SOLICITADA' or actor['role'] not in APPROVERS:raise PermissionError('Solo los autorizadores cancelan solicitudes antes de enviarse.')
     doc.update({'estado':'CANCELADA','canceladoPor':actor['email'],'cancelado':now()})
    else:raise ValueError('Acción de traspaso inválida.')
    doc['revision']+=1;db.execute('UPDATE inv_transfers SET state=?,payload=? WHERE id=?',(doc['estado'],dumps(doc),doc['id']))
   return self.remember(db,data,{'ok':True,'traspaso':doc})
 def receipt(self,db,doc,move,actor):
  w=str(doc['empresa'])+':'+doc['sucursal'];row=db.execute('SELECT active FROM inv_warehouses WHERE id=?',(w,)).fetchone()
  if not row or not row[0]:return
  for m in move['partidas']:
   line=next(l for l in doc['partidas'] if l['linea']==m['linea']);q=Decimal(m['cantidadEntrega']);cost=Decimal(line['precio'])/Decimal(line['factorEntrega']);self.post(db,w,{'sku':m['sku'],'nombre':m['nombre'],'unidad':m['unidadEntrega'],'materialId':m['materialId']},q,cost,'compra:'+move['id']+':'+m['linea'],'RECEPCION_COMPRA',actor,move['folio'],move.get('observaciones',''))
 def fulfillment(self,db,before,after,change,actor):
  if change['tipo'] not in ('surtir','corregir_surtido','cancelar'):return
  prior=before.get('inventario');w=prior.get('almacen') if prior else change.get('datos',{}).get('almacenInventario')
  active=[r[0] for r in db.execute('SELECT id FROM inv_warehouses WHERE branch=? AND active=1',(before['sucursal'],))]
  if not w:
   if not active:return
   if change['tipo']=='cancelar' and not prior:return
   if len(active)!=1:raise ValueError('Selecciona el almacén/razón social para descontar la requisición.')
   w=active[0]
  info=self.scope(actor,w,db,True)
  if info['sucursal']!=before['sucursal'] or not info['activo']:raise ValueError('Almacén de surtido no disponible para esta sucursal.')
  if prior and prior['ciclo']!=info['ciclo']:raise Conflict('El inventario fue restablecido. No se puede revertir un surtido de otro ciclo.')
  old={m['materialId']:m for m in before['partidas']};new={m['materialId']:m for m in after['partidas']};entries=copy.deepcopy(prior.get('partidas',{})) if prior else {}
  for id,m in new.items():
   was=Decimal(old[id].get('cantidadSurtida','0')) if prior else Decimal(0);actual=Decimal(0) if change['tipo']=='cancelar' else Decimal(m.get('cantidadSurtida','0'));delta=was-actual
   if delta:
    source='req:'+after['id']+':'+str(before.get('revision',1))+':'+str(id);cost=Decimal(entries[str(id)]['costo']) if delta>0 and str(id) in entries else None;move=self.post(db,w,{'sku':m['sku'],'nombre':m['nombre'],'unidad':m['unidad'],'materialId':id},delta,cost,source,'REQUISICION_DEVOLUCION' if delta>0 else 'REQUISICION_SURTIDO',actor,before['numero'],change['motivo']);entries[str(id)]={'costo':move['costoUnitario']}
  after['inventario']={'almacen':w,'ciclo':info['ciclo'],'partidas':entries,'fecha':now()}
