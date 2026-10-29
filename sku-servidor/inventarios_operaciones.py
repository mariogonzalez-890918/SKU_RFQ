"""Conceptos y operaciones autorizadas, con reversas de recepciones sin borrar historia."""
import json,re,uuid
from decimal import Decimal
from inventarios import APPROVERS,SYSTEM_CONCEPTS,dec,fmt
from requisiciones import Conflict,now,text
from comercial import dumps

DEFAULTS=(('DEVOLUCION_AREA','ENTRADA','Devolución de material de un área'),('RECUPERACION','ENTRADA','Recuperación de material'),('ENTRADA_OTROS','ENTRADA','Otras entradas autorizadas'),('MERMA','SALIDA','Merma'),('CADUCIDAD','SALIDA','Caducidad'),('ROTURA','SALIDA','Rotura o daño'),('MUESTRA','SALIDA','Muestra o prueba'),('SALIDA_OTROS','SALIDA','Otras salidas autorizadas'))

class InventoryOperations:
 def __init__(self,inv):
  self.inv=inv
  with inv.store.connect() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS inv_concepts(code TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,active INTEGER NOT NULL,revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS inv_operations(id TEXT PRIMARY KEY,warehouse TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL);''')
   for code,kind,name in DEFAULTS:db.execute('INSERT OR IGNORE INTO inv_concepts VALUES(?,?,?,1,1)',(code,kind,name))
 def concepts(self,actor):
  self.inv.scope(actor)
  with self.inv.store.connect() as db:return {'conceptos':[{'codigo':c,'tipo':t,'nombre':n,'activo':bool(a),'revision':r} for c,t,n,a,r in db.execute('SELECT * FROM inv_concepts ORDER BY kind,name') if a or actor['role'] in APPROVERS]}
 def save_concept(self,data,actor):
  self.inv.scope(actor)
  if actor['role'] not in APPROVERS:raise PermissionError('Gerencia, AUXTI y Superadministrador administran conceptos.')
  code=text(data.get('codigo',''),40).upper() or 'CON_'+uuid.uuid4().hex[:10].upper();name=text(data.get('nombre',''),160);kind=data.get('tipo')
  if code in SYSTEM_CONCEPTS:raise ValueError('Ese código pertenece a una operación automática del sistema.')
  if not re.fullmatch('[A-Z][A-Z0-9_]{1,39}',code) or not name or kind not in ('ENTRADA','SALIDA'):raise ValueError('Indica código, nombre y tipo de concepto válidos.')
  with self.inv.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT kind,revision FROM inv_concepts WHERE code=?',(code,)).fetchone()
   if row and (row[1]!=data.get('revision') or row[0]!=kind):raise Conflict('El concepto cambió o intentas cambiar su tipo. Actualiza y revisa.')
   db.execute('INSERT INTO inv_concepts VALUES(?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,active=excluded.active,revision=excluded.revision',(code,kind,name,int(data.get('activo',True) is True),(row[1] if row else 0)+1))
  return {'ok':True,'codigo':code}
 def list(self,w,actor):
  self.inv.scope(actor,w)
  with self.inv.store.connect() as db:return {'operaciones':[json.loads(p) for p, in db.execute('SELECT payload FROM inv_operations WHERE warehouse=? ORDER BY rowid DESC LIMIT 500',(w,))]}
 def submit(self,data,actor,cancel=False):
  inv=self.inv;inv.scope(actor);w=data.get('almacen');reason=text(data.get('motivo',''),2000)
  if not reason:raise ValueError('Escribe el motivo de la operación.')
  if not cancel and actor['role'] not in APPROVERS:raise PermissionError('Movimiento de almacén es exclusivo de Gerencia, AUXTI y Superadministrador.')
  materials=inv.materials() if not cancel else None
  with inv.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');info=inv.scope(actor,w,db,True);repeat=inv.repeat(db,data)
   if repeat:return repeat
   id=uuid.uuid4().hex;req={'id':id,'almacen':w,'ciclo':info['ciclo'],'estado':'PENDIENTE','fecha':now(),'solicitadoPor':actor['email'],'motivo':reason,'tipo':'CANCELAR_RECEPCION_COMPRA' if cancel else data.get('tipo')}
   if cancel:
    row=db.execute("SELECT order_id,payload FROM po_moves WHERE id=? AND kind='RECEPCION'",(data.get('recepcion'),)).fetchone()
    if not row:raise ValueError('Recepción de compra no encontrada.')
    doc=inv.po.document(db,row[0],actor);move=json.loads(row[1])
    if doc['empresa']!=info['empresa'] or doc['sucursal']!=info['sucursal']:raise PermissionError('La recepción pertenece a otro almacén.')
    if move.get('cancelacion'):raise Conflict('La recepción ya fue cancelada/devolucionada.')
    if data.get('devolucionFisica') is not True:raise ValueError('Confirma la devolución física del material para descontarlo.')
    req.update({'recepcion':data['recepcion'],'folio':move['folio'],'pedido':doc['folio'],'devolucionFisica':True,'partidas':[{k:l[k] for k in ('sku','nombre','cantidad','unidad','cantidadEntrega','unidadEntrega')} for l in move['partidas']]})
   else:
    m=materials.get(str(data.get('sku','')).upper());qty=dec(data.get('cantidad'),True);kind=data.get('tipo');code=data.get('concepto') or ('ENTRADA_OTROS' if kind=='ENTRADA' else 'SALIDA_OTROS');concept=db.execute('SELECT kind,name,active FROM inv_concepts WHERE code=?',(code,)).fetchone()
    # Las operaciones pueden preceder al conteo inicial; negativos requieren autorización.
    if not m or not concept or not concept[2] or concept[0]!=kind:raise ValueError('Selecciona SKU y concepto activo del tipo correspondiente.')
    if kind=='ENTRADA' and m['costo'] is None:raise ValueError('Falta costo de entrega del maestro para esta entrada.')
    req.update({'material':m,'cantidad':fmt(qty),'conceptoId':code,'concepto':concept[1],'referencia':text(data.get('referencia',''),300)})
   result=None
   if cancel:
    from pedidos_compra import delivery_in
    deficits=[]
    for l in move['partidas']:
     balance=inv.balance(db,w,l['sku'].upper());available=Decimal(balance['cantidad']) if balance else Decimal(0);quantity=delivery_in(Decimal(l['cantidadEntrega']),l['unidadEntrega'],balance['unidad'] if balance else l['unidadEntrega'])
     if quantity>available:deficits.append({'sku':l['sku'],'disponible':fmt(available),'salida':fmt(quantity),'saldoPropuesto':fmt(available-quantity)})
    if deficits:req['inventarioInsuficiente']=deficits
   if not cancel and req['tipo']=='SALIDA':
    balance=inv.balance(db,w,req['material']['sku']);available=Decimal(balance['cantidad']) if balance else Decimal(0)
    if available<Decimal(req['cantidad']):req['inventarioInsuficiente']=[{'sku':req['material']['sku'],'disponible':fmt(available),'salida':req['cantidad'],'saldoPropuesto':fmt(available-Decimal(req['cantidad']))}]
   if req.get('inventarioInsuficiente') and data.get('autorizarNegativo') is True and actor['role'] in APPROVERS:req['inventarioNegativoAutorizado']=True
   if actor['role'] in APPROVERS and (not req.get('inventarioInsuficiente') or req.get('inventarioNegativoAutorizado')):result=self.apply(db,req,actor);req.update({'estado':'APROBADA','autorizadoPor':actor['email'],'resuelto':now(),'comentario':reason})
   db.execute('INSERT INTO inv_operations VALUES(?,?,?,?)',(id,w,req['estado'],dumps(req)));return inv.remember(db,data,{'ok':True,'solicitud':req,**(result or {})})
 def apply(self,db,req,actor):
  inv=self.inv;info=inv.scope(actor,req['almacen'],db,True)
  if req['ciclo']!=info['ciclo']:raise Conflict('El almacén fue restablecido. Rechaza la operación y crea una nueva.')
  if req['tipo']=='CANCELAR_RECEPCION_COMPRA':return self.cancel_receipt(db,req,actor,info)
  m=req['material'];q=Decimal(req['cantidad']);concept=db.execute('SELECT active FROM inv_concepts WHERE code=?',(req['conceptoId'],)).fetchone()
  if not concept or not concept[0]:raise Conflict('El concepto fue desactivado; rechaza y solicita una nueva operación.')
  move=inv.post(db,info['id'],m,q if req['tipo']=='ENTRADA' else -q,Decimal(m['costo']) if req['tipo']=='ENTRADA' else None,'operacion:'+req['id'],req['tipo'],actor,req['referencia'],req['motivo'],{'conceptoId':req['conceptoId'],'concepto':req['concepto'],'solicitadoPor':req['solicitadoPor']},allow_negative=bool(req.get('inventarioNegativoAutorizado')));return {'movimiento':move}
 def cancel_receipt(self,db,req,actor,info):
  from pedidos_compra import delivery_in
  inv=self.inv;row=db.execute("SELECT order_id,payload FROM po_moves WHERE id=? AND kind='RECEPCION'",(req['recepcion'],)).fetchone()
  if not row:raise ValueError('La recepción ya no está disponible.')
  move=json.loads(row[1]);doc=inv.po.document(db,row[0],actor)
  if move.get('cancelacion'):raise Conflict('La recepción ya fue cancelada.')
  for l in move['partidas']:
   line=next(r for r in doc['partidas'] if r['linea']==l['linea']);remaining=Decimal(line['recibido'])-Decimal(l['cantidad'])
   if remaining<Decimal(line['comprado']):raise ValueError('La recepción tiene compras/facturas asociadas. Regulariza primero su devolución o nota de crédito; no se puede cancelar dejando compras sin recepción.')
   balance=inv.balance(db,info['id'],l['sku'].upper());delivery_unit=balance['unidad'] if balance else l['unidadEntrega'];qty=delivery_in(Decimal(l['cantidadEntrega']),l['unidadEntrega'],delivery_unit);inv.post(db,info['id'],{'sku':l['sku'],'nombre':l['nombre'],'unidad':delivery_unit,'materialId':l['materialId']},-qty,None,'cancelcompra:'+move['id']+':'+l['linea'],'CANCELACION_RECEPCION_COMPRA',actor,move['folio'],req['motivo'],{'pedido':doc['folio'],'pedidoId':doc['id'],'solicitadoPor':req['solicitadoPor'],'concepto':'Cancelación/devolución de recepción de compra'},allow_negative=bool(req.get('inventarioNegativoAutorizado')))
   line['recibido']=fmt(remaining)
  move['cancelacion']={'fecha':now(),'motivo':req['motivo'],'autorizadoPor':actor['email'],'solicitadoPor':req['solicitadoPor'],'devolucionFisica':True,'almacen':info['id']};db.execute('UPDATE po_moves SET payload=? WHERE id=?',(dumps(move),move['id']));doc['estado']='PEDIDO' if not any(Decimal(l['recibido']) for l in doc['partidas']) else 'RECIBIDO' if all(Decimal(l['recibido'])==Decimal(l['cantidad']) for l in doc['partidas']) else 'RECEPCION_PARCIAL';inv.po.update_doc(db,doc,actor,'CANCELACION_RECEPCION');return {'recepcion':move['id'],'folio':move['folio']}
 def decide(self,data,actor):
  inv=self.inv;inv.scope(actor)
  if actor['role'] not in APPROVERS:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador autorizan operaciones.')
  if type(data.get('aprobar')) is not bool:raise ValueError('Indica aprobar o rechazar.')
  comment=text(data.get('comentario',''),2000)
  if not comment:raise ValueError('Escribe el comentario de autorización.')
  with inv.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM inv_operations WHERE id=?',(data.get('id'),)).fetchone()
   if not row:raise ValueError('Solicitud no encontrada.')
   req=json.loads(row[0]);inv.scope(actor,req['almacen'],db,True)
   if req['estado']!='PENDIENTE':raise Conflict('La operación ya fue resuelta.')
   if data['aprobar'] and req.get('inventarioInsuficiente'):
    if data.get('autorizarNegativo') is not True:raise ValueError('Confirma la autorización del saldo negativo.')
    req['inventarioNegativoAutorizado']=True
   result=self.apply(db,req,actor) if data['aprobar'] else None;req.update({'estado':'APROBADA' if data['aprobar'] else 'RECHAZADA','autorizadoPor':actor['email'],'resuelto':now(),'comentario':comment});db.execute('UPDATE inv_operations SET state=?,payload=? WHERE id=?',(req['estado'],dumps(req),req['id']));return {'ok':True,'solicitud':req,**(result or {})}

 def missing_issues(self,w,actor):
  if actor['role'] not in APPROVERS:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador concilian movimientos de almacén.')
  inv=self.inv;info=inv.scope(actor,w);result=[]
  with inv.store.connect() as db:
   for id,p in db.execute("SELECT id,payload FROM req_documents WHERE json_extract(payload,'$.sucursal')=? AND json_extract(payload,'$.estado') IN ('SURTIDO','SURTIDA')",(info['sucursal'],)):
    doc=json.loads(p)
    if doc.get('inventario') or db.execute("SELECT 1 FROM inv_ledger WHERE json_extract(payload,'$.requisicionId')=?",(id,)).fetchone():continue
    result.append({'id':id,'folio':doc['numero'],'revision':doc.get('revision',1),'fecha':doc.get('surtido',{}).get('fecha',doc.get('fechaHora','')),'partidas':[{k:l.get(k) for k in ('materialId','sku','nombre','unidad','cantidadSurtida')} for l in doc['partidas'] if Decimal(l.get('cantidadSurtida','0'))>0]})
  return {'requisiciones':result}
 def regularize(self,data,actor):
  import copy
  inv=self.inv;inv.scope(actor)
  if actor['role'] not in APPROVERS:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador concilian salidas faltantes.')
  with inv.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');info=inv.scope(actor,data.get('almacen'),db,True);repeat=inv.repeat(db,data)
   if repeat:return repeat
   row=db.execute('SELECT payload FROM req_documents WHERE id=?',(data.get('id'),)).fetchone()
   if not row:raise ValueError('Requisición no encontrada.')
   before=json.loads(row[0]);after=copy.deepcopy(before)
   if before['sucursal']!=info['sucursal'] or before['estado'] not in ('SURTIDO','SURTIDA') or before.get('inventario'):raise Conflict('La requisición no está surtida, pertenece a otro almacén o ya tiene salida registrada.')
   if before.get('revision',1)!=data.get('revision'):raise Conflict('La requisición cambió; actualiza.')
   reason=text(data.get('motivo',''),1000)
   if not reason:raise ValueError('Escribe el motivo de conciliación.')
   change={'tipo':'surtir','datos':{'almacenInventario':info['id'],'partidas':[{'materialId':l['materialId'],'cantidadSurtida':l.get('cantidadSurtida','0')} for l in before['partidas']]},'motivo':reason};shortages=inv.fulfillment_preview(db,before,change,actor)
   if shortages and data.get('autorizarNegativo') is not True:raise ValueError('Pedido con menos inventario: confirma la autorización de saldo negativo para registrar esta salida histórica.')
   change['inventarioNegativoAutorizado']=bool(shortages);inv.fulfillment(db,before,after,change,actor);revision=before.get('revision',1);db.execute('INSERT OR IGNORE INTO req_document_versions VALUES(?,?,?)',(before['id'],revision,dumps(before)));after['revision']=revision+1;db.execute('UPDATE req_documents SET payload=? WHERE id=?',(dumps(after),before['id']));return inv.remember(db,data,{'ok':True,'folio':before['numero'],'salidaRegistrada':True})
