"""Entregas explícitas a Compras, bandeja de autorizaciones y documentos de almacén."""
import copy,html,io,json
from decimal import Decimal
from comercial import dumps
from comercial_print import report_pdf
from fechas import display_date,iso_date
from inventarios import APPROVERS,fmt
from requisiciones import Conflict,now,text

class InventoryDocuments:
 def __init__(self,inv):
  self.inv=inv
  with inv.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS inv_purchase_handoffs(request_id TEXT PRIMARY KEY,warehouse TEXT NOT NULL,created TEXT NOT NULL,payload TEXT NOT NULL)')
 def locations(self,w,actor):
  if w=='TODOS':return self.inv.warehouses(actor)['almacenes']
  return [self.inv.scope(actor,w)]
 def dates(self,q):
  start,end=iso_date(q.get('desde')),iso_date(q.get('hasta'))
  if start and end and start>end:raise ValueError('Desde debe ser anterior o igual a Hasta.')
  return start,end
 def handoffs(self,w,q,actor):
  allowed={r['id'] for r in self.locations(w,actor)};start,end=self.dates(q);delivered=[];candidates=[]
  with self.inv.store.connect() as db:
   for warehouse,stamp,p in db.execute('SELECT warehouse,created,payload FROM inv_purchase_handoffs ORDER BY created DESC'):
    if warehouse not in allowed or start and stamp[:10]<start or end and stamp[:10]>end:continue
    row=json.loads(p);current=db.execute('SELECT payload FROM req_documents WHERE id=?',(row['id'],)).fetchone();row['estadoActual']=json.loads(current[0])['estado'] if current else 'NO DISPONIBLE';row['pedidos']=[]
    for oid,op in db.execute('SELECT id,payload FROM po_orders WHERE company=?',(row['empresa'],)):
     order=json.loads(op)
     if any(l.get('requisicionId')==row['id'] for l in order['partidas']):row['pedidos'].append({'id':oid,'folio':order['folio'],'estado':order['estado']})
    delivered.append(row)
   if w!='TODOS':
    info=self.inv.scope(actor,w,db)
    for id,p in db.execute('SELECT id,payload FROM req_documents WHERE branch=?',(info['sucursal'],)):
     d=json.loads(p)
     if d['estado'] in ('CANCELADA','CANCELADO') or db.execute('SELECT 1 FROM inv_purchase_handoffs WHERE request_id=?',(id,)).fetchone():continue
     candidates.append({**{k:d.get(k,'') for k in ('id','numero','fecha','area','solicitante','estado')},'revision':d.get('revision',1)})
  return {'entregas':delivered,'pendientes':candidates}
 def handoff(self,data,actor):
  inv=self.inv;inv.scope(actor)
  if set(data)-{'almacen','id','revision','clave','observaciones'}:raise ValueError('Fecha y usuario de entrega se asignan automáticamente.')
  with inv.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');info=inv.scope(actor,data.get('almacen'),db,True);repeat=inv.repeat(db,data)
   if repeat:return repeat
   row=db.execute('SELECT payload FROM req_documents WHERE id=?',(data.get('id'),)).fetchone();d=json.loads(row[0]) if row else None
   if not d or d['sucursal']!=info['sucursal']:raise PermissionError('La requisición no pertenece al almacén seleccionado.')
   if d['estado'] in ('CANCELADA','CANCELADO'):raise Conflict('La requisición está cancelada.')
   if d.get('revision',1)!=data.get('revision'):raise Conflict('La requisición cambió. Actualiza antes de entregarla.')
   if db.execute('SELECT 1 FROM inv_purchase_handoffs WHERE request_id=?',(d['id'],)).fetchone():raise Conflict('Esta requisición ya fue entregada a Compras.')
   company=json.loads(db.execute('SELECT payload FROM cm_companies WHERE id=?',(info['empresa'],)).fetchone()[0]);value={**{k:d.get(k,'') for k in ('id','numero','fecha','sucursal','area','solicitante','estado','revision')},'revision':d.get('revision',1),'almacen':info['id'],'empresa':info['empresa'],'razonSocial':company['nombre'],'fechaEntrega':now(),'entregadoPor':actor['email'],'observacionesEntrega':text(data.get('observaciones',''),2000),'partidas':[{k:l.get(k,'') for k in ('materialId','sku','nombre','cantidad','unidad')} for l in d['partidas']]};db.execute('INSERT INTO inv_purchase_handoffs VALUES(?,?,?,?)',(d['id'],info['id'],value['fechaEntrega'],dumps(value)));return inv.remember(db,data,{'ok':True,'entrega':value})
 def negatives(self,w,actor):
  allowed={r['id'] for r in self.locations(w,actor)};result=[]
  with self.inv.store.connect() as db:
   for id,warehouse,p in db.execute("SELECT id,warehouse,payload FROM inv_operations WHERE state='PENDIENTE'"):
    d=json.loads(p)
    if warehouse in allowed and d.get('inventarioInsuficiente'):result.append({'clase':'operacion','id':id,'almacen':warehouse,'folio':d.get('folio',id[:8]),'tipo':d['tipo'],'fecha':d['fecha'],'solicitadoPor':d['solicitadoPor'],'partidas':d['inventarioInsuficiente']})
   for id,source,p in db.execute("SELECT id,source,payload FROM inv_transfers WHERE state='SOLICITADA'"):
    if source not in allowed:continue
    d=json.loads(p);parts=[]
    for l in d['partidas']:
     stock=self.inv.balance(db,source,l['sku']);q=Decimal(stock['cantidad']) if stock else Decimal(0)
     if q<Decimal(l['cantidad']):parts.append({'sku':l['sku'],'disponible':fmt(q),'salida':l['cantidad'],'saldoPropuesto':fmt(q-Decimal(l['cantidad']))})
    if parts:result.append({'clase':'traspaso','id':id,'almacen':source,'folio':d['folio'],'tipo':'SALIDA DE TRASPASO','fecha':d['fecha'],'solicitadoPor':d['solicitadoPor'],'partidas':parts})
   branches={self.inv.scope(actor,id,db)['sucursal'] for id in allowed}
   for id,branch,p in db.execute("SELECT id,branch,payload FROM req_changes WHERE status='PENDIENTE'"):
    d=json.loads(p)
    if branch in branches and (not d.get('datos',{}).get('almacenInventario') or d['datos']['almacenInventario'] in allowed) and d.get('inventarioInsuficiente'):result.append({'clase':'requisicion','id':id,'almacen':d.get('datos',{}).get('almacenInventario'),'folio':d.get('folio',id[:8]),'tipo':'SURTIDO / CORRECCIÓN','fecha':d['fecha'],'solicitadoPor':d['solicitadoPor'],'partidas':d['inventarioInsuficiente']})
  return {'pendientes':sorted(result,key=lambda d:d['fecha'],reverse=True),'puedeAutorizar':actor['role'] in APPROVERS}
 def handoff_pdf(self,w,q,actor):
  result=self.handoffs(w,q,actor);rows=[['Entrega a Compras','Requisición / Fecha','Sucursal / Razón social','Área / Solicitante','Entregó','SKU / Material','Cantidad','Unidad','Estado actual','Cotización / Pedido']]
  for d in result['entregas']:
   for l in d['partidas']:rows.append([display_date(d['fechaEntrega']),d['numero']+' / '+display_date(d['fecha']),d['sucursal']+' / '+d['razonSocial'],d['area']+' / '+d['solicitante'],d['entregadoPor'],l['sku']+' / '+l['nombre'],l['cantidad'],l['unidad'],d['estadoActual'],'; '.join(p['folio']+' '+p['estado'] for p in d['pedidos']) or 'Sin pedido'])
  return report_pdf(rows,'GMP ERP · Relación de requisiciones entregadas a Compras',subtitle='Fecha de entrega: '+display_date(q.get('desde',''))+' a '+display_date(q.get('hasta',''))+'. Se incluyen únicamente entregas registradas mediante el botón Entregar a Compras.'),'application/pdf'
 def receipts_pdf(self,w,q,actor):
  self.dates(q);rows=[['Fecha / Recepción','Sucursal / Razón social','Pedido / Proveedor','SKU / Material','Recibido / Unidad compra','Unidad entrega','Cancelado','Devuelto','Neto','Recibió / Estado']+(['Costo UM entrega','Importe neto'] if actor['role'] in APPROVERS else [])]
  with self.inv.store.connect() as db:
   for location in self.locations(w,actor):
    company=json.loads(db.execute('SELECT payload FROM cm_companies WHERE id=?',(location['empresa'],)).fetchone()[0])
    for r in self.inv.receipts(location['id'],q,actor)['recepciones']:
     net='0' if r['cancelada'] else r['cantidadNetaEntrega'];rows.append([display_date(r['fecha'])+' / '+r['recepcion'],location['sucursal']+' / '+company['nombre'],r['pedido']+' / '+r['proveedor'],r['sku']+' / '+r['nombre'],r['cantidadRecibida']+' '+r['unidadCompra'],r['unidadEntrega'],r.get('cantidadCanceladaEntrega','0'),r['cantidadDevueltaEntrega'],net,r['recibio']+' / '+('CANCELADA' if r['cancelada'] else 'CON CANCELACIÓN PARCIAL' if Decimal(r.get('cantidadCancelada','0')) else 'RECIBIDA')]+([r['costoUnitario'],fmt(Decimal(net)*Decimal(r['costoUnitario']))] if actor['role'] in APPROVERS else []))
  return report_pdf(rows,'GMP ERP · Relación de recepciones de compras',subtitle='Periodo por fecha de recepción: '+display_date(q.get('desde',''))+' a '+display_date(q.get('hasta',''))+'. Cantidades recibidas, canceladas, devueltas y netas por producto.'),'application/pdf'
 def transfer_pdf(self,id,q,actor):
  inv=self.inv;inv.scope(actor)
  with inv.store.connect() as db:
   row=db.execute('SELECT payload FROM inv_transfers WHERE id=?',(id,)).fetchone();d=json.loads(row[0]) if row else None
   if not d:raise ValueError('Traspaso no encontrado.')
   access=False
   for w in (d['origen'],d['destino']):
    try:inv.scope(actor,w,db);access=True
    except PermissionError:pass
   if not access:raise PermissionError('No tienes acceso a este traspaso.')
   def label(w):
    r=db.execute('SELECT company,branch FROM inv_warehouses WHERE id=?',(w,)).fetchone();co=db.execute('SELECT payload FROM cm_companies WHERE id=?',(r[0],)).fetchone();return (json.loads(co[0])['nombre'] if co else str(r[0]))+' / '+r[1]
   origin,destination=label(d['origen']),label(d['destino'])
  kind=q.get('tipo','SALIDA').upper();events=[]
  if kind=='SALIDA':events=[{'titulo':'Salida de traspaso' if d.get('fechaEnvio') else 'Solicitud de salida de traspaso','fecha':d.get('fechaEnvio',d['fecha']),'recibe':'','actor':d.get('enviadoPor',d['solicitadoPor']),'partidas':[{k:l[k] for k in ('sku','cantidad')} for l in d['partidas']]}]
  elif kind=='RECEPCION':
   if q.get('indice') not in (None,''):
    index=int(q['indice'])
    if index<0 or index>=len(d.get('recepciones',[])):raise ValueError('Recepción no disponible.')
    events=[d['recepciones'][index]]
   else:events=d.get('recepciones',[])
   if not events:raise ValueError('Aún no hay cantidades recibidas en este traspaso.')
  else:raise ValueError('Selecciona salida o recepción.')
  return transfer_document(d,events,origin,destination,actor['role'] in APPROVERS),'application/pdf'

