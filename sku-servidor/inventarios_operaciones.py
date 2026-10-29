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
  if not reason and not cancel:raise ValueError('Escribe el motivo de la operación.')
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
    if move.get('devoluciones'):raise Conflict('La recepción ya tiene devoluciones. Devuelve únicamente el remanente desde Devolver al proveedor.')
    if data.get('devolucionFisica') is not True:raise ValueError('Confirma la devolución física del material para descontarlo.')
    _,_,_,source=self.return_source(db,w,data['recepcion'],actor);mode=data.get('modo','TOTAL');requested=[{'linea':l['linea'],'cantidad':l['pendienteDevolver']} for l in source if Decimal(l['pendienteDevolver'])>0] if mode=='TOTAL' else data.get('partidas')
    if mode not in ('TOTAL','PARCIAL'):raise ValueError('Selecciona cancelación total o parcial.')
    parts=self.select_receipt_parts(source,requested);req.update({'recepcion':data['recepcion'],'folio':move['folio'],'pedido':doc['folio'],'devolucionFisica':True,'modo':mode,'partidas':parts})
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
    for l in req['partidas']:
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
  if req['tipo']=='DEVOLUCION_PROVEEDOR':return self.apply_return(db,req,actor,info)
  if req['tipo']=='CANCELAR_TRASPASO':return self.apply_transfer_cancel(db,req,actor)
  m=req['material'];q=Decimal(req['cantidad']);concept=db.execute('SELECT active FROM inv_concepts WHERE code=?',(req['conceptoId'],)).fetchone()
  if not concept or not concept[0]:raise Conflict('El concepto fue desactivado; rechaza y solicita una nueva operación.')
  move=inv.post(db,info['id'],m,q if req['tipo']=='ENTRADA' else -q,Decimal(m['costo']) if req['tipo']=='ENTRADA' else None,'operacion:'+req['id'],req['tipo'],actor,req['referencia'],req['motivo'],{'conceptoId':req['conceptoId'],'concepto':req['concepto'],'solicitadoPor':req['solicitadoPor']},allow_negative=bool(req.get('inventarioNegativoAutorizado')));return {'movimiento':move}
 def cancel_receipt(self,db,req,actor,info):
  from pedidos_compra import delivery_in
  inv=self.inv;row=db.execute("SELECT order_id,payload FROM po_moves WHERE id=? AND kind='RECEPCION'",(req['recepcion'],)).fetchone()
  if not row:raise ValueError('La recepción ya no está disponible.')
  move=json.loads(row[1]);doc=inv.po.document(db,row[0],actor)
  if move.get('cancelacion'):raise Conflict('La recepción ya fue cancelada.')
  if move.get('devoluciones'):raise Conflict('La recepción ya tiene devoluciones. Devuelve únicamente el remanente desde Devolver al proveedor.')
  _,_,_,source=self.return_source(db,info['id'],move['id'],actor);parts=[]
  for entry in req['partidas']:
   l=next((r for r in source if r['linea']==entry.get('linea') or 'linea' not in entry and r['sku']==entry['sku'] and r['unidad']==entry['unidad']),None)
   if not l or Decimal(entry['cantidad'])>Decimal(l['pendienteDevolver']):raise Conflict('Otra operación modificó la recepción. Revisa el remanente antes de cancelar.')
   q=Decimal(entry['cantidad']);entry={**l,**entry,'linea':l['linea']};line=next(r for r in doc['partidas'] if r['linea']==l['linea']);remaining=Decimal(line['recibido'])-q
   if remaining<Decimal(line['comprado']):raise ValueError('La recepción tiene compras/facturas asociadas. Regulariza primero su devolución o nota de crédito; no se puede cancelar dejando compras sin recepción.')
   balance=inv.balance(db,info['id'],l['sku'].upper());delivery_unit=balance['unidad'] if balance else l['unidadEntrega'];qty=delivery_in(Decimal(entry['cantidadEntrega']),l['unidadEntrega'],delivery_unit);inv.post(db,info['id'],{'sku':l['sku'],'nombre':l['nombre'],'unidad':delivery_unit,'materialId':l['materialId']},-qty,None,'cancelcompra:'+req['id']+':'+l['linea'],'CANCELACION_RECEPCION_COMPRA',actor,move['folio'],req['motivo'],{'pedido':doc['folio'],'pedidoId':doc['id'],'solicitadoPor':req['solicitadoPor'],'concepto':'Cancelación parcial/total de recepción de compra'},allow_negative=bool(req.get('inventarioNegativoAutorizado')));line['recibido']=fmt(remaining);line['recibidoNeto']=fmt(remaining-Decimal(line.get('devueltoProveedor','0')));parts.append({k:entry[k] for k in ('linea','sku','nombre','unidad','cantidad','cantidadEntrega','unidadEntrega')})
  cancellation={'id':req['id'],'fecha':now(),'motivo':req['motivo'],'autorizadoPor':actor['email'],'solicitadoPor':req['solicitadoPor'],'devolucionFisica':True,'almacen':info['id'],'partidas':parts};move.setdefault('cancelacionesParciales',[]).append(cancellation)
  all_cancelled=all(sum((Decimal(l['cantidad']) for c in move['cancelacionesParciales'] for l in c['partidas'] if l['linea']==r['linea']),Decimal(0))==Decimal(r['cantidad']) for r in move['partidas'])
  if all_cancelled:move['cancelacion']=cancellation
  db.execute('UPDATE po_moves SET payload=? WHERE id=?',(dumps(move),move['id']));doc['estado']='COMPRADO' if all(Decimal(l['comprado'])==Decimal(l['cantidad']) for l in doc['partidas']) else 'PEDIDO' if not any(Decimal(l['recibido']) for l in doc['partidas']) else 'RECIBIDO' if all(Decimal(l['recibido'])==Decimal(l['cantidad']) for l in doc['partidas']) else 'RECEPCION_PARCIAL';inv.po.update_doc(db,doc,actor,'CANCELACION_RECEPCION');return {'recepcion':move['id'],'folio':move['folio'],'cancelacionParcial':not all_cancelled}

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

 def return_source(self,db,w,id,actor):
  inv=self.inv;info=inv.scope(actor,w,db,True);row=db.execute("SELECT order_id,payload FROM po_moves WHERE id=? AND kind='RECEPCION'",(id,)).fetchone()
  if not row:raise ValueError('Recepción de compra no encontrada.')
  move=json.loads(row[1]);doc=inv.po.document(db,row[0],actor)
  if doc['empresa']!=info['empresa'] or doc['sucursal']!=info['sucursal']:raise PermissionError('La recepción pertenece a otro almacén.')
  if move.get('cancelacion'):raise Conflict('La recepción está cancelada.')
  lines=[]
  for line in move['partidas']:
   returned=sum((Decimal(l['cantidad']) for r in move.get('devoluciones',[]) for l in r['partidas'] if l['linea']==line['linea']),Decimal(0));cancelled=sum((Decimal(l['cantidad']) for c in move.get('cancelacionesParciales',[]) for l in c['partidas'] if l['linea']==line['linea']),Decimal(0));remaining=Decimal(line['cantidad'])-returned-cancelled;lines.append({**line,'devuelto':fmt(returned),'cancelado':fmt(cancelled),'pendienteDevolver':fmt(remaining)})
  return info,move,doc,lines
 def select_receipt_parts(self,source,requested):
  if not isinstance(requested,list) or not requested:raise ValueError('Selecciona al menos una partida con cantidad positiva.')
  parts=[];seen=set()
  for r in requested:
   l=next((l for l in source if l['linea']==r.get('linea')),None);q=dec(r.get('cantidad'),True)
   if not l or l['linea'] in seen or q>Decimal(l['pendienteDevolver']):raise ValueError('Cantidad superior al remanente o partida repetida.')
   seen.add(l['linea']);parts.append({**{k:l[k] for k in ('linea','materialId','sku','nombre','unidad','unidadEntrega')},'cantidad':fmt(q),'cantidadEntrega':fmt(q*Decimal(l['cantidadEntrega'])/Decimal(l['cantidad']))})
  return parts

 def returnable(self,w,id,actor):
  with self.inv.store.connect() as db:
   info,move,doc,lines=self.return_source(db,w,id,actor);return {'recepcion':move['id'],'folio':move['folio'],'pedido':doc['folio'],'proveedor':doc['proveedor']['nombre'],'partidas':lines,'devoluciones':move.get('devoluciones',[])}
 def submit_return(self,data,actor):
  from pedidos_compra import delivery_in
  inv=self.inv;inv.scope(actor)
  with inv.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');repeat=inv.repeat(db,data)
   if repeat:return repeat
   info,move,doc,source=self.return_source(db,data.get('almacen'),data.get('recepcion'),actor);mode=data.get('modo');requested=[{'linea':l['linea'],'cantidad':l['pendienteDevolver']} for l in source if Decimal(l['pendienteDevolver'])>0] if mode=='TOTAL' else data.get('partidas');lines=[];seen=set();needed={}
   if mode not in ('TOTAL','PARCIAL') or not isinstance(requested,list) or not requested:raise ValueError('Selecciona devolución parcial con cantidades o completa pendiente.')
   for r in requested:
    line=next((l for l in source if l['linea']==r.get('linea')),None);q=dec(r.get('cantidad'),True)
    if not line or line['linea'] in seen or q>Decimal(line['pendienteDevolver']):raise ValueError('Cantidad mayor al pendiente de devolver, partida repetida o inválida.')
    seen.add(line['linea']);entry={k:line[k] for k in ('linea','materialId','sku','nombre','unidad','unidadEntrega')};entry.update({'cantidad':fmt(q),'cantidadEntrega':fmt(q*Decimal(line['cantidadEntrega'])/Decimal(line['cantidad']))});lines.append(entry);balance=inv.balance(db,info['id'],line['sku'].upper());unit=balance['unidad'] if balance else line['unidadEntrega'];needed[line['sku']]=needed.get(line['sku'],Decimal(0))+delivery_in(Decimal(entry['cantidadEntrega']),line['unidadEntrega'],unit)
   deficits=[]
   for sku,q in needed.items():
    balance=inv.balance(db,info['id'],sku.upper());available=Decimal(balance['cantidad']) if balance else Decimal(0)
    if q>available:deficits.append({'sku':sku,'disponible':fmt(available),'salida':fmt(q),'saldoPropuesto':fmt(available-q)})
   req={'id':uuid.uuid4().hex,'almacen':info['id'],'ciclo':info['ciclo'],'estado':'PENDIENTE','fecha':now(),'solicitadoPor':actor['email'],'motivo':text(data.get('motivo',''),2000),'tipo':'DEVOLUCION_PROVEEDOR','recepcion':move['id'],'folio':move['folio'],'pedido':doc['folio'],'modo':mode,'partidas':lines}
   if deficits:req['inventarioInsuficiente']=deficits
   if deficits and actor['role'] in APPROVERS and data.get('autorizarNegativo') is True:req['inventarioNegativoAutorizado']=True
   result=None
   if actor['role'] in APPROVERS and (not deficits or req.get('inventarioNegativoAutorizado')):result=self.apply_return(db,req,actor,info);req.update({'estado':'APROBADA','autorizadoPor':actor['email'],'resuelto':now(),'comentario':req['motivo']})
   db.execute('INSERT INTO inv_operations VALUES(?,?,?,?)',(req['id'],info['id'],req['estado'],dumps(req)));return inv.remember(db,data,{'ok':True,'solicitud':req,**(result or {})})
 def apply_return(self,db,req,actor,info):
  from pedidos_compra import delivery_in
  from comercial import money
  inv=self.inv;info,source,doc,remaining=self.return_source(db,info['id'],req['recepcion'],actor);id=req['id'];number=db.execute("SELECT COUNT(*)+1 FROM po_moves WHERE kind='DEVOLUCION' OR kind='DEVOLUCION_PROVEEDOR'").fetchone()[0];folio='DVP-'+str(number).zfill(6);parts=[]
  for l in req['partidas']:
   old=next((r for r in remaining if r['linea']==l['linea']),None)
   if not old or Decimal(l['cantidad'])>Decimal(old['pendienteDevolver']):raise Conflict('Otra devolución modificó el remanente. Rechaza esta propuesta y carga las cantidades actuales.')
   line=next(r for r in doc['partidas'] if r['linea']==l['linea']);balance=inv.balance(db,info['id'],l['sku'].upper());unit=balance['unidad'] if balance else l['unidadEntrega'];q=delivery_in(Decimal(l['cantidadEntrega']),l['unidadEntrega'],unit);inv.post(db,info['id'],{'sku':l['sku'],'nombre':l['nombre'],'unidad':unit,'materialId':l['materialId']},-q,None,'devprov:'+id+':'+l['linea'],'DEVOLUCION_PROVEEDOR',actor,folio,req['motivo'],{'pedidoId':doc['id'],'pedido':doc['folio'],'recepcionId':source['id'],'recepcion':source['folio'],'solicitadoPor':req['solicitadoPor'],'concepto':'Devolución al proveedor','entrega':req['solicitadoPor'],'recibe':doc['proveedor']['nombre']},allow_negative=bool(req.get('inventarioNegativoAutorizado')));line['devueltoProveedor']=fmt(Decimal(line.get('devueltoProveedor','0'))+Decimal(l['cantidad']));line['recibidoNeto']=fmt(Decimal(line['recibido'])-Decimal(line['devueltoProveedor']));parts.append({**l,'base':money(Decimal(l['cantidad'])*Decimal(line['precio'])),'impuestos':money(Decimal(l['cantidad'])*Decimal(line['precio'])*Decimal(line['impuesto'])/100)})
  value={'id':id,'pedidoId':doc['id'],'empresa':doc['empresa'],'proveedorId':doc['proveedor']['id'],'tipo':'DEVOLUCION_PROVEEDOR','folio':folio,'fecha':now()[:10],'creado':now(),'actor':actor['email'],'referencia':source['folio'],'observaciones':req['motivo'],'partidas':parts,'total':money(sum((Decimal(l['base'])+Decimal(l['impuestos']) for l in parts),Decimal(0))),'recepcionId':source['id'],'autorizadoPor':actor['email'],'solicitadoPor':req['solicitadoPor']};source.setdefault('devoluciones',[]).append(value);db.execute('UPDATE po_moves SET payload=? WHERE id=?',(dumps(source),source['id']));db.execute('INSERT INTO po_moves VALUES(?,?,?,?,?)',(id,doc['id'],'DEVOLUCION_PROVEEDOR','devprov:'+id,dumps(value)));inv.po.update_doc(db,doc,actor,'DEVOLUCION_PROVEEDOR');return {'devolucion':value,'folioDevolucion':folio}

 def submit_transfer_cancel(self,data,actor):
  inv=self.inv;inv.scope(actor)
  with inv.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');repeat=inv.repeat(db,data)
   if repeat:return repeat
   row=db.execute('SELECT payload FROM inv_transfers WHERE id=?',(data.get('traspaso'),)).fetchone()
   if not row:raise ValueError('Traspaso no encontrado.')
   doc=json.loads(row[0]);info=inv.scope(actor,doc['origen'],db,True)
   if doc['revision']!=data.get('revision') or doc['estado'] not in ('SOLICITADA','EN_TRANSITO','PARCIAL','RECIBIDA','CERRADA_CON_DEVOLUCION'):raise Conflict('El traspaso cambió o ya fue cancelado.')
   return_received=data.get('devolverRecibido') is True;target=None;deficits=[]
   if doc['estado'] in ('RECIBIDA','CERRADA_CON_DEVOLUCION') and not return_received:raise ValueError('Confirma la devolución física de las cantidades recibidas en destino.')
   if return_received:
    target=inv.scope(actor,doc['destino'],db,True)
    if not text(data.get('entregaDevolucion',''),200):raise ValueError('Indica quién entrega físicamente en destino.')
    for m in doc['partidas']:
     qty=Decimal(m['recibido'])-Decimal(m.get('devueltoRecibido','0'));balance=inv.balance(db,doc['destino'],m['sku']);available=Decimal(balance['cantidad']) if balance else Decimal(0)
     if qty>available:deficits.append({'sku':m['sku'],'disponible':fmt(available),'salida':fmt(qty),'saldoPropuesto':fmt(available-qty)})
   if doc['estado']!='SOLICITADA' and (data.get('confirmarDevolucion') is not True or not text(data.get('persona',''),200)):raise ValueError('Confirma el regreso físico del tránsito e indica quién recibe en origen.')
   req={'id':uuid.uuid4().hex,'almacen':info['id'],'ciclo':info['ciclo'],'estado':'PENDIENTE','fecha':now(),'solicitadoPor':actor['email'],'motivo':text(data.get('motivo',''),2000),'tipo':'CANCELAR_TRASPASO','traspaso':doc['id'],'revisionTraspaso':doc['revision'],'folio':doc['folio'],'persona':text(data.get('persona',''),200),'confirmarDevolucion':data.get('confirmarDevolucion') is True,'partidas':[{**{k:m[k] for k in ('sku','nombre','unidad')},'cantidad':m['cantidad'] if doc['estado']=='SOLICITADA' else fmt(Decimal(m['cantidad'])-Decimal(m['recibido'])-Decimal(m.get('devuelto','0'))),'cantidadEntrega':'','unidadEntrega':''} for m in doc['partidas']]};result=None
   req.update({'devolverRecibido':return_received,'entregaDevolucion':text(data.get('entregaDevolucion',''),200),'cicloDestino':target['ciclo'] if target else None})
   for line,m in zip(req['partidas'],doc['partidas']):
    if return_received:line['cantidad']=fmt(Decimal(line['cantidad'])+Decimal(m['recibido'])-Decimal(m.get('devueltoRecibido','0')))
   if deficits:req.update({'inventarioInsuficiente':deficits,'almacenSalida':doc['destino']})
   if actor['role'] in APPROVERS and data.get('autorizarNegativo') is True:req['inventarioNegativoAutorizado']=True
   if actor['role'] in APPROVERS and (not deficits or req.get('inventarioNegativoAutorizado')):result=self.apply_transfer_cancel(db,req,actor);req.update({'estado':'APROBADA','autorizadoPor':actor['email'],'resuelto':now(),'comentario':req['motivo']})
   db.execute('INSERT INTO inv_operations VALUES(?,?,?,?)',(req['id'],info['id'],req['estado'],dumps(req)));return inv.remember(db,data,{'ok':True,'solicitud':req,**(result or {})})
 def apply_transfer_cancel(self,db,req,actor):
  inv=self.inv;row=db.execute('SELECT payload FROM inv_transfers WHERE id=?',(req['traspaso'],)).fetchone();doc=json.loads(row[0]) if row else None
  if not doc or doc['revision']!=req['revisionTraspaso']:raise Conflict('El traspaso cambió después de solicitar la cancelación. Rechaza la propuesta y revisa de nuevo.')
  inv.cancel_transfer(db,doc,{**req,'solicitadoPor':req['solicitadoPor']},actor);doc['revision']+=1;db.execute('UPDATE inv_transfers SET state=?,payload=? WHERE id=?',(doc['estado'],dumps(doc),doc['id']));return {'traspaso':doc}

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
