"""Formato A4 de compras: cabecera, partidas, impuestos y textos largos paginados."""
import html,io,zipfile
from decimal import Decimal,ROUND_HALF_UP
from fechas import display_date
from app_info import TITLE,VERSION
from comercial_print import report_xlsx
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,LongTable,TableStyle,KeepTogether,Image

def order_pdf(doc,movement=None):
 out=io.BytesIO();small=ParagraphStyle('small',fontName='Helvetica',fontSize=8,leading=11,spaceAfter=4,splitLongWords=True);normal=ParagraphStyle('normal',parent=small,fontSize=10,leading=14);title=ParagraphStyle('title',parent=normal,fontSize=19,leading=23,spaceAfter=12);label=ParagraphStyle('label',parent=normal,fontName='Helvetica-Bold');white=ParagraphStyle('white',parent=small,textColor=colors.white,fontName='Helvetica-Bold')
 def p(value,style=small):return Paragraph(html.escape(str(value or '')).replace('\n','<br/>'),style)
 def footer(canvas,document):
  canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#64716D'));canvas.drawString(34,22,TITLE+' · v'+VERSION);canvas.drawRightString(A4[0]-34,22,'Página '+str(document.page));canvas.restoreState()
 company=doc['emisor'];vendor=doc['proveedor'];folio=movement['folio'] if movement else doc['folio'];kind=('Registro de compra' if movement['tipo']=='COMPRA' else 'Recepción de compra') if movement else 'Solicitud de cotización' if doc['estado'] in ('BORRADOR','ENVIADO') else 'Pedido de compra';story=[]
 import requisiciones
 logo=requisiciones.ROOT/'public/logo.png'
 if logo.exists():story.append(Image(str(logo),width=48,height=48,hAlign='RIGHT'))
 story.extend([p(company['nombre'],label),p(company.get('rfc','')+'\n'+company.get('domicilio',''),small),Spacer(1,12),p(kind+' #'+folio,title)])
 info=Table([[p('Proveedor',label),p('Envío / sucursal',label)],[p(vendor['nombre']+'\n'+vendor.get('rfc','')+'\n'+vendor.get('domicilio','')+'\n'+vendor.get('correo','')+'\n'+vendor.get('telefono',''),normal),p(doc['sucursal']+'\nRazón social: '+company['nombre'],normal)]],colWidths=[265,262]);info.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),12)]));story.extend([info,Spacer(1,10),p('Fecha del pedido: '+display_date(doc['fechaPedido'])+' · Entrega: '+display_date(doc.get('fechaEntrega',''))+'\nReferencia del proveedor: '+doc.get('referenciaProveedor','')+'\nEstado: '+doc['estado'],normal)])
 if movement and movement.get('cancelacion'):story.extend([p('RECEPCIÓN CANCELADA / DEVUELTA',label),p(display_date(movement['cancelacion']['fecha'])+' · '+movement['cancelacion']['motivo'],normal)])
 if movement:story.append(p('Origen: '+doc['folio']+' · Fecha: '+display_date(movement['fecha'])+' · Referencia: '+movement.get('referencia',''),normal))
 rows=[[p(v,white) for v in ['DESCRIPCIÓN','IMPUESTO','FECHA REQ.','CANT. / UNIDAD','PRECIO UNITARIO','MONTO']]];lines=doc['partidas'];selected={l['linea']:l for l in movement['partidas']} if movement else None;base=tax=Decimal(0)
 for l in lines:
  if selected is not None and l['linea'] not in selected:continue
  quantity=Decimal(selected[l['linea']]['cantidad'] if selected is not None else l['cantidad']);net=(quantity*Decimal(l['precio'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);impuesto=(quantity*Decimal(l['precio'])*Decimal(l['impuesto'])/100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);base+=net;tax+=impuesto
  name='['+(l['sku'] or str(l['materialId']))+'] '+l['nombre']+('\nOrigen: '+l['requisicionNumero'] if l.get('requisicionNumero') else '')+('\n'+l['observaciones'] if l.get('observaciones') else '')
  rows.append([p(name),p(l['tipoImpuesto']+' ('+l['impuesto']+'%)'),p(display_date(l['fechaRequerida'])),p(str(quantity)+'\n'+l['unidad']),p('$ '+format(Decimal(l['precio']),',.6f').rstrip('0').rstrip('.')),p('$ '+format(net,',.2f'))])
 table=LongTable(rows,colWidths=[177,60,65,77,76,72],repeatRows=1,splitInRow=1,hAlign='LEFT');table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#284E42')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),1,colors.HexColor('#284E42')),('LINEBELOW',(0,1),(-1,-1),.4,colors.HexColor('#DCE3DF')),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]));story.extend([Spacer(1,10),table,Spacer(1,12),KeepTogether([p('Subtotal: $ '+format(base,',.2f'),label),p('Impuestos: $ '+format(tax,',.2f'),label),p('Total: $ '+format(base+tax,',.2f'),label)])])
 for heading,value in [('Observaciones',movement.get('observaciones','') if movement else doc.get('observaciones','')),('Condiciones de compra',doc.get('condiciones',''))]:
  if value:story.extend([Spacer(1,12),p(heading,label),p(value,normal)])
 signature=Table([[p('_____________________\nRecibió')]],colWidths=[527]);signature.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]));story.extend([Spacer(1,28),signature]);SimpleDocTemplate(out,pagesize=A4,leftMargin=34,rightMargin=34,topMargin=30,bottomMargin=38,title=kind+' '+folio,author=TITLE).build(story,onFirstPage=footer,onLaterPages=footer);return out.getvalue()

