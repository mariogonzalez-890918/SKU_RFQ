"""Cambios autorizados y trazables; nunca reutiliza folios ni altera fechas de emisión."""
import copy,decimal,json,uuid
from requisiciones import AREAS,Conflict,now,text,visible_branches,requester_document
EDITORS={'superadmin','gerente'}
APPROVERS=EDITORS|{'auxti'}

def requester_change(change):
 result={key:change[key] for key in ('id','fecha','tipo','objetivo','folio','sucursal','revision','motivo','solicitadoPor','estado','resueltoPor','resuelto','comentario','perfilSolicitante','requiereSistemas') if key in change}
 data=change.get('datos',{});result['datos']={key:data[key] for key in ('area','solicitante','observaciones') if key in data}
 if 'partidas' in data:result['datos']['partidas']=requester_document({'partidas':data['partidas']})['partidas']
 return result

class WorkflowStore:
 def __init__(self,store,requisitions,reports):
  self.store=store;self.requisitions=requisitions;self.reports=reports
  with store.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS req_changes(id TEXT PRIMARY KEY,branch TEXT NOT NULL,requester TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)')
   db.execute('CREATE INDEX IF NOT EXISTS req_changes_scope ON req_changes(branch,status,created_at)')
   db.execute("CREATE INDEX IF NOT EXISTS req_changes_document ON req_changes(json_extract(payload,'$.objetivo'))")
   db.execute('CREATE TABLE IF NOT EXISTS req_document_versions(document_id TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(document_id,revision))')
 def _document(self,db,id,actor):
  row=db.execute('SELECT payload,creator FROM req_documents WHERE id=?',(id,)).fetchone();doc=json.loads(row[0]) if row else None
  if actor['role']=='requisicion' and (not row or row[1]!=actor['email']):raise PermissionError('Solo puedes solicitar correcciones de tus propias requisiciones.')
  if not doc or doc['sucursal'] not in visible_branches(actor):raise PermissionError('Solicitud no disponible en tus almacenes autorizados.')
  return doc
 def _prepare(self,db,data,actor):
  kind=data.get('tipo');reason=text(data.get('motivo',''),1000)
  if not reason and kind not in ('cancelar','surtir','corregir_surtido'):raise ValueError('Escribe el motivo del cambio.')
  if kind not in ('cancelar','modificar','aprobar','surtir','corregir_surtido'):raise ValueError('Tipo de cambio inválido. Los costos solo los editan Gerente y Superadministrador.')
  id=data.get('objetivo');doc=self._document(db,id,actor);revision=data.get('revision')
  if type(revision) is not int or revision!=doc.get('revision',1):raise Conflict('La solicitud cambió. Ábrela de nuevo antes de proponer el cambio.')
  if doc['estado']=='CANCELADA':raise ValueError('La solicitud ya está cancelada; el folio permanece reservado.')
  values={};excess=[]
  if kind=='aprobar' and doc['estado']!='SOLICITADA':raise Conflict('Solo se aprueban requisiciones solicitadas.')
  if kind in ('surtir','corregir_surtido'):
   if actor['role'] not in APPROVERS|{'almacenista'}:raise PermissionError('Solo Almacenista, Superadministrador, Gerencia o AUXTI registran el surtido.')
   if kind=='surtir' and doc['estado'] not in ('SOLICITADA','APROBADA'):raise Conflict('La requisición ya tiene un surtido registrado. Solicita un cambio.')
   if kind=='corregir_surtido' and doc['estado'] not in ('SURTIDO','SURTIDA'):raise Conflict('Solo se corrigen entregas ya surtidas.')
   payload=data.get('datos');lines=payload.get('partidas') if isinstance(payload,dict) else None
   if not isinstance(payload,dict) or set(payload)-{'partidas','area','solicitante','observaciones','almacenInventario'} or not isinstance(lines,list) or len(lines)!=len(doc['partidas']):raise ValueError('Captura el surtido de todas las partidas.')
   original={line['materialId']:line for line in doc['partidas']};seen=set();actual=[]
   for line in lines:
    if not isinstance(line,dict) or set(line)!={'materialId','cantidadSurtida'} or type(line.get('materialId')) is not int or line['materialId'] not in original or line['materialId'] in seen or isinstance(line.get('cantidadSurtida'),bool):raise ValueError('Partida de surtido inválida o repetida.')
    try:q=decimal.Decimal(str(line['cantidadSurtida']))
    except decimal.InvalidOperation:raise ValueError('Cantidad surtida inválida.')
    if not q.is_finite() or not 0<=q<=999999999 or q.as_tuple().exponent < -6:raise ValueError('El surtido debe estar entre cero y 999999999, con hasta seis decimales.')
    source=original[line['materialId']];requested=decimal.Decimal(source['cantidad'])
    if q>requested:excess.append({'materialId':line['materialId'],'sku':source['sku'],'nombre':source['nombre'],'unidad':source['unidad'],'solicitada':source['cantidad'],'propuesta':format(q,'f'),'exceso':format(q-requested,'f')})
    seen.add(line['materialId']);actual.append({'materialId':line['materialId'],'cantidadSurtida':format(q,'f')})
   if not any(decimal.Decimal(r['cantidadSurtida'])>0 for r in actual):raise ValueError('Registra al menos una cantidad surtida mayor a cero.')
   if kind=='surtir' and actor['role']=='almacenista' and any(field in payload and payload[field]!=doc[field] for field in ('area','solicitante','observaciones')):raise PermissionError('Los datos originales de la requisición requieren una corrección autorizada; captura la entrega en observaciones de surtido.')
   area=payload.get('area',doc['area']);requester=text(payload.get('solicitante',doc['solicitante']),160);notes=text(payload.get('observaciones',doc['observaciones']),2000)
   if (area!=doc['area'] and area not in self.requisitions.areas.names(db=db)) or not requester:raise ValueError('Área o solicitante inválidos.')
   values={'partidas':actual,'area':area,'solicitante':requester,'observaciones':notes}
   if payload.get('almacenInventario') is not None:values['almacenInventario']=text(payload['almacenInventario'],100)
  if kind=='modificar':
   if doc['estado'] in ('SURTIDO','SURTIDA'):raise Conflict('La requisición ya tiene surtido registrado. Su entrega e historial se conservan.')
   values=data.get('datos')
   if not isinstance(values,dict) or set(values)-{'area','solicitante','observaciones','partidas'}:raise ValueError('Solo pueden corregirse área, solicitante, observaciones y partidas. Fecha, sucursal, SKU y folio se conservan.')
   area=values.get('area');requester=text(values.get('solicitante',''),160);notes=text(values.get('observaciones',''),2000);lines=values.get('partidas')
   if (area!=doc['area'] and area not in self.requisitions.areas.names(db=db)) or not requester or not isinstance(lines,list) or not 1<=len(lines)<=200:raise ValueError('Indica área, solicitante y entre 1 y 200 partidas.')
   old={line['materialId']:line for line in doc['partidas']};seen=set();snapshots=[]
   for line in lines:
    if not isinstance(line,dict) or set(line)-{'materialId','cantidad','observaciones'}:raise ValueError('Partida inválida.')
    idm=line.get('materialId');amount=line.get('cantidad');note=text(line.get('observaciones',''),500)
    if type(idm) is not int or idm in seen or isinstance(amount,bool):raise ValueError('Material inválido o repetido.')
    try:q=decimal.Decimal(str(amount))
    except decimal.InvalidOperation:raise ValueError('Cantidad inválida.')
    if not q.is_finite() or not 0<q<=999999999 or q.as_tuple().exponent < -6:raise ValueError('Cantidad positiva, máximo 999999999 y hasta seis decimales.')
    seen.add(idm)
    if idm in old:source=old[idm]
    else:
     row=db.execute('SELECT payload FROM req_materials WHERE id=?',(idm,)).fetchone();source=json.loads(row[0]) if row else None
     if not source or source['estado']!='ACTIVO' or not source['unidad']:raise ValueError('Material no disponible o sin unidad de entrega.')
    snapshots.append({'materialId':idm,'cantidad':format(q,'f'),'observaciones':note,**{key:source[key] for key in ('sku','nombre','unidad','proveedor')}})
   values={'area':area,'solicitante':requester,'observaciones':notes,'partidas':snapshots}
  return {'tipo':kind,'objetivo':doc['id'],'folio':doc['numero'],'sucursal':doc['sucursal'],'revision':revision,'motivo':reason,'datos':values,'excedentes':excess}
 def _apply(self,db,change,actor):
  doc=self._document(db,change['objetivo'],actor)
  if doc.get('revision',1)!=change['revision']:raise Conflict('La requisición cambió después de la propuesta. Rechaza esta y solicita una nueva.')
  if doc['estado']=='CANCELADA':raise Conflict('La requisición ya fue cancelada.')
  before=copy.deepcopy(doc)
  revision=doc.get('revision',1);db.execute('INSERT INTO req_document_versions VALUES(?,?,?)',(doc['id'],revision,json.dumps(doc,ensure_ascii=False)))
  if change['tipo']=='cancelar':doc['estado']='CANCELADA';doc['cancelacion']={'motivo':change['motivo'],'fecha':now(),'autorizadoPor':actor['email'],'solicitadoPor':change['solicitadoPor']}
  elif change['tipo']=='aprobar':doc['estado']='APROBADA';doc['aprobacion']={'fecha':now(),'autorizadoPor':actor['email'],'solicitadoPor':change['solicitadoPor']}
  elif change['tipo'] in ('surtir','corregir_surtido'):
   if change['tipo']=='surtir' and doc['estado'] not in ('SOLICITADA','APROBADA'):raise Conflict('La requisición ya tiene un surtido registrado.')
   if change['tipo']=='corregir_surtido' and doc['estado'] not in ('SURTIDO','SURTIDA'):raise Conflict('La requisición no está surtida.')
   if doc['estado']=='SOLICITADA':doc['aprobacion']={'fecha':now(),'autorizadoPor':actor['email'],'solicitadoPor':change['solicitadoPor']}
   for field in ('area','solicitante','observaciones'):
    if field in change['datos']:doc[field]=change['datos'][field]
   actual={r['materialId']:r['cantidadSurtida'] for r in change['datos']['partidas']}
   for line in doc['partidas']:line['cantidadSurtida']=actual[line['materialId']]
   doc['estado']='SURTIDO';doc['surtido']={'fecha':now(),'registradoPor':actor['email'],'observaciones':change['motivo']}
  else:
   doc.update(change['datos'])
   if doc['estado']=='APROBADA':doc['estado']='SOLICITADA';doc.pop('aprobacion',None)
  if hasattr(self,'inventory'):self.inventory.fulfillment(db,before,doc,change,actor)
  doc['revision']=revision+1;doc['ultimoCambio']={'tipo':change['tipo'],'motivo':change['motivo'],'fecha':now(),'autorizadoPor':actor['email'],'solicitadoPor':change['solicitadoPor']}
  db.execute('UPDATE req_documents SET payload=? WHERE id=?',(json.dumps(doc,ensure_ascii=False),doc['id']))
  return doc
 def submit(self,data,actor):
  if actor['role']=='requisicion' and data.get('tipo') not in ('modificar','cancelar','aprobar'):raise PermissionError('Este perfil solo puede solicitar corrección, cancelación o aprobación de sus propias requisiciones.')
  if actor['role'] not in EDITORS|{'almacenista','auxti','requisicion'}:raise PermissionError('Solo gerencia, superadministrador o almacenista pueden solicitar estos cambios.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');c=self._prepare(db,data,actor);c.update({'id':uuid.uuid4().hex,'fecha':now(),'solicitadoPor':actor['email'],'estado':'PENDIENTE','perfilSolicitante':actor['role']})
   # Correcciones, aprobaciones y cancelaciones del almacenista requieren autorización; el surtido se registra después de aprobarse.
   result=None
   old=self._document(db,c['objetivo'],actor);removed=c['tipo']=='modificar' and bool({r['materialId'] for r in old['partidas']}-{r['materialId'] for r in c['datos'].get('partidas',[])})
   c['requiereSistemas']=actor['role']=='auxti' and removed
   shortages=self.inventory.fulfillment_preview(db,old,c,actor) if hasattr(self,'inventory') else []
   if shortages:c.update({'inventarioInsuficiente':shortages,'alertaInventario':'Pedido con menos inventario: requiere aprobación para registrar saldo negativo.'})
   if shortages and c['tipo']=='surtir':c.update({'inventarioNegativoAutorizado':True,'inventarioNegativoDirecto':True,'alertaInventario':'Surtido registrado con menos inventario: se generó saldo negativo en el Kárdex.'})
   if c['excedentes']:c['alertaInventario']='Surtido mayor a lo solicitado: pendiente de autorización de Gerencia, AUXTI o Superadministrador. No se ha descontado inventario.'
   if not c['excedentes'] and (c['tipo']=='surtir' or not shortages and (actor['role'] in EDITORS or actor['role']=='auxti' and not removed)):result=self._apply(db,c,actor);c.update({'estado':'APROBADA','resueltoPor':actor['email'],'resuelto':now(),'comentario':'Surtido directo registrado por '+actor['role']+'.' if c['tipo']=='surtir' else 'Cambio autorizado por '+actor['role']+'.'})
   if c['tipo']=='surtir' and result:
    for pending_id,payload in db.execute("SELECT id,payload FROM req_changes WHERE status='PENDIENTE' AND json_extract(payload,'$.objetivo')=? AND json_extract(payload,'$.tipo')='aprobar'",(c['objetivo'],)).fetchall():
     pending=json.loads(payload)
     if pending['revision']==c['revision']:
      pending.update({'estado':'APROBADA','resueltoPor':actor['email'],'resuelto':now(),'comentario':'Aprobación con surtido real registrado.'});db.execute('UPDATE req_changes SET status=?,payload=? WHERE id=?',('APROBADA',json.dumps(pending,ensure_ascii=False),pending_id))
   db.execute('INSERT INTO req_changes VALUES(?,?,?,?,?,?)',(c['id'],c['sucursal'],actor['email'],c['estado'],c['fecha'],json.dumps(c,ensure_ascii=False)))
  return {'cambio':c,'documento':result}
 def list(self,actor):
  branches=visible_branches(actor);clauses=['branch IN ('+','.join('?' for _ in branches)+')'];params=list(branches)
  if actor['role'] not in EDITORS|{'auxti'}:clauses.append('requester=?');params.append(actor['email'])
  if actor['role']=='requisicion':clauses.append("json_extract(payload,'$.objetivo') IN (SELECT id FROM req_documents WHERE creator=?)");params.append(actor['email'])
  with self.store.connect() as db:rows=db.execute('SELECT payload FROM req_changes WHERE '+' AND '.join(clauses)+' ORDER BY created_at DESC,rowid DESC LIMIT 500',params).fetchall()
  changes=[json.loads(row[0]) for row in rows]
  if actor['role']=='requisicion':changes=[requester_change(c) for c in changes]
  return {'cambios':changes,'puedeAutorizar':actor['role'] in APPROVERS,'limite':500}
 def decide(self,id,data,actor):
  if actor['role'] not in APPROVERS:raise PermissionError('Solo Superadministrador, AUXTI y Gerente pueden aprobar o rechazar solicitudes.')
  approved=data.get('aprobar');comment=text(data.get('comentario',''),1000)
  if type(approved) is not bool:raise ValueError('Indica aprobar o rechazar.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM req_changes WHERE id=?',(id,)).fetchone()
   if not row:raise ValueError('Cambio no encontrado.')
   c=json.loads(row[0])
   if not comment and c['tipo'] not in ('cancelar','surtir','corregir_surtido'):raise ValueError('Indica el comentario de la decisión.')
   if c['sucursal'] not in visible_branches(actor):raise PermissionError('No tienes acceso a esta sucursal.')
   if c['estado']!='PENDIENTE':raise Conflict('El cambio ya fue resuelto. Actualiza la lista.')
   result=None
   if approved:
    # No aprobar propuestas de cuentas inactivas, sin módulo o sin el almacén asignado.
    user=db.execute('SELECT role,active FROM users WHERE email=?',(c['solicitadoPor'],)).fetchone()
    if c.get('requiereSistemas') and c['tipo']!='cancelar':
     if actor['email']!='sistemas@grupomipan.com':raise PermissionError('Solo sistemas@grupomipan.com puede aprobar eliminaciones de AUXTI.')
     if not user or not user[1] or user[0]!='auxti':raise Conflict('El solicitante ya no es AUXTI activo. Rechaza la propuesta.')
     modules=db.execute('SELECT modules FROM role_modules WHERE role=?',('auxti',)).fetchone()
     if not modules or 'requisiciones' not in json.loads(modules[0]):raise Conflict('AUXTI perdió acceso al módulo. Rechaza la propuesta.')
    elif c.get('perfilSolicitante')=='auxti':
     modules=db.execute("SELECT modules FROM role_modules WHERE role='auxti'").fetchone()
     if not user or not user[1] or user[0]!='auxti' or not modules or 'requisiciones' not in json.loads(modules[0]):raise Conflict('AUXTI perdió acceso al módulo. Rechaza la propuesta.')
    elif c.get('perfilSolicitante') in EDITORS:
     role=c['perfilSolicitante'];modules=db.execute('SELECT modules FROM role_modules WHERE role=?',(role,)).fetchone()
     if not user or not user[1] or user[0]!=role or not modules or 'requisiciones' not in json.loads(modules[0]):raise Conflict('El solicitante perdió el acceso a requisiciones.')
    elif c.get('perfilSolicitante')=='requisicion':
     if not user or not user[1] or user[0]!='requisicion':raise Conflict('El solicitante ya no tiene activo el perfil Requisición. Rechaza la propuesta.')
     modules=db.execute("SELECT modules FROM role_modules WHERE role='requisicion'").fetchone();owner=db.execute('SELECT creator FROM req_documents WHERE id=?',(c['objetivo'],)).fetchone()
     access=db.execute('SELECT sucursales FROM user_requisition_access WHERE email=?',(c['solicitadoPor'],)).fetchone()
     if not modules or 'requisiciones' not in json.loads(modules[0]) or not owner or owner[0]!=c['solicitadoPor'] or not access or c['sucursal'] not in json.loads(access[0]):raise Conflict('El solicitante perdió acceso a su requisición. Rechaza la propuesta.')
    else:
     if not user or not user[1] or user[0]!='almacenista':raise Conflict('El solicitante ya no es un almacenista activo. Rechaza la propuesta.')
     access=db.execute('SELECT almacenes FROM user_requisition_access WHERE email=?',(c['solicitadoPor'],)).fetchone();modules=db.execute('SELECT modules FROM role_modules WHERE role=?',('almacenista',)).fetchone()
     if not access or c['sucursal'] not in json.loads(access[0]) or not modules or 'requisiciones' not in json.loads(modules[0]):raise Conflict('El solicitante perdió acceso al almacén o módulo. Rechaza la propuesta.')
    if c.get('inventarioInsuficiente'):
     if c['tipo']!='surtir' and data.get('autorizarNegativo') is not True:raise ValueError('Confirma la autorización del saldo negativo por inventario insuficiente.')
     c['inventarioNegativoAutorizado']=True
    result=self._apply(db,c,actor)
    if c['tipo']=='surtir':
     for pending_id,payload in db.execute("SELECT id,payload FROM req_changes WHERE status='PENDIENTE' AND json_extract(payload,'$.objetivo')=? AND json_extract(payload,'$.tipo')='aprobar'",(c['objetivo'],)).fetchall():
      pending=json.loads(payload)
      if pending['revision']==c['revision']:
       pending.update({'estado':'APROBADA','resueltoPor':actor['email'],'resuelto':now(),'comentario':'Aprobación con surtido real registrado.'});db.execute('UPDATE req_changes SET status=?,payload=? WHERE id=?',('APROBADA',json.dumps(pending,ensure_ascii=False),pending_id))
   c.update({'estado':'APROBADA' if approved else 'RECHAZADA','resueltoPor':actor['email'],'resuelto':now(),'comentario':comment});db.execute('UPDATE req_changes SET status=?,payload=? WHERE id=?',(c['estado'],json.dumps(c,ensure_ascii=False),id))
  return {'cambio':c,'documento':result}
 def history(self,id,actor):
  with self.store.connect() as db:
   self._document(db,id,actor)
   versions=[{'revision':rev,'documento':json.loads(payload)} for rev,payload in db.execute('SELECT revision,payload FROM req_document_versions WHERE document_id=? ORDER BY revision',(id,))]
   changes=[json.loads(row[0]) for row in db.execute("SELECT payload FROM req_changes WHERE json_extract(payload,'$.objetivo')=? ORDER BY created_at,rowid",(id,))]
  if actor['role']=='requisicion':
   versions=[{**v,'documento':requester_document(v['documento'])} for v in versions];changes=[requester_change(c) for c in changes]
  return {'versiones':versions,'cambios':changes}
