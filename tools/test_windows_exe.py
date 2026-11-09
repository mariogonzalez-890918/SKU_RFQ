"""Prueba el binario distribuido, incluidos QR/Code128 dinámicos, antes de publicarlo."""
import hashlib,io,json,os,pathlib,secrets,shutil,socket,subprocess,sys,tempfile,time,urllib.request,urllib.error,uuid,zipfile

ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'sku-servidor'));sys.path.insert(0,str(ROOT/'tools'))
import server
from inicializar import create_initials
from app_info import VERSION

def verify(executable):
 executable=pathlib.Path(executable).resolve()
 with tempfile.TemporaryDirectory(prefix='gmp-exe-check-') as directory:
  folder=pathlib.Path(directory);seed=folder/'seed';seed.mkdir();password=secrets.token_urlsafe(24);create_initials(seed,password);shutil.copy2(ROOT/'sku-servidor/catalogos.json',seed/'catalogos.json');admin=json.loads((seed/'initial-admin.json').read_text());prior=server.ROOT
  try:server.ROOT=seed;server.Store(folder/'data',initial_admin=admin)
  finally:server.ROOT=prior
  with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
  base='http://127.0.0.1:'+str(port);auth={};process=None;log=open(folder/'server.log','wb')
  def call(path,data=None):
   headers={'Content-Type':'application/json',**auth};req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
   try:
    with urllib.request.urlopen(req,timeout=20) as response:return response.status,response.read(),response.headers
   except urllib.error.HTTPError as error:return error.code,error.read(),error.headers
  def value(path,data=None):
   status,raw,_=call(path,data)
   if status not in (200,201):raise AssertionError((path,status,raw[:200]))
   return json.loads(raw)
  def stop():
   nonlocal process
   if process:
    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:process.terminate()
    process.wait(timeout=20);process=None
  def start():
   nonlocal process,auth
   auth={};process=subprocess.Popen([str(executable),'--host','127.0.0.1','--port',str(port),'--data-dir',str(folder/'data')],cwd=folder,stdout=log,stderr=log,**({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
   for _ in range(240):
    if process.poll() is not None:raise AssertionError('El EXE terminó al iniciar.')
    try:
     status,raw,headers=call('/api/login',{'email':server.ADMIN_EMAIL,'password':password})
     if status!=200:raise AssertionError('No pudo iniciar sesión en la instalación temporal.')
     auth={'Cookie':headers['Set-Cookie'].split(';')[0]};me=value('/api/me');auth['X-CSRF-Token']=me['user']['csrf'];assert me['app']['version']==VERSION;return
    except (OSError,urllib.error.URLError):time.sleep(.25)
   raise AssertionError('El EXE no respondió al iniciar.')
  try:
   start();company=value('/api/comercial/empresas',{'nombre':'PRUEBA EXE','sucursales':['EJIDOS','SAN PABLO','CUAUTITLAN']})['id'];product=value('/api/comercial/productos',{'canal':'ventasins','empresa':company,'sku':'PTPD05B0000000','nombre':'PAN DE PRUEBA EXE','tipo':'PT','categoria':'PD','subcategoria':'05','unidad':'PIEZA','iva':'0','canales':['ventasins'],'precios':{'PUBLICO':'1'}});sku=product['sku'];p=value('/api/pt/producto?sku='+sku);data={'sku':sku,'sucursal':'EJIDOS','cantidad':'5','revisionProducto':p['revision'],'clave':uuid.uuid4().hex};entry=value('/api/pt/ingresos',data)['ingreso'];assert value('/api/pt/ingresos',data)['repetido'];assert len(value('/api/pt/ingresos')['ingresos'])==1
   for path,prefix in (('/pt',b'<!doctype html>'),('/pt-scanner.js',b''),('/api/pt/etiquetas/pdf?skus='+sku,b'%PDF-'),('/api/pt/codigo/svg?sku='+sku+'&tipo=qr',b'<?xml'),('/api/pt/codigo/svg?sku='+sku+'&tipo=barras',b'<?xml')):
    status,raw,_=call(path);assert status==200 and raw.startswith(prefix),(path,status,raw[:100])
   status,raw,_=call('/api/pt/excel?sucursal=EJIDOS&mes='+entry['mes']);assert status==200
   with zipfile.ZipFile(io.BytesIO(raw)) as archive:assert archive.testzip() is None;assert sku.encode() in archive.read('xl/worksheets/sheet1.xml');assert 'xl/worksheets/sheet2.xml' in archive.namelist()
   assert not value('/api/pt/onedrive')['conectado'];value('/api/pt/cancelar',{'id':entry['id'],'revision':1});stop();start();assert value('/api/pt/ingresos')['ingresos'][0]['estado']=='CANCELADO'
  except Exception:
   stop();log.flush();print((folder/'server.log').read_text(errors='replace')[-7000:]);raise
  finally:stop();log.close()
 print('PASS EXE Windows: versión, arranque, ingreso PT idempotente, PDF QR/Code128, SVG, lector, Excel mensual, cancelación y persistencia.')

if __name__=='__main__':verify(sys.argv[1])