def report_rows(result):
 rows=[['Folio','Fecha pedido','Fecha entrega','Razón social','Sucursal','Proveedor','Estado','Origen requisición','Subtotal','Impuestos','Total']]
 for d in result['pedidos']:rows.append([d['folio'],display_date(d['fechaPedido']),display_date(d.get('fechaEntrega','')),d['emisor']['nombre'],d['sucursal'],d['proveedor']['nombre'],d['estado'],', '.join(sorted({l['requisicionNumero'] for l in d['partidas'] if l.get('requisicionNumero')})),d['base'],d['importeImpuesto'],d['total']])
 return rows

def analyze_report(result):
 details=[];vendors={};totals={'pedidosConfirmados':0,'subtotal':Decimal(0),'impuestos':Decimal(0),'total':Decimal(0),'importeRecibido':Decimal(0),'importePendiente':Decimal(0),'importeComprado':Decimal(0),'importeDevuelto':Decimal(0),'importeRecibidoNeto':Decimal(0)}
 for d in result['pedidos']:
  included=d['estado'] not in ('BORRADOR','ENVIADO','CANCELADO');v=vendors.setdefault(d['proveedor']['id'],{'proveedor':d['proveedor']['nombre'],'documentos':0,'confirmados':0,'total':Decimal(0)});v['documentos']+=1
  if included:
   v['confirmados']+=1;v['total']+=Decimal(d['total']);totals['pedidosConfirmados']+=1;totals['subtotal']+=Decimal(d['base']);totals['impuestos']+=Decimal(d['importeImpuesto']);totals['total']+=Decimal(d['total'])
  for l in d['partidas']:
   qty=Decimal(l['cantidad']);received=Decimal(l['recibido']);billed=Decimal(l['comprado']);price=Decimal(l['precio']);factor=Decimal(l['factorEntrega']);tax=Decimal(l['impuesto']);r={**l,'idPedido':d['id'],'folio':d['folio'],'sucursal':d['sucursal'],'razonSocial':d['emisor']['nombre'],'proveedor':d['proveedor']['nombre'],'estado':d['estado'],'fechaPedido':d['fechaPedido'],'fechaEntrega':d.get('fechaEntrega',''),'pendiente':format(qty-received,'f'),'pendienteCompra':format(received-billed,'f'),'recibidoEntrega':format(received*factor,'f'),'pendienteEntrega':format((qty-received)*factor,'f'),'importeRecibido':format(received*price*(1+tax/100),'.2f'),'importePendiente':format((qty-received)*price*(1+tax/100),'.2f'),'importeComprado':format(billed*price*(1+tax/100),'.2f'),'incluido':included};returned=Decimal(l.get('devueltoProveedor','0'));r.update({'devueltoProveedor':format(returned,'f'),'recibidoNeto':format(received-returned,'f'),'importeDevuelto':format(returned*price*(1+tax/100),'.2f'),'importeRecibidoNeto':format((received-returned)*price*(1+tax/100),'.2f')});details.append(r)
   if included:
    for k in ('importeRecibido','importePendiente','importeComprado','importeDevuelto','importeRecibidoNeto'):totals[k]+=Decimal(r[k])
 for g in result['sucursales']:
  rows=[r for r in details if r['sucursal']==g['sucursal'] and r['incluido']]
  for k in ('importeRecibido','importePendiente','importeComprado'):g[k]=format(sum((Decimal(r[k]) for r in rows),Decimal(0)),'.2f')
 result.update({'detalle':details,'proveedores':[{**v,'total':format(v['total'],'.2f')} for v in vendors.values()],'resumen':{k:format(v,'.2f') if isinstance(v,Decimal) else v for k,v in totals.items()}});return result

