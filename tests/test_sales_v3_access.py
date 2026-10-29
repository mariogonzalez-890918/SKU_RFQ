import base64,json,uuid
import test_commercial as fixture
from plantillas_import import CLIENT_HEADERS

class SalesV3Access(fixture.CommercialTests):
 def test_pasteleria_own_history_no_template_no_prices_override(self):
  self.load_master();past=self.new_user('ventaspasteleria',[self.company]);other=self.order();own=self.order(past,partidas=[{'sku':fixture.SKU,'cantidad':'1','precio':'0.01','descuento':'99'}],tipo='PEDIDO');self.assertEqual(own['total'],'116.00');self.assertTrue(own['bloqueado']);self.assertEqual(len(self.cm('documentos',actor=past)['documentos']),1);self.assertEqual(self.call('/api/comercial/documento?canal=ventasins&id='+other['id'],actor=past)[0],403)
  for path in ('plantillas','plantillas/layout','productos/catalogo','clientes/excel','reportes','precios','fuente'):
   self.assertEqual(self.call('/api/comercial/'+path+'?canal=ventasins&empresa='+str(self.company),actor=past)[0],403)
  self.assertEqual(self.call('/api/comercial/pedidos/bloqueo',{'id':own['id'],'revision':own['revision'],'bloqueado':False},past)[0],403);self.assertEqual(self.call('/api/comercial/pedidos/cancelar',{'id':own['id'],'revision':own['revision'],'motivo':'NO'},past)[0],403)
 def test_requested_cancellation_requires_manager_aux_or_owner_and_is_audited(self):
  self.load_master();past=self.new_user('ventaspasteleria',[self.company]);doc=self.order(past,tipo='PEDIDO');request=self.cm('pedidos/cancelacion/solicitar',{'id':doc['id'],'revision':doc['revision'],'motivo':'Cliente solicita cambio'},past)['solicitud'];self.assertEqual(self.cm('documentos')['totales']['total'],'232.00');self.assertEqual(self.call('/api/comercial/pedidos/cancelacion/resolver',{'id':request['id'],'revision':1,'aprobar':True},past)[0],403)
  manager=self.new_user('gerente',[self.company]);self.cm('pedidos/cancelacion/resolver',{'id':request['id'],'revision':1,'aprobar':True,'comentario':'Autorizado'},manager);updated=self.cm('documento',actor=past,channel='ventasins') if False else self.value('/api/comercial/documento?canal=ventasins&id='+doc['id'],actor=past);self.assertEqual(updated['estado'],'CANCELADO');self.assertEqual(updated['cancelacion']['solicitadoPor'],'ventaspasteleria@example.test');self.assertEqual(updated['cancelacion']['autor'],'gerente@example.test');self.assertEqual(self.cm('documentos')['totales']['total'],'0.00');self.assertEqual(self.cm('cancelaciones',channel='expendios')['solicitudes'],[]);self.value('/api/respaldos?modulo=comercial')
 def test_order_lock_and_client_template_management_restricted(self):
  self.load_master();sales=self.new_user('ventasins',[self.company]);doc=self.order(sales,tipo='PEDIDO');self.assertEqual(self.call('/api/comercial/pedidos',{'empresa':self.company,'sucursal':'EJIDOS','id':doc['id'],'revision':doc['revision'],'tipo':'PEDIDO','clave':uuid.uuid4().hex,'partidas':[{'sku':fixture.SKU,'cantidad':'1'}]},sales)[0],400);unlocked=self.cm('pedidos/bloqueo',{'id':doc['id'],'revision':doc['revision'],'bloqueado':False},sales)['documento'];self.assertFalse(unlocked['bloqueado'])
  data={'empresa':self.company,'nombre':'Plantilla','partidas':[{'sku':fixture.SKU,'cantidad':'2'}]};self.assertEqual(self.call('/api/comercial/plantillas',data,sales)[0],403);manager=self.new_user('gerente',[self.company]);self.cm('plantillas',data,manager);self.assertEqual(len(self.cm('plantillas',actor=sales)['plantillas']),1)
 def test_customer_template_excel_grouping_preview_and_duplicate_rejection(self):
  self.load_master();text=';'.join(CLIENT_HEADERS)+'\n;PLANTILLA GENERAL;'+fixture.SKU+';5;Nota;Condiciones';data={'empresa':self.company,'contenido':base64.b64encode(text.encode()).decode()};review=self.cm('plantillas/importar',{**data,'revisar':True});self.assertEqual(review['nuevas'],1);self.assertEqual(self.cm('plantillas')['plantillas'],[]);self.cm('plantillas/importar',{**data,'huellaActual':review['huellaActual']});self.assertEqual(self.cm('plantillas')['plantillas'][0]['partidas'][0]['cantidad'],'5');self.assertEqual(self.cm('plantillas/importar',{**data,'revisar':True})['omitidas'],1)
  duplicate={'empresa':self.company,'contenido':base64.b64encode((text+'\n'+text.split('\n')[1]).encode()).decode(),'revisar':True};self.assertEqual(self.call('/api/comercial/plantillas/importar',duplicate)[0],400)

 def test_observations_conditions_and_line_notes_are_exported(self):
  import io,zipfile
  self.load_master();doc=self.order(observaciones='OBSERVACION DEL PEDIDO',condiciones='CONDICIONES QA',partidas=[{'sku':fixture.SKU,'cantidad':'1','nota':'OBSERVACION DE PARTIDA'}]);status,raw,_=self.call('/api/comercial/documento/excel?canal=ventasins&id='+doc['id']);self.assertEqual(status,200)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   sheet=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('OBSERVACION DEL PEDIDO',sheet);self.assertIn('OBSERVACION DE PARTIDA',sheet);self.assertIn('CONDICIONES QA',sheet)
  printed=self.call('/api/comercial/imprimir?canal=ventasins&id='+doc['id'])[1].decode();self.assertIn('OBSERVACION DEL PEDIDO',printed);self.assertIn('OBSERVACION DE PARTIDA',printed)

for name in dir(fixture.CommercialTests):
 if name.startswith('test_') and name not in SalesV3Access.__dict__:setattr(SalesV3Access,name,None)
