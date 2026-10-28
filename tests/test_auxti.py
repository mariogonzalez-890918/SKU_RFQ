"""AUXTI: acceso administrativo, fotos libres y bajas autorizadas solo por Sistemas."""
import copy,unittest
import test_backup_import as fixture
from test_images import png
class AuxTiTests(unittest.TestCase):
 def setUp(self):
  self.case=fixture.ModuleBackupTests();self.case.setUp();self.case.import_purchase([fixture.product()]);self.case.import_req([fixture.product(B='SKU00000000001')]);self.case.value('/api/users',{'email':'aux@example.com','name':'Aux TI','role':'auxti','active':True,'password':self.case.password});self.aux=self.case.login('aux@example.com')
 def tearDown(self):self.case.tearDown()
 def propose(self,action,data):return self.case.value('/api/autorizaciones-admin',{'accion':action,'datos':data,'motivo':'Prueba de autorización'},self.aux)['solicitud']
 def decide(self,r,actor=None,approve=True):return self.case.call('/api/autorizaciones-admin/'+r['id']+'/resolver',{'aprobar':approve,'comentario':'Decisión de Sistemas'},actor or self.case.admin)
 def test_existing_superadmin_profile_shows_all_new_capabilities(self):
  import json
  with self.case.store.connect() as db:db.execute("UPDATE role_modules SET modules=? WHERE role='superadmin'",(json.dumps(['ventas','compras','requisiciones']),))
  profiles=self.case.value('/api/perfiles');owner=next(p for p in profiles['perfiles'] if p['perfil']=='superadmin');self.assertEqual(set(owner['modulos']),set(profiles['modulos']));self.assertIn('imagenes',owner['modulos']);self.assertIn('cargar_maestro',owner['modulos'])

 def test_catalog_baja_requires_owner_and_is_single_use(self):
  catalog=self.case.value('/api/catalogo',actor=self.aux);edited=copy.deepcopy(catalog);record=edited['state']['registros'][0];record['eliminado']=True;edited['state']['reservados'].append(record['sku'])
  self.assertEqual(self.case.call('/api/catalogo',edited,self.aux,'PUT')[0],403)
  request=self.propose('baja_compra',{'id':record['id']});self.assertEqual(self.propose('baja_compra',{'id':record['id']})['id'],request['id']);self.assertFalse(self.case.value('/api/catalogo')['state']['registros'][0]['eliminado']);self.assertEqual(self.decide(request,self.aux)[0],403)
  self.case.value('/api/users',{'email':'root2@example.com','name':'Otro administrador','role':'superadmin','active':True,'password':self.case.password});other=self.case.login('root2@example.com');self.assertEqual(self.decide(request,other)[0],403)
  self.assertEqual(self.decide(request)[0],200);self.assertTrue(self.case.value('/api/catalogo')['state']['registros'][0]['eliminado']);self.assertEqual(self.decide(request)[0],409)
 def test_reject_stale_snapshot_and_reject_without_deleting(self):
  row=self.case.value('/api/catalogo')['state']['registros'][0];request=self.propose('baja_compra',{'id':row['id']});self.case.import_purchase([fixture.product(I='101')]);self.assertEqual(self.decide(request)[0],409);self.assertFalse(self.case.value('/api/catalogo')['state']['registros'][0]['eliminado']);request=self.propose('baja_compra',{'id':row['id']});self.assertEqual(self.decide(request,approve=False)[0],200);self.assertFalse(self.case.value('/api/catalogo')['state']['registros'][0]['eliminado'])
 def test_user_permissions_and_deactivation(self):
  for email,role in [('sistemas@grupomipan.com','superadmin'),('aux@example.com','superadmin'),('newroot@example.com','superadmin')]:self.assertEqual(self.case.call('/api/users',{'email':email,'name':'Intento','role':role,'active':True,'password':self.case.password},self.aux)[0],403)
  self.case.value('/api/users',{'email':'viewer@example.com','name':'Consulta','role':'visualizador','active':True,'password':self.case.password});self.assertEqual(self.case.call('/api/users',{'email':'viewer@example.com','name':'Consulta','role':'visualizador','active':False},self.aux)[0],403)
  request=self.propose('desactivar_usuario',{'email':'viewer@example.com'});self.assertEqual(self.decide(request)[0],200);self.assertFalse(next(u for u in self.case.value('/api/users')['users'] if u['email']=='viewer@example.com')['active']);self.assertEqual(self.case.call('/api/perfiles',{'perfil':'auxti','revision':1,'modulos':[]},self.aux,'PUT')[0],403)
 def test_images_are_free_for_aux_only_and_capabilities_apply(self):
  import base64
  id=self.case.value('/api/requisiciones/materiales')['materiales'][0]['id'];data={'archivos':[{'materialId':id,'archivo':'foto.jpg','contenido':base64.b64encode(png(4,3,format='JPEG')).decode()}]}
  self.assertEqual(self.case.value('/api/requisiciones/imagenes',data,self.aux)['guardadas'],1);self.assertEqual(self.case.call('/api/requisiciones/imagenes/'+str(id),actor=self.aux,method='DELETE')[0],200)
  profile=next(p for p in self.case.value('/api/perfiles')['perfiles'] if p['perfil']=='auxti');self.case.value('/api/perfiles',{'perfil':'auxti','revision':profile['revision'],'modulos':['compras','ventas','requisiciones']},method='PUT');self.assertEqual(self.case.call('/api/requisiciones/imagenes',data,self.aux)[0],403)
  self.assertEqual(self.case.call('/api/requisiciones/maestro',{'archivo':'test.xlsx','contenido':fixture.workbook([fixture.product()])},self.aux)[0],403)
  self.assertEqual(self.case.call('/api/compras/importar',{'archivo':'test.xlsx','contenido':fixture.workbook([fixture.product()]),'revision':self.case.value('/api/catalogo')['revision']},self.aux)[0],403)
 def test_reset_and_restore_need_approval_and_keep_module_scope(self):
  backup=self.case.value('/api/respaldos?modulo=compras',actor=self.aux);review=self.case.value('/api/respaldos/vaciar/revisar',{'modulo':'compras'},self.aux);self.assertEqual(self.case.call('/api/respaldos/vaciar/confirmar',{'modulo':'compras','huellaActual':review['huellaActual'],'texto':'VACIAR','confirmar':True},self.aux)[0],403)
  request=self.propose('reiniciar_modulo',{'modulo':'compras'});self.assertEqual(len(self.case.value('/api/catalogo')['state']['registros']),1);self.assertEqual(self.decide(request)[0],200);self.assertEqual(self.case.value('/api/catalogo')['state']['registros'],[]);self.assertEqual(len(self.case.value('/api/requisiciones/materiales')['materiales']),1)
  request=self.propose('restaurar_modulo',{'modulo':'compras','respaldo':backup});self.assertEqual(self.decide(request)[0],200);self.assertEqual(len(self.case.value('/api/catalogo')['state']['registros']),1)
 def test_req_cancellation_is_authorized_for_aux(self):
  doc=self.case.create_req();result=self.case.value('/api/requisiciones/cambios',{'tipo':'cancelar','objetivo':doc['id'],'revision':1,'motivo':'Cancelación autorizada'},self.aux)
  self.assertFalse(result['cambio']['requiereSistemas']);self.assertEqual(result['documento']['estado'],'CANCELADA');self.assertEqual(self.case.value('/api/requisiciones/reportes/general/ejecutar')['resumen']['total'],'0.00')
 def test_explicit_master_capability_grants_and_revokes_import(self):
  self.case.value('/api/users',{'email':'capture@example.com','name':'Carga autorizada','role':'visualizador','active':True,'password':self.case.password});viewer=self.case.login('capture@example.com');payload={'archivo':'productos.xlsx','contenido':fixture.workbook([fixture.product('NUEVO POR CARGA')]),'revision':self.case.value('/api/catalogo')['revision']}
  self.assertEqual(self.case.call('/api/compras/importar',payload,viewer)[0],403)
  profile=next(p for p in self.case.value('/api/perfiles')['perfiles'] if p['perfil']=='visualizador');saved=self.case.value('/api/perfiles',{'perfil':'visualizador','revision':profile['revision'],'modulos':['compras','requisiciones','cargar_maestro']},method='PUT')
  self.case.value('/api/compras/importar',payload,viewer);self.case.value('/api/requisiciones/maestro',{'archivo':'productos.xlsx','contenido':fixture.workbook([fixture.product('NUEVO MATERIAL')])},viewer)
  revision=next(p for p in saved['perfiles'] if p['perfil']=='visualizador')['revision'];self.case.value('/api/perfiles',{'perfil':'visualizador','revision':revision,'modulos':['compras','requisiciones']},method='PUT');self.assertEqual(self.case.call('/api/requisiciones/maestro',{'archivo':'x.xlsx','contenido':fixture.workbook([fixture.product()])},viewer)[0],403)

 def test_sales_baja_and_granted_master_permission(self):
  headers={'A':'SKU','B':'PRODUCTO','C':'CATEGORIA','D':'SUBCATEGORIA','F':'PDV','H':'DESCRIPCIÓN'};master=fixture.workbook([{'A':'PPMA18C5000008','B':'PP','C':'MA','D':'18','F':'A01','H':'BOLILLO CRUDO'}],sheet='SUGERIDO',headers=headers);revision=self.case.value('/api/ventas')['revision'];self.case.value('/api/ventas/importar',{'master':master,'revision':revision},self.aux)
  record=self.case.value('/api/ventas')['state']['registros'][0];request=self.propose('baja_venta',{'id':record['id']});self.assertEqual(self.decide(request)[0],200);self.assertTrue(self.case.value('/api/ventas')['state']['registros'][0]['eliminado'])

if __name__=='__main__':unittest.main()
