import contextlib,importlib.util,json,pathlib,secrets,shutil,sys,tempfile,threading,unittest,urllib.request
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'sku-servidor'))
import server,requisiciones,ventas
spec=importlib.util.spec_from_file_location('initializer',ROOT/'tools/inicializar.py');initializer=importlib.util.module_from_spec(spec);spec.loader.exec_module(initializer)

class CleanInstallation(unittest.TestCase):
 def test_empty_initialization_login_and_modules(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);password=secrets.token_urlsafe(20);initializer.create_initials(root,password);shutil.copy2(ROOT/'sku-servidor/catalogos.json',root/'catalogos.json');shutil.copytree(ROOT/'sku-servidor/public',root/'public')
   before=(root/'initial-admin.json').read_bytes()
   with self.assertRaises(ValueError):initializer.create_initials(root,'Replacement-Password')
   self.assertEqual(before,(root/'initial-admin.json').read_bytes())
   with contextlib.ExitStack() as contexts:
    for module in (server,requisiciones,ventas):contexts.enter_context(patch.object(module,'ROOT',root))
    (root/'initial-admin.json').unlink()
    with patch('getpass.getpass',side_effect=[password,password]) as prompt:
     store=server.Store(root/'data');self.assertEqual(prompt.call_count,2)
    with patch('getpass.getpass',side_effect=AssertionError('No debe pedir contraseña de nuevo.')):server.Store(root/'data')
    http=server.http.server.ThreadingHTTPServer(('127.0.0.1',0),server.create_handler(store));threading.Thread(target=self.http_serve,args=(http,),daemon=True).start();url='http://127.0.0.1:'+str(http.server_port)
    try:
     request=urllib.request.Request(url+'/api/login',data=json.dumps({'email':server.ADMIN_EMAIL,'password':password}).encode(),headers={'Content-Type':'application/json'},method='POST')
     with urllib.request.urlopen(request) as response:cookie=response.headers['Set-Cookie'].split(';')[0]
     def get(path):
      with urllib.request.urlopen(urllib.request.Request(url+path,headers={'Cookie':cookie})) as response:return response.read()
     self.assertEqual(json.loads(get('/api/catalogo'))['state']['registros'],[]);self.assertEqual(json.loads(get('/api/ventas'))['state']['registros'],[]);self.assertEqual(json.loads(get('/api/requisiciones/materiales'))['materiales'],[])
     self.assertEqual(json.loads(get('/api/requisiciones/reportes/general/ejecutar'))['resumen']['base'],'0.00');self.assertTrue(get('/api/requisiciones/reportes/general/xlsx').startswith(b'PK'));self.assertTrue(get('/api/requisiciones/reportes/general/pdf').startswith(b'%PDF-'))
     self.assertIn(b'gmpSidebar',get('/'));self.assertIn(b'data-erp-ready',get('/app.js'));self.assertEqual(len(json.loads(get('/api/me'))['roles']),12)
    finally:http.shutdown();http.server_close()
 @staticmethod
 def http_serve(http):http.serve_forever()

if __name__=='__main__':unittest.main()
