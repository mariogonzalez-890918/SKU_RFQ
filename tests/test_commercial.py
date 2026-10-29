import base64,json,sys,uuid,zipfile,io
import test_backup_import as fixtures
from test_backup_import import workbook
from comercial import CommercialStore,tax_line

HEADERS={'A':'SKU','B':'PRODUCTOS Y SERVICIOS','C':'CATEGORIA','D':'SUBCATEGORIA','E':'LINEA','F':'MODULO ID PDV','G':'EXPENDIO','H':'DESCRIPCION','I':'PRECIO DE VENTA PUERTA','J':'PRECIO DE VENTA EXPENDIO RUTA','K':'PRECIO DE VENTA EXPENDIO DESPACHO','N':'IMPUESTO','O':'UOM','S':'ESTATUS'}
SKU='PTPD05B0000000'
def master(price='116'):
 return workbook([{'A':SKU,'B':'PT','C':'PAN DULCE','D':'BIZCOCHO','F':'A01','G':'SI','H':'PRODUCTO DE PRUEBA','I':price,'J':price,'K':price,'N':'16%','O':'PIEZA','S':'ACTIVO'}],sheet='SUGERIDO',headers=HEADERS)

class CommercialTests(fixtures.ModuleBackupTests):
 # Reutiliza únicamente el entorno HTTP; las pruebas heredadas conservan su clase original.
 def setUp(self):
  super().setUp();self.company=self.value('/api/comercial/empresas',{'nombre':'EMPRESA DEMO','rfc':'RFC-PRUEBA','domicilio':'DOMICILIO FISCAL SECRETO','sucursales':['EJIDOS','SAN PABLO','CUAUTITLAN','EJE 8']})['id']
 def cm(self,path,data=None,actor=None,channel='ventasins'):
  return self.value('/api/comercial/'+path+(f'?canal={channel}&empresa={self.company}' if data is None else ''),None if data is None else {'canal':channel,**data},actor)
 def load_master(self,price='116'):
  return self.cm('maestro',{'empresas':[self.company],'archivo':'DEMO.xlsx','contenido':master(price)})
 def new_user(self,role,companies=None,branches=None,boxes=None):
  email=role+'@example.test';self.value('/api/users',{'email':email,'name':role,'role':role,'password':self.password,'active':True,'sucursales':['EJIDOS','SAN PABLO','CUAUTITLAN','EJE 8'] if role=='gerente' else [],'almacenes':[]})
  if role in ('auxti','gerente'):
   profiles=self.value('/api/perfiles')['perfiles'];p=next(p for p in profiles if p['perfil']==role);self.value('/api/perfiles',{'perfil':role,'revision':p['revision'],'modulos':list(dict.fromkeys(p['modulos']+['ventasins','expendios']))},method='PUT')
  if companies is not None:self.cm('accesos',{'email':email,'empresas':companies,'sucursales':branches or ['EJIDOS'],'cajas':boxes or [],'acciones':[],'revision':0})
  return self.login(email)
 def order(self,actor=None,**fields):
  return self.cm('pedidos',{'empresa':self.company,'sucursal':'EJIDOS','clave':uuid.uuid4().hex,'partidas':[{'sku':SKU,'cantidad':'2'}],**fields},actor)['documento']
 def sale(self,actor=None):
  box=self.cm('cajas',{'empresa':self.company,'sucursal':'EJIDOS','codigo':'CAJA1','nombre':'Caja demo','lista':'DESPACHO'},channel='expendios')['id'];session=self.cm('sesiones/abrir',{'empresa':self.company,'caja':box,'fondo':'100'},channel='expendios')
  data={'empresa':self.company,'sesion':session['id'],'clave':uuid.uuid4().hex,'partidas':[{'sku':SKU,'cantidad':'1','precio':'0.01'}],'metodo':'EFECTIVO','recibido':'120'}
  return self.cm('cobrar',data,channel='expendios')['documento'],data,box
 def test_company_crud_only_admins_and_conflicts(self):
  aux=self.new_user('auxti');company=self.cm('meta',actor=aux)['empresas'][0];self.cm('empresas',{'id':company['id'],'revision':company['revision'],'nombre':'EDITADA','sucursales':['CUAUTITLAN','EJE 8']},aux)
  self.assertEqual(self.cm('meta')['empresas'][0]['sucursales'],['CUAUTITLAN','EJE 8'])
  manager=self.new_user('gerente',[self.company]);self.assertEqual(self.call('/api/comercial/empresas',{'nombre':'NO','sucursales':['EJIDOS']},manager)[0],403)
  self.assertEqual(self.call('/api/comercial/empresas',{'id':self.company,'revision':1,'nombre':'ANTIGUA','sucursales':['EJIDOS']})[0],409)
 def test_scope_denies_unassigned_company_and_branch(self):
  self.load_master();user=self.new_user('ventasins',[],[]);self.assertEqual(self.call(f'/api/comercial/productos?canal=ventasins&empresa={self.company}',actor=user)[0],403)
  self.cm('accesos',{'email':'ventasins@example.test','empresas':[self.company],'sucursales':['SAN PABLO'],'cajas':[],'acciones':[],'revision':1});self.assertEqual(self.call('/api/comercial/pedidos',{'canal':'ventasins','empresa':self.company,'sucursal':'EJIDOS','clave':uuid.uuid4().hex,'partidas':[{'sku':SKU,'cantidad':'1'}]},user)[0],403)
 def test_import_preserves_customer_prices_and_skus(self):
  self.load_master();customer=self.cm('clientes',{'empresa':self.company,'nombre':'CLIENTE','codigo':'C1'})['id'];self.cm('precios',{'empresa':self.company,'sku':SKU,'lista':'PUBLICO','cliente':customer,'precio':'108'});self.load_master('232')
  doc=self.order(cliente=customer);self.assertEqual(doc['total'],'216.00');self.assertEqual(doc['partidas'][0]['sku'],SKU);self.assertEqual(self.order()['total'],'464.00')
 def test_order_idempotency_edit_confirm_cancel_and_folio(self):
  self.load_master();series=next(s for s in self.cm('folios')['series'] if s['tipo']=='PEDIDO');self.cm('folios',{'empresa':self.company,'tipo':'PEDIDO','revision':series['revision'],'serie':'INST','siguiente':150,'ancho':5})
  data={'empresa':self.company,'sucursal':'EJIDOS','clave':uuid.uuid4().hex,'partidas':[{'sku':SKU,'cantidad':'1'}]};a=self.cm('pedidos',data)['documento'];b=self.cm('pedidos',data)['documento'];self.assertEqual(a['id'],b['id'])
  edited=self.cm('pedidos',{**data,'id':a['id'],'revision':a['revision'],'tipo':'PEDIDO','partidas':[{'sku':SKU,'cantidad':'3'}]})['documento'];self.assertEqual(edited['folio'],'INST-00150');self.assertEqual(edited['presupuestoOrigen'],a['folio']);self.assertEqual(edited['total'],'348.00')
  edited=self.cm('pedidos/bloqueo',{'id':edited['id'],'revision':edited['revision'],'bloqueado':False})['documento']
  self.cm('pedidos/cancelar',{'id':edited['id'],'revision':edited['revision'],'motivo':'PRUEBA'});self.assertEqual(self.cm('documentos')['totales']['total'],'0.00')
 def test_pos_checkout_ignores_price_and_ticket_has_no_fiscal_data(self):
  self.load_master();doc,data,box=self.sale();self.assertEqual(doc['total'],'116.00');self.assertEqual(doc['pago']['cambio'],'4.00');self.assertEqual(self.cm('cobrar',data,channel='expendios')['documento']['id'],doc['id'])
  status,body,_=self.call('/api/comercial/imprimir?canal=expendios&id='+doc['id']);self.assertEqual(status,200);self.assertIn(b'EJIDOS',body);self.assertIn(b'/logo.png',body);self.assertNotIn(b'EMPRESA DEMO',body);self.assertNotIn(b'RFC-PRUEBA',body);self.assertNotIn(b'DOMICILIO FISCAL',body)
 def test_pos_cancel_only_aux_and_admin_cash_refund_separate(self):
  self.load_master();doc,data,box=self.sale();pending=self.cm('cancelaciones',{'id':doc['id'],'revision':doc['revision'],'motivo':'DEVOLUCION'},channel='expendios')['solicitud'];manager=self.new_user('gerente',[self.company],boxes=[box])
  decision={'canal':'expendios','id':pending['id'],'revision':1,'aprobar':True};self.assertEqual(self.call('/api/comercial/cancelaciones/resolver',decision,manager)[0],403);self.cm('cancelaciones/resolver',decision,channel='expendios')
  session=self.cm('sesiones',channel='expendios')['sesiones'][0];self.assertEqual(session['efectivoEsperado'],'216.00');cancelled=self.cm('documento',channel='expendios') if False else self.value('/api/comercial/documento?canal=expendios&id='+doc['id'])
  self.cm('reembolsar',{'id':doc['id'],'revision':cancelled['revision'],'sesion':data['sesion']},channel='expendios');self.assertEqual(self.cm('sesiones',channel='expendios')['sesiones'][0]['efectivoEsperado'],'100.00');self.assertEqual(self.cm('documentos',channel='expendios')['totales']['total'],'0.00')
 def test_tax_rates_extract_from_final_price(self):
  for rate,price in [('0','100'),('8','108'),('16','116')]:
   r=tax_line('1',price,rate);self.assertEqual(r['base'],'100.00');self.assertEqual(r['impuesto'],rate+'.00')
 def test_export_xlsx_uses_authorized_rows(self):
  self.load_master();self.order();raw=self.call('/api/comercial/exportar/xlsx',{'empresa':self.company})[1];self.assertTrue(raw.startswith(b'PK'))
  with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertIn('GRAN TOTAL',z.read('xl/worksheets/sheet1.xml').decode())
 def test_saved_reports_and_pdf_selection(self):
  self.load_master();doc=self.order();r=self.cm('reportes',{'empresa':self.company,'nombre':'PEDIDOS SEMANA','columnas':['folio','sku','total'],'filtros':{'estado':'PRESUPUESTO'}});saved=self.cm('reportes')['reportes'][0];self.assertEqual(saved['id'],r['id'])
  status,raw,_=self.call('/api/comercial/exportar/pdf',{'empresa':self.company,'columnas':['folio','sku','total'],'seleccion':[doc['id']]});self.assertEqual(status,200);self.assertTrue(raw.startswith(b'%PDF-'))
  self.assertEqual(self.call('/api/comercial/exportar/xlsx',{'empresa':self.company,'seleccion':['NO-AUTORIZADO']})[0],400)
 def test_source_interval_and_failure_preserve_master(self):
  from comercial_sync import INTERVAL
  from unittest.mock import patch
  self.assertEqual(INTERVAL,43200);self.load_master();source=self.cm('fuente');self.cm('fuente',{'url':'https://onedrive.live.com/download?test=demo','empresas':[self.company],'revision':source['revision'],'habilitada':True})
  service=self.http.RequestHandlerClass.commercial.sync
  with patch.object(service,'trigger') as trigger:
   service.tick();self.assertTrue(trigger.called)
  with self.store.connect() as db:db.execute('UPDATE cm_source SET state=?',(json.dumps({'ultimoIntento':__import__('time').time()}),))
  with patch.object(service,'trigger') as trigger:
   service.tick();trigger.assert_not_called()
  self.assertEqual(self.cm('productos')['productos'][0]['precios']['PUBLICO'],'116')
  self.assertEqual(self.call('/api/comercial/fuente',{'url':'http://127.0.0.1/private','empresas':[self.company],'revision':1})[0],400)
 def test_ticket_flags_and_deleted_company_keep_document(self):
  self.load_master();doc=self.order();co=self.cm('meta')['empresas'][0];self.cm('empresas/eliminar',{'id':co['id'],'revision':co['revision']});self.assertEqual(self.value('/api/comercial/documento?canal=ventasins&id='+doc['id'])['emisor']['nombre'],'EMPRESA DEMO')
  self.assertEqual(self.call('/api/comercial/pedidos',{'empresa':self.company,'sucursal':'EJIDOS','clave':uuid.uuid4().hex,'partidas':[{'sku':SKU,'cantidad':'1'}]})[0],400)
 def test_four_expendios_manual_company_assignment(self):
  second=self.cm('empresas',{'nombre':'SEGUNDA EMPRESA','sucursales':['SAN PABLO']})['id'];co=self.cm('meta')['empresas'];revisions={str(c['id']):c['revision'] for c in co}
  data={'sucursal':'EJIDOS','empresas':[second],'revisiones':revisions};aux=self.new_user('auxti');self.cm('sucursales/empresas',data,aux)
  updated={c['id']:c for c in self.cm('meta')['empresas']};self.assertNotIn('EJIDOS',updated[self.company]['sucursales']);self.assertIn('EJIDOS',updated[second]['sucursales']);self.assertEqual(len(self.cm('meta')['sucursales']),4)
  self.assertEqual(self.call('/api/comercial/sucursales/empresas',data)[0],409)
  manager=self.new_user('gerente',[second]);self.assertEqual(self.call('/api/comercial/sucursales/empresas',data,manager)[0],403)
 def test_pos_blocks_outdated_displayed_price_before_charging(self):
  self.load_master();doc,data,box=self.sale();data['clave']=uuid.uuid4().hex;data['partidas']=[{'sku':SKU,'cantidad':'1','precioVisto':'100','ivaVisto':'16'}]
  self.assertEqual(self.call('/api/comercial/cobrar',{'canal':'expendios',**data})[0],409);self.assertEqual(len(self.cm('documentos',channel='expendios')['documentos']),1)
 def test_commercial_backup_restore_keeps_folio_floor(self):
  self.load_master();doc=self.order();backup=self.value('/api/respaldos?modulo=comercial');review=self.value('/api/respaldos/restaurar/revisar',{'modulo':'comercial','respaldo':backup});self.value('/api/respaldos/restaurar/confirmar',{'modulo':'comercial','respaldo':backup,'huellaActual':review['huellaActual'],'confirmar':True})
  self.assertEqual(self.value('/api/comercial/documento?canal=ventasins&id='+doc['id'])['folio'],doc['folio']);new=self.order();self.assertNotEqual(new['folio'],doc['folio']);self.assertEqual(self.call('/api/respaldos/restaurar/revisar',{'modulo':'comercial','respaldo':backup})[0],409)
 def test_commercial_restore_rejects_foreign_references(self):
  import respaldos
  self.load_master();doc,data,box=self.sale();backup=self.value('/api/respaldos?modulo=comercial');table=backup['datos']['tablas']['cm_sessions'];table['filas'][0][table['columnas'].index('box')]='CAJA_INEXISTENTE';backup['checksum']=respaldos.digest({k:v for k,v in backup.items() if k!='checksum'})
  self.assertEqual(self.call('/api/respaldos/restaurar/revisar',{'modulo':'comercial','respaldo':backup})[0],400);self.assertEqual(self.call('/api/respaldos/vaciar/revisar',{'modulo':'comercial'})[0],400)

# No duplicar la batería de requisiciones heredada al descubrir esta clase.
for name in list(fixtures.ModuleBackupTests.__dict__):
 if name.startswith('test_') and name not in CommercialTests.__dict__:setattr(CommercialTests,name,None)
