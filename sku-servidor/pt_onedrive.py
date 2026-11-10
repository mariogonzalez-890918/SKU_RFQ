"""Publicación serializada de Excel PT en OneDrive personal; tokens privados con DPAPI."""
import base64,ctypes,ctypes.wintypes,json,re,threading,time,urllib.request,urllib.error,urllib.parse
from pt_folder import validate_root,publish_folder,probe_folder
from pt_registro import new_workbook,merge_workbook
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

def download_file(url):
 for _ in range(5):
  p=urllib.parse.urlsplit(url);host=p.hostname or ''
  if p.scheme!='https' or p.username or not any(host.endswith(s) for s in ('.1drv.com','.sharepoint.com','.onedrive.com','.storage.live.com','.livefilestore.com')):raise ValueError('Microsoft devolvió un destino de descarga no válido.')
  try:
   with urllib.request.build_opener(NoRedirect()).open(urllib.request.Request(url),timeout=25) as response:
    raw=response.read(100*1024*1024+1)
    if len(raw)>100*1024*1024:raise ValueError('El libro supera 100 MB.')
    return raw
  except urllib.error.HTTPError as error:
   if error.code in (301,302,303,307,308):url=urllib.parse.urljoin(url,error.headers.get('Location',''));continue
   raise CloudError(error.code)
  except OSError:raise CloudError('sin conexión')
 raise ValueError('Microsoft no completó la descarga del libro.')

