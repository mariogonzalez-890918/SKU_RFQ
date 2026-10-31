import base64,json,uuid,io,zipfile
import test_backup_import as fixtures
from test_commercial import HEADERS,SKU

class CatalogTests(fixtures.ModuleBackupTests):
 def setUp(self):
  super().setUp();self.company=self.value('/api/comercial/empresas',{'nombre':'CATALOGO DEMO','sucursales':['EJIDOS']})['id']
 def cm(self,path,data=None,actor=None,channel='ventasins'):
  return self.value('/api/comercial/'+path+(f'?canal={channel}&empresa={self.company}' if data is None else ''),None if data is None else {'canal':channel,**data},actor)
 def csv(self,rows):return base64.b64encode(('NOMBRE;CANAL;CORREO;TELEFONO;ACTIVO\n'+rows).encode()).decode()
 def test_manual_product_shared_channels_and_sku_reservation(self):
  data={'empresa':self.company,'nombre':'PRODUCTO MANUAL DEMO','tipo':'PT','categoria':'PD','subcategoria':'05','unidad':'PIEZA','iva':'8','canales':['expendios'],'precios':{'RUTA':'10','DESPACHO':'12'}};r=self.cm('productos',data);sku=r['sku'];self.assertEqual(len(sku),14);self.assertEqual(self.cm('productos')['productos'],[]);self.assertEqual(self.cm('productos',channel='expendios')['productos'][0]['sku'],sku)
  self.assertIn(sku,[p['sku'] for p in self.value('/api/ventas')['state']['registros']]);p=self.cm('productos/catalogo')['productos'][0];data.update({'sku':sku,'skuOriginal':sku,'revision':p['revision'],'canales':['ventasins','expendios'],'precios':{'PUBLICO':'15','RUTA':'10','DESPACHO':'12'}});self.cm('productos',data);self.assertEqual(self.cm('productos')['productos'][0]['sku'],sku)
 def test_master_optional_prices_and_missing_tax_remain_pending(self):
  raw=fixtures.workbook([{'A':SKU,'B':'PT','C':'PAN DULCE','D':'BIZCOCHO','G':'NO','H':'SIN IVA','I':'10.000000000000002','O':'PIEZA','S':'ACTIVO'}],sheet='SUGERIDO',headers=HEADERS);r=self.cm('maestro',{'contenido':raw,'empresas':[self.company]});self.assertEqual(r['productos'],1);self.assertEqual(r['totalPendientes'],1);p=self.cm('productos/catalogo')['productos'][0];self.assertIsNone(p['iva']);self.assertEqual(p['precios'],{'PUBLICO':'10'})
  self.assertEqual(self.call('/api/comercial/pedidos',{'empresa':self.company,'sucursal':'EJIDOS','clave':uuid.uuid4().hex,'partidas':[{'sku':SKU,'cantidad':'1'}]})[0],400);self.value('/api/respaldos?modulo=comercial')
 def test_auto_client_import_preview_deduplicate_and_edit(self):
  data={'empresa':self.company,'contenido':self.csv('CLIENTE UNO;AMBOS;uno@example.test;0012345678;SI\nCLIENTE DOS;EXPENDIOS;;;SI')};review=self.cm('clientes/importar',{**data,'revisar':True});self.assertEqual(review['nuevos'],2);self.assertEqual(self.cm('clientes')['clientes'],[]);self.cm('clientes/importar',{**data,'huellaActual':review['huellaActual']});clients=self.cm('clientes',channel='expendios')['clientes'];self.assertEqual(len(clients),2);self.assertEqual(len({c['codigo'] for c in clients}),2);self.assertTrue(all(c['codigo'].startswith('CLI01-') for c in clients));self.assertEqual(self.cm('clientes/importar',{**data,'revisar':True})['omitidos'],2)
  one=self.cm('clientes')['clientes'][0];self.cm('clientes',{**one,'empresa':self.company,'nombre':'MODIFICADO','telefono':'00112233','activo':False});updated=self.cm('clientes')['clientes'][0];self.assertEqual(updated['codigo'],one['codigo']);self.assertFalse(updated['activo']);self.assertEqual(updated['telefono'],'00112233')
 def test_invalid_clients_rollback_and_export_preserves_phone_text(self):
  data={'empresa':self.company,'contenido':self.csv('CLIENTE UNO;AMBOS;mal_correo;;SI')};self.assertEqual(self.call('/api/comercial/clientes/importar',data)[0],400);self.assertEqual(self.cm('clientes')['clientes'],[])
  self.cm('clientes',{'empresa':self.company,'nombre':'TELEFONO','telefono':'00112233','canales':['ventasins']});status,raw,_=self.call('/api/comercial/clientes/excel?canal=ventasins&empresa='+str(self.company));self.assertEqual(status,200)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('00112233',xml);self.assertIn('CLI01-000001',xml)
  review=self.cm('clientes/importar',{'empresa':self.company,'contenido':base64.b64encode(raw).decode(),'revisar':True});self.assertEqual(review['omitidos'],1)
 def test_operator_can_edit_shared_client_but_cannot_change_other_channel(self):
  c=self.cm('clientes',{'empresa':self.company,'nombre':'COMPARTIDO','canales':['ventasins','expendios']})['id'];email='venta@example.test';self.value('/api/users',{'email':email,'name':'Venta','role':'ventasins','password':self.password,'active':True});self.cm('accesos',{'email':email,'revision':0,'empresas':[self.company],'sucursales':['EJIDOS'],'cajas':[],'acciones':[]});actor=self.login(email);client=self.cm('clientes',actor=actor)['clientes'][0];self.cm('clientes',{**client,'empresa':self.company,'correo':'nuevo@example.test'},actor);self.assertEqual(self.cm('clientes')['clientes'][0]['correo'],'nuevo@example.test')
 def test_ticket_only_session_no_fund_or_cash_receipts(self):
  p=self.cm('productos',{'empresa':self.company,'nombre':'TICKET DEMO','tipo':'PT','categoria':'PD','subcategoria':'05','unidad':'PIEZA','iva':'8','canales':['expendios'],'precios':{'DESPACHO':'10.8'}});box=self.cm('cajas',{'empresa':self.company,'sucursal':'EJIDOS','codigo':'T1','nombre':'Emisor','lista':'DESPACHO'},channel='expendios')['id'];session=self.cm('sesiones/abrir',{'empresa':self.company,'caja':box,'modo':'TICKETS'},channel='expendios');self.assertEqual(session['fondo'],'0.00')
  doc=self.cm('cobrar',{'empresa':self.company,'sesion':session['id'],'clave':uuid.uuid4().hex,'partidas':[{'sku':p['sku'],'cantidad':'1'}],'soloTicket':True},channel='expendios')['documento'];self.assertEqual(doc['estado'],'EMITIDA');self.assertEqual(doc['pago']['metodo'],'TICKET');s=self.cm('sesiones',channel='expendios')['sesiones'][0];self.assertEqual(s['cobrado'],'0.00');self.assertEqual(s['efectivoEsperado'],'0.00');ticket=self.call('/api/comercial/imprimir?canal=expendios&id='+doc['id'])[1];self.assertNotIn(b'Recibido $',ticket);self.assertIn(b'Descargar Excel',ticket);status,raw,_=self.call('/api/comercial/documento/excel?canal=expendios&id='+doc['id']);self.assertEqual(status,200);self.assertTrue(raw.startswith(b'PK')); self.cm('sesiones/cerrar',{'empresa':self.company,'sesion':s['id'],'revision':s['revision']},channel='expendios')

 def test_layouts_and_initial_master_are_available_and_idempotent(self):
  import hashlib
  for name in ('clientes','productos'):
   status,raw,_=self.call('/api/comercial/'+name+'/layout?canal=ventasins&empresa='+str(self.company));self.assertEqual(status,200);self.assertTrue(raw.startswith(b'PK'))
  raw=fixtures.workbook([{'A':SKU,'B':'PT','C':'PAN DULCE','D':'BIZCOCHO','G':'SI','H':'PRODUCTO INICIAL','I':'12','J':'11','K':'10','N':'8','O':'PIEZA','S':'ACTIVO','W':'EXPENDIOS'}],sheet='SUGERIDO',headers={**HEADERS,'W':'CANAL'})
  config={'configuradoPor':'sistemas@grupomipan.com','maestroInicial':{'contenido':raw,'sha256':hashlib.sha256(base64.b64decode(raw)).hexdigest(),'empresas':[self.company]}}
  with self.store.connect() as db:db.execute('UPDATE cm_source SET payload=? WHERE id=1',(json.dumps(config),))
  self.http.RequestHandlerClass.commercial.sync.apply_initial();self.assertEqual(self.cm('productos')['productos'],[]);self.assertEqual(len(self.cm('productos',channel='expendios')['productos']),1)
  with self.store.connect() as db:
   saved=json.loads(db.execute('SELECT payload FROM cm_source WHERE id=1').fetchone()[0]);revision=db.execute('SELECT revision FROM cm_products WHERE sku=?',(SKU,)).fetchone()[0]
  self.assertTrue(saved['maestroInicial']['aplicado']);self.assertNotIn('contenido',saved['maestroInicial']);self.http.RequestHandlerClass.commercial.sync.apply_initial()
  with self.store.connect() as db:self.assertEqual(db.execute('SELECT revision FROM cm_products WHERE sku=?',(SKU,)).fetchone()[0],revision)

for name in fixtures.ModuleBackupTests.__dict__:
 if name.startswith('test_') and name not in CatalogTests.__dict__:setattr(CatalogTests,name,None)
