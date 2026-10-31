"""Actualización cada doce horas y bajo demanda. La liga solo vive en la base privada."""
import base64,hashlib,json,pathlib,threading,time,urllib.parse,urllib.request,urllib.error
from comercial import dumps
from maestro_comercial import import_master
from permissions import MODULES

INTERVAL=12*60*60
def validate_url(url):
 p=urllib.parse.urlsplit(url);host=(p.hostname or '').lower()
 if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not (host in ('1drv.ms','onedrive.live.com','api.onedrive.com','graph.microsoft.com') or host.endswith(('.sharepoint.com','.onedrive.live.com','.livefilestore.com','.files.1drv.com'))):raise ValueError('Usa una liga HTTPS de descarga de OneDrive, SharePoint o Microsoft Graph.')
 return url

class Redirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,request,fp,code,msg,headers,newurl):
  validate_url(newurl);result=super().redirect_request(request,fp,code,msg,headers,newurl)
  if result:result.remove_header('Authorization')
  return result

class SyncService:
 def __init__(self,cm):
  self.cm=cm;self.lock=threading.Lock()
  with cm.store.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS cm_source(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL)')
   db.execute("INSERT OR IGNORE INTO cm_source VALUES(1,0,'{}','{}')")
 def config(self,actor):
  self.cm.admin(actor)
  with self.cm.store.connect() as db:r=db.execute('SELECT revision,payload,state FROM cm_source WHERE id=1').fetchone()
  return {'revision':r[0],**json.loads(r[1]),'estado':json.loads(r[2]),'intervaloHoras':12}
 def save(self,data,actor):
  self.cm.admin(actor);kind=data.get('tipo','ONEDRIVE');url='';file_path=''
  if kind=='ARCHIVO':
   target=pathlib.Path(str(data.get('ruta','')).strip())
   if not target.is_absolute() or target.suffix.lower()!='.xlsx' or not target.is_file():raise ValueError('Indica una ruta absoluta de Excel que exista en el servidor.')
   file_path=str(target.resolve())
  elif kind=='ONEDRIVE':url=validate_url(str(data.get('url','')).strip())
  else:raise ValueError('Elige OneDrive o archivo del servidor.')
  companies=data.get('empresas',[])
  if not isinstance(companies,list) or not companies:raise ValueError('Selecciona razones sociales para actualizar.')
  for company in companies:self.cm.company(company,actor,True)
  with self.cm.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT revision FROM cm_source WHERE id=1').fetchone()
   if row[0]!=data.get('revision'):
    from requisiciones import Conflict
    raise Conflict('Cambió la configuración de sincronización.')
   value={'tipo':kind,'ruta':file_path,'url':url,'empresas':companies,'habilitada':data.get('habilitada') is True,'configuradoPor':actor['email']}
   db.execute('UPDATE cm_source SET revision=revision+1,payload=? WHERE id=1',(dumps(value),));self.cm.audit(db,actor,0,'fuente_comercial_configurada',{'empresas':companies,'habilitada':value['habilitada']})
  return {'ok':True}
 def actor(self,email):
  with self.cm.store.connect() as db:
   row=db.execute('SELECT role,active FROM users WHERE email=?',(email,)).fetchone()
   if not row or not row[1] or row[0] not in ('superadmin','auxti'):raise PermissionError('La cuenta que configuró la fuente ya no puede administrarla.')
   modules=list(MODULES) if row[0]=='superadmin' else json.loads(db.execute('SELECT modules FROM role_modules WHERE role=?',(row[0],)).fetchone()[0])
  return {'email':email,'role':row[0],'modulos':modules}
 def trigger(self,actor,automatic=False):
  self.cm.admin(actor)
  if not self.lock.acquire(False):return {'ok':True,'enProceso':True}
  with self.cm.store.connect() as db:rev,raw,state=db.execute('SELECT revision,payload,state FROM cm_source WHERE id=1').fetchone()
  config=json.loads(raw)
  if not config.get('url') and not config.get('ruta'):self.lock.release();raise ValueError('Configura primero OneDrive o el archivo Excel del servidor.')
  stamp={**{k:v for k,v in json.loads(state).items() if k=='ultimoExito'},'enProceso':True,'ultimoIntento':time.time(),'mensaje':'Descargando maestro…','automatico':automatic}
  with self.cm.store.connect() as db:db.execute('UPDATE cm_source SET state=? WHERE id=1',(dumps(stamp),))
  threading.Thread(target=self._run,args=(rev,config,stamp),daemon=True).start();return {'ok':True,'enProceso':True}
 def _run(self,revision,config,state):
  try:
   if config.get('tipo')=='ARCHIVO':
    target=pathlib.Path(config.get('ruta',''))
    if target.suffix.lower()!='.xlsx' or not target.is_absolute():raise ValueError('Ruta de Excel inválida.')
    with target.open('rb') as source:raw=source.read(15*1024*1024+1)
   else:
    url=validate_url(config['url']);request=urllib.request.Request(url,headers={'User-Agent':'RFQ-SKU-GMP/2.0','Accept':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
    with urllib.request.build_opener(Redirect()).open(request,timeout=45) as response:raw=response.read(15*1024*1024+1)
   if len(raw)>15*1024*1024 or not raw.startswith(b'PK'):raise ValueError('La liga no entregó un archivo Excel. Proporciona una descarga autorizada; un iframe o página de acceso no permite sincronizar.')
   actor=self.actor(config['configuradoPor']);result=import_master(self.cm,{'contenido':base64.b64encode(raw).decode(),'empresas':config['empresas'],'archivo':'OneDrive/SUGERIDO.xlsx','_source_revision':revision},actor)
   state.update({'ok':True,'mensaje':f"Maestro actualizado: {result['productos']} productos.",'ultimoExito':time.time()})
  except urllib.error.HTTPError as exc:
   state.update({'ok':False,'mensaje':'Microsoft no permitió descargar el archivo (HTTP '+str(exc.code)+'). Carga el Excel manualmente o configura su ruta en el servidor. El maestro actual se conserva.'})
  except (ValueError,FileNotFoundError,PermissionError) as exc:
   state.update({'ok':False,'mensaje':str(exc)[:400]})
  except Exception:
   # No incluir URLs con tokens ni respuestas del proveedor en logs o mensajes públicos.
   state.update({'ok':False,'mensaje':'No se pudo actualizar. Revisa que la liga permita descargar el Excel sin una sesión de navegador. El último maestro válido se conserva.'})
  finally:
   state.update({'enProceso':False,'finalizado':time.time()})
   try:
    with self.cm.store.connect() as db:db.execute('UPDATE cm_source SET state=? WHERE id=1',(dumps(state),))
   finally:self.lock.release()
 def apply_initial(self):
  """Carga solicitada por administración y guardada en la configuración privada."""
  with self.cm.store.connect() as db:revision,raw=db.execute('SELECT revision,payload FROM cm_source WHERE id=1').fetchone()
  config=json.loads(raw);job=config.get('maestroInicial')
  if not isinstance(job,dict) or job.get('aplicado'):return
  try:
   actor=self.actor(config['configuradoPor']);content=base64.b64decode(job['contenido'],validate=True)
   if len(content)>15*1024*1024 or hashlib.sha256(content).hexdigest()!=job['sha256']:raise ValueError('El maestro inicial no pasó su comprobación de integridad.')
   target=(self.cm.store.directory/'maestro-comercial.xlsx').resolve();target.write_bytes(content)
   result=import_master(self.cm,{'contenido':job['contenido'],'archivo':job.get('archivo','SUGERIDO.xlsx'),'empresas':job['empresas'],'_source_revision':revision},actor)
   job={k:v for k,v in job.items() if k!='contenido'};job.update({'aplicado':True,'resultado':result});config.update({'maestroInicial':job,'tipo':'ARCHIVO','ruta':str(target),'habilitada':False})
   with self.cm.store.connect() as db:
    db.execute('BEGIN IMMEDIATE')
    if db.execute('SELECT revision FROM cm_source WHERE id=1').fetchone()[0]!=revision:raise ValueError('La configuración cambió durante la carga inicial.')
    db.execute('UPDATE cm_source SET revision=revision+1,payload=?,state=? WHERE id=1',(dumps(config),dumps({'ok':True,'enProceso':False,'ultimoExito':time.time(),'mensaje':'Maestro SUGERIDO cargado: '+str(result['productos'])+' productos; '+str(result['totalPendientes'])+' pendientes por completar.'})))
  except Exception:
   with self.cm.store.connect() as db:db.execute('UPDATE cm_source SET state=? WHERE id=1',(dumps({'ok':False,'enProceso':False,'mensaje':'No se pudo completar el maestro inicial. El archivo permanece guardado para reintentar o cargarlo manualmente.'}),))
 def tick(self):
  with self.cm.store.connect() as db:raw,state=db.execute('SELECT payload,state FROM cm_source WHERE id=1').fetchone()
  config=json.loads(raw);state=json.loads(state)
  if config.get('habilitada') and time.time()-state.get('ultimoIntento',0)>=INTERVAL:self.trigger(self.actor(config['configuradoPor']),True)
 def start(self):
  def loop():
   while True:
    try:self.tick()
    except Exception:pass
    time.sleep(60)
  threading.Thread(target=loop,daemon=True).start()
