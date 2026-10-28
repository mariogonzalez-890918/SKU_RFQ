"""Gerente operativo y perfil Requisición con aislamiento por cuenta capturista."""
import base64,json,unittest,uuid
import test_backup_import as fixture
from test_images import png
import server
class RequisitionRoleTests(unittest.TestCase):
 def setUp(self):
  self.case=fixture.ModuleBackupTests();self.case.setUp();self.case.import_req([fixture.product(B='SKU00000000001')]);self.material=self.case.value('/api/requisiciones/materiales')['materiales'][0]
 def tearDown(self):self.case.tearDown()
 def user(self,email,role,**access):
  if role=='requisicion':access={'sucursales':['EJIDOS','SAN PABLO','CUAUTITLAN','EJE 8'],**access}
  self.case.value('/api/users',{'email':email,'name':email.split('@')[0],'role':role,'active':True,'password':self.case.password,**access});return self.case.login(email)
 def create(self,actor,branch='EJIDOS',key=None):
  data={'sucursal':branch,'area':'Produccion Donas','solicitante':'MISMO NOMBRE SOLICITANTE','observaciones':'','claveCliente':key or uuid.uuid4().hex,'partidas':[{'materialId':self.material['id'],'cantidad':'2','observaciones':''}]};return self.case.value('/api/requisiciones',data,actor)['documento']
 def test_own_list_count_detail_and_exports_ignore_requester_display_name(self):
  a=self.user('captura-a@example.com','requisicion');b=self.user('captura-b@example.com','requisicion');root=self.create(self.case.admin);one=self.create(a);other=self.create(b)
  listing=self.case.value('/api/requisiciones',actor=a);self.assertEqual(listing['total'],1);self.assertEqual([r['id'] for r in listing['solicitudes']],[one['id']]);self.assertEqual(self.case.value('/api/requisiciones/meta',actor=a)['totalSolicitudes'],1)
  self.assertEqual(self.case.value('/api/requisiciones?pagina=2',actor=a)['solicitudes'],[])
  for id in (root['id'],other['id']):
   for suffix in ('','/imprimir'):self.assertEqual(self.case.call('/api/requisiciones/'+id+suffix,actor=a)[0],404)
  for suffix in ('','/imprimir'):self.assertEqual(self.case.call('/api/requisiciones/'+one['id']+suffix,actor=a)[0],200)
  self.assertEqual(self.case.call('/api/requisiciones/'+one['id']+'/csv',actor=a)[0],403)
  manager=self.user('gerente@example.com','gerente');self.assertEqual(self.case.value('/api/requisiciones',actor=manager)['total'],3)
 def test_requisition_has_only_create_and_own_read_not_costs_or_admin(self):
  actor=self.user('captura@example.com','requisicion');doc=self.create(actor)
  for path in ('/api/catalogo','/api/ventas','/api/users','/api/perfiles','/api/respaldos?modulo=requisiciones','/api/autorizaciones-admin','/api/requisiciones/reportes','/api/requisiciones/reportes/general/ejecutar','/api/requisiciones/reportes/general/csv','/api/requisiciones/reportes/general/xlsx','/api/requisiciones/reportes/general/pdf','/api/requisiciones/costos','/api/requisiciones/catalogo.csv','/api/requisiciones/maestro/archivo'):
   with self.subTest(path=path):self.assertEqual(self.case.call(path,actor=actor)[0],403)
  for path,method in (('/api/requisiciones/maestro','POST'),('/api/requisiciones/series','PUT'),('/api/requisiciones/costos','PUT'),('/api/requisiciones/cambios','POST'),('/api/requisiciones/reportes','POST'),('/api/requisiciones/reportes/vista-previa','POST'),('/api/requisiciones/reportes/exportar/xlsx','POST'),('/api/requisiciones/imagenes','POST'),('/api/requisiciones/imagenes/'+str(self.material['id']),'DELETE')):
   with self.subTest(path=path,method=method):self.assertEqual(self.case.call(path,{},actor,method)[0],403)
  self.assertEqual(self.case.value('/api/me',actor=actor)['user']['modulos'],['requisiciones']);materials=self.case.value('/api/requisiciones/materiales',actor=actor)['materiales'];self.assertEqual(set(materials[0]),{'id','sku','nombre','unidad','proveedor','estado','skuRepetido'})
  self.case.value('/api/requisiciones/imagenes',{'archivos':[{'materialId':self.material['id'],'archivo':'foto.png','contenido':base64.b64encode(png()).decode()}]});photos=self.case.value('/api/requisiciones/imagenes',actor=actor);self.assertEqual(set(photos['imagenes'][0]),{'materialId','imagenId'});self.assertEqual(self.case.call('/api/requisiciones/imagenes/'+str(self.material['id'])+'?miniatura=1',actor=actor)[0],200)
 def test_profile_cannot_gain_other_modules_and_own_scope_survives_manager_edit(self):
  actor=self.user('captura@example.com','requisicion');doc=self.create(actor);profile=next(p for p in self.case.value('/api/perfiles')['perfiles'] if p['perfil']=='requisicion');self.assertEqual(self.case.call('/api/perfiles',{'perfil':'requisicion','revision':profile['revision'],'modulos':['requisiciones','cargar_maestro']},method='PUT')[0],400)
  manager=self.user('gerente@example.com','gerente');self.case.value('/api/requisiciones/cambios',{'tipo':'modificar','objetivo':doc['id'],'revision':1,'motivo':'Corregir nombre mostrado','datos':{'area':doc['area'],'solicitante':'OTRO NOMBRE','observaciones':'Actualizada por gerente','partidas':[{'materialId':self.material['id'],'cantidad':'3','observaciones':''}]}},manager)
  own=self.case.value('/api/requisiciones/'+doc['id'],actor=actor);self.assertEqual(own['creadoPor'],'captura@example.com');self.assertEqual(own['solicitante'],'OTRO NOMBRE');self.assertEqual(self.case.value('/api/requisiciones',actor=actor)['total'],1)
 def test_existing_manager_migrates_once_and_can_create_load_series_and_approve(self):
  manager=self.user('gerente@example.com','gerente')
  with self.case.store.connect() as db:db.execute("UPDATE role_modules SET modules=? WHERE role='gerente'",(json.dumps(['requisiciones']),));db.execute("DELETE FROM permission_features WHERE key='manager-requisitions-v2'")
  server.Store(self.case.store.directory);self.assertIn('cargar_maestro',self.case.value('/api/me',actor=manager)['user']['modulos']);self.case.value('/api/requisiciones/maestro',{'archivo':'GERENTE.xlsx','contenido':fixture.workbook([fixture.product(B='SKU00000000001')])},manager)
  branch=next(r for r in self.case.value('/api/requisiciones/meta',actor=manager)['sucursales'] if r['sucursal']=='EJIDOS');meta=self.case.value('/api/requisiciones/series',{'sucursal':'EJIDOS','serie':'GTE-EJI','siguiente':50,'revision':branch['revision']},manager,'PUT');doc=self.create(manager);self.assertEqual(doc['numero'],'GTE-EJI-000050')
  branch=next(r for r in self.case.value('/api/requisiciones/meta',actor=manager)['sucursales'] if r['sucursal']=='EJIDOS');self.assertEqual(self.case.call('/api/requisiciones/series',{'sucursal':'EJIDOS','serie':'GTE-EJI','siguiente':1,'revision':branch['revision']},manager,'PUT')[0],400)
  other=next(r for r in meta['sucursales'] if r['sucursal']=='SAN PABLO');self.assertEqual(self.case.call('/api/requisiciones/series',{'sucursal':'SAN PABLO','serie':'GTE-EJI','siguiente':1,'revision':other['revision']},manager,'PUT')[0],400)
  warehouse=self.user('almacen@example.com','almacenista',almacenes=['EJIDOS']);change=self.case.value('/api/requisiciones/cambios',{'tipo':'cancelar','objetivo':doc['id'],'revision':1,'motivo':'Cancelar solicitud'},warehouse)['cambio'];self.case.value('/api/requisiciones/cambios/'+change['id']+'/resolver',{'aprobar':True,'comentario':'Autorizado por gerente'},manager);self.assertEqual(self.case.value('/api/requisiciones/'+doc['id'],actor=manager)['estado'],'CANCELADA')
  profile=next(p for p in self.case.value('/api/perfiles')['perfiles'] if p['perfil']=='gerente');self.case.value('/api/perfiles',{'perfil':'gerente','revision':profile['revision'],'modulos':['requisiciones']},method='PUT');server.Store(self.case.store.directory);self.assertNotIn('cargar_maestro',self.case.value('/api/me',actor=manager)['user']['modulos'])
 def test_own_correction_waits_for_manager_authorization(self):
  actor=self.user('captura@example.com','requisicion');doc=self.create(actor);other=self.create(self.case.admin);values={'area':doc['area'],'solicitante':doc['solicitante'],'observaciones':'Corrección solicitada','partidas':[{'materialId':self.material['id'],'cantidad':'5','observaciones':''}]};proposal={'tipo':'modificar','objetivo':doc['id'],'revision':1,'motivo':'Necesito corregir cantidad','datos':values}
  result=self.case.value('/api/requisiciones/cambios',proposal,actor);change=result['cambio'];self.assertEqual(change['estado'],'PENDIENTE');self.assertIsNone(result['documento']);self.assertEqual(self.case.value('/api/requisiciones/'+doc['id'],actor=actor)['partidas'][0]['cantidad'],'2')
  self.assertEqual(self.case.call('/api/requisiciones/cambios',{**proposal,'objetivo':other['id']},actor)[0],403);self.assertEqual(self.case.call('/api/requisiciones/cambios',{'tipo':'cancelar','objetivo':doc['id'],'revision':1,'motivo':'Cancelar'},actor)[0],200)
  self.assertEqual(self.case.call('/api/requisiciones/cambios/'+change['id']+'/resolver',{'aprobar':True,'comentario':'Intento'},actor)[0],403);self.assertEqual(next(c for c in self.case.value('/api/requisiciones/cambios',actor=actor)['cambios'] if c['tipo']=='modificar')['id'],change['id'])
  manager=self.user('gerente@example.com','gerente');self.case.value('/api/requisiciones/cambios/'+change['id']+'/resolver',{'aprobar':True,'comentario':'Cantidad autorizada'},manager);updated=self.case.value('/api/requisiciones/'+doc['id'],actor=actor);self.assertEqual(updated['partidas'][0]['cantidad'],'5');self.assertEqual(updated['fechaHora'],doc['fechaHora']);self.assertEqual(updated['numero'],doc['numero'])
  history=self.case.value('/api/requisiciones/'+doc['id']+'/historial',actor=actor);self.assertEqual(history['cambios'][0]['estado'],'APROBADA');self.assertEqual(self.case.call('/api/requisiciones/'+other['id']+'/historial',actor=actor)[0],403)
  def no_costs(value):
   if isinstance(value,dict):
    for key,item in value.items():self.assertNotIn('costo',key.lower());self.assertNotIn('precio',key.lower());no_costs(item)
   elif isinstance(value,list):
    for item in value:no_costs(item)
  for value in (updated,history,result):no_costs(value)

 def test_legacy_cost_fields_never_leave_requester_responses(self):
  actor=self.user('captura@example.com','requisicion');key=uuid.uuid4().hex;doc=self.create(actor,key=key)
  with self.case.store.connect() as db:
   old=json.loads(db.execute('SELECT payload FROM req_documents WHERE id=?',(doc['id'],)).fetchone()[0]);old['costoTotal']='999';old['partidas'][0]['precioCompra']='500';db.execute('UPDATE req_documents SET payload=? WHERE id=?',(json.dumps(old),doc['id']));db.execute('INSERT INTO req_document_versions VALUES(?,?,?)',(doc['id'],1,json.dumps(old)))
   report=json.loads(db.execute('SELECT report FROM req_masters ORDER BY id DESC LIMIT 1').fetchone()[0]);report['costoTotalMaestro']='500';db.execute('UPDATE req_masters SET report=?',(json.dumps(report),))
  responses=[self.case.value('/api/requisiciones/'+doc['id'],actor=actor),self.case.value('/api/requisiciones',actor=actor),self.case.value('/api/requisiciones/'+doc['id']+'/historial',actor=actor),self.case.value('/api/requisiciones/meta',actor=actor),self.create(actor,key=key)]
  def check(value):
   if isinstance(value,dict):
    for name,child in value.items():self.assertNotIn('costo',name.lower());self.assertNotIn('precio',name.lower());check(child)
   elif isinstance(value,list):
    for child in value:check(child)
  for response in responses:check(response)
  self.assertIn('costoTotal',self.case.value('/api/requisiciones/'+doc['id']))

 def test_assigned_branches_limit_creation_read_and_pending_approval(self):
  actor=self.user('captura@example.com','requisicion',sucursales=['EJIDOS']);doc=self.create(actor)
  data={'sucursal':'SAN PABLO','area':'Produccion Donas','solicitante':'PRUEBA','observaciones':'','claveCliente':uuid.uuid4().hex,'partidas':[{'materialId':self.material['id'],'cantidad':'1','observaciones':''}]};self.assertEqual(self.case.call('/api/requisiciones',data,actor)[0],403);self.assertEqual([b['sucursal'] for b in self.case.value('/api/requisiciones/meta',actor=actor)['sucursales']],['EJIDOS']);self.assertEqual(self.case.call('/api/requisiciones?sucursal=SAN%20PABLO',actor=actor)[0],403)
  values={'area':doc['area'],'solicitante':doc['solicitante'],'observaciones':'','partidas':[{'materialId':self.material['id'],'cantidad':'5','observaciones':''}]};change=self.case.value('/api/requisiciones/cambios',{'tipo':'modificar','objetivo':doc['id'],'revision':1,'motivo':'Corregir','datos':values},actor)['cambio']
  self.case.value('/api/users',{'email':'captura@example.com','name':'Captura','role':'requisicion','active':True,'sucursales':['SAN PABLO']});self.assertEqual(self.case.value('/api/requisiciones',actor=actor)['total'],0);self.assertEqual(self.case.call('/api/requisiciones/'+doc['id'],actor=actor)[0],404);manager=self.user('gerente@example.com','gerente');self.assertEqual(self.case.call('/api/requisiciones/cambios/'+change['id']+'/resolver',{'aprobar':True,'comentario':'Revisar'},manager)[0],409);self.assertEqual(self.case.value('/api/requisiciones/'+doc['id'])['partidas'][0]['cantidad'],'2')

 def test_old_manager_changes_do_not_leak_after_role_becomes_requester(self):
  actor=self.user('captura@example.com','gerente');doc=self.create(self.case.admin);values={'area':doc['area'],'solicitante':doc['solicitante'],'observaciones':'','partidas':[{'materialId':self.material['id'],'cantidad':'3','observaciones':''}]};self.case.value('/api/requisiciones/cambios',{'tipo':'modificar','objetivo':doc['id'],'revision':1,'motivo':'Cambio anterior','datos':values},actor)
  self.case.value('/api/users',{'email':'captura@example.com','name':'Captura','role':'requisicion','active':True,'sucursales':['EJIDOS']});self.assertEqual(self.case.value('/api/requisiciones/cambios',actor=actor)['cambios'],[])

 def test_requisition_and_manager_can_create_in_four_branches(self):
  actor=self.user('captura@example.com','requisicion');manager=self.user('gerente@example.com','gerente');key=uuid.uuid4().hex
  for branch in ('EJIDOS','SAN PABLO','CUAUTITLAN','EJE 8'):
   key=uuid.uuid4().hex;first=self.create(actor,branch,key);second=self.create(manager,branch,key);self.assertNotEqual(first['id'],second['id']);self.assertEqual(first['creadoPor'],'captura@example.com');self.assertEqual(second['creadoPor'],'gerente@example.com')
  self.assertEqual(self.case.value('/api/requisiciones',actor=actor)['total'],4);self.assertEqual(self.case.value('/api/requisiciones',actor=manager)['total'],8)

if __name__=='__main__':unittest.main()
