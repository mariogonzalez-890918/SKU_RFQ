"""Descargas de reportes; las cifras y permisos se calculan siempre en el servidor."""
import decimal,html,io,json,re,zipfile
from app_info import TITLE,VERSION,SUPPORT_LINE
from xml.sax.saxutils import escape

def _metadata(r):
 c=r['configuracion'];s=r['resumen']
 return [[TITLE+' v'+VERSION,c['nombre']],['Versión',VERSION],['Soporte',SUPPORT_LINE],['Generado',r['generado']],['Alcance autorizado',', '.join(r['alcance']) or 'Sin coincidencias'],['Desde / hasta',(c.get('desde') or 'Sin inicio')+' / '+(c.get('hasta') or 'Sin fin')],['Áreas',', '.join(c.get('areas',[])) or 'Todas'],['Solicitante contiene',c.get('solicitante','')],['Material / SKU contiene',c.get('material','')],['Folio contiene',c.get('folios','')],['Base de valuación',r['baseValuacion']],['Impuestos',', '.join(t['nombre']+' '+t['tasa']+'%' for t in c['impuestos']) or 'Sin impuestos adicionales'],['Requisiciones',s['requisiciones']],['Partidas',s['partidas']],['Canceladas excluidas',s.get('canceladasExcluidas',0)],['Partidas pendientes de costo',s['pendientes']],['Costo de compra valorizado',decimal.Decimal(s['base'])],['Impuestos valorizados',decimal.Decimal(s['impuestos'])],['Total valorizado'+(' PARCIAL' if s['pendientes'] else ''),decimal.Decimal(s['total'])]]

def _number(value):return decimal.Decimal(value) if value is not None else None

