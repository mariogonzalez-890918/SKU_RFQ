"""Entradas PT en D/E/F: cambios acotados al registro de un libro existente."""
import datetime as dt,io,posixpath,re,zipfile,shutil,copy,xml.etree.ElementTree as ET
from decimal import Decimal
from xml.sax.saxutils import escape

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def label(value):return str(value).strip().upper()
def norm(value):return re.sub(r'[ _]+',' ',str(value)).strip().upper()
def serial_date(value,date1904=False):
 date=dt.datetime.fromisoformat(value).replace(tzinfo=None);base=dt.datetime(1904,1,1) if date1904 else dt.datetime(1899,12,30)
 return format(Decimal(str((date-base).total_seconds()))/Decimal(86400),'.10f')
def cell(ref,value,numeric=False,style=None):
 attrs=' r="'+ref+'"'+(' s="'+str(style)+'"' if style is not None else '')
 return '<c'+attrs+'><v>'+str(value)+'</v></c>' if numeric else '<c'+attrs+' t="inlineStr"><is><t xml:space="preserve">'+escape(str(value))+'</t></is></c>'
def new_workbook(entries):
 rows=['<row r="1">'+''.join(cell(c+'1',v,style=2) for c,v in zip('ABCDEF',('IDMOVIMIENTO','FECHA','NUM DOCUMENTO','PRODUCTO','CANTIDAD','UOM')))+'</row>']
 for index,e in enumerate(entries,2):
  values=[(index-1,True,None),(serial_date(e['fecha']),True,1),(e['folio'],False,None),(e['descripcion'],False,None),(e['cantidad'] if e['estado']=='REGISTRADO' else '0',True,None),(e['unidad'],False,None)]
  rows.append('<row r="'+str(index)+'">'+''.join(cell(c+str(index),v,numeric,style) for c,(v,numeric,style) in zip('ABCDEF',values))+'</row>')
 sheet='<worksheet xmlns="'+NS['s']+'"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols>'+''.join('<col min="'+str(i)+'" max="'+str(i)+'" width="'+str(w)+'" customWidth="1"'+(' style="1"' if i==2 else '')+'/>' for i,w in enumerate((18,23,24,52,16,18),1))+'</cols><sheetData>'+''.join(rows)+'</sheetData><autoFilter ref="A1:F'+str(len(rows))+'"/></worksheet>'
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="'+NS['s']+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="REGISTRO ENTRADA" sheetId="1" r:id="rId1"/></sheets><calcPr calcMode="auto" fullCalcOnLoad="1"/></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
  z.writestr('xl/worksheets/sheet1.xml',sheet)
  z.writestr('xl/styles.xml','<styleSheet xmlns="'+NS['s']+'"><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy hh:mm:ss"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
 return out.getvalue()

def shift_formula(formula,delta):
 # Las partes citadas, nombres de hojas y referencias estructuradas no se alteran.
 parts=re.split(r'("(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'|\[[^\]]*\])',formula)
 for index in range(0,len(parts),2):
  def change(m):
   if m.group(2) or m.group(4)=='(':return m.group(0)
   row=int(m.group(3))+delta
   if not 1<=row<=1048576:raise ValueError('La fórmula no puede extenderse a la fila nueva.')
   return m.group(1)+str(row)+m.group(4)
  parts[index]=re.sub(r'(?<![A-Za-z0-9_.])((?:\$)?[A-Za-z]{1,3})(\$?)([1-9][0-9]*)(\(?)',change,parts[index])
 return ''.join(parts)

