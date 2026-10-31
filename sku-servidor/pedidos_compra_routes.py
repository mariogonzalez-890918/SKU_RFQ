from plantillas_import import vendor_import
"""API del módulo de Compras de GMP ERP."""
from pedidos_compra import PurchaseStore
from pedidos_compra_vendors import HEADERS,import_vendors,smtp_config,save_smtp,send_order
from pedidos_compra_output import order_pdf,report_rows,purchase_report_xlsx,purchase_report_pdf
from comercial_print import report_xlsx,report_csv,report_pdf
from requisiciones import ROOT

class PurchaseAPI:
 def __init__(self,store,commercial,requisitions,reports):self.po=PurchaseStore(store,commercial,requisitions,reports)
 def get(self,path,query,actor):
  po=self.po;po.scope(actor);action=path.removeprefix('/api/pedidoscompra/');q={k:v[0] for k,v in query.items()};company=int(q.get('empresa') or 0);branch=q.get('sucursal');id=q.get('id')
  if action=='meta':return po.metadata(actor)
  if action=='accesos':return po.access_list(actor)
  if action=='proveedores':return po.vendors(company,actor)
  if action=='proveedores/layout':return (ROOT/'public/layout-proveedores.xlsx').read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='proveedores/excel':
   rows=[HEADERS]
   for r in po.vendors(company,actor)['proveedores']:rows.append([r['codigo'],r['nombre'],r['rfc'],r['correo'],r['contacto'],r['telefono'],r['domicilio'],r['referencia'],r['condiciones'],'SI' if r['activo'] else 'NO'])
   return report_xlsx(rows,'PROVEEDORES'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='plantillas':return po.templates(company,actor)
  if action=='plantillas/layout':return (ROOT/'public/layout-plantillas-proveedores.xlsx').read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='materiales/excel':
   rows=[['ID_MATERIAL','SKU','DESCRIPCION','UM_COMPRA','UM_ENTREGA','FACTOR','PRECIO_COMPRA_ANTES_IMPUESTO','COSTO_ENTREGA','IMPUESTO']]
   for m in po.materials(actor)['materiales']:rows.append([m['materialId'],m['sku'],m['nombre'],m['unidadCompra'],m['unidadEntrega'],m['factor'],m['precioCompra'],m['costoEntrega'],m['impuesto']])
   return report_xlsx(rows,'MATERIALES'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='materiales':return po.materials(actor)
  if action=='requisicion':return po.request_detail(company,branch,id,actor)
  if action=='requisiciones':return po.req_sources(company,branch,actor)
  if action=='series':return po.sequences(company,branch,actor)
  if action=='documento':return po.get_document(id,actor)
  if action=='documento/pdf':
   if q.get('formato') not in (None,'','a4'):raise ValueError('Compras se imprime solamente en hoja A4.')
   doc=po.get_document(id,actor);move=next((m for m in doc['movimientos'] if m['id']==q.get('movimiento')),None)
   if q.get('movimiento') and move is None:raise ValueError('Movimiento no disponible en este pedido.')
   return order_pdf(doc,move),'application/pdf'
  if action in ('pedidos','reportes'):return po.orders(actor,company,q)
  if action=='reportes/excel':return purchase_report_xlsx(po.orders(actor,company,q)),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action=='reportes/pdf':return purchase_report_pdf(po.orders(actor,company,q)),'application/pdf'
  if action=='smtp':return smtp_config(po,actor)
  if action=='respaldo':return po.backup(actor)
  raise ValueError('Opción de Compras no encontrada.')
 def mutate(self,path,data,actor):
  action=path.removeprefix('/api/pedidoscompra/');po=self.po;po.scope(actor)
  if action=='proveedores':return po.save_vendor(data,actor)
  if action=='proveedores/importar':return import_vendors(po,data,actor)
  if action=='plantillas':return po.save_template(data,actor)
  if action=='plantillas/importar':return vendor_import(po,data,actor)
  if action=='pedidos':return po.save_order(data,actor)
  if action=='accion':return po.transition(data,actor)
  if action=='recepcion':return po.movement(data,actor,'RECEPCION')
  if action=='compra':return po.movement(data,actor,'COMPRA')
  if action=='series':return po.save_sequence(data,actor)
  if action=='accesos':return po.save_access(data,actor)
  if action=='smtp':return save_smtp(po,data,actor)
  if action=='correo':return send_order(po,data,actor)
  if action=='restaurar':return po.restore(data,actor)
  raise ValueError('Acción de Compras inválida.')
