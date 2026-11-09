"""Publicación serializada de Excel PT en OneDrive personal; tokens privados con DPAPI."""
import base64,ctypes,ctypes.wintypes,json,re,threading,time,urllib.request,urllib.error,urllib.parse
from pt import BRANCHES,MANAGERS
from comercial import dumps
from requisiciones import Conflict,now,text

GRAPH='https://graph.microsoft.com/v1.0'
LOGIN='https://login.microsoftonline.com/consumers/oauth2/v2.0'
SCOPES='User.Read Files.ReadWrite offline_access'

def crypt(raw,decrypt=False):
 class Blob(ctypes.Structure):_fields_=[('size',ctypes.wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
 buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob();api=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
 if not api(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('No se puede abrir la conexión privada de OneDrive con esta cuenta de Windows. Vuelve a conectar OneDrive.')
 try:return ctypes.string_at(target.data,target.size)
 finally:ctypes.windll.kernel32.LocalFree(target.data)

class CloudError(ValueError):
 def __init__(self,code):self.code=code;super().__init__('OneDrive no completó la operación ('+str(code)+'). Revisa la conexión y vuelve a intentar.')

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def request(url,method='GET',data=None,token=None,headers=None,form=False):
 if not url.startswith(('https://graph.microsoft.com/','https://login.microsoftonline.com/')) and not upload_url(url):raise ValueError('Destino de Microsoft no válido.')
 h={**(headers or {})}
 if token:h['Authorization']='Bearer '+token
 if form:data=urllib.parse.urlencode(data).encode();h['Content-Type']='application/x-www-form-urlencoded'
 elif isinstance(data,dict):data=dumps(data).encode();h['Content-Type']='application/json'
 req=urllib.request.Request(url,data=data,headers=h,method=method)
 try:
  with urllib.request.build_opener(NoRedirect()).open(req,timeout=25) as response:
   raw=response.read(2*1024*1024);return json.loads(raw) if raw else {}
 except urllib.error.HTTPError as e:
  if form:
   try:return json.loads(e.read(16384))
   except (ValueError,UnicodeError):pass
  raise CloudError(e.code)
 except (OSError,TimeoutError):raise CloudError('sin conexión')

def upload_url(url):
 p=urllib.parse.urlsplit(url);host=p.hostname or ''
 return p.scheme=='https' and not p.username and any(host.endswith(s) for s in ('.1drv.com','.sharepoint.com','.onedrive.com'))

class OneDrivePT:
 def __init__(self,pt):
  self.pt=pt;self.store=pt.store;pt.publisher=self;self.worker_lock=threading.Lock();self.auth_lock=threading.Lock()
  with self.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS pt_cloud(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL,secret TEXT NOT NULL)');db.execute('INSERT OR IGNORE INTO pt_cloud VALUES(1,1,?,?)',(dumps({'cliente':'','cuenta':'soportetecnico@grupomipan.com','carpetas':{b:'GMP_PT/'+b.replace(' ','_') for b in BRANCHES},'habilitado':False}),'') )
 def read(self):
  with self.store.connect() as db:r=db.execute('SELECT revision,payload,secret FROM pt_cloud').fetchone()
  return r[0],json.loads(r[1]),r[2]
 def secret(self,raw):return json.loads(crypt(base64.b64decode(raw),True)) if raw else {}
 def save_secret(self,s):
  encrypted=base64.b64encode(crypt(dumps(s).encode())).decode() if s else ''
  with self.store.connect() as db:db.execute('UPDATE pt_cloud SET secret=? WHERE id=1',(encrypted,))
 def admin(self,actor):
  self.pt.scope(actor)
  if actor['role']!='superadmin':raise PermissionError('Solo Superadministrador conecta o configura la cuenta de OneDrive.')
 def status(self,actor):
  allowed=self.pt.scope(actor);revision,config,_=self.read()
  with self.store.connect() as db:
   jobs=[{'sucursal':b,'mes':m,'pendiente':r>s,'estado':state,'error':error if actor['role'] in MANAGERS else '',**({k:v for k,v in json.loads(payload).items() if k in ('archivo','enlace','publicado')} if actor['role'] in MANAGERS else {})} for b,m,r,s,state,error,payload in db.execute('SELECT branch,month,revision,synced,state,error,payload FROM pt_exports ORDER BY month DESC,branch') if b in allowed]
  result={'conectado':bool(config.get('conectado')),'habilitado':config.get('habilitado',False),'publicaciones':jobs[:36]}
  if actor['role']=='superadmin':result.update({'revision':revision,'configuracion':config})
  return result
 def configure(self,data,actor):
  with self.auth_lock:return self._configure(data,actor)
 def _configure(self,data,actor):
  self.admin(actor);revision,old,_=self.read();client=text(data.get('cliente',''),36);account=text(data.get('cuenta',''),160).lower();folders=data.get('carpetas')
  if not re.fullmatch('[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}',client) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',account):raise ValueError('Indica el Client ID de Microsoft y el correo propietario.')
  if not isinstance(folders,dict) or set(folders)!=set(BRANCHES):raise ValueError('Configura una carpeta para cada una de las tres sucursales.')
  normalized={}
  for b,p in folders.items():
   if not isinstance(p,str) or not re.fullmatch(r'[A-Za-z0-9_ /-]{1,160}',p) or any(v in ('','.','..') for v in p.split('/')):raise ValueError('Usa una ruta de carpeta válida, sin enlaces ni archivos.')
   normalized[b]=p.strip()
  if len(set(normalized.values()))!=3:raise ValueError('Cada sucursal debe publicar en una carpeta diferente.')
  changed=client!=old['cliente'] or account!=old['cuenta'];new={**old,'cliente':client,'cuenta':account,'carpetas':normalized,'habilitado':data.get('habilitado') is True}
  if changed:new['conectado']=False
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');current=db.execute('SELECT revision FROM pt_cloud').fetchone()[0]
   if current!=data.get('revision'):raise Conflict('La configuración cambió. Actualiza antes de guardar.')
   # No mover archivos ya publicados a otro destino por accidente.
   if normalized!=old['carpetas'] and db.execute('SELECT 1 FROM pt_exports WHERE synced>0').fetchone():raise ValueError('Hay archivos publicados. Conserva sus carpetas para mantener el historial mensual.')
   db.execute('UPDATE pt_cloud SET revision=revision+1,payload=?,secret=CASE WHEN ? THEN ? ELSE secret END WHERE id=1',(dumps(new),changed,''))
  self.kick();return self.status(actor)
 def start_auth(self,actor):
  self.admin(actor);_,config,_=self.read()
  if not config['cliente']:raise ValueError('Primero configura el identificador de aplicación de Microsoft (Client ID).')
  with self.auth_lock:
   response=request(LOGIN+'/devicecode','POST',{'client_id':config['cliente'],'scope':SCOPES},form=True)
   if 'device_code' not in response:raise ValueError('Microsoft no inició la conexión. Revisa que la aplicación admita cuentas personales y clientes públicos.')
   uri=response.get('verification_uri','')
   if urllib.parse.urlsplit(uri).hostname not in ('microsoft.com','www.microsoft.com','login.microsoftonline.com','login.live.com'):raise ValueError('Microsoft devolvió una dirección de autorización inesperada.')
   secret=self.secret(self.read()[2]);secret['device']={'code':response['device_code'],'expires':time.time()+response['expires_in'],'interval':response.get('interval',5),'next':0,'actor':actor['email'],'client':config['cliente']};self.save_secret(secret)
   return {'direccion':uri,'codigo':response['user_code'],'expiraEn':response['expires_in'],'intervalo':response.get('interval',5)}
 def poll_auth(self,actor):
  self.admin(actor)
  with self.auth_lock:
   revision,config,raw=self.read();s=self.secret(raw);d=s.get('device')
   if not d or d['actor']!=actor['email'] or d['client']!=config['cliente']:raise ValueError('Inicia una nueva conexión con Microsoft.')
   if time.time()>d['expires']:raise ValueError('La autorización expiró. Vuelve a conectar OneDrive.')
   if time.time()<d['next']:return {'pendiente':True}
   response=request(LOGIN+'/token','POST',{'client_id':config['cliente'],'grant_type':'urn:ietf:params:oauth:grant-type:device_code','device_code':d['code']},form=True);d['next']=time.time()+d['interval']
   if response.get('error') in ('authorization_pending','slow_down'):
    if response['error']=='slow_down':d['interval']+=5;d['next']=time.time()+d['interval']
    self.save_secret(s);return {'pendiente':True}
   if 'access_token' not in response:raise ValueError('Microsoft no autorizó la conexión. Vuelve a iniciar el proceso.')
   identity=request(GRAPH+'/me?$select=id,mail,userPrincipalName,otherMails',token=response['access_token']);emails=[identity.get('mail',''),identity.get('userPrincipalName',''),*identity.get('otherMails',[])]
   if config['cuenta'] not in [e.lower() for e in emails if isinstance(e,str)]:raise ValueError('Iniciaste sesión con otra cuenta. Utiliza el correo propietario configurado.')
   tokens={'access_token':response['access_token'],'refresh_token':response.get('refresh_token',''),'expires':time.time()+response['expires_in']-90};self.save_secret(tokens);config.update({'conectado':True,'cuentaConfirmada':config['cuenta']})
   with self.store.connect() as db:db.execute('UPDATE pt_cloud SET revision=revision+1,payload=? WHERE id=1',(dumps(config),))
  self.kick();return {'pendiente':False,'conectado':True}
 def disconnect(self,actor):
  self.admin(actor)
  with self.auth_lock:
   _,config,_=self.read();config.update({'conectado':False,'habilitado':False});self.save_secret({})
   with self.store.connect() as db:db.execute('UPDATE pt_cloud SET revision=revision+1,payload=? WHERE id=1',(dumps(config),))
  return self.status(actor)
 def access_token(self):
  with self.auth_lock:
   _,c,raw=self.read();s=self.secret(raw)
   if s.get('expires',0)>time.time():return s['access_token']
   if not s.get('refresh_token'):raise ValueError('Vuelve a autorizar la conexión de OneDrive.')
   r=request(LOGIN+'/token','POST',{'client_id':c['cliente'],'grant_type':'refresh_token','refresh_token':s['refresh_token'],'scope':SCOPES},form=True)
   if not r.get('access_token'):raise ValueError('La conexión expiró o fue revocada. Vuelve a conectar OneDrive.')
   self.save_secret({'access_token':r['access_token'],'refresh_token':r.get('refresh_token',s['refresh_token']),'expires':time.time()+r['expires_in']-90});return r['access_token']
 def retry(self,actor):
  self.pt.scope(actor)
  if actor['role'] not in MANAGERS:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador publican los archivos.')
  _,config,_=self.read()
  if not config.get('conectado') or not config.get('habilitado'):raise ValueError('Conecta OneDrive y activa la publicación automática primero.')
  with self.store.connect() as db:db.execute('UPDATE pt_exports SET retry_at=0,attempts=0 WHERE revision>synced')
  self.kick();return {'ok':True,'mensaje':'Publicación iniciada. Los ingresos ya están guardados en GMP.'}
 def kick(self):
  _,config,_=self.read()
  if not config.get('conectado') or not config.get('habilitado') or not self.worker_lock.acquire(False):return
  def run():
   try:
    while self.store.path.exists():
     if self.process_once():continue
     _,current,_=self.read()
     if not current.get('habilitado') or not current.get('conectado'):break
     with self.store.connect() as db:future=db.execute('SELECT MIN(MAX(retry_at,lease)) FROM pt_exports WHERE revision>synced AND attempts<8').fetchone()[0]
     if future is None:break
     time.sleep(max(1,min(30,future-time.time()+.1)))
   finally:self.worker_lock.release()
  threading.Thread(target=run,daemon=True,name='PT-OneDrive').start()
 def process_once(self):
  _,config,_=self.read()
  if not config.get('habilitado') or not config.get('conectado'):return False
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');job=db.execute('SELECT branch,month,revision,synced,payload FROM pt_exports WHERE revision>synced AND lease<? AND retry_at<? AND attempts<8 ORDER BY month,branch LIMIT 1',(time.time(),time.time())).fetchone()
   if not job:return False
   branch,month,revision,_,payload=job;db.execute("UPDATE pt_exports SET lease=?,state='PUBLICANDO' WHERE branch=? AND month=?",(time.time()+240,branch,month))
  try:
   actor={'role':'superadmin','email':'publicador-pt','modulos':['pt']};raw=self.pt.workbook(actor,{'sucursal':branch,'mes':month});token=self.access_token();remote=self.publish_file(config,branch,month,raw,json.loads(payload),token)
   with self.store.connect() as db:db.execute("UPDATE pt_exports SET synced=?,state=CASE WHEN revision>? THEN 'PENDIENTE' ELSE 'PUBLICADO' END,lease=0,error='',attempts=0,retry_at=0,payload=? WHERE branch=? AND month=?",(revision,revision,dumps({**remote,'publicado':now()}),branch,month))
  except Exception as error:
   # Nunca guardar respuestas crudas, URLs de carga ni tokens dentro del estado público.
   message=str(error) if isinstance(error,(CloudError,ValueError)) else 'No se pudo publicar. Reintenta la conexión con Microsoft.'
   with self.store.connect() as db:db.execute("UPDATE pt_exports SET state='PENDIENTE',lease=0,error=?,retry_at=?,attempts=attempts+1 WHERE branch=? AND month=?",(message[:300],time.time()+60,branch,month))
  return True
 def publish_file(self,config,branch,month,raw,old,token):
  folder=config['carpetas'][branch];path='';parent='root'
  for part in folder.split('/'):
   path+='/'+part
   try:item=request(GRAPH+'/me/drive/root:'+urllib.parse.quote(path,safe='/'),token=token)
   except CloudError as error:
    if error.code!=404:raise
    item=request(GRAPH+'/me/drive/'+('root' if parent=='root' else 'items/'+parent)+'/children','POST',{'name':part,'folder':{},'@microsoft.graph.conflictBehavior':'fail'},token)
   if 'folder' not in item:raise ValueError('El destino de PT debe ser una carpeta de OneDrive.')
   parent=item['id']
  name='PT_'+branch.replace(' ','_')+'_'+month+'.xlsx';headers={}
  if old.get('archivoId'):
   current=request(GRAPH+'/me/drive/items/'+urllib.parse.quote(old['archivoId'],safe=''),token=token)
   if current.get('eTag')!=old.get('etag'):raise ValueError('El Excel fue modificado fuera de GMP. Conserva esa copia y revisa el archivo antes de reanudar la publicación.')
   url=GRAPH+'/me/drive/items/'+urllib.parse.quote(old['archivoId'],safe='')+'/createUploadSession';headers['If-Match']=old['etag']
  else:url=GRAPH+'/me/drive/items/'+urllib.parse.quote(parent,safe='')+':/'+urllib.parse.quote(name,safe='')+':/createUploadSession'
  session=request(url,'POST',{'item':{'@microsoft.graph.conflictBehavior':'replace' if old.get('archivoId') else 'fail'}},token,headers);upload=session.get('uploadUrl','')
  if not upload_url(upload):raise ValueError('Microsoft devolvió un destino de carga no válido.')
  result={};size=len(raw)
  for offset in range(0,size,3276800):
   chunk=raw[offset:offset+3276800];result=request(upload,'PUT',chunk,headers={'Content-Type':'application/octet-stream','Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{size}'})
  if not result.get('id') or not result.get('eTag'):raise ValueError('Microsoft no confirmó que el Excel se guardó. Revisa la publicación antes de reintentar.')
  return {'archivoId':result['id'],'etag':result['eTag'],'archivo':name,'enlace':result.get('webUrl','')}
