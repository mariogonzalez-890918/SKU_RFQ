"""PT con HTTP/SQLite real y publicación Microsoft simulada: alcance, precisión y reintentos."""
import io,json,uuid,zipfile,concurrent.futures,sys,urllib.request,urllib.parse,tempfile,pathlib,time,threading
from unittest.mock import patch
import test_commercial as fixture
from pt_routes import PTAPI
from pt_onedrive import OneDrivePT,CloudError,crypt
from pt import qr_value,scan_sku

class PTTests(fixture.CommercialTests):
 def setUp(self):
  super().setUp();self.load_master();self.api=PTAPI(self.store);self.pt=self.api.pt;self.cloud=self.api.cloud;self.sku=fixture.SKU
 def user(self,role='pt',branches=None,email=None):
  email=email or role+'@pt.test';self.value('/api/users',{'email':email,'name':'Usuario '+role,'role':role,'password':self.password,'active':True,'sucursales':branches or ['EJIDOS']});return self.login(email)
 def product(self,actor=None):return self.value('/api/pt/producto?sku='+self.sku,actor=actor)
 def entry(self,actor=None,**fields):return self.value('/api/pt/ingresos',self.data(actor,**fields),actor)
 def data(self,actor=None,**fields):return {'sku':self.sku,'sucursal':'EJIDOS','cantidad':'3','revisionProducto':self.product(actor)['revision'],'clave':uuid.uuid4().hex,**fields}
 def configure(self,actor=None):
  state=self.value('/api/pt/onedrive');return self.value('/api/pt/onedrive/configurar',{'revision':state['revision'],'cliente':'11111111-1111-1111-1111-111111111111','cuenta':'soportetecnico@grupomipan.com','carpetas':{'EJIDOS':'GMP_PT/EJIDOS','SAN PABLO':'GMP_PT/SAN_PABLO','CUAUTITLAN':'GMP_PT/CUAUTITLAN'},'habilitado':True},actor)
 def enable(self):
  self.configure()
  with self.store.connect() as db:
   c=json.loads(db.execute('SELECT payload FROM pt_cloud').fetchone()[0]);c['conectado']=True;db.execute('UPDATE pt_cloud SET payload=?',(json.dumps(c),))
 def test_pt_only_own_history_branch_scope_no_prices_or_module_escalation(self):
  pt=self.user();other=self.user(email='otro@pt.test');meta=self.value('/api/pt/meta',actor=pt);self.assertEqual(meta['sucursales'],['EJIDOS']);self.assertFalse(meta['administra']);self.assertEqual(self.value('/api/me',actor=pt)['user']['modulos'],['pt']);one=self.entry(pt)['ingreso'];self.entry(other)
  history=self.value('/api/pt/ingresos',actor=pt)['ingresos'];self.assertEqual([r['id'] for r in history],[one['id']]);self.assertEqual(len(self.value('/api/pt/ingresos')['ingresos']),2)
  for path in ('/api/catalogo','/api/comercial/productos?canal=ventasins&empresa='+str(self.company),'/api/requisiciones/materiales','/api/pt/ingresos?sucursal=SAN%20PABLO','/api/pt/etiquetas/pdf'):
   self.assertEqual(self.call(path,actor=pt)[0],403,path)
  text=json.dumps(self.product(pt));self.assertNotIn('precio',text);self.assertNotIn('iva',text);self.assertNotIn('costo',text)
  profile=next(p for p in self.value('/api/perfiles')['perfiles'] if p['perfil']=='pt');self.assertEqual(self.call('/api/perfiles',{'perfil':'pt','revision':profile['revision'],'modulos':['pt','compras']},method='PUT')[0],400)
 def test_exact_quantity_server_master_fields_and_closed_eje8(self):
  pt=self.user();base=self.data(pt)
  for qty in ('0','-1','NaN','Infinity','1.5','1e10',True,'0.00001'):
   self.assertEqual(self.call('/api/pt/ingresos',{**base,'cantidad':qty},pt)[0],400,qty)
  for extra in ({'fecha':'2000-01-01'},{'descripcion':'OTRO PAN'},{'unidad':'KILO'},{'sucursal':'EJE 8'}):self.assertIn(self.call('/api/pt/ingresos',{**base,**extra},pt)[0],(400,403))
  saved=self.entry(pt)['ingreso'];self.assertEqual(saved['descripcion'],'PRODUCTO DE PRUEBA');self.assertEqual(saved['unidad'],'PIEZA');self.assertNotIn('2000',saved['fecha']);self.assertIn('revisionMaestro',saved)
 def test_duplicate_concurrent_retry_creates_one_row_and_queues_once(self):
  actor=self.user();data=self.data(actor)
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.call('/api/pt/ingresos',data,actor),range(4)))
  self.assertTrue(all(s==200 for s,_,_ in results));self.assertEqual(len(self.value('/api/pt/ingresos')['ingresos']),1)
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT revision FROM pt_exports').fetchone()[0],1)
  self.assertEqual(self.call('/api/pt/ingresos',{**data,'cantidad':'4'},actor)[0],409)
 def test_master_change_requires_rescan_and_inactive_product_rejected(self):
  data=self.data();self.cm('maestro',{'empresas':[self.company],'archivo':'NEW.xlsx','contenido':fixture.master().replace('X','X')})
  with self.store.connect() as db:
   row=db.execute('SELECT payload FROM cm_products WHERE sku=?',(self.sku,)).fetchone();product=json.loads(row[0]);product['nombre']='NOMBRE NUEVO';db.execute('UPDATE cm_products SET payload=? WHERE sku=?',(json.dumps(product),self.sku))
  self.assertEqual(self.call('/api/pt/ingresos',data)[0],409)
  with self.store.connect() as db:product['activo']=False;db.execute('UPDATE cm_products SET payload=? WHERE sku=?',(json.dumps(product),self.sku))
  self.assertEqual(self.call('/api/pt/producto?sku='+self.sku)[0],400)
 def test_three_branches_month_rollover_cancel_original_month_and_xlsx_numbers(self):
  entries=[]
  with patch('pt.now',return_value='2026-11-30T23:59:59-06:00'):
   for b in ('EJIDOS','SAN PABLO','CUAUTITLAN'):entries.append(self.entry(sucursal=b)['ingreso'])
  with patch('pt.now',return_value='2026-12-01T00:00:01-06:00'):self.entry();self.value('/api/pt/cancelar',{'id':entries[0]['id'],'revision':1,'motivo':''})
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT revision FROM pt_exports WHERE branch=? AND month=?',('EJIDOS','2026-11')).fetchone()[0],2);self.assertEqual(db.execute('SELECT COUNT(*) FROM pt_exports').fetchone()[0],4)
  status,raw,_=self.call('/api/pt/excel?sucursal=EJIDOS&mes=2026-11');self.assertEqual(status,200)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertEqual(z.testzip(),None);xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('CANCELADO',xml);self.assertIn('<c r="I2"><v>0</v></c>',xml);self.assertIn(self.sku,xml);self.assertNotIn('Precio',xml);self.assertIn('RESUMEN_PT',z.read('xl/workbook.xml').decode())
 def test_cancellation_requires_manager_and_does_not_delete_original(self):
  user=self.user();entry=self.entry(user)['ingreso'];data={'id':entry['id'],'revision':1};self.assertEqual(self.call('/api/pt/cancelar',data,user)[0],403)
  manager=self.user('gerente',list(fixture.fixtures.requisiciones.BRANCHES));self.value('/api/pt/cancelar',data,manager);current=self.value('/api/pt/ingresos',actor=user)['ingresos'][0];self.assertEqual(current['estado'],'CANCELADO');self.assertEqual(current['cantidad'],'3');self.assertEqual(self.call('/api/pt/cancelar',data,manager)[0],409)
 def test_pdf_qr_and_bars_from_validated_master_and_permissions(self):
  import pypdf
  status,raw,_=self.call('/api/pt/etiquetas/pdf?skus='+self.sku);self.assertEqual(status,200);pdf=pypdf.PdfReader(io.BytesIO(raw));self.assertIn(self.sku,pdf.pages[0].extract_text());self.assertIn('PRODUCTO DE PRUEBA',pdf.pages[0].extract_text())
  for kind in ('qr','barras'):
   status,raw,_=self.call('/api/pt/codigo/svg?sku='+self.sku+'&tipo='+kind);self.assertEqual(status,200);self.assertIn(b'<svg',raw)
 def test_mobile_qr_url_and_legacy_barcodes_resolve_same_product(self):
  actor=self.user()
  for base in ('http://192.168.1.20:8080','http://26.10.20.30:8080','https://gmp.example.test'):
   code=qr_value(self.sku,base);self.assertEqual(scan_sku(code),self.sku)
   self.assertEqual(self.value('/api/pt/producto?'+urllib.parse.urlencode({'sku':code}),actor=actor)['sku'],self.sku)
  self.assertEqual(scan_sku(self.sku),self.sku)
  for code in ('https://example.test/pt?sku='+self.sku+'&cantidad=3','https://example.test/pt?sku='+self.sku+'&sku='+self.sku,'https://example.test/otro?sku='+self.sku,'https://user:pass@example.test/pt?sku='+self.sku):
   self.assertEqual(self.call('/api/pt/producto?'+urllib.parse.urlencode({'sku':code}),actor=actor)[0],400)
  self.assertEqual(self.value('/api/pt/ingresos',actor=actor)['ingresos'],[])
 def test_mobile_label_url_validation_and_authentication_preserve_product(self):
  for base in ('javascript:alert(1)','https://user:pass@example.test','https://example.test/?token=secret','https://example.test/otro','https://example.test/#x'):
   with self.assertRaises(ValueError):qr_value(self.sku,base)
  with urllib.request.urlopen(self.url+'/pt?sku='+self.sku) as response:
   html=response.read().decode();self.assertIn('id="login"',html);self.assertIn("'/pt'+location.search",html)
  status,raw,_=self.call('/api/pt/etiquetas/pdf?'+urllib.parse.urlencode({'skus':self.sku,'servidor':'http://26.10.20.30:8080'}));self.assertEqual(status,200);self.assertTrue(raw.startswith(b'%PDF-'))
 def test_cloud_configuration_not_exposed_to_pt_and_device_authorization_tokens_private(self):
  actor=self.user();self.assertEqual(self.call('/api/pt/onedrive/configurar',{},actor)[0],403);self.configure()
  def fake(url,method='GET',data=None,token=None,**kw):
   if url.endswith('/devicecode'):return {'device_code':'secret-device','verification_uri':'https://microsoft.com/devicelogin','user_code':'DEMO1234','expires_in':900,'interval':5}
   if url.endswith('/token'):return {'access_token':'secret-access-token','refresh_token':'secret-refresh-token','expires_in':3600}
   return {'mail':'soportetecnico@grupomipan.com'}
  # Native DPAPI remains exercised on Windows; only network is replaced.
  with patch('pt_onedrive.request',side_effect=fake),patch.object(OneDrivePT,'kick'):
   r=self.value('/api/pt/onedrive/conectar',{});self.assertEqual(r['codigo'],'DEMO1234');self.assertNotIn('secret',json.dumps(r));self.assertTrue(self.value('/api/pt/onedrive/verificar',{})['conectado'])
  public=self.value('/api/pt/onedrive',actor=actor);self.assertNotIn('configuracion',public);self.assertNotIn('secret',json.dumps(self.value('/api/pt/onedrive')))
  with self.store.connect() as db:self.assertNotIn('secret-access-token',db.execute('SELECT secret FROM pt_cloud').fetchone()[0])
 def test_cloud_publication_failure_pending_then_retry_full_snapshot_without_double_rows(self):
  with patch.object(OneDrivePT,'kick'):
   self.enable();self.entry();calls=[]
   def publish(c,b,m,raw,old,token,*extra):
    with zipfile.ZipFile(io.BytesIO(raw)) as z:calls.append(z.read('xl/worksheets/sheet1.xml').count(b'<row'))
    if len(calls)==1:raise CloudError(503)
    return {'archivoId':'demo','etag':'v1','archivo':'PT_EJIDOS_'+m+'.xlsx','enlace':'https://onedrive.live.com/demo'}
   with patch.object(self.cloud,'access_token',return_value='test'),patch.object(self.cloud,'publish_file',side_effect=publish):
    self.cloud.process_once();state=self.value('/api/pt/onedrive')['publicaciones'][0];self.assertTrue(state['pendiente']);self.assertIn('503',state['error']);self.entry();self.cloud.process_once()
   state=self.value('/api/pt/onedrive')['publicaciones'][0];self.assertFalse(state['pendiente']);self.assertEqual(calls,[2,3]);self.assertEqual(len(self.value('/api/pt/ingresos')['ingresos']),2)
 def test_cloud_snapshot_new_capture_during_upload_remains_pending(self):
  with patch.object(OneDrivePT,'kick'):
   self.enable();self.entry()
   def publish(*args):self.entry();return {'archivoId':'demo','etag':'v1'}
   with patch.object(self.cloud,'access_token',return_value='test'),patch.object(self.cloud,'publish_file',side_effect=publish):self.cloud.process_once()
   with self.store.connect() as db:self.assertEqual(db.execute('SELECT revision,synced FROM pt_exports').fetchone(),(2,1))
 def test_external_workbook_edit_is_not_overwritten(self):
  calls=[]
  def remote(url,*args,**kwargs):
   calls.append(url)
   return {'id':'folder','folder':{}} if '/root:' in url else {'id':'file','eTag':'changed-outside'}
  _,config,_=self.cloud.read()
  with patch('pt_onedrive.request',side_effect=remote):
   with self.assertRaisesRegex(ValueError,'modificado fuera'):self.cloud.publish_file(config,'EJIDOS','2026-11',b'x',{'archivoId':'file','etag':'before'},'test')
  self.assertFalse(any('UploadSession' in u for u in calls))
 def test_cloud_creates_three_monthly_files_and_updates_with_etag_without_token_on_upload(self):
  _,config,_=self.cloud.read();calls=[];filename=[]
  def remote(url,method='GET',data=None,token=None,headers=None,**kw):
   calls.append((url,method,data,token,headers))
   if '/root:' in url:return {'id':'folder','folder':{}}
   if url.endswith('/createUploadSession'):
    if '/items/file-' in url:self.assertEqual(headers['If-Match'],'v1');self.assertEqual(data['item']['@microsoft.graph.conflictBehavior'],'replace')
    else:filename.append(url);self.assertEqual(data['item']['@microsoft.graph.conflictBehavior'],'fail')
    return {'uploadUrl':'https://test.up.1drv.com/upload'}
   if method=='PUT':
    self.assertIsNone(token);self.assertEqual(headers['Content-Range'],'bytes 0-2/3');return {'id':'file-'+str(len(filename)),'eTag':'v1','webUrl':'https://onedrive.live.com/example'}
   return {'id':'file','eTag':'v1'}
  with patch('pt_onedrive.request',side_effect=remote):
   for branch in ('EJIDOS','SAN PABLO','CUAUTITLAN'):
    saved=self.cloud.publish_file(config,branch,'2026-11',b'abc',{},'private-token');self.cloud.publish_file(config,branch,'2026-11',b'abc',saved,'private-token')
   self.cloud.publish_file(config,'EJIDOS','2026-12',b'abc',{},'private-token')
  self.assertEqual(len(filename),4);self.assertTrue(any('PT_SAN_PABLO_2026-11.xlsx' in u for u in filename));self.assertTrue(any('PT_EJIDOS_2026-12.xlsx' in u for u in filename))
 def test_native_token_encryption_roundtrip(self):
  raw=b'test-token-only';encrypted=crypt(raw);self.assertNotEqual(raw,encrypted);self.assertEqual(crypt(encrypted,True),raw)

 def folder_config(self,root):
  state=self.value('/api/pt/onedrive');return {'revision':state['revision'],'modo':'carpeta','directorio':str(root),'cliente':'','cuenta':'soportetecnico@grupomipan.com','carpetas':{b:b.replace(' ','_') for b in ('EJIDOS','SAN PABLO','CUAUTITLAN')},'habilitado':True}
 def test_folder_three_branches_month_files_cancellation_and_private_path(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'),patch('pt_onedrive.request',side_effect=AssertionError('No se debe llamar Microsoft')):
   root=pathlib.Path(folder);state=self.value('/api/pt/onedrive/configurar',self.folder_config(root));self.assertTrue(state['conectado']);self.assertEqual(state['modo'],'carpeta')
   entries=[]
   with patch('pt.now',return_value='2026-11-30T23:59:59-06:00'):
    for branch in ('EJIDOS','SAN PABLO','CUAUTITLAN'):entries.append(self.entry(sucursal=branch)['ingreso']);self.cloud.process_once()
   self.assertEqual(len(list(root.rglob('*.xlsx'))),3)
   self.value('/api/pt/cancelar',{'id':entries[0]['id'],'revision':1});self.cloud.process_once()
   with zipfile.ZipFile(root/'EJIDOS/PT_EJIDOS_2026-11.xlsx') as archive:self.assertIn(b'REGISTRO ENTRADA',archive.read('xl/workbook.xml'));self.assertIn(b'<c r="E2"><v>0</v></c>',archive.read('xl/worksheets/sheet1.xml'))
   with patch('pt.now',return_value='2026-12-01T00:00:01-06:00'):self.entry();self.cloud.process_once()
   self.assertEqual(len(list(root.rglob('*.xlsx'))),4);self.assertTrue(all(j['estado']=='GUARDADO_EN_CARPETA' for j in self.value('/api/pt/onedrive')['publicaciones']))
   pt=self.user();public=self.value('/api/pt/onedrive',actor=pt);self.assertNotIn(folder,json.dumps(public));self.assertNotIn('configuracion',public);self.assertEqual(self.call('/api/pt/onedrive/probar-carpeta',{},pt)[0],403)
 def test_folder_unavailable_keeps_capture_then_retries_without_duplicate(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   root=pathlib.Path(folder)/'pc-apagada';self.value('/api/pt/onedrive/configurar',self.folder_config(root));self.entry();self.cloud.process_once();job=self.value('/api/pt/onedrive')['publicaciones'][0];self.assertTrue(job['pendiente']);self.assertIn('carpeta',job['error'])
   root.mkdir();self.value('/api/pt/onedrive/publicar',{});self.cloud.process_once();self.assertFalse(self.value('/api/pt/onedrive')['publicaciones'][0]['pendiente']);self.assertEqual(len(self.value('/api/pt/ingresos')['ingresos']),1);self.assertEqual(len(list(root.rglob('*.xlsx'))),1)
 def test_folder_external_edit_and_destination_change_do_not_overwrite(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   root=pathlib.Path(folder);self.value('/api/pt/onedrive/configurar',self.folder_config(root));self.entry();self.cloud.process_once();target=next(root.rglob('*.xlsx'));target.write_bytes(b'edicion fuera de GMP');self.entry();self.cloud.process_once();self.assertEqual(target.read_bytes(),b'edicion fuera de GMP');self.assertTrue(self.value('/api/pt/onedrive')['publicaciones'][0]['pendiente'])
   data=self.folder_config(root/'nuevo');self.assertEqual(self.call('/api/pt/onedrive/configurar',data)[0],400)
 def test_folder_locked_file_leaves_previous_excel_intact_and_cleans_temp(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   root=pathlib.Path(folder);self.value('/api/pt/onedrive/configurar',self.folder_config(root));self.entry();self.cloud.process_once();target=next(root.rglob('*.xlsx'));previous=target.read_bytes();self.entry()
   with patch('pt_folder.os.replace',side_effect=PermissionError('archivo abierto')):self.cloud.process_once()
   self.assertEqual(target.read_bytes(),previous);self.assertFalse(list(root.rglob('*.tmp')));self.assertTrue(self.value('/api/pt/onedrive')['publicaciones'][0]['pendiente']);self.value('/api/pt/onedrive/publicar',{});self.cloud.process_once();self.assertFalse(self.value('/api/pt/onedrive')['publicaciones'][0]['pendiente'])
 def test_folder_probe_is_async_and_does_not_confirm_cloud(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   self.value('/api/pt/onedrive/configurar',self.folder_config(folder));release=threading.Event()
   def blocking(config):release.wait(4)
   with patch('pt_onedrive.probe_folder',side_effect=blocking):
    self.value('/api/pt/onedrive/probar-carpeta',{});self.assertEqual(self.value('/api/pt/onedrive')['configuracion']['pruebaCarpeta']['estado'],'PROBANDO');release.set()
    for _ in range(50):
     state=self.value('/api/pt/onedrive')['configuracion']['pruebaCarpeta']
     if state['estado']!='PROBANDO':break
     time.sleep(.02)
    self.assertEqual(state['estado'],'CARPETA_VERIFICADA')
   self.assertFalse(list(pathlib.Path(folder).iterdir()))
 def test_folder_config_change_invalidates_inflight_probe_and_allows_retry(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   self.value('/api/pt/onedrive/configurar',self.folder_config(folder));release=threading.Event();completed=threading.Event()
   def blocking(config):release.wait(4);completed.set()
   with patch('pt_onedrive.probe_folder',side_effect=blocking):
    self.value('/api/pt/onedrive/probar-carpeta',{});data=self.folder_config(folder);data['habilitado']=False;self.value('/api/pt/onedrive/configurar',data);self.assertNotIn('pruebaCarpeta',self.value('/api/pt/onedrive')['configuracion']);release.set();completed.wait(4);self.value('/api/pt/onedrive/probar-carpeta',{})
    for _ in range(50):
     state=self.value('/api/pt/onedrive')['configuracion'].get('pruebaCarpeta',{})
     if state.get('estado')=='CARPETA_VERIFICADA':break
     time.sleep(.02)
    self.assertEqual(state['estado'],'CARPETA_VERIFICADA')
 def test_folder_paths_and_config_permissions(self):
  from pt_folder import validate_root,probe_folder,publish_folder
  for value in ('carpeta','https://onedrive.live.com/carpeta',str(pathlib.Path.cwd().anchor),'C:\\data\\..\\otra','C:\\datos:alterno'):
   with self.assertRaises(ValueError):validate_root(value)
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   data=self.folder_config(folder);pt=self.user();self.assertEqual(self.call('/api/pt/onedrive/configurar',data,pt)[0],403);data['carpetas']['EJIDOS']='CON';self.assertEqual(self.call('/api/pt/onedrive/configurar',data)[0],400);probe_folder({'directorio':folder});self.assertFalse(list(pathlib.Path(folder).iterdir()))
 def test_folder_same_snapshot_recovery_without_replacing_existing_file(self):
  from pt_folder import publish_folder
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   self.entry();_,config,_=self.cloud.read();config.update({'directorio':folder,'modo':'carpeta'});actor={'role':'superadmin','email':'test','modulos':['pt']};raw=self.pt.workbook(actor,{'sucursal':'EJIDOS'});first=publish_folder(config,'EJIDOS','2026-11',raw,{})
   with patch('pt_folder.os.replace',side_effect=AssertionError('No debe reemplazar')):second=publish_folder(config,'EJIDOS','2026-11',raw,{})
   self.assertEqual(first['firma'],second['firma']);self.assertEqual(len(list(pathlib.Path(folder).rglob('*.xlsx'))),1)

 def registry_entry(self,folio='LEGACY-1',quantity='2',state='REGISTRADO'):
  return {'folio':folio,'sku':self.sku,'fecha':'2026-11-09T10:00:00-06:00','descripcion':'PRODUCTO DE PRUEBA','unidad':'PIEZA','cantidad':quantity,'estado':state}
 def test_registry_export_has_one_row_per_capture_and_def_columns(self):
  from pt_registro import new_workbook
  entries=[self.registry_entry('PT-EJI-0000001','3'),self.registry_entry('PT-EJI-0000002','7')]
  with zipfile.ZipFile(io.BytesIO(new_workbook(entries))) as z:
   xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('REGISTRO ENTRADA',z.read('xl/workbook.xml').decode());self.assertIn('r="D1"',xml);self.assertIn('PRODUCTO',xml);self.assertIn('<c r="E2"><v>3</v></c>',xml);self.assertIn('<c r="E3"><v>7</v></c>',xml);self.assertNotIn(self.sku,xml)
 def test_existing_registry_preserves_original_cells_and_retries_without_duplicate(self):
  from pt_registro import new_workbook,merge_workbook
  entry=self.registry_entry('PT-EJI-0000001','6');base=new_workbook([self.registry_entry()]);once=merge_workbook(base,[entry],'2026-11');twice=merge_workbook(once,[entry],'2026-11');cancelled=merge_workbook(twice,[{**entry,'estado':'CANCELADO'}],'2026-11')
  with zipfile.ZipFile(io.BytesIO(base)) as a,zipfile.ZipFile(io.BytesIO(twice)) as b,zipfile.ZipFile(io.BytesIO(cancelled)) as c:
   xml=b.read('xl/worksheets/sheet1.xml').decode();self.assertEqual(xml.count(entry['folio']),1);self.assertIn('<c r="E2"><v>2</v></c>',xml);self.assertIn('<c r="E3"><v>6</v></c>',xml);self.assertIn('<c r="E3"><v>0</v></c>',c.read('xl/worksheets/sheet1.xml').decode());self.assertEqual(a.read('xl/styles.xml'),b.read('xl/styles.xml'));self.assertEqual(a.read('xl/_rels/workbook.xml.rels'),b.read('xl/_rels/workbook.xml.rels'))
 def test_registry_rejects_wrong_headers_month_or_folio_product(self):
  from pt_registro import new_workbook,merge_workbook
  base=new_workbook([self.registry_entry()]);entry=self.registry_entry('PT-EJI-0000001')
  with self.assertRaisesRegex(ValueError,'otro mes'):merge_workbook(base,[entry],'2026-12')
  with self.assertRaisesRegex(ValueError,'mismo producto'):merge_workbook(new_workbook([entry]),[{**entry,'descripcion':'OTRO'}],'2026-11')
  bad=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(base)) as src,zipfile.ZipFile(bad,'w') as dest:
   for name in src.namelist():dest.writestr(name,src.read(name).replace(b'>UOM<',b'>CANTIDAD<') if name.endswith('sheet1.xml') else src.read(name))
  with self.assertRaisesRegex(ValueError,'Encabezados'):merge_workbook(bad.getvalue(),[entry],'2026-11')
 def test_registry_formula_translation_preserves_literals_and_merge_ranges(self):
  from pt_registro import new_workbook,merge_workbook,shift_formula
  self.assertEqual(shift_formula('IF($D2="A2",E2*2+$A$2+SUM(A2:A3),0)',3),'IF($D5="A2",E5*2+$A$2+SUM(A5:A6),0)')
  base=new_workbook([self.registry_entry()]);out=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(base)) as src,zipfile.ZipFile(out,'w') as dest:
   for name in src.namelist():
    raw=src.read(name)
    if name.endswith('sheet1.xml'):raw=raw.replace(b'</row></sheetData>',b'<c r="H2"><f>E2*2</f><v>4</v></c></row></sheetData>').replace(b'</worksheet>',b'<mergeCells count="1"><mergeCell ref="H1:I1"/></mergeCells></worksheet>')
    dest.writestr(name,raw)
  updated=merge_workbook(out.getvalue(),[self.registry_entry('PT-EJI-0000001')],'2026-11')
  with zipfile.ZipFile(io.BytesIO(updated)) as z:xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('ref="H1:I1"',xml);self.assertIn('<f>E3*2</f>',xml)
 def test_existing_book_publication_has_original_backup_and_rejects_external_change(self):
  from pt_registro import new_workbook
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   root=pathlib.Path(folder);target=root/'EJIDOS/PT_EJIDOS_2026-11.xlsx';target.parent.mkdir();base=new_workbook([self.registry_entry()]);target.write_bytes(base);data={**self.folder_config(root),'libroExistente':True};self.value('/api/pt/onedrive/configurar',data)
   with patch('pt.now',return_value='2026-11-09T11:00:00-06:00'):entry=self.entry()['ingreso'];self.cloud.process_once()
   self.assertFalse(self.value('/api/pt/onedrive')['publicaciones'][0]['pendiente']);status,backup,_=self.call('/api/pt/onedrive/libro-original?sucursal=EJIDOS&mes=2026-11');self.assertEqual(status,200);self.assertEqual(backup,base)
   pt=self.user();self.assertEqual(self.call('/api/pt/onedrive/libro-original?sucursal=EJIDOS&mes=2026-11',actor=pt)[0],403);data=self.folder_config(root);data['libroExistente']=False;self.assertEqual(self.call('/api/pt/onedrive/configurar',data)[0],400)
   self.value('/api/pt/cancelar',{'id':entry['id'],'revision':1});self.cloud.process_once()
   with zipfile.ZipFile(target) as z:self.assertIn(b'<c r="E3"><v>0</v></c>',z.read('xl/worksheets/sheet1.xml'))
   target.write_bytes(b'CAMBIO EXTERNO');self.entry();self.cloud.process_once();self.assertEqual(target.read_bytes(),b'CAMBIO EXTERNO')
 def test_existing_book_missing_target_keeps_capture_pending(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   self.value('/api/pt/onedrive/configurar',{**self.folder_config(folder),'libroExistente':True});self.entry();self.cloud.process_once();state=self.value('/api/pt/onedrive')['publicaciones'][0];self.assertTrue(state['pendiente']);self.assertIn('Prepara el libro',state['error']);self.assertEqual(len(self.value('/api/pt/ingresos')['ingresos']),1)

 def test_drive_file_picker_is_root_only_and_filters_to_folders_and_xlsx(self):
  pt=self.user()
  with patch.object(OneDrivePT,'kick'):
   self.enable()
   def remote(url,**kwargs):return {'value':[{'id':'folder','name':'Inventarios','folder':{}},{'id':'book','name':'Entradas.xlsx','file':{}},{'id':'doc','name':'Otra.docx','file':{}}]}
   with patch.object(self.cloud,'access_token',return_value='test'),patch('pt_onedrive.OneDrivePT.access_token',return_value='test'),patch('pt_onedrive.request',side_effect=remote):
    rows=self.value('/api/pt/onedrive/archivos')['elementos'];self.assertEqual([x['id'] for x in rows],['folder','book']);self.assertEqual(self.call('/api/pt/onedrive/archivos',actor=pt)[0],403)
 def test_drive_selected_book_is_updated_in_def_and_has_private_original_backup(self):
  from pt_registro import new_workbook
  pt=self.user();base=new_workbook([]);uploaded=[]
  with patch.object(OneDrivePT,'kick'):
   self.enable()
   def remote(url,method='GET',data=None,token=None,headers=None,**kwargs):
    if url.endswith('/createUploadSession'):
     self.assertEqual(headers['If-Match'],'v1');return {'uploadUrl':'https://test.up.1drv.com/upload'}
    if method=='PUT':uploaded.append(data);self.assertIsNone(token);return {'id':'book','eTag':'v2','webUrl':'https://onedrive.live.com/book'}
    return {'id':'book','name':'Inventario.xlsx','file':{},'eTag':'v1','@microsoft.graph.downloadUrl':'https://test.files.1drv.com/source'}
   with patch('pt_onedrive.OneDrivePT.access_token',return_value='test'),patch('pt_onedrive.request',side_effect=remote),patch('pt_onedrive.download_file',side_effect=lambda url:uploaded[-1] if uploaded else base):
    state=self.value('/api/pt/onedrive');selected=self.value('/api/pt/onedrive/seleccionar-archivo',{'revision':state['revision'],'sucursal':'EJIDOS','mes':'2026-11','archivoId':'book'});self.assertEqual(selected['configuracion']['archivosPorSucursal']['EJIDOS']['2026-11']['id'],'book')
    with patch('pt.now',return_value='2026-11-09T12:00:00-06:00'):entry=self.entry()['ingreso'];self.cloud.process_once()
    self.assertEqual(len(uploaded),1)
    with zipfile.ZipFile(io.BytesIO(uploaded[0])) as z:xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('PRODUCTO DE PRUEBA',xml);self.assertIn('<c r="E2"><v>3</v></c>',xml);self.assertNotIn(self.sku,xml)
    self.assertEqual(self.call('/api/pt/onedrive/libro-original?sucursal=EJIDOS&mes=2026-11')[1],base);self.assertEqual(self.call('/api/pt/onedrive/libro-original?sucursal=EJIDOS&mes=2026-11',actor=pt)[0],403)
    state=self.value('/api/pt/onedrive');self.assertEqual(self.call('/api/pt/onedrive/seleccionar-archivo',{'revision':state['revision'],'sucursal':'SAN PABLO','mes':'2026-11','archivoId':'book'})[0],400)
    self.value('/api/pt/cancelar',{'id':entry['id'],'revision':1});self.cloud.process_once();self.assertEqual(len(uploaded),2)
    with zipfile.ZipFile(io.BytesIO(uploaded[-1])) as z:self.assertIn(b'<c r="E2"><v>0</v></c>',z.read('xl/worksheets/sheet1.xml'))
 def test_drive_download_rejects_non_microsoft_or_insecure_destinations(self):
  from pt_onedrive import download_file
  for url in ('http://test.files.1drv.com/a','https://example.test/a','https://user:pass@test.files.1drv.com/a','https://127.0.0.1/a'):
   with self.assertRaises(ValueError):download_file(url)

 def test_provider_switch_preserves_existing_files_and_requires_explicit_selection(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(OneDrivePT,'kick'):
   self.value('/api/pt/onedrive/configurar',self.folder_config(folder));self.entry();self.cloud.process_once();target=next(pathlib.Path(folder).rglob('*.xlsx'));previous=target.read_bytes();state=self.value('/api/pt/onedrive');data={'revision':state['revision'],'modo':'microsoft','cliente':'11111111-1111-1111-1111-111111111111','cuenta':'soportetecnico@grupomipan.com','carpetas':{b:b.replace(' ','_') for b in ('EJIDOS','SAN PABLO','CUAUTITLAN')},'habilitado':True};self.assertEqual(self.call('/api/pt/onedrive/configurar',data)[0],400);data['habilitado']=False;result=self.value('/api/pt/onedrive/configurar',data);self.assertFalse(result['conectado']);self.assertTrue(result['configuracion']['seleccionarLibros']);self.assertEqual(target.read_bytes(),previous);self.assertEqual(len(self.value('/api/pt/ingresos')['ingresos']),1)

 def test_registry_accepts_recalculated_caches_but_rejects_edited_gmp_quantity(self):
  from pt_registro import new_workbook,merge_workbook
  entry=self.registry_entry('PT-EJI-0000001','3');base=new_workbook([entry]);out=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(base)) as src,zipfile.ZipFile(out,'w') as dest:
   for name in src.namelist():dest.writestr(name,src.read(name))
   dest.writestr('docProps/test-autosave.xml','<modified>Excel recalculated</modified>')
  later=self.registry_entry('PT-EJI-0000002','4');expected={entry['folio']:'3'};merged=merge_workbook(out.getvalue(),[entry,later],'2026-11',expected)
  with zipfile.ZipFile(io.BytesIO(merged)) as z:self.assertIn('docProps/test-autosave.xml',z.namelist());self.assertEqual(z.read('xl/worksheets/sheet1.xml').count(entry['folio'].encode()),1)
  bad=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(base)) as src,zipfile.ZipFile(bad,'w') as dest:
   for name in src.namelist():dest.writestr(name,src.read(name).replace(b'<c r="E2"><v>3</v></c>',b'<c r="E2"><v>99</v></c>') if name.endswith('sheet1.xml') else src.read(name))
  with self.assertRaisesRegex(ValueError,'modificada fuera'):merge_workbook(bad.getvalue(),[entry,later],'2026-11',expected)
  textqty=io.BytesIO()
  with zipfile.ZipFile(io.BytesIO(base)) as src,zipfile.ZipFile(textqty,'w') as dest:
   for name in src.namelist():dest.writestr(name,src.read(name).replace(b'<c r="E2"><v>3</v></c>',b'<c r="E2" t="inlineStr"><is><t>3</t></is></c>') if name.endswith('sheet1.xml') else src.read(name))
  with self.assertRaisesRegex(ValueError,'modificada fuera'):merge_workbook(textqty.getvalue(),[entry,later],'2026-11',expected)

 def test_publication_queue_does_not_starve_branches_under_continuous_capture(self):
  seen=[]
  with patch.object(OneDrivePT,'kick'):
   self.enable()
   for branch in ('EJIDOS','SAN PABLO','CUAUTITLAN'):self.entry(sucursal=branch)
   def publish(config,branch,month,raw,old,token,*extra):seen.append(branch);self.entry(sucursal='CUAUTITLAN');return {'archivoId':branch,'etag':'v1'}
   with patch.object(self.cloud,'access_token',return_value='test'),patch.object(self.cloud,'publish_file',side_effect=publish):
    for _ in range(3):self.cloud.process_once()
  self.assertEqual(set(seen),{'EJIDOS','SAN PABLO','CUAUTITLAN'})

for name in dir(fixture.CommercialTests):
 if name.startswith('test_') and name not in PTTests.__dict__:setattr(PTTests,name,None)
