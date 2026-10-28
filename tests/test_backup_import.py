import base64,contextlib,copy,importlib.util,io,json,pathlib,secrets,shutil,sys,tempfile,threading,unittest,urllib.request,urllib.error,uuid,zipfile
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT/'sku-servidor'))
import server,requisiciones,ventas,respaldos
spec=importlib.util.spec_from_file_location('init_local',ROOT/'tools/inicializar.py');initializer=importlib.util.module_from_spec(spec);spec.loader.exec_module(initializer)
HEADERS={'A':'CLAVE PROVEEDOR','B':'SKU','C':'STATUS DE COMPRA','D':'','E':'PRODUCTO','F':'CATEGORÍA','G':'SUBCATEGORÍA','H':'DESCRIPCIÓN','I':'PRECIO DE COMPRA','L':'U_M','M':'UM_COMPRA','N':'UM_ENTREGA','O':'PROVEEDOR PRINCIPAL','U':'UM_ENTREGA SUCURSALES'}
def workbook(rows,sheet='PRODUCTOS',headers=None):
 from xml.sax.saxutils import escape
 raw=base64.b64decode(initializer.empty_workbook(sheet,headers or HEADERS));out=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(raw)) as z,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as result:
  for entry in z.infolist():
   data=z.read(entry.filename)
   if entry.filename=='xl/worksheets/sheet1.xml':
    xml=data.decode();body=''.join('<row r="'+str(n)+'">'+''.join('<c r="'+col+str(n)+'" t="inlineStr"><is><t>'+escape(str(value))+'</t></is></c>' for col,value in row.items())+'</row>' for n,row in enumerate(rows,2));data=xml.replace('</sheetData>',body+'</sheetData>').encode()
   result.writestr(entry,data)
 return base64.b64encode(out.getvalue()).decode()
def product(name='PRODUCTO PRUEBA',**fields):return {'B':'','C':'ACTIVO','D':'1','E':'INSUMO','F':'POLVOS','G':'SALES Y ESPECIAS','H':name,'I':'100','L':'10','M':'BOLSA 10 KG','N':'KILO','O':'PROVEEDOR DE PRUEBA','U':'BOLSA 10 KG',**fields}

class ModuleBackupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=pathlib.Path(self.tmp.name);self.root=root;self.password=secrets.token_urlsafe(20);initializer.create_initials(root,self.password);shutil.copy2(ROOT/'sku-servidor/catalogos.json',root/'catalogos.json');shutil.copytree(ROOT/'sku-servidor/public',root/'public');self.context=contextlib.ExitStack()
  for module in (server,requisiciones,ventas):self.context.enter_context(patch.object(module,'ROOT',root))
  self.store=server.Store(root/'data');self.http=server.http.server.ThreadingHTTPServer(('127.0.0.1',0),server.create_handler(self.store));threading.Thread(target=self.http.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.http.server_port);self.admin=self.login(server.ADMIN_EMAIL)
 def tearDown(self):self.http.shutdown();self.http.server_close();self.context.close();self.tmp.cleanup()
 def call(self,path,data=None,actor=None,method=None):
  actor=actor or self.admin if hasattr(self,'admin') else actor;headers={'Content-Type':'application/json'}
  if actor:headers.update({'Cookie':actor['cookie'],'X-CSRF-Token':actor['csrf']})
  request=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method or ('POST' if data is not None else 'GET'))
  try:
   with urllib.request.urlopen(request) as response:return response.status,response.read(),response.headers
  except urllib.error.HTTPError as error:return error.code,error.read(),error.headers
 def value(self,path,data=None,actor=None,method=None):
  status,body,_=self.call(path,data,actor,method);self.assertIn(status,(200,201),body[:300]);return json.loads(body)
 def login(self,email):
  status,body,headers=self.call('/api/login',{'email':email,'password':self.password});self.assertEqual(status,200,body);actor={'cookie':headers['Set-Cookie'].split(';')[0],'csrf':''};actor['csrf']=self.value('/api/me',actor=actor)['user']['csrf'];return actor
 def import_purchase(self,rows,review=False,actor=None):
  return self.value('/api/compras/importar',{'archivo':'PRUEBA.xlsx','contenido':workbook(rows),'revision':self.value('/api/catalogo')['revision'],'revisar':review},actor)
 def import_req(self,rows):return self.value('/api/requisiciones/maestro',{'archivo':'PRUEBA.xlsx','contenido':workbook(rows)})
 def create_req(self,quantity='3'):
  material=self.value('/api/requisiciones/materiales')['materiales'][0]
  return self.value('/api/requisiciones',{'sucursal':'EJIDOS','area':'Produccion Donas','solicitante':'PRUEBA','observaciones':'','claveCliente':uuid.uuid4().hex,'partidas':[{'materialId':material['id'],'cantidad':quantity,'observaciones':''}]})['documento']
 def delivered_req(self,quantity='3'):
  doc=self.create_req(quantity)
  self.value('/api/requisiciones/cambios',{'tipo':'surtir','objetivo':doc['id'],'revision':1,'motivo':'Entrega de prueba','datos':{'partidas':[{'materialId':doc['partidas'][0]['materialId'],'cantidadSurtida':quantity}]}})
  return doc
 def review(self,module,backup):return self.value('/api/respaldos/restaurar/revisar',{'modulo':module,'respaldo':backup})
 def restore(self,module,backup,review):return self.value('/api/respaldos/restaurar/confirmar',{'modulo':module,'respaldo':backup,'huellaActual':review['huellaActual'],'confirmar':True})
 def test_detail_excel_selection_and_grand_total(self):
  import xml.etree.ElementTree as ET
  self.import_req([product()]);first=self.delivered_req('2');self.delivered_req('3')
  config=self.value('/api/requisiciones/reportes/general/ejecutar')['configuracion'];config['agrupacion']='requisicion';config['impuestos']=[{'nombre':'IVA','tasa':'16'}]
  result=self.value('/api/requisiciones/reportes/vista-previa',config)
  self.assertEqual(result['resumen']['total'],'58.00');group=next(g for g in result['grupos'] if g['grupo']==first['numero'])
  selection={k:group[k] for k in ('grupo','materialId','unidad')}
  status,body,_=self.call('/api/requisiciones/reportes/exportar/xlsx',{'configuracion':config,'seleccion':selection})
  self.assertEqual(status,200,body[:200])
  ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
  with zipfile.ZipFile(io.BytesIO(body)) as z:
   xml=ET.fromstring(z.read('xl/worksheets/sheet3.xml'));rows=xml.findall('s:sheetData/s:row',ns)
   self.assertEqual(len(rows),3)
   self.assertIn(first['numero'],''.join(rows[1].itertext()))
   self.assertIn('GRAN TOTAL',''.join(rows[-1].itertext()))
   values={c.attrib['r']:''.join(c.itertext()) for c in rows[-1]}
   self.assertEqual(values['N3'],'20.00');self.assertEqual(values['O3'],'23.20')
   self.assertEqual(xml.find('s:autoFilter',ns).attrib['ref'],'A1:O2')
   self.assertNotIn('ORIGEN',''.join(rows[0].itertext()))
   for name in ('sheet1','sheet2','sheet3'):
    content=''.join(ET.fromstring(z.read('xl/worksheets/'+name+'.xml')).itertext()).upper()
    for removed in ('IMPUESTOS','PENDIENTE','ORIGEN','IVA 16'):self.assertNotIn(removed,content)
  selection['grupo']='SUCURSAL NO AUTORIZADA'
  self.assertEqual(self.call('/api/requisiciones/reportes/exportar/xlsx',{'configuracion':config,'seleccion':selection})[0],400)

 def test_productos_update_sku_export_and_no_duplicates(self):
  row=product();preview=self.import_purchase([row],True);self.assertEqual(preview['resumen']['agregados'],1);self.assertEqual(self.value('/api/catalogo')['state']['maxId'],0)
  self.import_purchase([row]);before=self.value('/api/catalogo')['state']['registros'][0];self.assertEqual(len(before['sku']),14)
  row['F']='LIQUIDOS';change=self.import_purchase([row],True);self.assertEqual(change['resumen']['skuActualizados'],1);self.assertEqual(self.value('/api/catalogo')['state']['registros'][0]['sku'],before['sku'])
  self.import_purchase([row]);catalog=self.value('/api/catalogo');after=catalog['state']['registros'][0];self.assertEqual(after['id'],before['id']);self.assertNotEqual(after['sku'],before['sku']);self.assertIn(before['sku'],catalog['state']['reservados'])
  again=self.import_purchase([row]);self.assertEqual(again['resumen']['agregados'],0);self.assertEqual(again['resumen']['skuActualizados'],0);self.assertEqual(len(self.value('/api/catalogo')['state']['registros']),1)
  status,raw,_=self.call('/api/compras/excel');self.assertEqual(status,200);rows,_=requisiciones.read_rows(raw,'descarga.xlsx');self.assertEqual(rows[0][1]['D'],'SKU NUEVO');self.assertEqual(rows[1][1]['D'],after['sku']);self.assertEqual(rows[1][1]['I'],'100');self.assertEqual(rows[1][1]['N'],'KILO')
  bad={'archivo':'OTRA.xlsx','contenido':workbook([row],sheet='OTRA'),'revision':self.value('/api/catalogo')['revision']};self.assertEqual(self.call('/api/compras/importar',bad)[0],400)
 def test_um_entrega_cost_and_historical_unit_conversion(self):
  row=product();self.import_req([row]);first=self.value('/api/requisiciones/materiales')['materiales'][0];self.assertEqual(first['unidad'],'KILO');doc=self.delivered_req();self.assertEqual(doc['partidas'][0]['unidad'],'KILO');report=self.value('/api/requisiciones/reportes/general/ejecutar');self.assertEqual(report['resumen']['base'],'30.00');self.assertEqual(report['detalle'][0]['costoUnitario'],'10')
  row['N']='GRAMO';self.import_req([row]);updated=self.value('/api/requisiciones/materiales')['materiales'];self.assertEqual(len(updated),1);self.assertEqual(updated[0]['id'],first['id']);self.assertEqual(updated[0]['unidad'],'GRAMO');self.assertEqual(self.value('/api/requisiciones/'+doc['id'])['partidas'][0]['unidad'],'KILO');self.assertEqual(self.value('/api/requisiciones/reportes/general/ejecutar')['resumen']['base'],'30.00');self.delivered_req('100');self.assertEqual(self.value('/api/requisiciones/reportes/general/ejecutar')['resumen']['base'],'31.00')
  row['L']='0';self.import_req([row]);report=self.value('/api/requisiciones/reportes/general/ejecutar');self.assertEqual(report['resumen']['pendientes'],2);self.assertFalse(report['resumen']['completo']);self.assertEqual(report['resumen']['base'],'0.00')
 def test_multiple_renames_do_not_leave_stale_matching_keys(self):
  self.import_purchase([product('ANTES UNO'),product('ANTES DOS')]);old=self.value('/api/catalogo')['state']['registros'];rows=[product('NUEVO UNO',B=old[0]['sku']),product('NUEVO DOS',B=old[1]['sku']),product('ANTES UNO')];first=self.import_purchase(rows);self.assertEqual(first['resumen']['agregados'],1);second=self.import_purchase(rows);self.assertEqual(second['resumen']['agregados'],0);self.assertEqual(len(self.value('/api/catalogo')['state']['registros']),3)
 def test_distinct_presentation_and_supplier_code_are_not_duplicates(self):
  rows=[product('MISMO NOMBRE',A='',M='CUBETA 4 LT',N='LITROS'),product('MISMO NOMBRE',A='',M='LITROS',N='LITROS'),product('MISMO NOMBRE',A='123',M='LITROS',N='LITROS')];self.assertEqual(self.import_purchase(rows)['resumen']['agregados'],3);self.assertEqual(self.import_purchase(rows)['resumen']['agregados'],0);self.assertEqual(len({r['sku'] for r in self.value('/api/catalogo')['state']['registros']}),3)
 def test_duplicated_legacy_code_does_not_merge_different_products(self):
  rows=[product('ARTICULO UNO',AD='ANTIGUO_REPETIDO'),product('ARTICULO DOS',AD='ANTIGUO_REPETIDO')];self.assertEqual(self.import_purchase(rows)['resumen']['agregados'],2);self.assertEqual(self.import_purchase(rows)['resumen']['agregados'],0)
 def test_costo_header_has_priority_and_uom_aliases(self):
  headers={**HEADERS,'M':'UOM_COMPRA','N':'UOM_ENTREGA','K':'COSTO'};self.value('/api/requisiciones/maestro',{'archivo':'COSTO.xlsx','contenido':workbook([product(K='7.25')],headers=headers)});doc=self.delivered_req();self.assertEqual(doc['partidas'][0]['unidad'],'KILO');r=self.value('/api/requisiciones/reportes/general/ejecutar');self.assertEqual(r['resumen']['base'],'21.75');self.assertEqual(r['detalle'][0]['costoUnitario'],'7.25')
 def test_sales_reset_can_reimport_same_validated_historical_sku(self):
  sku='PTPB19'+'TEST000'+'0';master=workbook([{'A':sku,'B':'PRODUCTO TERMINADO','C':'PAN BLANCO','D':'PAN BLANCO','H':'PAN PRUEBA'}],sheet='SUGERIDO',headers={'A':'SKU','B':'PRODUCTOS Y SERVICIOS','C':'CATEGORIA','D':'SUBCATEGORIA','H':'DESCRIPCION'})
  self.value('/api/ventas/importar',{'revision':self.value('/api/ventas')['revision'],'master':master});review=self.value('/api/respaldos/vaciar/revisar',{'modulo':'ventas'});self.value('/api/respaldos/vaciar/confirmar',{'modulo':'ventas','huellaActual':review['huellaActual'],'confirmar':True,'texto':'VACIAR'});self.assertEqual(self.value('/api/ventas')['state']['registros'],[]);self.value('/api/ventas/importar',{'revision':self.value('/api/ventas')['revision'],'master':master});self.assertEqual(self.value('/api/ventas')['state']['registros'][0]['sku'],sku)
 def test_reset_module_keeps_other_modules_and_creates_backup(self):
  self.import_purchase([product()]);self.import_req([product()]);self.create_req();sku=self.value('/api/catalogo')['state']['registros'][0]['sku'];review=self.value('/api/respaldos/vaciar/revisar',{'modulo':'compras'});self.assertEqual(self.call('/api/respaldos/vaciar/confirmar',{'modulo':'compras','huellaActual':review['huellaActual'],'confirmar':True,'texto':'NO'})[0],400)
  result=self.value('/api/respaldos/vaciar/confirmar',{'modulo':'compras','huellaActual':review['huellaActual'],'confirmar':True,'texto':'VACIAR'});self.assertEqual(len(self.value('/api/catalogo')['state']['registros']),0);self.assertEqual(self.value('/api/requisiciones')['total'],1);self.assertEqual(len(self.value('/api/respaldos/previo/'+result['respaldoPrevio'])['datos']['catalogo']['state']['registros']),1);self.import_purchase([product()]);new=self.value('/api/catalogo')['state']['registros'][0];self.assertEqual(new['id'],2);self.assertNotEqual(new['sku'],sku)
  review=self.value('/api/respaldos/vaciar/revisar',{'modulo':'requisiciones'});self.value('/api/respaldos/vaciar/confirmar',{'modulo':'requisiciones','huellaActual':review['huellaActual'],'confirmar':True,'texto':'VACIAR'});self.assertEqual(self.value('/api/requisiciones')['total'],0);self.assertEqual(len(self.value('/api/requisiciones/materiales')['materiales']),0);self.import_req([product()]);self.assertEqual(self.create_req()['folio'],2);self.assertEqual(len(self.value('/api/catalogo')['state']['registros']),1)
 def test_backups_restore_only_selected_module_and_keep_folio_floor(self):
  self.import_purchase([product()]);self.import_req([product()]);self.create_req();backups={m:self.value('/api/respaldos?modulo='+m) for m in ('compras','ventas','requisiciones')};self.assertNotIn('users',backups['requisiciones']['datos']['tablas'])
  self.create_req();review=self.review('requisiciones',backups['requisiciones']);self.create_req();stale=self.call('/api/respaldos/restaurar/confirmar',{'modulo':'requisiciones','respaldo':backups['requisiciones'],'huellaActual':review['huellaActual'],'confirmar':True});self.assertEqual(stale[0],409);self.assertEqual(self.value('/api/requisiciones')['total'],3)
  current_purchase=self.value('/api/catalogo');current_sales=self.value('/api/ventas');review=self.review('requisiciones',backups['requisiciones']);result=self.restore('requisiciones',backups['requisiciones'],review);self.assertEqual(self.value('/api/requisiciones')['total'],1);self.assertEqual(self.create_req()['folio'],4);self.assertEqual(self.value('/api/catalogo'),current_purchase);self.assertEqual(self.value('/api/ventas'),current_sales);self.assertEqual(self.value('/api/respaldos/previo/'+result['respaldoPrevio'])['modulo'],'requisiciones')
  self.import_purchase([product(),product('SEGUNDO ARTICULO')]);req_before=self.value('/api/requisiciones')['total'];review=self.review('compras',backups['compras']);self.restore('compras',backups['compras'],review);p=self.value('/api/catalogo');self.assertEqual(len(p['state']['registros']),1);self.assertEqual(p['state']['maxId'],2);self.assertEqual(self.value('/api/requisiciones')['total'],req_before)
  review=self.review('ventas',backups['ventas']);self.restore('ventas',backups['ventas'],review);self.assertEqual(self.value('/api/catalogo'),p)
 def test_invalid_files_permissions_and_atomic_rollback(self):
  self.import_req([product()]);self.create_req();backup=self.value('/api/respaldos?modulo=requisiciones');tampered=copy.deepcopy(backup);tampered['datos']['tablas']['req_documents']['filas']=[];self.assertEqual(self.call('/api/respaldos/restaurar/revisar',{'modulo':'requisiciones','respaldo':tampered})[0],400);self.assertEqual(self.call('/api/respaldos/restaurar/revisar',{'modulo':'ventas','respaldo':backup})[0],400)
  self.value('/api/users',{'email':'viewer@example.com','name':'Consulta','role':'visualizador','active':True,'password':self.password});viewer=self.login('viewer@example.com');self.assertEqual(self.call('/api/respaldos?modulo=compras',actor=viewer)[0],403);self.assertEqual(self.call('/api/respaldos/restaurar/revisar',{'modulo':'requisiciones','respaldo':backup},viewer)[0],403)
  # Un fallo de integridad en una tabla no deja las anteriores borradas a medias.
  duplicate=copy.deepcopy(backup);rows=duplicate['datos']['tablas']['req_report_features']['filas'];rows.append(rows[0]);duplicate['checksum']=respaldos.digest({k:v for k,v in duplicate.items() if k!='checksum'});status=self.call('/api/respaldos/restaurar/revisar',{'modulo':'requisiciones','respaldo':duplicate})[0];self.assertEqual(status,400);self.assertEqual(self.value('/api/requisiciones')['total'],1)
if __name__=='__main__':unittest.main()
