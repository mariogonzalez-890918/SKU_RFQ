"""Servidor SKU JAD: Python estándar, SQLite y control de concurrencia."""
import argparse,base64,contextlib,datetime,hashlib,hmac,http.server,http.cookies,json,pathlib,re,secrets,sqlite3,time,unicodedata,zipfile,io,sys
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from ventas import SalesStore,export_master
from requisiciones import RequisitionStore,Conflict as RequisitionConflict,print_document,document_csv,csv_bytes,BRANCHES,SCOPED_ROLES
from urllib.parse import urlsplit,parse_qs
from permissions import MODULES,DEFAULTS,require_module,enabled_modules
from reportes import ReportStore,report_csv
from reporte_export import report_xlsx,report_pdf,select_detail
from autorizaciones import WorkflowStore
from compras import PurchaseImporter,export_products
from respaldos import BackupStore
from app_info import TITLE,VERSION,SUPPORT_LINE
from imagenes import ImageStore
from aprobaciones_admin import AdminApprovals
from comercial_routes import CommercialAPI
from pedidos_compra_routes import PurchaseAPI
from inventarios_routes import InventoryAPI
APP_DIR=pathlib.Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else ROOT
ALPHABET='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
MAX_BODY=25*1024*1024
ADMIN_EMAIL='sistemas@grupomipan.com'
ROLES={'superadmin':'SUPERADMINISTRADOR','auxti':'AUXTI','visualizador':'VISUALIZADOR','ventas':'VENTAS','compras':'COMPRAS','alta':'ALTA DE PRODUCTOS','gerente':'GERENTE','almacenista':'ALMACENISTA','requisicion':'REQUISICIÓN','ventaspasteleria':'VENTASPASTELERIA','ventasins':'VentasIns','expendios':'Expendios'}
def read_scope(actor,scope):
 require_module(actor,scope)
def write_scope(actor,scope):
 read_scope(actor,scope)
 if actor['role'] not in ('superadmin','auxti','alta',scope):raise PermissionError('Tu perfil solo permite consultar este módulo.')
def password_hash(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),310000).hex()
def new_password(password):
 if not isinstance(password,str) or not 4<=len(password)<=200:raise ValueError('La contraseña debe tener entre 4 y 200 caracteres.')
 salt=secrets.token_hex(16);return salt,password_hash(password,salt)
def norm(value):
 return ' '.join(''.join(c for c in unicodedata.normalize('NFD',str(value or '')) if not unicodedata.combining(c)).upper().split())
def identity(r):return tuple(norm(r.get(k,'')) for k in ('tipo','categoria','subcategoria','nombre','proveedor','claveProveedor','unidadCompra','unidadEntrega'))
def sku(r):
 body=r['tipo']+r['categoria']+r['subcategoria']+str(r['id']).zfill(7)
 total=0;factor=2
 for c in reversed(body):
  n=ALPHABET.index(c)*factor;total+=n//36+n%36;factor=1 if factor==2 else 2
 return body+ALPHABET[(36-total%36)%36]
def validate(data,catalogs):
 s=data.get('state');master=data.get('master')
 if not isinstance(s,dict) or s.get('version')!=3 or not isinstance(s.get('registros'),list) or not isinstance(s.get('reservados'),list):raise ValueError('Respaldo inválido.')
 if type(s.get('maxId')) is not int or not 0<=s['maxId']<=9999999:raise ValueError('Consecutivo inválido.')
 if not all(isinstance(v,str) and v for v in s['reservados']):raise ValueError('Reservas inválidas.')
 ids=set();skus=set();rows=set();reserved=set(s['reservados'])
 for r in s['registros']:
  if not isinstance(r,dict) or type(r.get('id')) is not int or not 1<=r['id']<=s['maxId'] or r['id'] in ids:raise ValueError('ID inválido o repetido.')
  ids.add(r['id'])
  if not isinstance(r.get('nombre'),str) or not r['nombre'].strip() or len(r['nombre'])>300 or type(r.get('eliminado')) is not bool or not isinstance(r.get('estado'),str):raise ValueError('Datos del artículo inválidos.')
  if not isinstance(r.get('proveedor',''),str) or len(r.get('proveedor',''))>500:raise ValueError('Proveedor inválido.')
  for k,cat in [('tipo','TIP'),('categoria','CAT'),('subcategoria','SUB')]:
   if r.get(k) not in catalogs[cat]:raise ValueError('Clasificación inválida.')
  expected=sku(r)
  if r.get('sku')!=expected or expected in skus or not r['eliminado'] and expected in reserved:raise ValueError('SKU repetido, reservado o verificador incorrecto.')
  skus.add(expected)
  row=r.get('fila')
  if row is not None:
   if type(row) is not int or row<2 or row in rows:raise ValueError('Fila Excel inválida o repetida.')
   rows.add(row)
 if not isinstance(master,str):raise ValueError('Falta el maestro Excel.')
 try:
  raw=base64.b64decode(master,validate=True)
  if len(raw)>15*1024*1024:raise ValueError('El maestro supera 15 MB.')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   if 'xl/workbook.xml' not in z.namelist():raise ValueError('Plantilla Excel inválida.')
 except (ValueError,zipfile.BadZipFile) as e:raise ValueError('Plantilla Excel inválida: '+str(e))
 return data