class OneDrivePT:
 def __init__(self,pt):
  self.pt=pt;self.store=pt.store;pt.publisher=self;self.worker_lock=threading.Lock();self.auth_lock=threading.Lock();self.destination_lock=threading.Lock()
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
  result={'modo':config.get('modo','microsoft'),'conectado':self.ready(config),'habilitado':config.get('habilitado',False),'publicaciones':jobs[:36]}
  if actor['role']=='superadmin':
   with self.store.connect() as db:originals=set(db.execute('SELECT branch,month FROM pt_original_workbooks'))
   for job in jobs:job['respaldoOriginal']=(job['sucursal'],job['mes']) in originals
  if actor['role']=='superadmin':result.update({'revision':revision,'configuracion':config})
  return result
 def ready(self,config):return bool(config.get('directorio')) if config.get('modo')=='carpeta' else bool(config.get('conectado'))
 def configure(self,data,actor):
  self.admin(actor)
  if not self.destination_lock.acquire(False):raise Conflict('Hay una publicación en curso. Espera a que termine antes de cambiar el destino.')
  try:
   with self.auth_lock:result=self._configure(data,actor)
  finally:self.destination_lock.release()
  self.kick();return result
 def _configure(self,data,actor):
  self.admin(actor);revision,old,_=self.read();mode=data.get('modo','microsoft');client=text(data.get('cliente',''),36);account=text(data.get('cuenta',''),160).lower();folders=data.get('carpetas')
  if mode not in ('microsoft','carpeta'):raise ValueError('Selecciona conexión Microsoft o carpeta sincronizada.')
  directory=validate_root(data.get('directorio','')) if mode=='carpeta' else ''
  if mode=='microsoft' and not re.fullmatch('[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}',client):raise ValueError('Indica el Client ID de Microsoft.')
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',account):raise ValueError('Indica el correo propietario de los archivos.')
  if not isinstance(folders,dict) or set(folders)!=set(BRANCHES):raise ValueError('Configura una carpeta para cada una de las tres sucursales.')
  normalized={}
  for b,p in folders.items():
   if not isinstance(p,str) or not re.fullmatch(r'[A-Za-z0-9_ /-]{1,160}',p) or any(v in ('','.','..') for v in p.split('/')):raise ValueError('Usa una ruta de carpeta válida, sin enlaces ni archivos.')
   normalized[b]=p.strip()
   if not normalized[b]:raise ValueError('Indica una carpeta para cada sucursal.')
   if mode=='carpeta' and any(v.strip()!=v or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',v,re.I) for v in normalized[b].split('/')):raise ValueError('La carpeta contiene un nombre no válido para Windows.')
  if len(set(v.casefold() for v in normalized.values()))!=3:raise ValueError('Cada sucursal debe publicar en una carpeta diferente.')
  method_changed=mode!=old.get('modo','microsoft')
  with self.store.connect() as db:was_published=bool(db.execute('SELECT 1 FROM pt_exports WHERE synced>0').fetchone())
  if method_changed and was_published and data.get('habilitado') is True:raise ValueError('Desactiva la publicación automática antes de cambiar el método. Los archivos actuales se conservarán.')
  changed=client!=old['cliente'] or account!=old['cuenta'] or mode!=old.get('modo','microsoft');destination_changed=mode!=old.get('modo','microsoft') or directory!=old.get('directorio','') or normalized!=old['carpetas'];new={**old,'libroExistente':data.get('libroExistente',old.get('libroExistente',False)) is True,'modo':mode,'directorio':directory,'cliente':client,'cuenta':account,'carpetas':normalized,'habilitado':data.get('habilitado') is True}
  if method_changed and mode=='microsoft':new['seleccionarLibros']=True;new['archivosPorSucursal']={}
  if mode=='microsoft' and new['libroExistente']:raise ValueError('Para conservar un libro existente utiliza carpeta sincronizada / PC puente.')
  if changed:new['conectado']=False
  if destination_changed or new.get('pruebaCarpeta',{}).get('estado')=='PROBANDO':new.pop('pruebaCarpeta',None)
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');current=db.execute('SELECT revision FROM pt_cloud').fetchone()[0]
   if current!=data.get('revision'):raise Conflict('La configuración cambió. Actualiza antes de guardar.')
   if not method_changed and old.get('libroExistente') and not new['libroExistente'] and db.execute('SELECT 1 FROM pt_exports WHERE synced>0').fetchone():raise ValueError('No desactives el libro existente después de publicar: sus demás pestañas deben conservarse.')
   # No mover archivos ya publicados a otro destino por accidente.
   if destination_changed and not method_changed and db.execute('SELECT 1 FROM pt_exports WHERE synced>0').fetchone():raise ValueError('Hay archivos publicados. Conserva el mismo modo y destino para mantener el historial mensual.')
   db.execute('UPDATE pt_cloud SET revision=revision+1,payload=?,secret=CASE WHEN ? THEN ? ELSE secret END WHERE id=1',(dumps(new),changed,''))
  return self.status(actor)
 def test_folder(self,actor):
  self.admin(actor);revision,config,_=self.read()
  if config.get('modo')!='carpeta':raise ValueError('Selecciona y guarda primero el modo carpeta sincronizada.')
  if config.get('pruebaCarpeta',{}).get('estado')=='PROBANDO':return {'ok':True,'mensaje':'La comprobación de carpeta ya está en curso.'}
  def record(state,error=''):
   with self.store.connect() as db:
    db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT revision,payload FROM pt_cloud WHERE id=1').fetchone()
    if row[0]!=revision:return
    current=json.loads(row[1]);current['pruebaCarpeta']={'estado':state,'error':error,'fecha':now()};db.execute('UPDATE pt_cloud SET payload=? WHERE id=1',(dumps(current),))
  record('PROBANDO')
  def run():
   try:probe_folder(config);record('CARPETA_VERIFICADA')
   except Exception as error:record('ERROR',str(error) if isinstance(error,ValueError) else 'No se pudo abrir la carpeta compartida. Revisa permisos y conexión con la PC puente.')
  threading.Thread(target=run,daemon=True,name='PT-Carpeta-Prueba').start();return {'ok':True,'mensaje':'Prueba iniciada. Consulta el estado; esto no confirma sincronización en la nube.'}
 def browse(self,actor,query):
  self.admin(actor);_,config,_=self.read()
  if config.get('modo','microsoft')!='microsoft' or not config.get('conectado'):raise ValueError('Primero guarda el modo Microsoft y autoriza tu cuenta. El selector directo necesita esa conexión.')
  parent=query.get('carpeta',['root'])[0];url=GRAPH+'/me/drive/'+('root' if parent=='root' else 'items/'+urllib.parse.quote(parent,safe=''))+'/children?$select=id,name,folder,file&$top=200'
  next_url=query.get('pagina',[''])[0]
  if next_url:
   if not next_url.startswith(GRAPH+'/') or urllib.parse.urlsplit(next_url).hostname!='graph.microsoft.com':raise ValueError('Página de archivos no válida.')
   url=next_url
  data=request(url,token=self.access_token());items=[{'id':x['id'],'nombre':x.get('name',''),'carpeta':'folder' in x} for x in data.get('value',[]) if 'folder' in x or x.get('name','').lower().endswith('.xlsx')]
  return {'elementos':items,'siguiente':data.get('@odata.nextLink','')}
 def select_file(self,data,actor):
  self.admin(actor);branch=data.get('sucursal');self.pt.scope(actor,branch);month=data.get('mes','');id=text(data.get('archivoId',''),300)
  if branch not in BRANCHES or not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])',month) or not id:raise ValueError('Selecciona sucursal, mes y archivo Excel.')
  if not self.destination_lock.acquire(False):raise Conflict('Hay una publicación en curso. Espera antes de cambiar el archivo.')
  try:
   revision,config,_=self.read()
   if revision!=data.get('revision'):raise Conflict('La configuración cambió. Actualiza antes de seleccionar el archivo.')
   if config.get('modo','microsoft')!='microsoft' or not config.get('conectado'):raise ValueError('Autoriza primero la cuenta Microsoft en el aplicativo.')
   item=request(GRAPH+'/me/drive/items/'+urllib.parse.quote(id,safe=''),token=self.access_token())
   if 'file' not in item or not item.get('name','').lower().endswith('.xlsx'):raise ValueError('Selecciona un libro .xlsx de tu OneDrive.')
   raw=download_file(item.get('@microsoft.graph.downloadUrl',''));merge_workbook(raw,[],month)
   with self.store.connect() as db:
    db.execute('BEGIN IMMEDIATE');current=db.execute('SELECT revision,payload FROM pt_cloud WHERE id=1').fetchone()
    if current[0]!=revision:raise Conflict('La conexión cambió. Actualiza y selecciona de nuevo.')
    config=json.loads(current[1]);job=db.execute('SELECT synced,payload FROM pt_exports WHERE branch=? AND month=?',(branch,month)).fetchone()
    if job and job[0]>0 and json.loads(job[1]).get('modo')!='carpeta' and json.loads(job[1]).get('archivoId')!=id:raise ValueError('Ese mes ya fue publicado en otro archivo. Conserva el destino para no separar el histórico.')
    config['seleccionarLibros']=True;selected=config.setdefault('archivosPorSucursal',{}).setdefault(branch,{})
    if any(v.get('id')==id for b,months in config['archivosPorSucursal'].items() for m,v in months.items() if b!=branch or m!=month):raise ValueError('Cada sucursal y mes debe usar su propio archivo.')
    selected[month]={'id':id,'nombre':item['name']};db.execute('UPDATE pt_cloud SET revision=revision+1,payload=? WHERE id=1',(dumps(config),))
    if db.execute('SELECT 1 FROM pt_entries WHERE branch=? AND month=?',(branch,month)).fetchone():self.pt.queued(db,branch,month)
  finally:self.destination_lock.release()
  self.kick();return self.status(actor)
 def start_auth(self,actor):
  self.admin(actor);_,config,_=self.read()
  if config.get('modo')=='carpeta':raise ValueError('En modo carpeta no necesitas Client ID ni autorización de Microsoft dentro de GMP.')
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
  if not self.ready(config) or not config.get('habilitado'):raise ValueError('Configura el destino y activa la publicación automática primero.')
  with self.store.connect() as db:db.execute('UPDATE pt_exports SET retry_at=0,attempts=0 WHERE revision>synced')
  self.kick();return {'ok':True,'mensaje':'Publicación iniciada. Los ingresos ya están guardados en GMP.'}
 def kick(self):
  _,config,_=self.read()
  if not self.ready(config) or not config.get('habilitado') or not self.worker_lock.acquire(False):return
  def run():
   try:
    while self.store.path.exists():
     if self.process_once():continue
     _,current,_=self.read()
     if not current.get('habilitado') or not self.ready(current):break
     with self.store.connect() as db:future=db.execute('SELECT MIN(MAX(retry_at,lease)) FROM pt_exports WHERE revision>synced AND attempts<8').fetchone()[0]
     if future is None:break
     time.sleep(max(1,min(30,future-time.time()+.1)))
   finally:self.worker_lock.release()
  threading.Thread(target=run,daemon=True,name='PT-OneDrive').start()
 def process_once(self):
  with self.destination_lock:return self._process_once()
 def _process_once(self):
  _,config,_=self.read()
  if not config.get('habilitado') or not self.ready(config):return False
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');job=db.execute('SELECT branch,month,revision,synced,payload FROM pt_exports WHERE revision>synced AND lease<? AND retry_at<? AND attempts<8 ORDER BY last_attempt,month,branch LIMIT 1',(time.time(),time.time())).fetchone()
   if not job:return False
   branch,month,revision,_,payload=job;db.execute("UPDATE pt_exports SET lease=?,last_attempt=?,state='PUBLICANDO' WHERE branch=? AND month=?",(time.time()+240,time.time(),branch,month))
  try:
   actor={'role':'superadmin','email':'publicador-pt','modulos':['pt']};entries=list(reversed(self.pt.entries(actor,{'sucursal':branch,'mes':month})['ingresos']));raw=new_workbook(entries)
   def backup(original):
    with self.store.connect() as db:db.execute('INSERT OR IGNORE INTO pt_original_workbooks VALUES(?,?,?)',(branch,month,original))
   remote=publish_folder(config,branch,month,raw,json.loads(payload),entries,backup) if config.get('modo')=='carpeta' else self.publish_file(config,branch,month,raw,json.loads(payload),self.access_token(),entries,backup)
   remote['cantidades']={e['folio']:e['cantidad'] if e['estado']=='REGISTRADO' else '0' for e in entries}
   with self.store.connect() as db:db.execute("UPDATE pt_exports SET synced=?,state=CASE WHEN revision>? THEN 'PENDIENTE' ELSE ? END,lease=0,error='',attempts=0,retry_at=0,payload=? WHERE branch=? AND month=?",(revision,revision,'GUARDADO_EN_CARPETA' if config.get('modo')=='carpeta' else 'PUBLICADO',dumps({**remote,'publicado':now()}),branch,month))
  except Exception as error:
   # Nunca guardar respuestas crudas, URLs de carga ni tokens dentro del estado público.
   message=str(error) if isinstance(error,(CloudError,ValueError)) else ('No se pudo guardar en la carpeta. Revisa la PC puente, los permisos de Windows y que Excel esté cerrado.' if config.get('modo')=='carpeta' else 'No se pudo publicar. Reintenta la conexión con Microsoft.')
   with self.store.connect() as db:db.execute("UPDATE pt_exports SET state='PENDIENTE',lease=0,error=?,retry_at=?,attempts=attempts+1 WHERE branch=? AND month=?",(message[:300],time.time()+60,branch,month))
  return True
 def publish_file(self,config,branch,month,raw,old,token,entries=None,backup=None):
  selected=config.get('archivosPorSucursal',{}).get(branch,{}).get(month)
  if config.get('seleccionarLibros') and not selected:raise ValueError('Selecciona el libro de '+branch+' para el mes '+month+' desde Superadministrador.')
  if selected:
   id=selected['id'];current=request(GRAPH+'/me/drive/items/'+urllib.parse.quote(id,safe=''),token=token)
   if old.get('archivoId') and old['archivoId']!=id:raise ValueError('El libro cambió fuera de GMP. Revisa esa copia antes de publicar.')
   original=download_file(current.get('@microsoft.graph.downloadUrl',''));raw=merge_workbook(original,entries or [],month,old.get('cantidades') if old.get('archivoId')==id else None)
   if backup and not old.get('archivoId'):backup(original)
   return self.upload_file(GRAPH+'/me/drive/items/'+urllib.parse.quote(id,safe='')+'/createUploadSession',raw,current.get('name',selected['nombre']),token,{'If-Match':current['eTag']},True)
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
   if current.get('eTag')!=old.get('etag') and not old.get('cantidades'):raise ValueError('El Excel fue modificado fuera de GMP. Conserva esa copia y revisa el archivo antes de reanudar la publicación.')
   if old.get('cantidades'):raw=merge_workbook(download_file(current.get('@microsoft.graph.downloadUrl','')),entries or [],month,old['cantidades'])
   url=GRAPH+'/me/drive/items/'+urllib.parse.quote(old['archivoId'],safe='')+'/createUploadSession';headers['If-Match']=current['eTag']
  else:url=GRAPH+'/me/drive/items/'+urllib.parse.quote(parent,safe='')+':/'+urllib.parse.quote(name,safe='')+':/createUploadSession'
  return self.upload_file(url,raw,name,token,headers,bool(old.get('archivoId')))
 def upload_file(self,url,raw,name,token,headers,replace):
  session=request(url,'POST',{'item':{'@microsoft.graph.conflictBehavior':'replace' if replace else 'fail'}},token,headers);upload=session.get('uploadUrl','')
  if not upload_url(upload):raise ValueError('Microsoft devolvió un destino de carga no válido.')
  result={};size=len(raw)
  for offset in range(0,size,3276800):
   chunk=raw[offset:offset+3276800];result=request(upload,'PUT',chunk,headers={'Content-Type':'application/octet-stream','Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{size}'})
  if not result.get('id') or not result.get('eTag'):raise ValueError('Microsoft no confirmó que el Excel se guardó. Revisa la publicación antes de reintentar.')
  return {'archivoId':result['id'],'etag':result['eTag'],'archivo':name,'enlace':result.get('webUrl','')}