DETAIL_HEADERS=['Folio','Fecha pedido','Fecha entrega','Razón social','Sucursal','Proveedor','Estado','SKU','Descripción','Cantidad','Unidad','Recibido','Pendiente','Comprado','Pendiente de comprar','Unidad entrega','Recibido entrega','Pendiente entrega','Precio antes de impuesto','Tasa %','Subtotal','Impuesto','Total','Importe recibido','Importe pendiente','Importe comprado','Requisición','Observaciones partida','Devuelto proveedor','Recibido neto','Importe devuelto','Importe recibido neto']
def detail_rows(result):
 return [DETAIL_HEADERS]+[[r['folio'],display_date(r['fechaPedido']),display_date(r['fechaEntrega']),r['razonSocial'],r['sucursal'],r['proveedor'],r['estado'],r['sku'],r['nombre'],r['cantidad'],r['unidad'],r['recibido'],r['pendiente'],r['comprado'],r['pendienteCompra'],r['unidadEntrega'],r['recibidoEntrega'],r['pendienteEntrega'],r['precio'],r['impuesto'],r['base'],r['importeImpuesto'],r['total'],r['importeRecibido'],r['importePendiente'],r['importeComprado'],r.get('requisicionNumero',''),r.get('observaciones',''),r['devueltoProveedor'],r['recibidoNeto'],r['importeDevuelto'],r['importeRecibidoNeto']] for r in result['detalle']]

