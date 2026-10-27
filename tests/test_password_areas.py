"""Política de cuatro caracteres y catálogo de áreas con permisos e historial."""
import hashlib,json,pathlib,secrets,tempfile,unittest,uuid
import test_backup_import as fixture
from respaldos import digest
class PasswordAreaTests(unittest.TestCase):
 def setUp(self):
  self.case=fixture.ModuleBackupTests();self.case.setUp();self.case.import_req([fixture.product()]);self.material=self.case.value('/api/requisiciones/materiales')['materiales'][0]
 def tearDown(self):self.case.tearDown()
 def user(self,role):
  email=role+'@example.com';extra={'almacenes':['EJIDOS']} if role=='almacenista' else {'sucursales':['EJIDOS']} if role=='requisicion' else {};self.case.value('/api/users',{'email':email,'name':role,'role':role,'active':True,'password':self.case.password,**extra});return self.case.login(email)
 def create(self,area):return self.case.value('/api/requisiciones',{'sucursal':'EJIDOS','area':area,'solicitante':'PRUEBA','observaciones':'','claveCliente':uuid.uuid4().hex,'partidas':[{'materialId':self.material['id'],'cantidad':'2','observaciones':''}]})['documento']
 def test_four_characters_create_change_login_and_initialization(self):
  short=secrets.token_urlsafe(3);email='password@example.com'
  self.assertEqual(len(short),4)
  self.assertEqual(self.case.call('/api/users',{'email':email,'name':'Prueba','role':'visualizador','active':True,'password':short[:3]})[0],400)
  self.case.value('/api/users',{'email':email,'name':'Prueba','role':'visualizador','active':True,'password':short});self.assertEqual(self.case.call('/api/login',{'email':email,'password':short})[0],200)
  other=short+'x';self.case.value('/api/users',{'email':email,'name':'Prueba','role':'visualizador','active':True,'password':other});self.assertEqual(self.case.call('/api/login',{'email':email,'password':short})[0],401);self.assertEqual(self.case.call('/api/login',{'email':email,'password':other})[0],200)
  with self.case.store.connect() as db:stored=db.execute('SELECT password_hash FROM users WHERE email=?',(email,)).fetchone()[0];self.assertEqual(len(stored),64);self.assertNotEqual(stored,other)
  with tempfile.TemporaryDirectory() as directory:
   fixture.initializer.create_initials(pathlib.Path(directory),short);admin=json.loads((pathlib.Path(directory)/'initial-admin.json').read_text(encoding='utf-8'));self.assertEqual(admin['password_hash'],hashlib.pbkdf2_hmac('sha256',short.encode(),bytes.fromhex(admin['salt']),310000).hex())
 def test_area_permissions_all_roles(self):
  for role in ('auxti','gerente','compras','ventas','alta','visualizador','almacenista','requisicion'):
   actor=self.user(role);allowed=role in ('auxti','gerente');status,_,_=self.case.call('/api/requisiciones/areas',actor=actor);self.assertEqual(status,200 if allowed else 403)
   catalog=self.case.value('/api/requisiciones/areas');status,_,_=self.case.call('/api/requisiciones/areas',{'nombre':'Área '+role,'revision':catalog['revision']},actor);self.assertEqual(status,200 if allowed else 403)
   catalog=self.case.value('/api/requisiciones/areas');row=catalog['areas'][0];self.assertEqual(self.case.call('/api/requisiciones/areas/'+str(row['id']),{'nombre':row['nombre'],'revision':catalog['revision']},actor,'PUT')[0],200 if allowed else 403)
 def test_area_rename_keeps_documents_report_filters_and_corrections(self):
  catalog=self.case.value('/api/requisiciones/areas');added=self.case.value('/api/requisiciones/areas',{'nombre':'Pruebas nuevas','revision':catalog['revision']});row=added['areas'][-1];doc=self.create(row['nombre']);saved=self.case.value('/api/requisiciones/reportes',{'nombre':'Histórico de área','areas':[row['nombre']],'agrupacion':'area','impuestos':[]})
  self.case.value('/api/requisiciones/areas/'+str(row['id']),{'nombre':'Pruebas actualizadas','revision':added['revision']},method='PUT');meta=self.case.value('/api/requisiciones/meta');self.assertIn('Pruebas actualizadas',meta['areas']);self.assertNotIn('Pruebas nuevas',meta['areas']);self.assertIn('Pruebas nuevas',meta['areasReporte']);self.assertEqual(self.case.value('/api/requisiciones/'+doc['id'])['area'],'Pruebas nuevas');self.assertEqual(self.case.value('/api/requisiciones/reportes/'+saved['id']+'/ejecutar')['resumen']['partidas'],1)
  manager=self.user('gerente');self.case.value('/api/requisiciones/cambios',{'tipo':'modificar','objetivo':doc['id'],'revision':1,'motivo':'Corregir cantidad','datos':{'area':doc['area'],'solicitante':doc['solicitante'],'observaciones':'','partidas':[{'materialId':self.material['id'],'cantidad':'3','observaciones':''}]}},manager);self.assertEqual(self.case.value('/api/requisiciones/'+doc['id'])['area'],'Pruebas nuevas')
  self.assertEqual(self.create('Pruebas actualizadas')['area'],'Pruebas actualizadas')
 def test_duplicate_and_stale_area_updates(self):
  catalog=self.case.value('/api/requisiciones/areas');self.assertEqual(self.case.call('/api/requisiciones/areas',{'nombre':'producción','revision':catalog['revision']})[0],400)
  self.case.value('/api/requisiciones/areas',{'nombre':'Área exclusiva','revision':catalog['revision']});self.assertEqual(self.case.call('/api/requisiciones/areas',{'nombre':'Otra área','revision':catalog['revision']})[0],409)
 def test_area_backup_restore_legacy_and_reset(self):
  legacy=self.case.value('/api/respaldos?modulo=requisiciones');del legacy['datos']['tablas']['req_areas'];legacy['checksum']=digest({k:v for k,v in legacy.items() if k!='checksum'});self.case.review('requisiciones',legacy)
  catalog=self.case.value('/api/requisiciones/areas');added=self.case.value('/api/requisiciones/areas',{'nombre':'Área de respaldo','revision':catalog['revision']});row=added['areas'][-1];doc=self.create(row['nombre']);backup=self.case.value('/api/respaldos?modulo=requisiciones');self.case.value('/api/requisiciones/areas/'+str(row['id']),{'nombre':'Área posterior','revision':added['revision']},method='PUT');review=self.case.review('requisiciones',backup);self.case.restore('requisiciones',backup,review);self.assertIn('Área de respaldo',self.case.value('/api/requisiciones/meta')['areas']);self.assertEqual(self.case.value('/api/requisiciones/'+doc['id'])['area'],'Área de respaldo')
  reset=self.case.value('/api/respaldos/vaciar/revisar',{'modulo':'requisiciones'});self.case.value('/api/respaldos/vaciar/confirmar',{'modulo':'requisiciones','huellaActual':reset['huellaActual'],'texto':'VACIAR','confirmar':True});self.assertIn('Área de respaldo',self.case.value('/api/requisiciones/meta')['areas'])

if __name__=='__main__':unittest.main()