def protect(old,new):
 a=old['state'];b=new['state'];previous={r['id']:r for r in a['registros']};current={r['id']:r for r in b['registros']}
 if b['maxId']<a['maxId'] or not set(previous)<=set(current):raise ValueError('No se pueden borrar identificadores del historial ni reducir el consecutivo.')
 reserved=set(a['reservados'])|set(b['reservados'])
 for id,r in previous.items():
  updated=current[id]
  if r['eliminado'] and any(updated.get(k)!=v for k,v in r.items() if k!='fila'):raise ValueError('Un artículo dado de baja no puede reactivarse ni cambiar.')
  if r['sku']!=updated['sku'] or updated['eliminado']:reserved.add(r['sku'])
 active_identities={}
 for r in b['registros']:
  if not r['eliminado']:active_identities.setdefault(identity(r),[]).append(r['id'])
 for r in b['registros']:
  if r['id'] not in previous and r['id']<=a['maxId']:raise ValueError('El identificador ya fue utilizado.')
  oldrow=previous.get(r['id'])
  if not r['eliminado'] and (oldrow is None or identity(oldrow)!=identity(r)):
   if len(active_identities[identity(r)])>1:raise ValueError('El artículo ya existe con la misma clasificación y proveedor.')
 b['reservados']=sorted(reserved)
