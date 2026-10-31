from plantillas_import import customer_import
from precios_masivos import import_prices
"""Rutas de la v2, aisladas de los catálogos y requisiciones existentes."""
from comercial import CommercialStore,CHANNELS,tax_name
from maestro_comercial import import_master
from comercial_print import document_html,report_rows,report_csv,report_xlsx,report_pdf
from comercial_sync import SyncService
from productos_comerciales import catalog as product_catalog,save_product
from clientes_comerciales import import_customers

class CommercialAPI:
 def __init__(self,store):self.cm=CommercialStore(store);self.sync=SyncService(self.cm)
 def get(self,path,query,actor):
  cm=self.cm;channel=query.get('canal',['ventasins'])[0];cm.module(actor,channel);company=int(query.get('empresa',['0'])[0]);action=path.removeprefix('/api/comercial/')
  if actor['role']=='ventaspasteleria' and action not in ('meta','productos','clientes','documentos','documento','imprimir','documento/excel','pedidos/cancelaciones'):raise PermissionError('VENTASPASTELERIA solo captura y consulta sus pedidos y presupuestos.')
  if action=='pedidos/cancelaciones':return cm.institutional_cancel_requests(company,actor)
  if action=='meta':return cm.metadata(actor,channel)
  if action=='fuente':return self.sync.config(actor)
  if action=='accesos':return cm.access_list(actor)
  if action=='productos':return cm.products(company,actor,channel,query.get('q',[''])[0],query.get('cliente',[''])[0])
  if action=='productos/catalogo':return product_catalog(cm,company,actor)
  if action=='clientes/layout':
   from ventas import ROOT
   return (ROOT/'public/layout-clientes.xlsx').read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='precios/layout':
   from ventas import ROOT
   cm.admin(actor);return (ROOT/'public/layout-precios.xlsx').read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='plantillas/layout':
   from ventas import ROOT
   cm.module(actor,'ventasins')
   if actor['role'] not in ('gerente','auxti','superadmin'):raise PermissionError('Solo Gerencia y administración gestionan plantillas.')
   return (ROOT/'public/layout-plantillas-clientes.xlsx').read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='productos/layout':
   from ventas import ROOT
   return (ROOT/'public/layout-productos.xlsx').read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='clientes/excel':
   from clientes_comerciales import HEADERS,customer_channels
   rows=[HEADERS]
   for c in cm.customers(company,actor,channel)['clientes']:
    ch=customer_channels(c);label='AMBOS' if len(ch)>1 else 'EXPENDIOS' if ch==['expendios'] else 'INSTITUCIONALES';rows.append([c.get('codigo',''),c['nombre'],label,c.get('rfc',''),c.get('correo',''),c.get('telefono',''),c.get('domicilio',''),c.get('entrega',''),c.get('condiciones',''),'SI' if c.get('activo') else 'NO'])
   return report_xlsx(rows,'CLIENTES'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='productos/excel':
   rows=[['SKU','DESCRIPCION','CANAL','UOM','TIPO IMPUESTO','Tasa %','PRECIO PUBLICO','PRECIO RUTA','PRECIO DESPACHO','ACTIVO']]
   products=product_catalog(cm,company,actor)['productos'] if actor['role'] in ('superadmin','auxti') else cm.products(company,actor,channel)['productos']
   for p in products:
    if channel=='ventasins' and not p.get('institucional',True) or channel=='expendios' and not p.get('expendio'):continue
    ch='AMBOS' if p.get('institucional',True) and p.get('expendio') else 'EXPENDIOS' if p.get('expendio') else 'INSTITUCIONALES';prices=p.get('precios',{});rows.append([p['sku'],p['nombre'],ch,p['unidad'],tax_name(p.get('iva')),p['iva'] if p.get('iva') is not None else 'PENDIENTE',prices.get('PUBLICO',''),prices.get('RUTA',''),prices.get('DESPACHO',''),'SI' if p.get('activo') else 'NO'])
   return report_xlsx(rows),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='clientes':
   result=cm.customers(company,actor,channel)
   if actor['role']=='ventaspasteleria':result['clientes']=[{k:c[k] for k in ('id','codigo','nombre','activo') if k in c} for c in result['clientes']]
   return result
  if action=='precios':return cm.prices(company,actor)
  if action=='plantillas':return cm.templates(company,actor)
  if action=='reportes':return cm.report_definitions(company,actor,channel)
  if action=='folios':return cm.sequences(company,actor)
  if action=='cajas':return cm.boxes(company,actor)
  if action=='sesiones':return cm.sessions(company,actor)
  if action=='cancelaciones':return cm.cancellations(company,actor)
  if action=='documentos':return cm.documents(company,actor,channel,{k:v[0] for k,v in query.items()})
  if action=='documento/excel':return report_xlsx(report_rows({'documentos':[cm.get_document(query.get('id',[''])[0],actor,channel)]})),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='documento':return cm.get_document(query.get('id',[''])[0],actor,channel)
  if action=='imprimir':return document_html(cm.get_document(query.get('id',[''])[0],actor,channel),channel,query.get('formato',[''])[0]),'text/html; charset=utf-8'
  raise ValueError('Opción comercial no encontrada.')
 def mutate(self,path,data,actor):
  cm=self.cm;channel=data.get('canal','ventasins');cm.module(actor,channel);action=path.removeprefix('/api/comercial/')
  if actor['role']=='ventaspasteleria' and action not in ('pedidos','pedidos/cancelacion/solicitar'):raise PermissionError('VENTASPASTELERIA solo puede agregar nuevos pedidos y presupuestos.')
  if action=='pedidos/cancelacion/solicitar':return cm.request_institutional_cancel(data,actor)
  if action=='pedidos/cancelacion/resolver':return cm.decide_institutional_cancel(data,actor)
  if action=='pedidos/bloqueo':return cm.toggle_order_lock(data,actor)
  if action=='empresas':return cm.save_company(data,actor)
  if action=='sucursales/empresas':return cm.save_branch_companies(data,actor)
  if action=='fuente':return self.sync.save(data,actor)
  if action=='sincronizar':return self.sync.trigger(actor)
  if action=='empresas/eliminar':return cm.save_company(data,actor,True)
  if action=='accesos':return cm.save_access(data,actor)
  if action=='clientes':return cm.save_customer(data,actor,channel)
  if action=='precios/importar':return import_prices(cm,data,actor)
  if action=='clientes/importar':return import_customers(cm,data,actor,channel)
  if action=='productos':return save_product(cm,data,actor)
  if action=='precios':return cm.save_price(data,actor)
  if action=='plantillas/importar':return customer_import(cm,data,actor)
  if action=='plantillas':return cm.save_template(data,actor)
  if action=='reportes':return cm.save_report(data,actor,channel)
  if action=='folios':return cm.save_sequence(data,actor)
  if action=='cajas':return cm.save_box(data,actor)
  if action=='sesiones/abrir':return cm.open_session(data,actor)
  if action=='sesiones/cerrar':return cm.close_session(data,actor)
  if action=='pedidos':return cm.save_order(data,actor)
  if action=='pedidos/cancelar':return cm.cancel_order(data,actor)
  if action=='cobrar':return cm.checkout(data,actor)
  if action=='cancelaciones':return cm.request_cancel(data,actor)
  if action=='cancelaciones/resolver':return cm.decide_cancel(data,actor)
  if action=='reembolsar':return cm.refund(data,actor)
  if action=='maestro':return import_master(cm,data,actor)
  if action in ('exportar/xlsx','exportar/csv','exportar/pdf'):
   cm.action(actor,channel,'reportes');result=cm.documents(data.get('empresa'),actor,channel,data.get('filtros',{}));rows=report_rows(result,data.get('columnas'),data.get('seleccion'))
   if action.endswith('pdf'):return report_pdf(rows),'application/pdf'
   return (report_xlsx(rows),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') if action.endswith('xlsx') else (report_csv(rows),'text/csv; charset=utf-8')
  raise ValueError('Opción comercial no encontrada.')
