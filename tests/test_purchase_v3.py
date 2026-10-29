import base64,copy,io,json,uuid,zipfile
from unittest.mock import patch,MagicMock
import test_backup_import as fixtures
from pedidos_compra_vendors import HEADERS
from app_info import SUPPORT_LINE

class PurchaseV3Tests(fixtures.ModuleBackupTests):
 def setUp(self):
  super().setUp();self.company=self.value('/api/comercial/empresas',{'nombre':'EMPRESA COMPRAS DEMO','rfc':'DEMO','domicilio':'Domicilio demo','sucursales':['EJIDOS','SAN PABLO']})['id'];email='compras@example.test';self.value('/api/users',{'email':email,'name':'Compras demo','role':'compras','password':self.password,'active':True,'sucursales':['EJIDOS'],'almacenes':['EJIDOS']});self.po('accesos',{'email':email,'revision':0,'empresas':[self.company],'sucursales':['EJIDOS']});self.buyer=self.login(email);self.vendor=self.po('proveedores',{'empresa':self.company,'nombre':'PROVEEDOR DEMO','correo':'vendor@example.test'})['id'];self.value('/api/requisiciones/maestro',{'archivo':'PRUEBA.xlsx','contenido':fixtures.workbook([fixtures.product('INSUMO DEMO',B='INPO0101DEM000',V='0.08')],headers={**fixtures.HEADERS,'V':'IMPUESTO'})});self.material=self.po('materiales')['materiales'][0]
 def po(self,path,data=None,actor=None,extra=''):
  return self.value('/api/pedidoscompra/'+path+(f'?empresa={self.company}&sucursal=EJIDOS'+extra if data is None else ''),None if data is None else {'empresa':self.company,'sucursal':'EJIDOS',**data},actor)
 def order(self,**overrides):
  payload={'proveedor':self.vendor,'clave':uuid.uuid4().hex,'fechaPedido':'2026-10-28','fechaEntrega':'2026-11-02','partidas':[{'materialId':self.material['materialId'],'cantidad':'2','tipoUnidad':'COMPRA','precio':'100','impuesto':'8'}],**overrides};return self.po('pedidos',payload,self.buyer)['documento']
 def confirm(self,doc):return self.po('accion',{'id':doc['id'],'revision':doc['revision'],'accion':'confirmar'},self.buyer)['documento']
 def move(self,doc,qty,kind='recepcion',**fields):return self.po(kind,{'id':doc['id'],'revision':doc['revision'],'clave':uuid.uuid4().hex,'partidas':[{'linea':'1','cantidad':qty}],**fields},self.buyer)
 def test_roles_company_scope_and_four_series_editors(self):
  self.assertIn('pedidoscompra',self.value('/api/me')['user']['modulos']);self.assertTrue(self.po('meta')['puedeCapturar']);created=self.po('pedidos',{'proveedor':self.vendor,'clave':uuid.uuid4().hex,'partidas':[{'materialId':self.material['materialId'],'cantidad':'1','tipoUnidad':'COMPRA','precio':'100','impuesto':'0'}]});self.assertEqual(created['documento']['creador'],'sistemas@grupomipan.com')
  other=self.value('/api/comercial/empresas',{'nombre':'OTRA','sucursales':['EJIDOS']})['id'];self.assertEqual(self.call('/api/pedidoscompra/proveedores?empresa='+str(other),actor=self.buyer)[0],403)
  for role in ('gerente','auxti'):
   email=role+'@example.test';self.value('/api/users',{'email':email,'name':role,'role':role,'password':self.password,'active':True,'sucursales':list(fixtures.requisiciones.BRANCHES) if role=='gerente' else ['EJIDOS']});self.po('accesos',{'email':email,'revision':0,'empresas':[self.company],'sucursales':['EJIDOS']});actor=self.login(email);s=self.po('series',actor=actor)['series'][0];self.po('series',{'tipo':s['tipo'],'revision':s['revision'],'serie':s['serie'],'siguiente':s['siguiente']+1},actor)
 def test_master_purchase_delivery_conversion_and_partial_receipt_bill(self):
  self.assertEqual(self.material['unidadCompra'],'BOLSA 10 KG');self.assertEqual(self.material['unidadEntrega'],'KILO');self.assertEqual(self.material['factor'],'10');self.assertEqual(self.material['impuesto'],'8');doc=self.confirm(self.order());self.assertEqual(doc['partidas'][0]['cantidadEntrega'],'20');self.assertEqual(doc['total'],'216.00')
  bad={'empresa':self.company,'sucursal':'EJIDOS','id':doc['id'],'revision':doc['revision'],'clave':uuid.uuid4().hex,'partidas':[{'linea':'1','cantidad':'1'}]};self.assertEqual(self.call('/api/pedidoscompra/compra',bad,self.buyer)[0],400)
  result=self.move(doc,'1');doc=result['documento'];self.assertEqual(doc['estado'],'RECEPCION_PARCIAL');self.assertEqual(result['movimiento']['partidas'][0]['cantidadEntrega'],'10');doc=self.move(doc,'1','compra',referencia='FACT-1')['documento'];self.assertEqual(doc['partidas'][0]['comprado'],'1');doc=self.move(doc,'1')['documento'];self.assertEqual(doc['estado'],'RECIBIDO');doc=self.move(doc,'1','compra',referencia='FACT-2')['documento'];self.assertEqual(doc['estado'],'COMPRADO')
  self.assertEqual(self.call('/api/pedidoscompra/accion',{'id':doc['id'],'revision':doc['revision'],'accion':'cancelar','motivo':'Error'},self.buyer)[0],400)
 def test_requisition_link_no_overorder_and_no_cost_leak(self):
  req=self.create_req('20');line={'materialId':self.material['materialId'],'cantidad':'1','tipoUnidad':'COMPRA','precio':'100','impuesto':'0','requisicionId':req['id']};doc=self.order(partidas=[line]);self.assertEqual(doc['partidas'][0]['requisicionNumero'],req['numero']);self.order(partidas=[line]);self.assertEqual(self.call('/api/pedidoscompra/pedidos',{'empresa':self.company,'sucursal':'EJIDOS','proveedor':self.vendor,'clave':uuid.uuid4().hex,'partidas':[line]},self.buyer)[0],400)
  links=self.value('/api/requisiciones/'+req['id']+'/pedidos-compra');self.assertEqual(len(links['pedidos']),2);self.assertNotIn('precio',json.dumps(links));self.assertNotIn('total',json.dumps(links));doc=self.confirm(doc);doc=self.move(doc,'1')['documento'];self.assertEqual(self.value('/api/requisiciones/'+req['id'])['estado'],'SOLICITADA')
 def test_personalized_sequences_idempotency_and_reservations(self):
  s=next(s for s in self.po('series')['series'] if s['tipo']=='PEDIDO');self.po('series',{'tipo':'PEDIDO','revision':s['revision'],'serie':'OC-DEMO','siguiente':500},self.buyer);doc=self.confirm(self.order());self.assertEqual(doc['folio'],'OC-DEMO-000500');s=next(s for s in self.po('series')['series'] if s['tipo']=='PEDIDO');self.assertEqual(self.call('/api/pedidoscompra/series',{'empresa':self.company,'sucursal':'EJIDOS','tipo':'PEDIDO','revision':s['revision'],'serie':'OC-DEMO','siguiente':500},self.buyer)[0],400)
  key=uuid.uuid4().hex;data={'id':doc['id'],'revision':doc['revision'],'clave':key,'partidas':[{'linea':'1','cantidad':'1'}]};one=self.po('recepcion',data,self.buyer);two=self.po('recepcion',data,self.buyer);self.assertEqual(one['movimiento']['id'],two['movimiento']['id'])
 def test_vendor_layout_import_and_existing_update(self):
  status,raw,_=self.call('/api/pedidoscompra/proveedores/layout');self.assertEqual(status,200)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertIsNone(z.testzip())
  text=';'.join(HEADERS)+'\n;NUEVO;;nuevo@example.test;Contacto;001122;Domicilio;;Contado;SI';data={'contenido':base64.b64encode(text.encode()).decode()};review=self.po('proveedores/importar',{**data,'revisar':True},self.buyer);self.assertEqual(review['nuevos'],1);self.assertEqual(len(self.po('proveedores')['proveedores']),1);self.po('proveedores/importar',{**data,'huellaActual':review['huellaActual']},self.buyer);self.assertEqual(len(self.po('proveedores')['proveedores']),2)
 def test_long_notes_a4_pdf_no_support_credit_and_report(self):
  notes=('Certificado de calidad y observaciones de entrega. '*1200);terms='Condiciones de compra. '*200;doc=self.confirm(self.order(observaciones=notes,condiciones=terms,referenciaProveedor='REF OPCIONAL'));self.assertGreater(len(doc['observaciones']),50000);self.assertGreater(len(doc['condiciones']),3000);status,pdf,_=self.call('/api/pedidoscompra/documento/pdf?id='+doc['id']);self.assertEqual(status,200);self.assertTrue(pdf.startswith(b'%PDF-'));self.assertEqual(self.call('/api/pedidoscompra/documento/pdf?id='+doc['id']+'&formato=ticket')[0],400)
  result=self.po('reportes');self.assertEqual(next(s for s in result['sucursales'] if s['sucursal']=='EJIDOS')['emitidas'],1);self.assertEqual(self.call('/api/pedidoscompra/reportes/excel?empresa='+str(self.company))[0],200)
 def test_detailed_report_partial_receipts_bills_and_filters(self):
  self.order();doc=self.confirm(self.order(observaciones='Observaciones de compra '*1800));doc=self.move(doc,'1')['documento'];self.move(doc,'0.5','compra',referencia='FACT-PARCIAL');result=self.po('reportes');summary=result['resumen'];self.assertEqual(summary['total'],'216.00');self.assertEqual(summary['importeRecibido'],'108.00');self.assertEqual(summary['importePendiente'],'108.00');self.assertEqual(summary['importeComprado'],'54.00');line=next(r for r in result['detalle'] if r['idPedido']==doc['id']);self.assertEqual(line['recibidoEntrega'],'10');self.assertEqual(line['pendiente'],'1');self.assertEqual(len(self.po('reportes',extra='&campoFecha=entrega&desde=2026-11-03')['pedidos']),0)
  status,raw,_=self.call('/api/pedidoscompra/reportes/excel?empresa='+str(self.company));self.assertEqual(status,200)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertEqual(len([n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]),5);self.assertIn('Observaciones (2)',z.read('xl/worksheets/sheet1.xml').decode());self.assertIn('FACT-PARCIAL',z.read('xl/worksheets/sheet3.xml').decode())
  status,raw,_=self.call('/api/pedidoscompra/reportes/pdf?empresa='+str(self.company));self.assertEqual(status,200);self.assertTrue(raw.startswith(b'%PDF-'))
 def test_smtp_explicit_send_mock_and_secret_not_exposed(self):
  self.po('smtp',{'revision':1,'host':'smtp.example.test','port':587,'seguridad':'STARTTLS','usuario':'test','password':'private-secret','remitente':'compras@example.test'});self.assertNotIn('private-secret',json.dumps(self.po('smtp')));doc=self.order();mock=MagicMock();mock.__enter__.return_value=mock
  with patch('pedidos_compra_vendors.smtplib.SMTP',return_value=mock):result=self.po('correo',{'id':doc['id'],'revision':doc['revision'],'clave':uuid.uuid4().hex,'destinatario':'vendor@example.test','asunto':'Pedido demo','mensaje':'Mensaje de prueba'},self.buyer)
  self.assertTrue(result['ok']);mock.send_message.assert_called_once();self.assertEqual(self.po('documento',extra='&id='+doc['id'])['estado'],'ENVIADO')
 def test_backup_restore_preserves_old_folios(self):
  initial=self.po('respaldo');doc=self.confirm(self.order());review=self.po('restaurar',{'respaldo':initial});self.po('restaurar',{'respaldo':initial,'huellaActual':review['huellaActual'],'aplicar':True});next_doc=self.confirm(self.order());self.assertNotEqual(next_doc['folio'],doc['folio'])

 def test_delivery_unit_uses_master_cost_conversion(self):
  doc=self.order(partidas=[{'materialId':self.material['materialId'],'cantidad':'20','tipoUnidad':'ENTREGA','impuesto':'8'}]);self.assertEqual(doc['partidas'][0]['precio'],'10');self.assertEqual(doc['partidas'][0]['cantidadEntrega'],'20');self.assertEqual(doc['total'],'216.00')
 def test_vendor_template_bulk_import_managers_only(self):
  from plantillas_import import VENDOR_HEADERS
  code=next(v['codigo'] for v in self.po('proveedores')['proveedores'] if v['id']==self.vendor);row=[code,'SEMANAL',self.material['sku'],str(self.material['materialId']),'2','COMPRA','100','8','Nota','Observaciones','Condiciones'];content=';'.join(VENDOR_HEADERS)+'\n'+';'.join(row);data={'contenido':base64.b64encode(content.encode()).decode()};review=self.po('plantillas/importar',{**data,'revisar':True});self.assertEqual(review['nuevas'],1);self.assertEqual(self.po('plantillas')['plantillas'],[]);self.po('plantillas/importar',{**data,'huellaActual':review['huellaActual']});tpl=self.po('plantillas')['plantillas'][0];self.assertEqual(tpl['partidas'][0]['tipoUnidad'],'COMPRA');self.assertEqual(len(self.po('plantillas',actor=self.buyer)['plantillas']),1);self.assertEqual(self.call('/api/pedidoscompra/plantillas',{'empresa':self.company,'nombre':'NO','proveedor':self.vendor,'partidas':[{'materialId':self.material['materialId'],'cantidad':'1'}]},self.buyer)[0],403)
  status,raw,_=self.call('/api/pedidoscompra/plantillas/layout');self.assertEqual(status,200);self.assertTrue(raw.startswith(b'PK'))

 def test_request_detail_includes_lines_and_blocks_wrong_branch(self):
  req=self.create_req('20');detail=self.po('requisicion',extra='&id='+req['id']);self.assertEqual(detail['requisicion']['numero'],req['numero']);self.assertEqual(detail['requisicion']['partidas'][0]['cantidad'],'20');self.assertEqual(self.call('/api/pedidoscompra/requisicion?empresa='+str(self.company)+'&sucursal=SAN%20PABLO&id='+req['id'])[0],403)
 def test_aux_and_warehouse_can_capture_but_warehouse_cannot_edit_series(self):
  for role in ('auxti','almacenista'):
   who=role+'@example.test';self.value('/api/users',{'email':who,'name':role,'role':role,'password':self.password,'active':True,'almacenes':['EJIDOS']});self.po('accesos',{'email':who,'revision':0,'empresas':[self.company],'sucursales':['EJIDOS']});actor=self.login(who);self.assertTrue(self.po('meta',actor=actor)['puedeCapturar']);created=self.po('pedidos',{'proveedor':self.vendor,'clave':uuid.uuid4().hex,'partidas':[{'materialId':self.material['materialId'],'cantidad':'1','tipoUnidad':'ENTREGA','precio':'10','impuesto':'8'}]},actor);self.assertEqual(created['documento']['creador'],who)
   if role=='almacenista':self.assertFalse(self.po('meta',actor=actor)['puedeSeries'])
 def test_purchase_tax_column_priority_existing_master_and_manual_override(self):
  headers={**fixtures.HEADERS,'J':'IMPUESTO DE COMPRA','AC':'IMPUESTO'}
  rows=[fixtures.product('CON IVA',B='TAX16',J='0.16',AC='002 - IVA'),fixtures.product('CON IEPS',B='TAX08',J='0.08',AC='003 - IEPS'),fixtures.product('SIN IVA',B='TAX00',J='0',AC='002 - IVA')]
  self.value('/api/requisiciones/maestro',{'archivo':'IMPUESTOS.xlsx','contenido':fixtures.workbook(rows,headers=headers)})
  # Simula la columna SAT que guardaron versiones anteriores. El Excel original se conserva.
  with self.store.connect() as db:
   for id,p in db.execute('SELECT id,payload FROM req_materials').fetchall():
    value=json.loads(p);value['impuestoCompra']='002 - IVA';db.execute('UPDATE req_materials SET payload=? WHERE id=?',(json.dumps(value),id))
  materials={m['sku']:m for m in self.po('materiales')['materiales']};self.assertEqual({sku:m['impuesto'] for sku,m in materials.items() if sku.startswith('TAX')},{'TAX16':'16','TAX08':'8','TAX00':'0'})
  for sku,tax in (('TAX16','16'),('TAX08','8'),('TAX00','0')):
   line={'materialId':materials[sku]['materialId'],'cantidad':'1','tipoUnidad':'COMPRA','precio':'100'};doc=self.order(partidas=[line]);self.assertEqual(doc['partidas'][0]['impuesto'],tax);override=self.order(partidas=[{**line,'impuesto':'0' if tax!='0' else '16'}]);self.assertEqual(override['partidas'][0]['impuesto'],'0' if tax!='0' else '16')

for name in fixtures.ModuleBackupTests.__dict__:
 if name.startswith('test_') and name not in PurchaseV3Tests.__dict__:setattr(PurchaseV3Tests,name,None)
