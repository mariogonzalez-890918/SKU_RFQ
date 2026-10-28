"""Documentos comerciales. El ticket usa una lista explícita sin datos fiscales."""
import csv,html,io,zipfile,re
from decimal import Decimal

def esc(v):return html.escape(str(v),quote=True)

def document_html(doc,channel):
 ticket=channel=='expendios';settings=doc.get('ticket',{});logo='<img src="/logo.png" alt="Mi Pan" class="logo">'
 if ticket:
  header=(logo if settings.get('mostrarLogo',True) else '')+('<h2>'+esc(doc['sucursal'])+'</h2>' if settings.get('mostrarSucursal',True) else '')
  subtitle='Ticket '+esc(doc['folio'])+'<br>Folio interno '+esc(doc['folioInterno'])
 else:
  company=doc['emisor'];customer=doc.get('cliente') or {}
  header=logo+'<h1>'+esc(company['nombre'])+'</h1><p>'+esc(company.get('rfc',''))+'<br>'+esc(company.get('domicilio',''))+'</p>'
  subtitle=esc(doc['tipo'])+' '+esc(doc['folio'])+'<p>Cliente: '+esc(customer.get('nombre','Público general'))+'<br>'+esc(customer.get('domicilio',''))+'</p>'
 rows=''.join('<tr><td>'+esc(r['nombre'])+'<small>'+esc(r['sku'])+'</small></td><td>'+esc(r['cantidad'])+' '+esc(r['unidad'])+'</td><td>$'+esc(r['precio'])+'</td><td>$'+esc(r['total'])+'</td></tr>' for r in doc['partidas'])
 css='@page{size:80mm auto;margin:4mm}body{width:72mm;margin:0;font:11px Arial}.logo{width:30mm}h2{font-size:15px}' if ticket else '@page{size:A4;margin:15mm}body{font:13px Arial;max-width:900px;margin:auto}.logo{width:85px;float:right}'
 return ('<!doctype html><html lang="es"><meta charset="utf-8"><title>'+esc(doc['folio'])+'</title><style>'+css+'table{width:100%;border-collapse:collapse}td,th{padding:6px 2px;border-bottom:1px solid #ddd;text-align:left}small{display:block;font-size:.8em}.total{text-align:right;font-weight:bold;font-size:1.3em}.sign{margin-top:35px;border-top:1px solid #555;text-align:center}@media print{button{display:none}}</style><button onclick="window.print()">Imprimir / Guardar PDF</button><header>'+header+'</header><p>'+subtitle+'<br>'+esc(doc['fecha'][:19])+' · '+esc(doc['estado'])+'</p><table><thead><tr><th>Producto</th><th>Cantidad</th><th>Precio</th><th>Total</th></tr></thead><tbody>'+rows+'</tbody></table><p>Subtotal $'+esc(doc['base'])+'<br>IVA incluido $'+esc(doc['impuesto'])+'</p><p class="total">TOTAL $'+esc(doc['total'])+'</p>'+('<p>Recibido $'+esc(doc['pago']['recibido'])+' · Cambio $'+esc(doc['pago']['cambio'])+'</p>' if ticket else '<p>'+esc(doc.get('condiciones',''))+'</p>')+'<div class="sign">Recibió / Firma</div></html>').encode()

COLUMNS={'folio':'Folio','fecha':'Fecha','estado':'Estado','sucursal':'Sucursal','cliente':'Cliente','sku':'SKU','descripcion':'Descripción','cantidad':'Cantidad','unidad':'Unidad','precio':'Precio con IVA','iva':'IVA %','base':'Subtotal','impuesto':'IVA incluido','total':'Total'}

def report_rows(result,columns=None,selection=None):
 columns=columns or list(COLUMNS)
 if not isinstance(columns,list) or not columns or len(set(columns))!=len(columns) or any(c not in COLUMNS for c in columns):raise ValueError('Selecciona columnas válidas.')
 docs=result['documentos']
 if selection is not None:
  if not isinstance(selection,list) or set(selection)-{d['id'] for d in docs}:raise ValueError('La selección no pertenece al resultado autorizado.')
  docs=[d for d in docs if d['id'] in selection]
 rows=[[COLUMNS[c] for c in columns]];total=Decimal(0)
 for doc in docs:
  if doc['estado']=='CANCELADO':continue
  total+=Decimal(doc['total'])
  for line in doc['partidas']:
   v={**doc,**line,'descripcion':line['nombre'],'cliente':(doc.get('cliente') or {}).get('nombre','Público general')};rows.append([str(v.get(c,'')) for c in columns])
 rows.append([str(total) if c=='total' else 'GRAN TOTAL' if i==0 else '' for i,c in enumerate(columns)])
 return rows

def report_csv(rows):
 out=io.StringIO();writer=csv.writer(out,delimiter=';')
 # Evita interpretar nombres/códigos como fórmulas al abrir CSV en Excel.
 writer.writerows([[("'"+v) if v.startswith(('=','+','-','@')) else v for v in row] for row in rows]);return ('\ufeff'+out.getvalue()).encode('utf8')

def report_xlsx(rows):
 from xml.sax.saxutils import escape
 def column(n):
  value=''
  while n:n,r=divmod(n-1,26);value=chr(65+r)+value
  return value
 def cell(v,i,j):
  ref=column(j)+str(i)
  numeric=i>1 and rows[0][j-1] in ('Cantidad','Precio con IVA','IVA %','Subtotal','IVA incluido','Total') and re.fullmatch(r'\d+(?:\.\d+)?',v) and len(v.replace('.','').lstrip('0'))<=15
  return '<c r="'+ref+'"><v>'+v+'</v></c>' if numeric else '<c r="'+ref+'" t="inlineStr"><is><t xml:space="preserve">'+escape(v)+'</t></is></c>'
 sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join('<row r="'+str(i)+'">'+''.join(cell(v,i,j) for j,v in enumerate(row,1))+'</row>' for i,row in enumerate(rows,1))+'</sheetData></worksheet>'
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Reporte" sheetId="1" r:id="rId1"/></sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>');z.writestr('xl/worksheets/sheet1.xml',sheet)
 return out.getvalue()

def report_pdf(rows):
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import A4,landscape
 from reportlab.lib.styles import ParagraphStyle
 from reportlab.platypus import SimpleDocTemplate,LongTable,TableStyle,Paragraph,Spacer
 out=io.BytesIO();page=landscape(A4);style=ParagraphStyle('cm',fontName='Helvetica',fontSize=7,leading=9);heading=ParagraphStyle('heading',fontName='Helvetica-Bold',fontSize=16,leading=22)
 cells=[[Paragraph(esc(v),style) for v in row] for row in rows];table=LongTable(cells,repeatRows=1,colWidths=[(page[0]-40)/len(rows[0])]*len(rows[0]))
 table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eae1e7')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f6f7f8')]),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7)]))
 SimpleDocTemplate(out,pagesize=page,leftMargin=20,rightMargin=20,topMargin=24,bottomMargin=24).build([Paragraph('RFQ_SKU_GMP · Reporte comercial',heading),Paragraph('Documentos cancelados excluidos de los totales.',style),Spacer(1,12),table]);return out.getvalue()