def transfer_document(doc,events,origin,destination,costs):
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import A4
 from reportlab.lib.styles import ParagraphStyle
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,Table,TableStyle,PageBreak
 out=io.BytesIO();normal=ParagraphStyle('normal',fontName='Helvetica',fontSize=9,leading=12,spaceAfter=6);heading=ParagraphStyle('heading',parent=normal,fontName='Helvetica-Bold',fontSize=17,leading=21,spaceAfter=12);story=[]
 def p(v,style=normal):return Paragraph(html.escape(str(v or '')).replace('\n','<br/>'),style)
 for i,event in enumerate(events):
  if i:story.append(PageBreak())
  title=event.get('titulo') or ('Recepción real de traspaso' if event['tipo']=='recibir' else 'Regreso de material al origen');story.extend([p('GMP ERP · '+title,heading),p('Folio: '+doc['folio']+' · Estado: '+doc['estado']),p('Fecha: '+display_date(event['fecha'])),p('Origen: '+origin),p('Destino: '+destination),p('Entregó: '+doc.get('entrega','Pendiente')+' · Recibió: '+event.get('recibe','')+' · Registró: '+event['actor']),Spacer(1,10)]);rows=[['SKU','Descripción','Unidad','Cantidad real' if 'titulo' not in event else 'Cantidad']+(['Costo unitario','Importe'] if costs else [])]
  for l in event['partidas']:
   original=next(r for r in doc['partidas'] if r['sku']==l['sku']);cost=original.get('costo');rows.append([original['sku'],original['nombre'],original['unidad'],l['cantidad']]+([cost if cost is not None else 'Pendiente',fmt(Decimal(cost)*Decimal(l['cantidad'])) if cost is not None else 'Pendiente'] if costs else []))
  table=LongTable([[p(v) for v in row] for row in rows],repeatRows=1,colWidths=[(A4[0]-64)*r for r in ([.19,.29,.10,.16,.13,.13] if costs else [.20,.48,.14,.18])]);table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eee6ed')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));signatures=Table([['______________________']*3,['Entrega','Recibe','Autoriza']],colWidths=[(A4[0]-64)/3]*3);signatures.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story.extend([table,Spacer(1,18),p('Motivo: '+doc.get('motivo','')),Spacer(1,35),signatures])
 SimpleDocTemplate(out,pagesize=A4,leftMargin=32,rightMargin=32,topMargin=32,bottomMargin=32).build(story);return out.getvalue()