def merge_workbook(raw,entries,month):
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if sum(i.file_size for i in z.infolist())>256*1024*1024:raise ValueError('El libro es demasiado grande para validar sus registros.')
  wb=ET.fromstring(z.read('xl/workbook.xml'));rels={x.get('Id'):x.get('Target') for x in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))};sheets={s.get('name'):s for s in wb.find('s:sheets',NS)}
  candidates=[n for n in sheets if norm(n)=='REGISTRO ENTRADA']
  if len(candidates)!=1:raise ValueError('El libro debe contener una sola pestaña REGISTRO ENTRADA o registro_entrada.')
  name=candidates[0];target=rels[sheets[name].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
  ss=[''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
  def value(c):
   if c is None:return ''
   v=c.find('s:v',NS);text=v.text or '' if v is not None else ''.join(c.find('s:is',NS).itertext()) if c.find('s:is',NS) is not None else ''
   return ss[int(text)] if c.get('t')=='s' and text else text
  source=z.read(target).decode('utf8');root=ET.fromstring(source);sheetdata=root.find('s:sheetData',NS);parsed={int(r.get('r')):{re.sub('[0-9]','',c.get('r')):c for c in r} for r in sheetdata};head=parsed.get(1,{})
  if [norm(value(head.get(c))) for c in 'DEF']!=['PRODUCTO','CANTIDAD','UOM']:raise ValueError('Encabezados incompatibles: D debe ser PRODUCTO, E CANTIDAD y F UOM. El libro no se cambió.')
  date1904=wb.find('s:workbookPr',NS);date1904=date1904 is not None and date1904.get('date1904') in ('1','true')
  rowxml={int(m.group(1)):m.group(0) for m in re.finditer(r'<row\b[^>]*\br="([0-9]+)"[^>]*(?:/>|>.*?</row>)',source,re.S)}
  formulas={};styles={};docs={};last=1;identifier=0
  for col in root.findall('s:cols/s:col',NS):
   if col.get('style') and int(col.get('min'))<=2<=int(col.get('max')):styles['B']=col.get('style')
  for number,cells in parsed.items():
   for col,c in cells.items():
    if number==1:continue
    styles[col]=c.get('s')
    f=c.find('s:f',NS)
    if f is not None and f.text:formulas[col]=(number,f.text)
   if number==1 or not value(cells.get('D')):continue
   last=max(last,number);doc=value(cells.get('C'))
   if doc.startswith('PT-'):
    if doc in docs:raise ValueError('Hay folios PT duplicados en el libro. Revisa el registro antes de publicar.')
    docs[doc]=number
   a=value(cells.get('A'))
   if a.isdigit():identifier=max(identifier,int(a))
   b=value(cells.get('B'))
   if b and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',b):
    date=(dt.datetime(1904,1,1) if date1904 else dt.datetime(1899,12,30))+dt.timedelta(days=float(b))
    if date.strftime('%Y-%m')!=month:raise ValueError('El libro contiene entradas de otro mes. Prepara el inventario del mes '+month+' antes de publicar.')
  names={};units={}
  if 'PRODUCTOS' in sheets:
   p=rels[sheets['PRODUCTOS'].get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];p=p.lstrip('/') if p.startswith('/') else posixpath.normpath('xl/'+p)
   bysku={};byname={}
   for row in ET.fromstring(z.read(p)).findall('s:sheetData/s:row',NS):
    cells={re.sub('[0-9]','',c.get('r')):c for c in row};sku=value(cells.get('A'));description=value(cells.get('H'));unit=value(cells.get('O'))
    if int(row.get('r'))==1 or not description:continue
    item=(description,unit);bysku.setdefault(sku,set()).add(item);byname.setdefault(label(description),set()).add(item)
   for e in entries:
    choices=bysku.get(e['sku']) or byname.get(label(e['descripcion'])) or set()
    if len(choices)!=1:raise ValueError('El SKU '+e['sku']+' no tiene una coincidencia única en PRODUCTOS del libro. Actualiza ese maestro antes de publicar.')
    description,unit=next(iter(choices));aliases={'PIEZAS':'PIEZA','PZA':'PIEZA','PZ':'PIEZA','UNIDADES':'UNIDAD','KG':'KILOGRAMO','KGS':'KILOGRAMO','KILOGRAMOS':'KILOGRAMO','LTS':'LITRO','LT':'LITRO','LITROS':'LITRO'}
    if unit and aliases.get(label(unit),label(unit))!=aliases.get(label(e['unidad']),label(e['unidad'])):raise ValueError('La unidad del SKU '+e['sku']+' no coincide entre GMP y el libro; no se convirtió la cantidad.')
    names[e['folio']]=description
  replacements={};newrows=[]
  for e in entries:
   number=docs.get(e['folio']);known=number is not None
   if known:
    cells=parsed[number]
    if value(cells.get('D')).strip()!=names.get(e['folio'],e['descripcion']).strip() or label(value(cells.get('F')))!=label(e['unidad']):raise ValueError('Un folio PT existente no corresponde al mismo producto o unidad. No se cambió el libro.')
    try:same_date=abs(Decimal(value(cells.get('B')))-Decimal(serial_date(e['fecha'],date1904)))<Decimal('0.0000001')
    except Exception:same_date=False
    if not same_date:raise ValueError('Un folio PT existente tiene otra fecha de captura. No se cambió el libro.')
   else:last+=1;number=last;identifier+=1
   if number>1048576:raise ValueError('El registro de Excel llegó a su límite de filas.')
   text=rowxml.get(number,'<row r="'+str(number)+'"></row>');text=re.sub(r'/>$','></row>',text);cells=parsed.get(number,{})
   values={'E':(e['cantidad'] if e['estado']=='REGISTRADO' else '0',True)}
   if not known:values.update({'A':(identifier,True),'B':(serial_date(e['fecha'],date1904),True),'C':(e['folio'],False),'D':(names.get(e['folio'],e['descripcion']),False),'F':(e['unidad'],False)})
   fragments={re.match(r'<c\b[^>]*\br="([A-Z]+)[0-9]+"',m.group(0)).group(1):m.group(0) for m in re.finditer(r'<c\b[^>]*\br="[A-Z]+[0-9]+"[^>]*(?:/>|>.*?</c>)',text,re.S)}
   for col,(v,numeric) in values.items():fragments[col]=cell(col+str(number),v,numeric,cells.get(col).get('s') if col in cells else styles.get(col))
   if not known:
    for col,(anchor,formula) in formulas.items():
     if col in set('ABCDEF') or col in fragments:continue
     fragments[col]='<c r="'+col+str(number)+'"'+(' s="'+styles[col]+'"' if styles.get(col) is not None else '')+'><f>'+escape(shift_formula(formula,number-anchor))+'</f></c>'
   for col,textcell in list(fragments.items()):
    if '<f' in textcell:fragments[col]=re.sub(r'<v(?:\s[^>]*)?>.*?</v>|<v\s*/>','',textcell,flags=re.S)
   def order(col):
    n=0
    for c in col:n=n*26+ord(c)-64
    return n
   opening=text[:text.index('>')+1];text=opening+''.join(fragments[c] for c in sorted(fragments,key=order))+'</row>'
   if number in rowxml:replacements[number]=text
   else:newrows.append(text)
  updated=re.sub(r'<row\b[^>]*\br="([0-9]+)"[^>]*(?:/>|>.*?</row>)',lambda m:replacements.get(int(m.group(1)),m.group(0)),source,flags=re.S)
  updated=updated.replace('</sheetData>',''.join(newrows)+'</sheetData>')
  def expand(m):
   col=m.group(1);return col+str(max(int(m.group(2)),last))
  def expand_ref_tags(text,tags):
   return re.sub(r'<(?:'+tags+r')\b[^>]*>',lambda m:re.sub(r'(?<=:)(\$?[A-Z]+\$?)([0-9]+)(?=")',expand,m.group(0)),text)
  updated=expand_ref_tags(updated,'dimension|autoFilter')
  ET.fromstring(updated);changes={target:updated.encode()}
  workbook=z.read('xl/workbook.xml').decode()
  if '<calcPr' in workbook:workbook=re.sub(r'<calcPr\b[^>]*/>',lambda m:re.sub(r'\s(?:fullCalcOnLoad|forceFullCalc|calcMode)="[^"]*"','',m.group(0))[:-2]+' fullCalcOnLoad="1" forceFullCalc="1" calcMode="auto"/>',workbook)
  else:workbook=workbook.replace('</workbook>','<calcPr fullCalcOnLoad="1" forceFullCalc="1" calcMode="auto"/></workbook>')
  refs=re.compile(re.escape("'"+name.replace("'","''")+"'!")+r'(\$?[A-Z]+\$?[0-9]+:\$?[A-Z]+\$?)([0-9]+)')
  def expand_inputs(text):return refs.sub(lambda m:m.group(0)[:-len(m.group(2))]+str(max(int(m.group(2)),last)),text)
  workbook=re.sub(r'<definedName\b[^>]*>.*?</definedName>',lambda m:expand_inputs(m.group(0)),workbook,flags=re.S)
  changes['xl/workbook.xml']=workbook.encode()
  for path in z.namelist():
   if path==target or not re.fullmatch(r'xl/worksheets/sheet[0-9]+\.xml',path):continue
   found=False;tail=b''
   with z.open(path) as stream:
    while True:
     chunk=stream.read(1024*1024)
     if not chunk:break
     data=tail+chunk
     if name.encode() in data:found=True;break
     tail=data[-200:]
   if not found:continue
   original=z.read(path).decode();modified=re.sub(r'<f\b[^>]*>.*?</f>',lambda m:expand_inputs(m.group(0)),original,flags=re.S)
   if modified!=original:changes[path]=modified.encode()
  # Actualizar únicamente tablas y cachés cuyo origen es la hoja de entradas.
  relpath=posixpath.dirname(target)+'/_rels/'+posixpath.basename(target)+'.rels'
  table_names=set()
  if relpath in z.namelist():
   for rel in ET.fromstring(z.read(relpath)):
    if not rel.get('Type','').endswith('/table'):continue
    link=rel.get('Target');path=link.lstrip('/') if link.startswith('/') else posixpath.normpath(posixpath.dirname(target)+'/'+link);table=z.read(path).decode();definition=ET.fromstring(table);table_names.add(definition.get('name'));table_names.add(definition.get('displayName'))
    if re.search(r'totalsRowCount="[1-9]',table):raise ValueError('La tabla de entradas tiene una fila de totales. Prepara una tabla de captura sin totales antes de publicar.')
    changes[path]=expand_ref_tags(table,'table|autoFilter').encode()
  for path in z.namelist():
   if not re.fullmatch(r'xl/pivotCache/pivotCacheDefinition[0-9]+\.xml',path):continue
   text=z.read(path).decode();cache=ET.fromstring(text);src=cache.find('s:cacheSource/s:worksheetSource',NS)
   if src is not None and (src.get('sheet')==name or src.get('name') in table_names-{None}):
    text=expand_ref_tags(text,'worksheetSource')
    text=re.sub(r'<pivotCacheDefinition\b[^>]*>',lambda m:re.sub(r'\srefreshOnLoad="[^"]*"','',m.group(0))[:-1]+' refreshOnLoad="1">',text,count=1);changes[path]=text.encode()
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dest:
   for info in z.infolist():
    if info.filename in changes:dest.writestr(copy.copy(info),changes[info.filename])
    else:
     with z.open(info) as source,dest.open(copy.copy(info),'w') as output:shutil.copyfileobj(source,output,1024*1024)
  return out.getvalue()