def report_xlsx(r):
 sheets=[('Resumen',_metadata(r),[36,110],False),('Grupos',[['GRUPO','ID MATERIAL','UNIDAD','CANTIDAD','REQUISICIONES','COSTO COMPRA','IMPUESTOS','TOTAL','PENDIENTES']]+[[g['grupo'],g['materialId'] or '',g['unidad'],_number(g['cantidad']),g['requisiciones'],_number(g['base']),_number(g['impuestos']),_number(g['total']),g['pendientes']] for g in r['grupos']],[40,14,20,18,18,22,22,22,16],True)]
 taxes=r['configuracion']['impuestos']
 headers=['FOLIO','FECHA','SUCURSAL','ÁREA','SOLICITANTE','SKU','DESCRIPCIÓN','CANTIDAD','UNIDAD','COSTO UNITARIO','COSTO COMPRA']+[t['nombre']+' '+t['tasa']+'%' for t in taxes]+['IMPUESTOS','TOTAL','PENDIENTE / ORIGEN']
 rows=[headers]
 for d in r['detalle']:
  rows.append([d['folio'],d['fecha'],d['sucursal'],d['area'],d['solicitante'],d['sku'],d['descripcion'],_number(d['cantidad']),d['unidad'],_number(d['costoUnitario']),_number(d['costoCompra'])]+[_number(t['importe']) for t in d['impuestos']]+[_number(d['importeImpuestos']),_number(d['total']),d['pendiente'] or d['origenCosto']])
 sheets.append(('Detalle',rows,[24,14,20,36,30,22,55,18,22,24,24]+[22]*len(taxes)+[22,24,65],True))
 def col(n):
  s=''
  while n:n,v=divmod(n-1,26);s=chr(65+v)+s
  return s
 def clean(value):return re.sub('[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value))[:32767]
 def cell(value,address,header=False):
  style='1' if header else '0'
  if isinstance(value,(int,decimal.Decimal)):
   # Excel conserva hasta 15 cifras significativas; importes mayores se preservan como texto.
   if not isinstance(value,decimal.Decimal) or len(value.as_tuple().digits)<=15:
    return '<c r="'+address+'" s="'+('2' if isinstance(value,decimal.Decimal) else style)+'"><v>'+str(value)+'</v></c>'
  return '<c r="'+address+'" s="'+style+'" t="inlineStr"><is><t xml:space="preserve">'+escape(clean('' if value is None else value))+'</t></is></c>'
 output=io.BytesIO();ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join('<Override PartName="/xl/worksheets/sheet'+str(i)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join('<sheet name="'+name+'" sheetId="'+str(i)+'" r:id="rId'+str(i)+'"/>' for i,(name,*_) in enumerate(sheets,1))+'</sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join('<Relationship Id="rId'+str(i)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+str(i)+'.xml"/>' for i in range(1,len(sheets)+1))+'<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
  z.writestr('xl/styles.xml','<styleSheet xmlns="'+ns+'"><numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00######"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF284E42"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf xfId="0" fontId="0" fillId="0" borderId="0" numFmtId="0"/><xf xfId="0" fontId="1" fillId="2" borderId="0" numFmtId="0" applyFill="1" applyFont="1"><alignment wrapText="1" vertical="top"/></xf><xf xfId="0" fontId="0" fillId="0" borderId="0" numFmtId="164" applyNumberFormat="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
  for i,(name,rows,widths,filtered) in enumerate(sheets,1):
   xml='<worksheet xmlns="'+ns+'"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>'+''.join('<col min="'+str(j)+'" max="'+str(j)+'" width="'+str(w)+'" customWidth="1"/>' for j,w in enumerate(widths,1))+'</cols><sheetData>'
   xml+=''.join('<row r="'+str(n)+'">'+''.join(cell(value,col(j)+str(n),n==1) for j,value in enumerate(row,1))+'</row>' for n,row in enumerate(rows,1))+'</sheetData>'
   if filtered:xml+='<autoFilter ref="A1:'+col(len(widths))+str(len(rows))+'"/>'
   z.writestr('xl/worksheets/sheet'+str(i)+'.xml',xml+'</worksheet>')
 return output.getvalue()

def report_pdf(r):
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import landscape,A4
 from reportlab.lib.styles import ParagraphStyle
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,LongTable,TableStyle,PageBreak,KeepTogether
 if len(r['detalle'])>10000:raise ValueError('Para PDF reduce los filtros a 10,000 partidas. Excel y CSV incluyen el detalle completo.')
 out=io.BytesIO();page=landscape(A4);doc=SimpleDocTemplate(out,pagesize=page,rightMargin=25,leftMargin=25,topMargin=28,bottomMargin=32,title=r['configuracion']['nombre'],author='Grupo Mi Pan')
 normal=ParagraphStyle('GMP',fontName='Helvetica',fontSize=8,leading=11,spaceAfter=5)
 small=ParagraphStyle('Small',parent=normal,fontSize=7,leading=9,spaceAfter=0)
 heading=ParagraphStyle('Heading',parent=normal,fontSize=18,leading=22,textColor=colors.HexColor('#284e42'),spaceAfter=12)
 white=ParagraphStyle('White',parent=small,textColor=colors.white,fontName='Helvetica-Bold')
 def p(v,style=small):return Paragraph(html.escape(str('—' if v is None else v)).replace('\n','<br/>'),style)
 def fmt(v):return 'PENDIENTE' if v is None else '$ '+format(decimal.Decimal(v),',.2f')
 def table(rows,widths):
  t=LongTable([[p(v,white if n==0 else small) for v in row] for n,row in enumerate(rows)],colWidths=widths,repeatRows=1,hAlign='LEFT')
  t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#284e42')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f3f4ef')]),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#284e42')),('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5)]))
  return t
 width=page[0]-50;story=[p(TITLE+' v'+VERSION,heading),p(r['configuracion']['nombre'],heading)]
 for key,value in _metadata(r)[1:-7]:story.append(p(key+': '+str(value),normal))
 s=r['resumen'];story.extend([p('Requisiciones: '+str(s['requisiciones'])+' · Partidas: '+str(s['partidas'])+' · Canceladas excluidas: '+str(s.get('canceladasExcluidas',0)),normal),p(('TOTAL PARCIAL · ' if s['pendientes'] else '')+'Costo compra: '+fmt(s['base'])+' · Impuestos: '+fmt(s['impuestos'])+' · Total valorizado: '+fmt(s['total']),normal),p('Partidas pendientes de costo o equivalencia: '+str(s['pendientes'])+'. No se consideran costo cero.',normal),Spacer(1,10)])
 groups=[['Grupo','Cantidad / unidad','Solicitudes','Costo compra','Impuestos','Total','Pendientes']]+[[g['grupo'],(g['cantidad']+' '+g['unidad']) if g['cantidad'] is not None else '—',g['requisiciones'],fmt(g['base']),fmt(g['impuestos']),fmt(g['total']),g['pendientes']] for g in r['grupos']]
 story.append(table(groups,[width*x for x in (.30,.16,.09,.13,.11,.13,.08)]))
 if r['detalle']:
  story.extend([PageBreak(),p('Detalle de requisiciones',heading)])
  rows=[['Folio / fecha','Sucursal / área','Material / SKU','Cantidad / unidad','Costo unitario','Costo compra','Impuestos','Total']]
  for d in r['detalle']:
   review='\nPENDIENTE: '+d['pendiente'] if d['pendiente'] else ''
   unit_price='PENDIENTE' if d['costoUnitario'] is None else '$ '+format(decimal.Decimal(d['costoUnitario']),',.6f').rstrip('0').rstrip('.')
   rows.append([d['folio']+'\n'+d['fecha'],d['sucursal']+'\n'+d['area']+'\n'+d['solicitante'],d['descripcion']+'\n'+(d['sku'] or 'ID '+str(d['materialId']))+review,d['cantidad']+' '+d['unidad'],unit_price,fmt(d['costoCompra']),fmt(d['importeImpuestos']),fmt(d['total'])])
  story.append(table(rows,[width*x for x in (.12,.16,.24,.10,.10,.10,.08,.10)]))
 def footer(canvas,document):
  canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#555555'));canvas.drawString(25,16,'GMP · '+r['generado']+' · Canceladas excluidas del costeo');canvas.drawRightString(page[0]-25,16,'Página '+str(document.page));canvas.restoreState()
 doc.build(story,onFirstPage=footer,onLaterPages=footer);return out.getvalue()