class Store:
 def __init__(self,directory,initial_admin=None):
  self.directory=pathlib.Path(directory);self.directory.mkdir(parents=True,exist_ok=True);self.path=self.directory/'sku.sqlite3';self.catalogs=json.loads((ROOT/'catalogos.json').read_text(encoding='utf8'))
  with self.connect() as db:
   db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE IF NOT EXISTS catalog (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL)');db.execute('CREATE TABLE IF NOT EXISTS history (revision INTEGER PRIMARY KEY,created TEXT NOT NULL,payload TEXT NOT NULL)')
   if not db.execute('SELECT 1 FROM catalog').fetchone():
    initial=json.loads((ROOT/'initial.json').read_text(encoding='utf8'));validate(initial,self.catalogs);db.execute('INSERT INTO catalog VALUES(1,1,?)',(json.dumps(initial,ensure_ascii=False),))
   db.execute('CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL,active INTEGER NOT NULL)')
   db.execute("UPDATE users SET role='alta' WHERE role='captura'")
   db.execute('CREATE TABLE IF NOT EXISTS user_requisition_access(email TEXT PRIMARY KEY,sucursales TEXT NOT NULL,almacenes TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS role_modules(role TEXT PRIMARY KEY,modules TEXT NOT NULL,revision INTEGER NOT NULL)')
   for role,modules in DEFAULTS.items():db.execute('INSERT OR IGNORE INTO role_modules VALUES(?,?,1)',(role,json.dumps(modules)))
   db.execute('CREATE TABLE IF NOT EXISTS permission_features(key TEXT PRIMARY KEY)')
   if not db.execute("SELECT 1 FROM permission_features WHERE key='capabilities-v1'").fetchone():
    for role in ('ventas','compras','alta'):
     row=db.execute('SELECT modules FROM role_modules WHERE role=?',(role,)).fetchone();modules=json.loads(row[0]);modules=list(dict.fromkeys(modules+['cargar_maestro']));db.execute('UPDATE role_modules SET modules=?,revision=revision+1 WHERE role=?',(json.dumps(modules),role))
    db.execute("INSERT INTO permission_features VALUES('capabilities-v1')")
   if not db.execute("SELECT 1 FROM permission_features WHERE key='manager-requisitions-v2'").fetchone():
    row=db.execute("SELECT modules FROM role_modules WHERE role='gerente'").fetchone();modules=list(dict.fromkeys(json.loads(row[0])+['requisiciones','cargar_maestro']));db.execute("UPDATE role_modules SET modules=?,revision=revision+1 WHERE role='gerente'",(json.dumps(modules),));db.execute("INSERT INTO permission_features VALUES('manager-requisitions-v2')")
   db.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY,email TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS login_attempts (key TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL)')
   if not db.execute('SELECT 1 FROM users WHERE email=?',(ADMIN_EMAIL,)).fetchone():
    admin=initial_admin
    if admin is None:
     seed_admin=ROOT/'initial-admin.json'
     if seed_admin.exists():admin=json.loads(seed_admin.read_text(encoding='utf8'))
     else:
      import getpass
      print('PRIMER INICIO: define la contraseña de '+ADMIN_EMAIL+'. No hay contraseña predeterminada.',flush=True)
      while admin is None:
       password=getpass.getpass('Contraseña nueva (mínimo 4 caracteres): ')
       if password!=getpass.getpass('Confirma la contraseña: '):print('Las contraseñas no coinciden.',flush=True);continue
       try:salt,digest=new_password(password);admin={'salt':salt,'password_hash':digest}
       except ValueError as error:print(str(error),flush=True)
    db.execute('INSERT INTO users VALUES(?,?,?,?,?,1)',(ADMIN_EMAIL,'Sistemas GMP','superadmin',admin['salt'],admin['password_hash']))
 @contextlib.contextmanager
 def connect(self):
  db=sqlite3.connect(self.path,timeout=15)
  try:
   with db:yield db
  finally:db.close()
 def get(self):
  with self.connect() as db:rev,payload=db.execute('SELECT revision,payload FROM catalog WHERE id=1').fetchone()
  return {**json.loads(payload),'revision':rev}
 def put(self,data,actor):
  write_scope(actor,'compras')
  if type(data.get('revision')) is not int:raise ValueError('Falta la revisión del catálogo.')
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');rev,payload=db.execute('SELECT revision,payload FROM catalog WHERE id=1').fetchone()
   if data['revision']!=rev:return None
   old=json.loads(payload);updated={**old,'state':data.get('state'),'master':data.get('master')};validate(updated,self.catalogs)
   if updated['master']!=old['master']:raise ValueError('Las cargas agregan artículos sin reemplazar el maestro existente.')
   if actor['role']!='superadmin':
    previous={r['id']:r for r in old['state']['registros']}
    if any(r['eliminado'] and (r['id'] not in previous or not previous[r['id']]['eliminado']) for r in updated['state']['registros']):raise PermissionError('Solo el super administrador puede borrar artículos.')
   protect(old,updated);validate(updated,self.catalogs)
   db.execute('INSERT INTO history VALUES(?,?,?)',(rev,datetime.datetime.now(datetime.timezone.utc).isoformat(),payload));db.execute('UPDATE catalog SET revision=?,payload=? WHERE id=1',(rev+1,json.dumps(updated,ensure_ascii=False)));db.execute('DELETE FROM history WHERE revision < ?',(rev-99,))
  return {**updated,'revision':rev+1}
 def login(self,email,password,ip):
  email=str(email).strip().lower();key=ip+'|'+email;now=time.time()
  with self.connect() as db:
   attempt=db.execute('SELECT count,until FROM login_attempts WHERE key=?',(key,)).fetchone()
   if attempt and attempt[0]>=8 and attempt[1]>now:raise PermissionError('Demasiados intentos. Espera 15 minutos.')
   row=db.execute('SELECT email,name,role,salt,password_hash,active FROM users WHERE email=?',(email,)).fetchone()
   valid=isinstance(password,str) and len(password)<=200 and hmac.compare_digest(password_hash(password,row[3] if row else '00'*16),row[4] if row else '00'*32)
   if not row or not row[5] or not valid:
    count=attempt[0]+1 if attempt and attempt[1]>now else 1
    db.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(key,count,now+900));result=None
   else:
    db.execute('DELETE FROM login_attempts WHERE key=?',(key,));db.execute('DELETE FROM sessions WHERE expires<?',(now,));token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),email,csrf,now+43200));result=token
  return result
 def session(self,token):
  with self.connect() as db:
   row=db.execute('SELECT u.email,u.name,u.role,s.csrf,a.sucursales,a.almacenes,p.modules FROM sessions s JOIN users u ON s.email=u.email LEFT JOIN user_requisition_access a ON a.email=u.email LEFT JOIN role_modules p ON p.role=u.role WHERE s.token_hash=? AND s.expires>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
  if not row or row[2] not in ROLES:return None
  return {**dict(zip(('email','name','role','csrf'),row[:4])),'sucursales':json.loads(row[4] or '[]'),'almacenes':json.loads(row[5] or '[]'),'modulos':list(MODULES) if row[2]=='superadmin' else enabled_modules({'role':row[2],'modulos':json.loads(row[6] or '[]')})}
 def profiles(self):
  with self.connect() as db:rows=db.execute('SELECT role,modules,revision FROM role_modules ORDER BY rowid').fetchall()
  return {'perfiles':[{'perfil':role,'nombre':ROLES[role],'modulos':list(MODULES) if role=='superadmin' else json.loads(modules),'revision':revision} for role,modules,revision in rows],'modulos':MODULES}
 def save_profile(self,data,actor):
  if actor['role']!='superadmin':raise PermissionError('Solo el superadministrador puede configurar accesos por perfil.')
  role=data.get('perfil');modules=data.get('modulos');revision=data.get('revision')
  if role not in ROLES or role=='superadmin':raise ValueError('El superadministrador conserva acceso completo.')
  if not isinstance(modules,list) or any(not isinstance(m,str) or m not in MODULES for m in modules) or len(set(modules))!=len(modules) or type(revision) is not int:raise ValueError('Configuración de módulos inválida.')
  if role=='requisicion' and any(m!='requisiciones' for m in modules):raise ValueError('El perfil Requisición solo permite crear y consultar sus propias solicitudes.')
  with self.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT revision FROM role_modules WHERE role=?',(role,)).fetchone()
   if old[0]!=revision:raise RequisitionConflict('Los accesos cambiaron. Actualiza los perfiles.')
   db.execute('UPDATE role_modules SET modules=?,revision=revision+1 WHERE role=?',(json.dumps(modules),role))
  return self.profiles()
 def logout(self,token):
  with self.connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
 def users(self):
  with self.connect() as db:rows=db.execute('SELECT u.email,u.name,u.role,u.active,a.sucursales,a.almacenes FROM users u LEFT JOIN user_requisition_access a ON u.email=a.email ORDER BY u.email').fetchall()
  return [{**dict(zip(('email','name','role','active'),r[:4])),'sucursales':json.loads(r[4] or '[]'),'almacenes':json.loads(r[5] or '[]')} for r in rows]
 def user_fingerprint(self,db,email):
  row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone();access=db.execute('SELECT * FROM user_requisition_access WHERE email=?',(email,)).fetchone()
  return hashlib.sha256(json.dumps([row,access],ensure_ascii=False).encode()).hexdigest()
 def manage_user(self,data,actor):
  if actor['role'] not in ('superadmin','auxti'):raise PermissionError('Solo administración puede administrar usuarios.')
  email=str(data.get('email','')).strip().lower();name=str(data.get('name','')).strip();role=data.get('role');active=data.get('active',True);password=data.get('password','')
  if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>160 or not 1<=len(name)<=100 or role not in ROLES or type(active) is not bool:raise ValueError('Correo, nombre o perfil inválido.')
  if actor['role']=='auxti' and role=='superadmin':raise PermissionError('AUXTI no puede asignar Superadministrador.')
  if email==ADMIN_EMAIL and (role!='superadmin' or not active):raise ValueError('La cuenta de sistemas debe permanecer activa como super administrador.')
  if email==actor['email'] and (not active or role!=actor['role']):raise ValueError('No puedes quitarte tu acceso de super administrador.')
  with self.connect() as db:
   existing=db.execute('SELECT role FROM users WHERE email=?',(email,)).fetchone()
   if actor['role']=='auxti':
    if role=='superadmin' or email==ADMIN_EMAIL or existing and existing[0]=='superadmin':raise PermissionError('AUXTI no puede crear ni modificar cuentas de Superadministrador.')
    if not active:raise PermissionError('Solicita aprobación de sistemas para desactivar usuarios.')
   if data.get('_huellaUsuario') and self.user_fingerprint(db,email)!=data['_huellaUsuario']:raise RequisitionConflict('El usuario cambió; solicita una nueva autorización.')
   old=db.execute('SELECT salt,password_hash FROM users WHERE email=?',(email,)).fetchone()
   previous=db.execute('SELECT sucursales,almacenes FROM user_requisition_access WHERE email=?',(email,)).fetchone()
   assigned={}
   for field,index in [('sucursales',0),('almacenes',1)]:
    values=data.get(field,list(BRANCHES) if role=='gerente' and field=='sucursales' else json.loads(previous[index]) if previous else [])
    if not isinstance(values,list) or any(not isinstance(v,str) or v not in BRANCHES for v in values) or len(set(values))!=len(values):raise ValueError('Asignación de sucursales o almacenes inválida.')
    assigned[field]=values
   if role=='gerente' and set(assigned['sucursales'])!=set(BRANCHES):raise ValueError('El gerente consulta las cuatro sucursales.')
   if role=='almacenista' and not assigned['almacenes']:raise ValueError('Selecciona al menos un almacén para el almacenista.')
   if role=='requisicion' and not assigned['sucursales']:raise ValueError('Selecciona al menos una sucursal para el perfil Requisición.')
   if role not in ('gerente','requisicion'):assigned['sucursales']=[]
   if role!='almacenista':assigned['almacenes']=[]
   if not old and not password:raise ValueError('Define una contraseña para el usuario nuevo.')
   salt,digest=new_password(password) if password else old
   db.execute('INSERT INTO users VALUES(?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET name=excluded.name,role=excluded.role,salt=excluded.salt,password_hash=excluded.password_hash,active=excluded.active',(email,name,role,salt,digest,int(active)))
   db.execute('INSERT INTO user_requisition_access VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET sucursales=excluded.sucursales,almacenes=excluded.almacenes',(email,json.dumps(assigned['sucursales']),json.dumps(assigned['almacenes'])))
   if password or not active:db.execute('DELETE FROM sessions WHERE email=?',(email,))
def create_handler(store):
 commercial=CommercialAPI(store)
 sales=SalesStore(store)
 commercial.sync.apply_initial()
 requisitions=RequisitionStore(store)
 reports=ReportStore(store,requisitions)
 procurement=PurchaseAPI(store,commercial.cm,requisitions,reports)
 inventory=InventoryAPI(store,procurement.po)
 procurement.po.inventory=inventory.inv
 workflow=WorkflowStore(store,requisitions,reports)
 workflow.inventory=inventory.inv
 purchases=PurchaseImporter(store,sku,validate,protect)
 images=ImageStore(store,requisitions)
 backups=BackupStore(store,validate,reports)
 admin_approvals=AdminApprovals(store,sales,images,backups)
 class Handler(http.server.BaseHTTPRequestHandler):
  def auth(self):
   cookie=http.cookies.SimpleCookie()
   try:cookie.load(self.headers.get('Cookie',''))
   except http.cookies.CookieError:return None
   self.token=cookie['gmp_session'].value if 'gmp_session' in cookie else ''
   return store.session(self.token) if self.token else None
  def reply(self,status,body,ctype='application/json; charset=utf-8',cookie=None):
   if isinstance(body,dict):body=json.dumps(body,ensure_ascii=False).encode()
   self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
   if cookie:self.send_header('Set-Cookie',cookie)
   self.end_headers();self.wfile.write(body)
  def do_GET(self):
   path=self.path.split('?')[0]
   if path=='/logo.png':return self.reply(200,(ROOT/'public/logo.png').read_bytes(),'image/png')
   actor=self.auth()
   if path in ('/','/index.html'):
    name='index.html' if actor else 'login.html';return self.reply(200,(ROOT/'public'/name).read_bytes(),'text/html; charset=utf-8')
   if not actor:return self.reply(401,{'error':'Inicia sesión para continuar.'})
   if path=='/api/me':return self.reply(200,{'user':actor,'roles':ROLES,'app':{'titulo':TITLE,'version':VERSION,'soporte':SUPPORT_LINE}})
   if path in ('/comercial','/commercial.js','/commercial.css'):
    if not any(m in enabled_modules(actor) for m in ('ventasins','expendios')):return self.reply(403,{'error':'Módulo comercial no habilitado.'})
    file,kind={'/comercial':('commercial.html','text/html'),'/commercial.js':('commercial.js','text/javascript'),'/commercial.css':('commercial.css','text/css')}[path]
    return self.reply(200,(ROOT/'public'/file).read_bytes(),kind+'; charset=utf-8')
   if path in ('/inventarios','/inventory.js'):
    try:
     require_module(actor,'inventarios');name,kind=('inventory.html','text/html') if path=='/inventarios' else ('inventory.js','text/javascript');return self.reply(200,(ROOT/'public'/name).read_bytes(),kind+'; charset=utf-8')
    except PermissionError as e:return self.reply(403,{'error':str(e)})
   if path.startswith('/api/inventarios/'):
    try:
     result=inventory.get(path,parse_qs(urlsplit(self.path).query),actor);return self.reply(200,*result) if isinstance(result,tuple) else self.reply(200,result)
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except RequisitionConflict as e:return self.reply(409,{'error':str(e)})
    except (ValueError,KeyError,TypeError,ArithmeticError) as e:return self.reply(400,{'error':str(e)})
   if path in ('/compras','/purchase.js','/purchase.css'):
    try:
     require_module(actor,'pedidoscompra');file,kind={'/compras':('purchase.html','text/html'),'/purchase.js':('purchase.js','text/javascript'),'/purchase.css':('purchase.css','text/css')}[path];return self.reply(200,(ROOT/'public'/file).read_bytes(),kind+'; charset=utf-8')
    except PermissionError as e:return self.reply(403,{'error':str(e)})
   linked_purchase=re.fullmatch('/api/requisiciones/([a-f0-9]{32})/pedidos-compra',path)
   if linked_purchase:
    try:return self.reply(200,procurement.po.links_for_requisition(linked_purchase[1],actor))
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except ValueError as e:return self.reply(400,{'error':str(e)})
   if path.startswith('/api/pedidoscompra/'):
    try:
     result=procurement.get(path,parse_qs(urlsplit(self.path).query),actor);return self.reply(200,*result) if isinstance(result,tuple) else self.reply(200,result)
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except RequisitionConflict as e:return self.reply(409,{'error':str(e)})
    except (ValueError,KeyError,TypeError,ArithmeticError) as e:return self.reply(400,{'error':str(e)})
   if path.startswith('/api/comercial/'):
    try:
     result=commercial.get(path,parse_qs(urlsplit(self.path).query),actor)
     return self.reply(200,*result) if isinstance(result,tuple) else self.reply(200,result)
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except RequisitionConflict as e:return self.reply(409,{'error':str(e)})
    except (ValueError,KeyError,TypeError) as e:return self.reply(400,{'error':str(e)})
   if path.startswith('/api/respaldos'):
    try:
     previous=re.fullmatch('/api/respaldos/previo/([a-f0-9]{32})',path)
     if previous:return self.reply(200,backups.previous(previous[1],actor),'application/json; charset=utf-8')
     if path=='/api/respaldos':return self.reply(200,backups.create(parse_qs(urlsplit(self.path).query).get('modulo',[''])[0],actor))
     return self.reply(404,{'error':'No encontrado.'})
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except ValueError as e:return self.reply(400,{'error':str(e)})
   if path=='/api/compras/excel':
    try:
     read_scope(actor,'compras');return self.reply(200,export_products(store.get(),store.catalogs),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except ValueError as e:return self.reply(400,{'error':str(e)})
   if path=='/api/perfiles':
    if actor['role'] not in ('superadmin','auxti'):return self.reply(403,{'error':'Solo administración.'})
    return self.reply(200,store.profiles())
   if path.startswith('/api/requisiciones'):
    try:
     require_module(actor,'requisiciones')
     query=parse_qs(urlsplit(self.path).query)
     if actor['role']=='requisicion' and path not in ('/api/requisiciones','/api/requisiciones/meta','/api/requisiciones/materiales','/api/requisiciones/imagenes','/api/requisiciones/cambios') and not re.fullmatch('/api/requisiciones/(?:imagenes/[1-9][0-9]*|[a-f0-9]{32}(?:/(?:imprimir|historial))?)',path):raise PermissionError('Este perfil solo puede crear y consultar sus propias requisiciones.')
     if path=='/api/requisiciones/imagenes':
      photos=images.list(actor)
      if actor['role']=='requisicion':photos={'puedeEditar':False,'imagenes':[{k:r[k] for k in ('materialId','imagenId')} for r in photos['imagenes']]}
      return self.reply(200,photos)
     image_match=re.fullmatch('/api/requisiciones/imagenes/([1-9][0-9]*)',path)
     if image_match:
      raw=images.get(int(image_match[1]),thumbnail=query.get('miniatura')==['1']);return self.reply(200,raw,'image/png' if query.get('miniatura')==['1'] else images.content_type(int(image_match[1]))) if raw is not None else self.reply(404,{'error':'Este material no tiene imagen.'})
     if path=='/api/requisiciones/reportes':return self.reply(200,{'reportes':reports.definitions(),'puedeEditar':actor['role'] in ('superadmin','auxti','gerente')})
     if path=='/api/requisiciones/costos':return self.reply(200,{'costos':reports.costs()})
     if path=='/api/requisiciones/cambios':return self.reply(200,workflow.list(actor))
     history_match=re.fullmatch('/api/requisiciones/([a-f0-9]{32})/historial',path)
     if history_match:return self.reply(200,workflow.history(history_match[1],actor))
     report_match=re.fullmatch('/api/requisiciones/reportes/([a-zA-Z0-9_-]{1,64})/(ejecutar|csv|xlsx|pdf)',path)
     if report_match:
      result=reports.run(actor,id=report_match[1])
      if report_match[2]=='xlsx':return self.reply(200,report_xlsx(result),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      if report_match[2]=='pdf':return self.reply(200,report_pdf(result),'application/pdf')
      return self.reply(200,report_csv(result),'text/csv; charset=utf-8') if report_match[2]=='csv' else self.reply(200,result)
     if path=='/api/requisiciones/areas':return self.reply(200,requisitions.areas.list(actor))
     if path=='/api/requisiciones/meta':return self.reply(200,requisitions.metadata(actor))
     if path=='/api/requisiciones/materiales':
      materials=requisitions.materials()
      if actor['role']=='requisicion':materials=[{k:r.get(k,'') for k in ('id','sku','nombre','unidad','proveedor','estado','skuRepetido')} for r in materials if r['estado']=='ACTIVO']
      return self.reply(200,{'materiales':materials})
     if path=='/api/requisiciones/catalogo.csv':
      rows=[['ID MATERIAL','SKU','DESCRIPCION','UNIDAD','PROVEEDOR','CATEGORIA','ESTADO'],*[ [r['id'],r['sku'],r['nombre'],r['unidad'],r['proveedor'],r['categoria'],r['estado']] for r in requisitions.materials()]]
      return self.reply(200,csv_bytes(rows),'text/csv; charset=utf-8')
     if path=='/api/requisiciones/maestro/archivo':
      name,raw=requisitions.master_file();return self.reply(200,raw,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' if name.lower().endswith('.xlsx') else 'text/csv; charset=utf-8')
     if path=='/api/requisiciones':return self.reply(200,requisitions.list(query.get('sucursal',[''])[0],int(query.get('pagina',['1'])[0]),actor))
     match=re.fullmatch('/api/requisiciones/([a-f0-9]{32})(?:/(imprimir|csv))?',path)
     if match:
      document=requisitions.get(match[1],actor)
      if document is None:return self.reply(404,{'error':'Solicitud no encontrada.'})
      if match[2]=='imprimir':return self.reply(200,print_document(document,query.get('formato',['actual'])[0]),'text/html; charset=utf-8')
      if match[2]=='csv':return self.reply(200,document_csv(document),'text/csv; charset=utf-8')
      return self.reply(200,document)
     return self.reply(404,{'error':'No encontrado.'})
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except ValueError as e:return self.reply(400,{'error':str(e)})
   if path.startswith('/api/autorizaciones-admin'):
    try:
     if path=='/api/autorizaciones-admin':return self.reply(200,admin_approvals.list(actor))
     match=re.fullmatch('/api/autorizaciones-admin/([a-f0-9]{32})',path)
     if match:return self.reply(200,admin_approvals.detail(match[1],actor))
     return self.reply(404,{'error':'No encontrado.'})
    except PermissionError as e:return self.reply(403,{'error':str(e)})
    except ValueError as e:return self.reply(400,{'error':str(e)})
   if path=='/api/users':
    if actor['role'] not in ('superadmin','auxti'):return self.reply(403,{'error':'Solo administración puede consultar usuarios.'})
    return self.reply(200,{'users':store.users(),'roles':ROLES,'sucursalesDisponibles':list(BRANCHES),'almacenesDisponibles':list(BRANCHES)})
   if path in ('/api/catalogo','/api/ventas','/api/ventas/excel','/api/ventas/respaldo','/api/compras/respaldo'):
    try:
     read_scope(actor,'compras' if path in ('/api/catalogo','/api/compras/respaldo') else 'ventas')
     if path.endswith('/respaldo') and actor['role'] not in ('superadmin','auxti'):raise PermissionError('Los respaldos son exclusivos del superadministrador.')
     if path=='/api/ventas/excel':return self.reply(200,export_master(sales.get()),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
     return self.reply(200,store.get() if path in ('/api/catalogo','/api/compras/respaldo') else sales.get())
    except PermissionError as e:return self.reply(403,{'error':str(e)})
   if path=='/api/salud':return self.reply(200,{'ok':True} if actor['role'] in SCOPED_ROLES else {'ok':True,'revision':store.get()['revision']})
   if path=='/app.js':return self.reply(200,(ROOT/'public/app.js').read_bytes(),'text/javascript; charset=utf-8')
   self.reply(404,{'error':'No encontrado.'})
  def read_body(self):
   length=int(self.headers.get('Content-Length','0'))
   limit=128*1024*1024 if self.path.startswith(('/api/respaldos/restaurar','/api/autorizaciones-admin')) else MAX_BODY
   if length<=0 or length>limit and self.path!='/api/requisiciones/imagenes' and not self.path.startswith(('/api/respaldos/restaurar','/api/autorizaciones-admin')):raise ValueError('Archivo demasiado grande o solicitud vacía.')
   data=json.loads(self.rfile.read(length))
   if not isinstance(data,dict):raise ValueError('Solicitud inválida.')
   return data
  def do_POST(self):self.mutate()
  def do_PUT(self):self.mutate()
  def do_DELETE(self):self.mutate()
  def mutate(self):
   origin=self.headers.get('Origin')
   if origin and origin not in ('http://'+self.headers.get('Host',''),'https://'+self.headers.get('Host','')):return self.reply(403,{'error':'Origen no permitido.'})
   try:
    if self.path=='/api/login' and self.command=='POST':
     data=self.read_body();token=store.login(data.get('email',''),data.get('password',''),self.client_address[0])
     if not token:return self.reply(401,{'error':'Correo o contraseña incorrectos.'})
     return self.reply(200,{'ok':True},cookie='gmp_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200')
    actor=self.auth()
    if not actor:return self.reply(401,{'error':'La sesión expiró. Inicia sesión de nuevo.'})
    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),actor['csrf']):return self.reply(403,{'error':'Solicitud sin verificación de sesión.'})
    if self.path=='/api/logout' and self.command=='POST':
     store.logout(self.token);return self.reply(200,{'ok':True},cookie='gmp_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
    if self.path.startswith('/api/inventarios/') and self.command=='POST':
     result=inventory.mutate(self.path,self.read_body(),actor);return self.reply(200,*result) if isinstance(result,tuple) else self.reply(200,result)
    if self.path.startswith('/api/pedidoscompra/') and self.command=='POST':
     result=procurement.mutate(self.path,self.read_body(),actor);return self.reply(200,*result) if isinstance(result,tuple) else self.reply(200,result)
    if self.path.startswith('/api/comercial/') and self.command=='POST':
     result=commercial.mutate(self.path,self.read_body(),actor)
     return self.reply(200,*result) if isinstance(result,tuple) else self.reply(200,result)
    if self.path=='/api/autorizaciones-admin' and self.command=='POST':return self.reply(200,admin_approvals.submit(self.read_body(),actor))
    admin_decision=re.fullmatch('/api/autorizaciones-admin/([a-f0-9]{32})/resolver',self.path)
    if admin_decision and self.command=='POST':
     result=admin_approvals.decide(admin_decision[1],self.read_body(),actor);return self.reply(200 if result['ok'] else 409,result)
    if self.path=='/api/users' and self.command in ('POST','PUT'):
     if actor['role'] not in ('superadmin','auxti'):raise PermissionError('Solo administración puede administrar usuarios.')
     store.manage_user(self.read_body(),actor);return self.reply(200,{'users':store.users()})
    if self.path=='/api/perfiles' and self.command=='PUT':return self.reply(200,store.save_profile(self.read_body(),actor))
    if self.path in ('/api/respaldos/restaurar/revisar','/api/respaldos/restaurar/confirmar') and self.command=='POST':return self.reply(200,backups.review(self.read_body(),actor,apply=self.path.endswith('/confirmar')))
    if self.path in ('/api/respaldos/vaciar/revisar','/api/respaldos/vaciar/confirmar') and self.command=='POST':return self.reply(200,backups.reset(self.read_body(),actor,apply=self.path.endswith('/confirmar')))
    if self.path=='/api/compras/importar' and self.command=='POST':
     read_scope(actor,'compras');require_module(actor,'cargar_maestro');return self.reply(200,purchases.run(self.read_body(),actor))
    if self.path.startswith('/api/requisiciones'):require_module(actor,'requisiciones')
    if actor['role']=='requisicion' and self.path.startswith('/api/requisiciones') and not (self.path in ('/api/requisiciones','/api/requisiciones/cambios') and self.command=='POST'):raise PermissionError('Este perfil solo permite agregar requisiciones y consultar las propias.')
    if self.path=='/api/requisiciones/imagenes' and self.command=='POST':return self.reply(200,images.upload(self.read_body(),actor))
    image_match=re.fullmatch('/api/requisiciones/imagenes/([1-9][0-9]*)',self.path)
    if image_match and self.command=='DELETE':return self.reply(200,images.remove(int(image_match[1]),actor))
    if self.path=='/api/requisiciones/areas' and self.command=='POST':return self.reply(200,requisitions.areas.save(self.read_body(),actor))
    area_match=re.fullmatch('/api/requisiciones/areas/([1-9][0-9]*)',self.path)
    if area_match and self.command=='PUT':return self.reply(200,requisitions.areas.save(self.read_body(),actor,int(area_match[1])))
    if self.path=='/api/requisiciones/cambios' and self.command=='POST':return self.reply(200,workflow.submit(self.read_body(),actor))
    decision=re.fullmatch('/api/requisiciones/cambios/([a-f0-9]{32})/resolver',self.path)
    if decision and self.command=='POST':return self.reply(200,workflow.decide(decision[1],self.read_body(),actor))
    export_match=re.fullmatch('/api/requisiciones/reportes/exportar/(xlsx|pdf)',self.path)
    if export_match and self.command=='POST':
     data=self.read_body();result=select_detail(reports.run(actor,id=data.get('id'),preview=data.get('configuracion')),data.get('seleccion'))
     return self.reply(200,report_xlsx(result),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') if export_match[1]=='xlsx' else self.reply(200,report_pdf(result),'application/pdf')
    if self.path=='/api/requisiciones' and self.command=='POST':
     result=requisitions.create(self.read_body(),actor);return self.reply(200 if result['repetido'] else 201,result)
    if self.path=='/api/requisiciones/maestro' and self.command=='POST':
     data=self.read_body();result=requisitions.import_master(data,actor)
     if not data.get('revisar',False):reports.sync_import(actor)
     return self.reply(200,result)
    if self.path=='/api/requisiciones/reportes' and self.command in ('POST','PUT'):return self.reply(200,reports.save(self.read_body(),actor))
    if self.path=='/api/requisiciones/reportes/vista-previa' and self.command=='POST':return self.reply(200,reports.run(actor,preview=self.read_body()))
    if self.path=='/api/requisiciones/costos' and self.command=='PUT':return self.reply(200,reports.save_cost(self.read_body(),actor))
    if self.path=='/api/requisiciones/series' and self.command=='PUT':return self.reply(200,requisitions.configure(self.read_body(),actor))
    if self.path=='/api/catalogo' and self.command=='PUT':
     if actor['role']=='visualizador':raise PermissionError('El visualizador no puede modificar el catálogo.')
     data=self.read_body();result=store.put(data,actor)
     if result is None:return self.reply(409,{'error':'El catálogo cambió. Actualiza antes de guardar.'})
     return self.reply(200,result)
    if self.path in ('/api/ventas','/api/ventas/importar') and self.command in ('PUT','POST'):
     read_scope(actor,'ventas')
     if self.path.endswith('/importar'):require_module(actor,'cargar_maestro')
     else:write_scope(actor,'ventas')
     data=self.read_body();result=sales.import_master(data,actor) if self.path.endswith('/importar') else sales.put(data,actor)
     if result is None:return self.reply(409,{'error':'Ventas cambió. Actualiza antes de guardar.'})
     return self.reply(200,result)
    return self.reply(404,{'error':'No encontrado.'})
   except RequisitionConflict as e:self.reply(409,{'error':str(e)})
   except sqlite3.IntegrityError:self.reply(400,{'error':'Datos duplicados o incompatibles. No se aplicaron los cambios.'})
   except PermissionError as e:self.reply(403,{'error':str(e)})
   except (ValueError,KeyError,TypeError) as e:self.reply(400,{'error':str(e)})
   except Exception:self.reply(500,{'error':'No se pudo guardar. Revisa el registro del servidor.'})
  def log_message(self,fmt,*args):print(self.address_string(),fmt%args,flush=True)
 Handler.commercial=commercial
 Handler.inventory=inventory
 Handler.procurement=procurement
 return Handler
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--host',default='0.0.0.0');parser.add_argument('--port',type=int);parser.add_argument('--data-dir',default=str(APP_DIR/'data'));args=parser.parse_args()
 configpath=APP_DIR/'config.json'
 if not configpath.exists():configpath.write_text(json.dumps({'port':8080},indent=2),encoding='utf8')
 config=json.loads(configpath.read_text(encoding='utf8'))
 if 'password' in config or 'user' in config:
  config={k:v for k,v in config.items() if k not in ('password','user')};configpath.write_text(json.dumps(config,indent=2),encoding='utf8')
 port=args.port or config.get('port',8080);store=Store(args.data_dir)
 handler=create_handler(store);handler.commercial.sync.start()
 server=http.server.ThreadingHTTPServer((args.host,port),handler);server.daemon_threads=True
 print(f'\n{TITLE} v{VERSION}\n{SUPPORT_LINE}\nPuerto: {port}\nLocal: http://127.0.0.1:{port}\nRed/VPN: http://IP-DEL-SERVIDOR:{port}\nSuperadministrador: {ADMIN_EMAIL}\nInicia sesión con la contraseña configurada.\nDatos: {store.path}\nCtrl+C para detener.\n',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()
if __name__=='__main__':main()