def purchase_report_xlsx(result):
 orders=report_rows(result);chunks=max([1]+[(len(d.get('observaciones',''))+31999)//32000 for d in result['pedidos']]);orders[0]+= ['Referencia proveedor','Observaciones']+['Observaciones ('+str(i)+')' for i in range(2,chunks+1)]+['Condiciones']
 for row,d in zip(orders[1:],result['pedidos']):row.extend([d.get('referenciaProveedor','')]+[d.get('observaciones','')[i*32000:(i+1)*32000] for i in range(chunks)]+[d.get('condiciones','')])
 moves=[['Pedido','Sucursal','Proveedor','Movimiento','Tipo','Estado','Fecha','SKU','Descripción','Cantidad','Unidad','Cantidad entrega','Unidad entrega','Registró','Referencia','Observaciones','Motivo cancelación']]
 for d in result['pedidos']:
  for m in d.get('movimientos',[]):
   for l in m['partidas']:moves.append([d['folio'],d['sucursal'],d['proveedor']['nombre'],m['folio'],m['tipo'],'CANCELADA' if m.get('cancelacion') else 'VIGENTE',display_date(m['fecha']),l['sku'],l['nombre'],l['cantidad'],l['unidad'],l['cantidadEntrega'],l['unidadEntrega'],m['actor'],m.get('referencia',''),m.get('observaciones',''),(m.get('cancelacion') or {}).get('motivo','')])
 sheets=[('Pedidos',orders),('Partidas',detail_rows(result)),('Movimientos',moves),('Por sucursal',[['Sucursal','Emitidas','Borradores','Canceladas','Total','Importe recibido','Importe pendiente','Importe comprado']]+[[g[k] for k in ('sucursal','emitidas','borradores','canceladas','total','importeRecibido','importePendiente','importeComprado')] for g in result['sucursales']]),('Por proveedor',[['Proveedor','Documentos','Confirmados','Total']]+[[r[k] for k in ('proveedor','documentos','confirmados','total')] for r in result['proveedores']])];out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  with zipfile.ZipFile(io.BytesIO(report_xlsx(sheets[0][1],sheets[0][0]))) as first:
   for info in first.infolist():
    if info.filename in ('xl/workbook.xml','xl/_rels/workbook.xml.rels','[Content_Types].xml'):
     raw=first.read(info.filename).decode()
     for i,(name,_) in enumerate(sheets[1:],2):
      if info.filename=='xl/workbook.xml':raw=raw.replace('</sheets>',f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/></sheets>')
      elif info.filename.endswith('.rels'):raw=raw.replace('</Relationships>',f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/></Relationships>')
      else:raw=raw.replace('</Types>',f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
     z.writestr(info.filename,raw)
    else:z.writestr(info,first.read(info.filename))
  for i,(name,rows) in enumerate(sheets[1:],2):
   with zipfile.ZipFile(io.BytesIO(report_xlsx(rows,name))) as source:z.writestr(f'xl/worksheets/sheet{i}.xml',source.read('xl/worksheets/sheet1.xml'))
 return out.getvalue()

def purchase_report_pdf(result):
 from reportlab.lib.pagesizes import landscape
 out=io.BytesIO();style=ParagraphStyle('report',fontName='Helvetica',fontSize=8,leading=11);heading=ParagraphStyle('heading',parent=style,fontSize=15,leading=20,spaceBefore=12,spaceAfter=8)
 def p(v):return Paragraph(html.escape(str(v)).replace('\n','<br/>'),style)
 story=[Paragraph('GMP ERP · Reporte detallado de compras',heading),p('Solo pedidos confirmados se suman a los importes generales. Cantidades en la unidad indicada; recepciones canceladas se conservan en el historial.'),p('Total confirmado: $'+result['resumen']['total']+' · Recibido: $'+result['resumen']['importeRecibido']+' · Pendiente: $'+result['resumen']['importePendiente']+' · Comprado: $'+result['resumen']['importeComprado'])]
 for d in result['pedidos']:
  story.extend([Paragraph(html.escape(d['folio']+' · '+d['sucursal']+' · '+d['proveedor']['nombre']),heading),p(d['estado']+' · Pedido '+display_date(d['fechaPedido'])+' · Entrega '+display_date(d.get('fechaEntrega','')))])
  rows=[['SKU / Producto','Unidad','Pedido','Recibido','Pendiente','Comprado','Precio','Impuesto','Total']]
  for r in result['detalle']:
   if r['idPedido']==d['id']:rows.append([r['sku']+' · '+r['nombre']+('\nRequisición: '+r['requisicionNumero'] if r.get('requisicionNumero') else '')+('\n'+r['observaciones'] if r.get('observaciones') else ''),r['unidad'],r['cantidad'],r['recibido'],r['pendiente'],r['comprado'],r['precio'],r['impuesto']+'%',r['total']])
  t=LongTable([[p(v) for v in row] for row in rows],colWidths=[205,80,60,60,60,60,65,55,60],repeatRows=1,splitInRow=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eae1e7')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#dddddd'))]));story.append(t)
  for label in ('observaciones','condiciones'):
   if d.get(label):story.extend([p(label.capitalize()),p(d[label])])
 SimpleDocTemplate(out,pagesize=landscape(A4),leftMargin=30,rightMargin=30,topMargin=24,bottomMargin=24).build(story);return out.getvalue()
