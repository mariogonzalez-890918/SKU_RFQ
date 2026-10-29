"""API de inventarios, con autorización y descargas calculadas en servidor."""
from inventarios import InventoryStore,HEADERS,APPROVERS
from comercial_print import report_xlsx,report_pdf
from fechas import display_date
from inventarios_operaciones import InventoryOperations
from inventarios_documentos import InventoryDocuments

def kardex_export(result,filters,action,costs):
 import html,io,xml.etree.ElementTree as ET
 if action=='kardex/xml':
  root=ET.Element('Kardex',{'aplicacion':'GMP ERP','version':'1'});f=ET.SubElement(root,'Filtros')
  for key in ('almacen','desde','hasta','sku','direccion','tipo'):ET.SubElement(f,key).text=display_date(filters.get(key,'')) if key in ('desde','hasta') else filters.get(key,'')
  for section,row_name,key in (('Resumen','Material','resumenPorSku'),('Movimientos','Movimiento','movimientos')):
   group=ET.SubElement(root,section)
   for row in result[key]:
    node=ET.SubElement(group,row_name)
    for name,value in row.items():ET.SubElement(node,name).text='' if value is None else display_date(value) if name=='fecha' else str(value)
  ET.indent(root);return ET.tostring(root,encoding='utf-8',xml_declaration=True),'application/xml; charset=utf-8'
 summary=[['Almacén / Razón social','SKU / Material','Unidad','Inicial','Entradas','Salidas','Al corte','Actual']+(['Costo actual','Valor actual'] if costs else [])]
 for r in result['resumenPorSku']:summary.append([r['sucursal']+' / '+r['razonSocial'],r['sku']+' / '+r['nombre'],r['unidad'],r['saldoInicial'],r['entradas'],r['salidas'],r['saldoFinal'],r['existenciaActual']]+([r['costoUnitarioActual'],r['valorExistenciaActual']] if costs else []))
 detail=[['Fecha','Concepto de movimiento','Almacén / Material','Unidad','Inicial','Entrada','Salida','Saldo anterior','Saldo','Referencia / Entrega / Recibe']+(['Costo / Importe'] if costs else [])]
 for r in result['movimientos']:detail.append([display_date(r['fecha']),r.get('concepto',r['tipo']),r['sucursal']+' / '+r['razonSocial']+' / '+r['sku']+' / '+r['nombre'],r['unidad'],r['inicial'],r['entrada'],r['salida'],r['antes'],r['saldo'],r['referencia']+' / '+r.get('entrega','')+' / '+r.get('recibe','')+' / '+r['actor']]+([r['costoUnitario']+' / '+r['importe']] if costs else []))
 subtitle='Almacén: '+filters.get('almacen','')+' · Desde: '+display_date(filters.get('desde',''))+' · Hasta: '+display_date(filters.get('hasta',''))+' · SKU: '+filters.get('sku','')+' · Dirección: '+filters.get('direccion','Todas')+' · Tipo: '+filters.get('tipo','Todos')
 note='El resumen incluye todas las entradas y salidas del periodo. Dirección y tipo filtran el detalle. El saldo anterior al conteo inicial es provisional.'
 def esc(v):return html.escape('Pendiente' if v is None else str(v))
 if action=='kardex/imprimir':
  def table(rows):return '<table><thead><tr>'+''.join('<th>'+esc(v)+'</th>' for v in rows[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows[1:])+'</tbody></table>'
  page='<!doctype html><html lang="es"><meta charset="utf-8"><title>Kárdex de materiales</title><style>body{font:12px Arial;color:#222}table{border-collapse:collapse;width:100%;margin-bottom:24px;table-layout:fixed}th,td{border:1px solid #ccc;padding:6px;vertical-align:top;overflow-wrap:anywhere}th{background:#eee}thead{display:table-header-group}tr{break-inside:avoid}@page{size:A4 landscape;margin:12mm}@media print{button{display:none}}button{padding:10px}</style><button onclick="window.print()">Imprimir / Guardar PDF</button><h1>GMP ERP · Kárdex de materiales</h1><p>'+esc(subtitle)+'</p><p>'+esc(note)+'</p><h2>Inicial, entradas, salidas y existencias</h2>'+table(summary)+'<h2>Detalle de movimientos</h2>'+table(detail)+'</html>'
  return page.encode('utf8'),'text/html; charset=utf-8'
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import A4,landscape
 from reportlab.lib.styles import ParagraphStyle
 from reportlab.platypus import SimpleDocTemplate,LongTable,TableStyle,Paragraph,Spacer
 out=io.BytesIO();page=landscape(A4);style=ParagraphStyle('kardex',fontName='Helvetica',fontSize=7,leading=9);heading=ParagraphStyle('heading',parent=style,fontSize=15,leading=19,spaceAfter=8);story=[Paragraph('GMP ERP · Kárdex de materiales',heading),Paragraph(esc(subtitle),style),Paragraph(esc(note),style),Spacer(1,12)]
 for title,rows in (('Inicial, entradas, salidas y existencias',summary),('Detalle de movimientos',detail)):
  story.append(Paragraph(title,heading));t=LongTable([[Paragraph(esc(v),style) for v in row] for row in rows],repeatRows=1,colWidths=[(page[0]-40)/len(rows[0])]*len(rows[0]));t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eae1e7')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.extend([t,Spacer(1,14)])
 SimpleDocTemplate(out,pagesize=page,leftMargin=20,rightMargin=20,topMargin=24,bottomMargin=24).build(story);return out.getvalue(),'application/pdf'

class InventoryAPI:
 def __init__(self,store,po):self.inv=InventoryStore(store,po);self.ops=InventoryOperations(self.inv);self.docs=InventoryDocuments(self.inv)
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
  if action=='requisiciones-sin-salida':return self.ops.missing_issues(w,actor)
  if action=='operaciones':return self.ops.list(w,actor)
  if action=='negativos':return self.docs.negatives(w,actor)
  if action=='entregas-compras':return self.docs.handoffs(w,q,actor)
  if action=='reportes/entregas-compras/pdf':return self.docs.handoff_pdf(w,q,actor)
  if action=='recepciones/pdf':return self.docs.receipts_pdf(w,q,actor)
  if action=='traspaso/pdf':return self.docs.transfer_pdf(q.get('id'),q,actor)
  if action=='pedidos-recibir':return inv.pending_receipts(w,actor)
  if action=='recepciones':return inv.receipts(w,q,actor)
  if action=='recepciones/devolver':return self.ops.returnable(w,q.get('recepcion'),actor)
  if action=='disponibilidad':return inv.availability(w,q.get('sku'),actor)
  if action in ('kardex/xml','kardex/pdf','kardex/imprimir'):
   result=inv.public(inv.kardex(w,q,actor,True),actor)
   return kardex_export(result,q,action,actor['role'] in APPROVERS)
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
  if action=='regularizar-surtido':return self.ops.regularize(data,actor)
  if action=='conceptos':return self.ops.save_concept(data,actor)
  if action=='movimiento':return self.ops.submit(data,actor)
  if action=='recepciones/cancelar':return self.ops.submit(data,actor,True)
  if action=='recepciones/devolver':return self.ops.submit_return(data,actor)
  if action=='operaciones/autorizar':return self.ops.decide(data,actor)
  if action=='traspaso':return inv.transfer(data,actor)
  if action=='traspaso/cancelar':return self.ops.submit_transfer_cancel(data,actor)
  if action=='entregar-compras':return self.docs.handoff(data,actor)
  if action=='accesos':return inv.po.save_access(data,actor)
  raise ValueError('Acción de Inventarios inválida.')
