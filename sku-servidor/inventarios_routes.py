"""API de inventarios, con autorización y descargas calculadas en servidor."""
from inventarios import InventoryStore,HEADERS
from comercial_print import report_xlsx,report_pdf
from fechas import display_date

class InventoryAPI:
 def __init__(self,store,po):self.inv=InventoryStore(store,po)
 def get(self,path,query,actor):
  inv=self.inv;inv.scope(actor);action=path.removeprefix('/api/inventarios/');q={k:v[0] for k,v in query.items()};w=q.get('almacen')
  if action=='meta':return inv.warehouses(actor)
  if action=='accesos':return inv.po.access_list(actor)
  if action=='materiales':return {'materiales':list(inv.materials().values())}
  if action=='traspasos':return inv.transfers(actor)
  if action=='estado':return inv.state(w,actor)
  if action=='layout':
   inv.scope(actor,w)
   return report_xlsx([HEADERS,*[[m['sku'],m['nombre'],m['unidad'],''] for m in inv.materials().values()]],'INVENTARIO_INICIAL'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action in ('excel','pdf'):
   state=inv.state(w,actor);rows=[['SKU','DESCRIPCION','UNIDAD_ENTREGA','FISICO','COSTO_UNITARIO_SIN_IMPUESTO','VALOR']]+[[r['sku'],r['nombre'],r['unidad'],r['cantidad'],r['costo'],r['valor']] for r in state['existencias']]+[['GRAN TOTAL','','','','',state['valorTotal']]]
   return (report_xlsx(rows,'EXISTENCIAS'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') if action=='excel' else (report_pdf(rows,'GMP ERP · Inventario '+state['almacen']['sucursal']),'application/pdf')
  if action=='movimientos/excel':
   state=inv.state(w,actor);rows=[['FECHA','TIPO','REFERENCIA','SKU','DESCRIPCION','UNIDAD','CANTIDAD','ANTES','DESPUES','COSTO_UNITARIO','IMPORTE','USUARIO','ENTREGA','RECIBE','OBSERVACIONES']]+[[display_date(r['fecha']),r['tipo'],r['referencia'],r['sku'],r['nombre'],r['unidad'],r['cantidad'],r['antes'],r['despues'],r['costoUnitario'],r['importe'],r['actor'],r.get('entrega',''),r.get('recibe',''),r['observaciones']] for r in state['movimientos']]
   return report_xlsx(rows,'MOVIMIENTOS'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  raise ValueError('Opción de Inventarios no encontrada.')
 def mutate(self,path,data,actor):
  inv=self.inv;inv.scope(actor);action=path.removeprefix('/api/inventarios/')
  if action=='conteo':return inv.count(data,actor)
  if action=='autorizar':return inv.decide(data,actor)
  if action=='restablecer':return inv.reset(data,actor)
  if action=='movimiento':return inv.manual(data,actor)
  if action=='traspaso':return inv.transfer(data,actor)
  if action=='accesos':return inv.po.save_access(data,actor)
  raise ValueError('Acción de Inventarios inválida.')
