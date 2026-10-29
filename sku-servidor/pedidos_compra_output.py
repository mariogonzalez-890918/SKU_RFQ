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

def purchase_report_xlsx(result):
 detail=report_xlsx(report_rows(result),'Pedidos');summary=report_xlsx([['Sucursal','Emitidas','Borradores','Canceladas','Total']]+[[g['sucursal'],g['emitidas'],g['borradores'],g['canceladas'],g['total']] for g in result['sucursales']],'Por sucursal');out=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(detail)) as source,zipfile.ZipFile(io.BytesIO(summary)) as second,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as target:
  for info in source.infolist():
   raw=source.read(info.filename)
   if info.filename=='xl/workbook.xml':raw=raw.decode().replace('</sheets>','<sheet name="Por sucursal" sheetId="2" r:id="rId2"/></sheets>').encode()
   if info.filename=='xl/_rels/workbook.xml.rels':raw=raw.decode().replace('</Relationships>','<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>').encode()
   if info.filename=='[Content_Types].xml':raw=raw.decode().replace('</Types>','<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>').encode()
   target.writestr(info,raw)
  target.writestr('xl/worksheets/sheet2.xml',second.read('xl/worksheets/sheet1.xml'))
 return out.getvalue()
