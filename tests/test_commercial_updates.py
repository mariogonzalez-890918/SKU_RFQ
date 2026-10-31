import base64,json,uuid,io,zipfile
import test_commercial_catalogs as catalogs
from fechas import display_date,iso_date
from comercial import tax_line

class CommercialUpdates(catalogs.CatalogTests):
 def product(self,name='PRODUCTO DEMO',rate='8',price='108'):
  return self.cm('productos',{'empresa':self.company,'nombre':name,'tipo':'PT','categoria':'PD','subcategoria':'05','unidad':'PIEZA','iva':rate,'canales':['ventasins','expendios'],'precios':{'PUBLICO':price,'DESPACHO':price}})['sku']
 def test_box_filter_snapshot_saved_report_and_exports(self):
  sku=self.product();docs=[];boxes=[]
  for n in (1,2):
   box=self.cm('cajas',{'empresa':self.company,'sucursal':'EJIDOS','codigo':'B'+str(n),'nombre':'Emisor '+str(n),'lista':'DESPACHO'},channel='expendios')['id'];boxes.append(box);session=self.cm('sesiones/abrir',{'empresa':self.company,'caja':box,'modo':'TICKETS'},channel='expendios');docs.append(self.cm('cobrar',{'empresa':self.company,'sesion':session['id'],'clave':uuid.uuid4().hex,'partidas':[{'sku':sku,'cantidad':str(n)}],'soloTicket':True},channel='expendios')['documento'])
  self.cm('cajas',{'empresa':self.company,'id':boxes[0],'revision':1,'sucursal':'EJIDOS','codigo':'B1','nombre':'Nombre cambiado','lista':'DESPACHO'},channel='expendios')
  result=self.value('/api/comercial/documentos?canal=expendios&empresa='+str(self.company)+'&caja='+boxes[0]);self.assertEqual(len(result['documentos']),1);self.assertEqual(result['totales']['total'],'108.00');self.assertEqual(result['documentos'][0]['cajaNombre'],'Emisor 1')
  with self.store.connect() as db:
   v=json.loads(db.execute('SELECT payload FROM cm_documents WHERE id=?',(docs[1]['id'],)).fetchone()[0]);v.pop('cajaNombre');v.pop('cajaCodigo');db.execute('UPDATE cm_documents SET payload=? WHERE id=?',(json.dumps(v),docs[1]['id']))
  self.assertEqual(self.value('/api/comercial/documento?canal=expendios&id='+docs[1]['id'])['cajaNombre'],'Emisor 2')
  for ext in ('xlsx','csv','pdf'):
   status,raw,_=self.call('/api/comercial/exportar/'+ext,{'canal':'expendios','empresa':self.company,'columnas':['folio','caja','total'],'filtros':{'caja':boxes[0]}});self.assertEqual(status,200)
   if ext=='csv':self.assertIn('B1 · Emisor 1',raw.decode());self.assertNotIn('Emisor 2',raw.decode())
  self.cm('reportes',{'empresa':self.company,'nombre':'Por caja','columnas':['caja','total'],'filtros':{'caja':boxes[0]}},channel='expendios');self.assertEqual(self.cm('reportes',channel='expendios')['reportes'][0]['filtros']['caja'],boxes[0])
 def test_tax_identity_net_prices_dates_and_both_print_formats(self):
  skus=[self.product('PRUEBA '+str(r),str(r),str(price)) for r,price in [(0,100),(8,108),(16,116)]]
  doc=self.cm('pedidos',{'empresa':self.company,'sucursal':'EJIDOS','tipo':'PEDIDO','fechaPedido':'2026-10-28','fechaEntrega':'2026-11-02','clave':uuid.uuid4().hex,'partidas':[{'sku':s,'cantidad':'1'} for s in skus]})['documento'];self.assertEqual(doc['total'],'324.00');self.assertEqual([l['tipoImpuesto'] for l in doc['partidas']],['SIN IVA','IEPS','IVA']);self.assertEqual(doc['impuesto'],'24.00')
  for fmt in ('a4','ticket'):
   status,raw,_=self.call('/api/comercial/imprimir?canal=ventasins&id='+doc['id']+'&formato='+fmt);self.assertEqual(status,200);self.assertIn(b'02/11/2026',raw);self.assertIn(b'IEPS incluido $8.00',raw);self.assertIn(b'IVA incluido $16.00',raw);self.assertIn(b'size:80mm' if fmt=='ticket' else b'size:A4',raw)
  url='/api/comercial/documentos?canal=ventasins&empresa='+str(self.company)
  self.assertEqual(self.value(url+'&campoFecha=entrega&desde=2026-11-02&hasta=2026-11-02')['cantidad'],1);self.assertEqual(self.value(url+'&campoFecha=pedido&desde=2026-11-02')['cantidad'],0);self.assertEqual(self.value(url+'&producto=INEXISTENTE')['cantidad'],0)
  self.assertEqual(display_date('2026-10-28T12:34:56-06:00'),'28/10/2026 12:34:56');self.assertRaises(ValueError,iso_date,'2026-02-30');self.assertEqual(tax_line('1','108','8')['base'],'100.00')
 def test_institutional_operator_edits_prices_and_template_directly(self):
  sku=self.product();email='inst@example.test';self.value('/api/users',{'email':email,'name':'Institucional','role':'ventasins','password':self.password,'active':True});self.cm('accesos',{'email':email,'revision':0,'empresas':[self.company],'sucursales':['EJIDOS'],'cajas':[],'acciones':[]});actor=self.login(email)
  doc=self.cm('pedidos',{'empresa':self.company,'sucursal':'EJIDOS','clave':uuid.uuid4().hex,'partidas':[{'sku':sku,'cantidad':'1','precio':'54','iva':'16'}]},actor)['documento'];self.assertEqual(doc['total'],'54.00');self.assertEqual(doc['partidas'][0]['iva'],'8');self.assertEqual(doc['partidas'][0]['impuesto'],'4.00')
  self.assertEqual(self.call('/api/comercial/plantillas',{'canal':'ventasins','empresa':self.company,'nombre':'NO PERMITIDA','partidas':[{'sku':sku,'cantidad':'2'}]},actor)[0],403)
  template=self.cm('plantillas',{'empresa':self.company,'nombre':'Directa','partidas':[{'sku':sku,'cantidad':'2'}]})['id'];self.cm('plantillas',{'empresa':self.company,'id':template,'revision':1,'nombre':'Editada','partidas':[{'sku':sku,'cantidad':'3','observaciones':'Entrega'}]});t=self.cm('plantillas',actor=actor)['plantillas'][0];self.assertEqual(t['partidas'][0]['cantidad'],'3');self.assertEqual(t['revision'],2)
 def test_bulk_customer_prices_final_and_before_tax_atomic(self):
  sku=self.product();client=self.cm('clientes',{'empresa':self.company,'nombre':'CLIENTE','canales':['ventasins']})['id'];code=self.cm('clientes')['clientes'][0]['codigo']
  def upload(text):return {'empresa':self.company,'contenido':base64.b64encode(('CODIGO_CLIENTE;SKU;PRECIO_CON_IMPUESTO;PRECIO_ANTES_IMPUESTO\n'+text).encode()).decode()}
  data=upload(code+';'+sku+';108;100');review=self.cm('precios/importar',{**data,'revisar':True});self.assertEqual(review['detalle'][0]['tipoImpuesto'],'IEPS');self.assertEqual(self.cm('precios')['precios'][0]['origen'],'MANUAL');self.cm('precios/importar',{**data,'huellaActual':review['huellaActual']});prices=self.cm('precios')['precios'];self.assertEqual(next(p['precio'] for p in prices if p['cliente']==client),'108')
  bad=upload(code+';'+sku+';200;100');self.assertEqual(self.call('/api/comercial/precios/importar',{**bad,'revisar':True})[0],400)
  before=upload(code+';'+sku+';;50');review=self.cm('precios/importar',{**before,'revisar':True});self.assertEqual(review['detalle'][0]['precio'],'54');self.cm('precios/importar',{**before,'huellaActual':review['huellaActual']})
  status,raw,_=self.call('/api/comercial/precios/layout?canal=ventasins&empresa='+str(self.company));self.assertEqual(status,200)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertIsNone(z.testzip())

for name in dir(catalogs.CatalogTests):
 if name.startswith('test_') and name not in CommercialUpdates.__dict__:setattr(CommercialUpdates,name,None)
