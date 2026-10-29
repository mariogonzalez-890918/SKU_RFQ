"""API de inventarios, con autorización y descargas calculadas en servidor."""
from inventarios import InventoryStore,HEADERS,APPROVERS
from comercial_print import report_xlsx,report_pdf
from fechas import display_date
from inventarios_operaciones import InventoryOperations

class InventoryAPI:
 def __init__(self,store,po):self.inv=InventoryStore(store,po);self.ops=InventoryOperations(self.inv)
 def get(self,path,query,actor):
  result=self._get(path,query,actor)
  return self.inv.public(result,actor) if isinstance(result,dict) else result
 def _get(self,path,query,actor):
  inv=self.inv;inv.scope(actor);action=path.removeprefix('/api/inventarios/');q={k:v[0] for k,v in query.items()};w=q.get('almacen')
  if action=='meta':return {**inv.warehouses(actor),'puedeVerCostos':actor['role'] in APPROVERS}
  if action=='accesos':return inv.po.access_list(actor)
  if action=='materiales':return {'materiales':list(inv.materials().values())}
  if action=='traspasos':return inv.transfers(actor)
  if action=='estado':return inv.state(w,actor)
  if action=='kardex':return inv.kardex(w,q,actor)
  if action=='conceptos':return self.ops.concepts(actor)
  if action=='operaciones':return self.ops.list(w,actor)
  if action=='pedidos-recibir':return inv.pending_receipts(w,actor)
  if action=='recepciones':return inv.receipts(w,q,actor)
  if action=='disponibilidad':return inv.availability(w,q.get('sku'),actor)
  if action=='layout':
   inv.scope(actor,w)
   return report_xlsx([HEADERS,*[[m['sku'],m['nombre'],m['unidad'],''] for m in inv.materials().values()]],'INVENTARIO_INICIAL'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  if action in ('excel','pdf'):
   state=inv.state(w,actor);costs=actor['role'] in APPROVERS;rows=[['SKU','DESCRIPCION','UNIDAD_ENTREGA','FISICO']+(['COSTO_UNITARIO_SIN_IMPUESTO','VALOR'] if costs else [])]+[[r['sku'],r['nombre'],r['unidad'],'PENDIENTE DE CONTEO' if r['cantidad'] is None else r['cantidad']]+([r['costo'],r['valor']] if costs else []) for r in state['existencias']]
   if costs:rows.append(['GRAN TOTAL CONTADO','','','','',state['valorTotal']])
   return (report_xlsx(rows,'EXISTENCIAS'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') if action=='excel' else (report_pdf(rows,'GMP ERP · Inventario '+state['almacen']['sucursal'],subtitle='Existencias físicas en unidad de entrega.'),'application/pdf')
  if action in ('kardex/resumen/excel','kardex/resumen/pdf'):
   result=inv.kardex(w,q,actor,True);costs=actor['role'] in APPROVERS;rows=[['ALMACEN','RAZON_SOCIAL','SKU','DESCRIPCION','UNIDAD_ENTREGA','INICIAL_PERIODO','ENTRADAS','SALIDAS','EXISTENCIA_AL_CORTE','EXISTENCIA_ACTUAL']+(['COSTO_UNITARIO','VALOR'] if costs else [])]+[[r['sucursal'],r['razonSocial'],r['sku'],r['nombre'],r['unidad'],r['saldoInicial'] if r['saldoInicial'] is not None else 'PENDIENTE',r['entradas'],r['salidas'],r['saldoFinal'] if r['saldoFinal'] is not None else 'PENDIENTE',r['existenciaActual'] if r['existenciaActual'] is not None else 'PENDIENTE']+([r.get('costoUnitarioActual'),r.get('valorExistenciaActual')] if costs else []) for r in result['resumenPorSku']]
   return (report_xlsx(rows,'KARDEX_GENERAL'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') if action.endswith('excel') else (report_pdf(rows,'GMP ERP · Kárdex general',subtitle='Inicial, entradas, salidas y existencias en unidad de entrega.'),'application/pdf')
  if action in ('movimientos/excel','kardex/excel'):
   result=inv.kardex(w,q,actor,True);costs=actor['role'] in APPROVERS;rows=[['FECHA','ALMACEN','RAZON_SOCIAL','TIPO','CONCEPTO','REFERENCIA','SKU','DESCRIPCION','UNIDAD','INICIAL','ENTRADA','SALIDA','SALDO_ANTERIOR','SALDO']+(['COSTO_UNITARIO','IMPORTE'] if costs else [])+['USUARIO','ENTREGA','RECIBE','OBSERVACIONES']]+[[display_date(r['fecha']),r['sucursal'],r['razonSocial'],r['tipo'],r.get('concepto',r['tipo']),r['referencia'],r['sku'],r['nombre'],r['unidad'],r['inicial'],r['entrada'],r['salida'],r['antes'],r['saldo']]+([r['costoUnitario'],r['importe']] if costs else [])+[r['actor'],r.get('entrega',''),r.get('recibe',''),r['observaciones']] for r in result['movimientos']]
   return report_xlsx(rows,'KARDEX'),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  raise ValueError('Opción de Inventarios no encontrada.')
 def mutate(self,path,data,actor):
  return self.inv.public(self._mutate(path,data,actor),actor)
 def _mutate(self,path,data,actor):
  inv=self.inv;inv.scope(actor);action=path.removeprefix('/api/inventarios/')
  if action=='conteo':return inv.count(data,actor)
  if action=='autorizar':return inv.decide(data,actor)
  if action=='restablecer':return inv.reset(data,actor)
  if action=='conceptos':return self.ops.save_concept(data,actor)
  if action=='movimiento':return self.ops.submit(data,actor)
  if action=='recepciones/cancelar':return self.ops.submit(data,actor,True)
  if action=='operaciones/autorizar':return self.ops.decide(data,actor)
  if action=='traspaso':return inv.transfer(data,actor)
  if action=='accesos':return inv.po.save_access(data,actor)
  raise ValueError('Acción de Inventarios inválida.')
