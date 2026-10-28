"""Rutas de la v2, aisladas de los catálogos y requisiciones existentes."""
from comercial import CommercialStore,CHANNELS
from maestro_comercial import import_master
from comercial_print import document_html,report_rows,report_csv,report_xlsx,report_pdf
from comercial_sync import SyncService

class CommercialAPI:
 def __init__(self,store):self.cm=CommercialStore(store);self.sync=SyncService(self.cm)
 def get(self,path,query,actor):
  cm=self.cm;channel=query.get('canal',['ventasins'])[0];cm.module(actor,channel);company=int(query.get('empresa',['0'])[0]);action=path.removeprefix('/api/comercial/')
  if action=='meta':return cm.metadata(actor,channel)
  if action=='fuente':return self.sync.config(actor)
  if action=='accesos':return cm.access_list(actor)
  if action=='productos':return cm.products(company,actor,channel,query.get('q',[''])[0],query.get('cliente',[''])[0])
  if action=='clientes':return cm.customers(company,actor,channel)
  if action=='precios':return cm.prices(company,actor)
  if action=='plantillas':return cm.templates(company,actor)
  if action=='reportes':return cm.report_definitions(company,actor,channel)
  if action=='folios':return cm.sequences(company,actor)
  if action=='cajas':return cm.boxes(company,actor)
  if action=='sesiones':return cm.sessions(company,actor)
  if action=='cancelaciones':return cm.cancellations(company,actor)
  if action=='documentos':return cm.documents(company,actor,channel,{k:v[0] for k,v in query.items()})
  if action=='documento':return cm.get_document(query.get('id',[''])[0],actor,channel)
  if action=='imprimir':return document_html(cm.get_document(query.get('id',[''])[0],actor,channel),channel),'text/html; charset=utf-8'
  raise ValueError('Opción comercial no encontrada.')
 def mutate(self,path,data,actor):
  cm=self.cm;channel=data.get('canal','ventasins');cm.module(actor,channel);action=path.removeprefix('/api/comercial/')
  if action=='empresas':return cm.save_company(data,actor)
  if action=='fuente':return self.sync.save(data,actor)
  if action=='sincronizar':return self.sync.trigger(actor)
  if action=='empresas/eliminar':return cm.save_company(data,actor,True)
  if action=='accesos':return cm.save_access(data,actor)
  if action=='clientes':return cm.save_customer(data,actor,channel)
  if action=='precios':return cm.save_price(data,actor)
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
