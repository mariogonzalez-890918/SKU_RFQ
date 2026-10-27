"""Autorizaciones de sistemas para operaciones destructivas solicitadas por AUXTI."""
import copy,hashlib,json,uuid
from permissions import require_module
from requisiciones import Conflict,now,text
OWNER='sistemas@grupomipan.com'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
class AdminApprovals:
 def __init__(self,store,sales,images,backups):
  self.store=store;self.sales=sales;self.images=images;self.backups=backups
  with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS admin_approvals(id TEXT PRIMARY KEY,status TEXT NOT NULL,requester TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL)')
 def authorize(self,actor):
  if actor['role'] not in ('superadmin','auxti'):raise PermissionError('Solo administración puede consultar estas solicitudes.')
 def prepare(self,action,data,actor):
  self.authorize(actor)
  if not isinstance(data,dict):raise ValueError('Datos de autorización inválidos.')
  if action in ('baja_compra','baja_venta'):
   module='compras' if action=='baja_compra' else 'ventas';require_module(actor,module);catalog=self.store.get() if module=='compras' else self.sales.get();id=data.get('id')
   row=next((r for r in catalog['state']['registros'] if type(id) is int and r['id']==id and not r['eliminado']),None)
   if not row:raise ValueError('Artículo no disponible para baja.')
   return {'id':id},{'Acción':'Baja de SKU '+module,'Artículo':row['nombre'],'SKU':row['sku'],'Revisión':catalog['revision']},digest([catalog['revision'],row])
  if action=='quitar_imagen':
   require_module(actor,'requisiciones');require_module(actor,'imagenes');id=data.get('materialId');row=next((r for r in self.images.list(actor)['imagenes'] if type(id) is int and r['materialId']==id),None)
   if not row:raise ValueError('Imagen no disponible.')
   return {'materialId':id},{'Acción':'Quitar imagen','SKU al cargar':row['skuAlCargar'],'Archivo':row['archivo'],'Imagen':row['imagenId']},row['imagenId']
  if action=='desactivar_usuario':
   email=str(data.get('email','')).strip().lower();row=next((u for u in self.store.users() if u['email']==email),None)
   if not row or row['role']=='superadmin' or email in (OWNER,actor['email']) or not row['active']:raise ValueError('No se puede solicitar esta desactivación.')
   with self.store.connect() as db:token=self.store.user_fingerprint(db,email)
   return {'email':email},{'Acción':'Desactivar usuario','Correo':email,'Nombre':row['name'],'Perfil':row['role']},token
  if action in ('reiniciar_modulo','restaurar_modulo'):
   normalized={'modulo':data.get('modulo')}
   if action=='restaurar_modulo':normalized['respaldo']=data.get('respaldo');review=self.backups.review(normalized,actor)
   else:review=self.backups.reset(normalized,actor)
   summary={'Acción':'Vaciar módulo' if action=='reiniciar_modulo' else 'Restaurar módulo','Módulo':review['nombre'],'Datos actuales':review['actual']}
   if action=='restaurar_modulo':summary['Datos del respaldo']=review['respaldo']
   return normalized,summary,digest([review['huellaActual'],normalized])
  raise ValueError('Operación no autorizable.')
 def submit(self,data,actor):
  if actor['role']!='auxti':raise PermissionError('Estas solicitudes son exclusivas de AUXTI.')
  action=data.get('accion');reason=text(data.get('motivo',''),1000)
  if not reason:raise ValueError('Escribe el motivo para sistemas.')
  normalized,summary,token=self.prepare(action,data.get('datos'),actor)
  request={'id':uuid.uuid4().hex,'accion':action,'datos':normalized,'resumen':summary,'huella':token,'motivo':reason,'solicitadoPor':actor['email'],'fecha':now(),'estado':'PENDIENTE'}
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   for row in db.execute("SELECT payload FROM admin_approvals WHERE requester=? AND status='PENDIENTE'",(actor['email'],)):
    old=json.loads(row[0])
    if old['accion']==action and old['huella']==token:return {'solicitud':self.public(old),'repetida':True}
   db.execute('INSERT INTO admin_approvals VALUES(?,?,?,?,?)',(request['id'],'PENDIENTE',actor['email'],request['fecha'],json.dumps(request,ensure_ascii=False)))
  return {'solicitud':self.public(request)}
 @staticmethod
 def public(request):return {k:v for k,v in request.items() if k not in ('datos','huella')}
 def list(self,actor):
  self.authorize(actor)
  with self.store.connect() as db:rows=db.execute('SELECT payload FROM admin_approvals ORDER BY created_at DESC,rowid DESC LIMIT 500').fetchall()
  return {'solicitudes':[self.public(json.loads(r[0])) for r in rows],'puedeAutorizar':actor['email']==OWNER}
 def detail(self,id,actor):
  self.authorize(actor)
  with self.store.connect() as db:row=db.execute('SELECT payload FROM admin_approvals WHERE id=?',(id,)).fetchone()
  if not row:raise ValueError('Solicitud de autorización no encontrada.')
  return json.loads(row[0])
 def execute(self,request,actor):
  data=request['datos'];action=request['accion']
  with self.store.connect() as db:
   row=db.execute('SELECT role,active FROM users WHERE email=?',(request['solicitadoPor'],)).fetchone();modules=db.execute("SELECT modules FROM role_modules WHERE role='auxti'").fetchone()
  if not row or row!=('auxti',1):raise Conflict('El solicitante ya no es AUXTI activo.')
  requester={'email':request['solicitadoPor'],'role':'auxti','modulos':json.loads(modules[0])}
  _,_,token=self.prepare(action,data,requester)
  if token!=request['huella']:raise Conflict('Los datos cambiaron después de la solicitud. Rechaza esta y solicita una nueva autorización.')
  if action in ('baja_compra','baja_venta'):
   target=self.store if action=='baja_compra' else self.sales;catalog=target.get();current=next(r for r in catalog['state']['registros'] if r['id']==data['id']);
   if digest([catalog['revision'],current])!=token:raise Conflict('El catálogo cambió. Solicita una nueva autorización.')
   catalog=copy.deepcopy(catalog);record=next(r for r in catalog['state']['registros'] if r['id']==data['id']);record['eliminado']=True;record['editado']=True;catalog['state']['reservados']=list(set(catalog['state']['reservados'])|{record['sku']});result=target.put(catalog,actor)
   if result is None:raise Conflict('El catálogo cambió. Solicita una nueva autorización.')
  elif action=='quitar_imagen':self.images.remove(data['materialId'],actor,expected=token)
  elif action=='desactivar_usuario':
   user=next(u for u in self.store.users() if u['email']==data['email']);self.store.manage_user({**user,'active':False,'_huellaUsuario':token},actor)
  elif action=='reiniciar_modulo':
   review=self.backups.reset(data,actor)
   if digest([review['huellaActual'],data])!=token:raise Conflict('El módulo cambió. Solicita una nueva autorización.')
   self.backups.reset({**data,'huellaActual':review['huellaActual'],'texto':'VACIAR','confirmar':True},actor,True)
  elif action=='restaurar_modulo':
   review=self.backups.review(data,actor)
   if digest([review['huellaActual'],data])!=token:raise Conflict('El módulo cambió. Solicita una nueva autorización.')
   self.backups.review({**data,'huellaActual':review['huellaActual'],'confirmar':True},actor,True)
 def decide(self,id,data,actor):
  if actor['role']!='superadmin' or actor['email']!=OWNER:raise PermissionError('Solo sistemas@grupomipan.com puede autorizar eliminaciones de AUXTI.')
  approved=data.get('aprobar');comment=text(data.get('comentario',''),1000)
  if type(approved) is not bool or not comment:raise ValueError('Indica decisión y comentario.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM admin_approvals WHERE id=?',(id,)).fetchone()
   if not row:raise ValueError('Solicitud no encontrada.')
   request=json.loads(row[0])
   if request['estado']!='PENDIENTE':raise Conflict('La solicitud ya fue resuelta o está aplicándose.')
   request.update({'estado':'APLICANDO' if approved else 'RECHAZADA','resueltoPor':actor['email'],'resuelto':now(),'comentario':comment});db.execute('UPDATE admin_approvals SET status=?,payload=? WHERE id=?',(request['estado'],json.dumps(request,ensure_ascii=False),id))
  error=None
  if approved:
   try:self.execute(request,actor);request['estado']='APROBADA'
   except (ValueError,PermissionError,Conflict) as exc:error=str(exc);request.update({'estado':'NO_APLICADA','error':error})
   except Exception:request.update({'estado':'REVISAR','error':'La ejecución se interrumpió. Sistemas debe revisar el estado antes de realizar otra operación.'});error=request['error']
   with self.store.connect() as db:db.execute('UPDATE admin_approvals SET status=?,payload=? WHERE id=?',(request['estado'],json.dumps(request,ensure_ascii=False),id))
  return {'ok':error is None,'solicitud':self.public(request),**({'error':error} if error else {})}
