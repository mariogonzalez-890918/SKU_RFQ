from permissions import require_module
"""Catálogo de ventas independiente: SKU históricos inmutables y sufijo de colisión."""
import base64,copy,datetime,io,json,pathlib,re,unicodedata,zipfile,xml.etree.ElementTree as ET

ROOT=pathlib.Path(__file__).resolve().parent
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
N={'m':NS}
ALPHABET='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
TIP={'PP':'PRODUCTO EN PROCESO','PT':'PRODUCTO TERMINADO'}
CAT=dict(zip('AP GE LI MA PB PD PG PM RE RP TO'.split(),['ALIMENTOS PREPARADOS','GELATINAS','LIQUIDOS','MASAS','PAN BLANCO','PAN DULCE','PASTELES Y GALLETAS','PLANCHAS Y MAMONES','REPOSTERIA','REPROCESO','TORTILLA']))
SUB={str(i+1).zfill(2):v for i,v in enumerate(['BAGEL','BARRA','BASE PARA PIZZA','BATIDO','BIZCOCHO','BOCADILLOS','BOLILLO','BOLLO','CHAPATA','CHESSECAKE','ESPECIALIDAD','GALLETAS','GELATINA COMBINADA','GELATINA DE AGUA','GELATINA DE LECHE','GELATINA ESPECIAL','LACTEOS','MASA PAN BLANCO','PAN BLANCO','PAN DE CAJA','PAN DE ESPECIES','PAN DE HOT DOG','PAN DULCE','PAN ESPAÑOL','PAN MOLIDO','PASTEL COMERCIAL','PASTEL PEDIDO','PIZZA','POLVORON','POSTRE','PRODUCTO DE TEMPORADA','REPOSTERIA','REPOSTERIA FINA','RUSTICO','TELERA','TORTILLA DE HARINA','VARIEDAD','VARIOS'])}
PDV={f'A{i+1:02}':v for i,v in enumerate(['BIZCOCHO','CAFETERIA','CHEESECAKE','DONA','EMPACADO','GALLETAS','GELATINAS','MINI Y REB','PASTEL 10 PORCIONES','PASTEL 20 PORCIONES','PAN BLANCO','PASTEL MINI','PASTEL PEDIDO','PIZZA','PAN PEDIDO','POSTRE','PRODUCTO DE TEMPORADA','PASTEL BARRA','REPOSTERIA','REPOSTERIA FINA','RUSTICO','VELA'])}
ALIASES={'PRODUCTOS EN PROCESO':'PRODUCTO EN PROCESO','RUSTICOS':'RUSTICO','GELATINAS COMBINADAS':'GELATINA COMBINADA','CHEESECAKE':'CHESSECAKE'}
def norm(v):return ' '.join(''.join(c for c in unicodedata.normalize('NFD',str(v or '')) if not unicodedata.combining(c)).upper().split())
def resolve(v,table):
 s=norm(v);s=ALIASES.get(s,s)
 return next((k for k,name in table.items() if s in (k,norm(name))), '00')
def resolve_pdv(value):
 s=norm(value)
 if s=='CHESSECAKE':s='CHEESECAKE'
 return next((k for k,name in PDV.items() if s in (k,norm(name))), '000')
def key_from_name(name):
 words=re.findall(r'[A-Z]+',norm(re.sub(r'\d+(?:[.,]\d+)*',' ',str(name))))
 initials=''.join(w[0] for w in words if w not in {'LA','LOS','EL','DEL'})[:7]
 if not initials:raise ValueError('La descripción requiere al menos una palabra para generar la clave.')
 return initials.ljust(7,'0')
def row_identity(r):return tuple(norm(r.get(k)) for k in ('tipo','categoria','subcategoria','nombre'))
def classify(row):
 return {'tipo':resolve(row.get('B'),TIP),'categoria':resolve(row.get('C'),CAT),'subcategoria':resolve(row.get('D'),SUB),'originalTipo':row.get('B',''),'originalCategoria':row.get('C',''),'originalSubcategoria':row.get('D','')}
def read_master(master,sheet_name='SUGERIDO'):
 try:raw=base64.b64decode(master,validate=True)
 except Exception:raise ValueError('Maestro de ventas inválido.')
 if len(raw)>15*1024*1024:raise ValueError('El maestro de ventas supera 15 MB.')
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('El contenido del Excel supera 100 MB.')
  wb=ET.fromstring(z.read('xl/workbook.xml'));rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'));targets={r.get('Id'):r.get('Target') for r in rels}
  sheet=next((s for s in wb.findall('m:sheets/m:sheet',N) if s.get('name')==sheet_name),None)
  if sheet is None:raise ValueError('Falta la hoja '+sheet_name+'.')
  target=targets[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];path=target.lstrip('/') if target.startswith('/') else 'xl/'+target.lstrip('./')
  strings=[]
  if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(t.text or '' for t in si.iter('{'+NS+'}t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
  xml=z.read(path).decode('utf8');doc=ET.fromstring(xml);rows=[]
  for row in doc.findall('m:sheetData/m:row',N):
   values={'fila':int(row.get('r')),'_tipos':{}}
   for c in row.findall('m:c',N):
    col=re.sub(r'\d','',c.get('r'));value=c.findtext('m:v','',N);kind=c.get('t')
    values['_tipos'][col]=kind or 'n'
    values[col]=strings[int(value)] if kind=='s' and value else ''.join(t.text or '' for t in c.iter('{'+NS+'}t')) if kind=='inlineStr' else value
   if values.get('H','').strip():rows.append(values)
  if not rows or norm(rows[0].get('A'))!='SKU' or norm(rows[0].get('H'))!='DESCRIPCION':raise ValueError('Se requiere SKU en A y DESCRIPCIÓN en H de SUGERIDO.')
  return raw,path,xml,rows[1:]
def initial(master):
 _,_,_,rows=read_master(master);records=[];skus=set()
 for row in rows:
  s=norm(row.get('A'))
  if s and (not re.fullmatch('[A-Z0-9]{14}',s) or s in skus):raise ValueError(f'SKU histórico inválido o repetido en fila {row["fila"]}.')
  if s:skus.add(s)
  records.append({'id':len(records)+1,**classify(row),'nombre':row['H'],'sku':s,'anterior':s,'clave':s[6:13] if s else '', 'digito':s[-1:] if s else '', 'modulo':resolve_pdv(row.get('F','')),'originalModulo':row.get('F',''),'fila':row['fila'],'estado':row.get('S') or 'ACTIVO','eliminado':False,'validado':bool(s),'editado':False,'camposExcel':{k:v for k,v in row.items() if re.fullmatch('[A-Z]+',k)},'tiposExcel':row['_tipos']})
 state={'version':1,'maxId':len(records),'registros':records,'reservados':[]}
 for r in records:
  if not r['sku']:
   if '00' in (r['tipo'],r['categoria'],r['subcategoria']):continue
   assign(state,r)
 return {'state':state,'master':master,'sheet':'SUGERIDO'}
def assign(state,r):
 r['clave']=r.get('clave') or key_from_name(r['nombre']);body=r['tipo']+r['categoria']+r['subcategoria']+r['clave']
 used=set(state['reservados'])|{x['sku'] for x in state['registros'] if x.get('sku')}
 suffix=next((c for c in ALPHABET if body+c not in used),None)
 if suffix is None:raise ValueError('Los 36 sufijos de esta clave están ocupados. Ajusta la clave de 7 caracteres.')
 r['digito']=suffix;r['sku']=body+suffix
def validate(data):
 s=data.get('state')
 if not isinstance(s,dict) or s.get('version')!=1 or type(s.get('maxId')) is not int or s['maxId']<0 or not isinstance(s.get('registros'),list) or not isinstance(s.get('reservados'),list):raise ValueError('Catálogo de ventas inválido.')
 ids=set();codes=set();rows=set()
 if not all(isinstance(c,str) and re.fullmatch('[A-Z0-9]{14}',c) for c in s['reservados']):raise ValueError('Reservas de ventas inválidas.')
 for r in s['registros']:
  if type(r.get('id')) is not int or not 1<=r['id']<=s['maxId'] or r['id'] in ids:raise ValueError('Identificador de ventas repetido o inválido.')
  ids.add(r['id'])
  if not isinstance(r.get('nombre'),str) or not r['nombre'].strip() or len(r['nombre'])>300 or type(r.get('eliminado')) is not bool or type(r.get('validado')) is not bool:raise ValueError('Artículo de ventas inválido.')
  if r.get('modulo') not in PDV and r.get('modulo')!='000':raise ValueError('Módulo PDV inválido. Utiliza A01–A22.')
  for field,table in [('tipo',TIP),('categoria',CAT),('subcategoria',SUB)]:
   if r.get(field) not in table and r.get(field)!='00':raise ValueError('Clasificación de ventas inválida.')
  sku=r.get('sku','')
  if sku:
   if not re.fullmatch('[A-Z0-9]{14}',sku) or sku in codes or (not r['eliminado'] and sku in s['reservados']):raise ValueError('SKU de ventas repetido, reservado o inválido.')
   codes.add(sku)
   if r.get('clave')!=sku[6:13] or r.get('digito')!=sku[-1]:raise ValueError('Clave o sufijo de ventas incorrectos.')
   if not r['validado'] and sku!=r['tipo']+r['categoria']+r['subcategoria']+r['clave']+r['digito']:raise ValueError('El SKU de ventas no corresponde a su clasificación.')
  elif r['validado']:raise ValueError('Falta el SKU validado.')
  row=r.get('fila')
  if row is not None:
   if type(row) is not int or row<2 or row in rows:raise ValueError('Fila del maestro de ventas inválida.')
   rows.add(row)
 if not isinstance(data.get('master'),str):raise ValueError('Falta el maestro de ventas.')
 return data
def protected(old,new,actor):
 a=old['state'];b=new['state'];previous={r['id']:r for r in a['registros']};current={r['id']:r for r in b['registros']}
 if b['maxId']<a['maxId'] or not set(previous)<=set(current):raise ValueError('No se puede reducir el historial de ventas.')
 reservations=set(a['reservados'])|set(b['reservados'])
 for id,r in previous.items():
  updated=current[id]
  if updated['validado']!=r['validado']:raise ValueError('La condición de SKU validado no se puede cambiar.')
  if r['validado'] and (updated.get('sku')!=r['sku'] or updated.get('anterior')!=r.get('anterior') or not updated.get('validado')):raise ValueError('Los SKU validados de la columna A no se pueden modificar.')
  if r['eliminado'] and any(updated.get(k)!=v for k,v in r.items() if k!='fila'):raise ValueError('Una baja de ventas no puede reactivarse.')
  if updated['eliminado'] and not r['eliminado'] and actor['role']!='superadmin':raise PermissionError('Solo el super administrador puede dar de baja.')
  if r['sku'] and (r['sku']!=updated['sku'] or updated['eliminado']):reservations.add(r['sku'])
 for r in b['registros']:
  if r['id'] not in previous and r['id']<=a['maxId']:raise ValueError('ID de ventas ya utilizado.')
  if r['id'] not in previous and r['validado']:raise ValueError('Los SKU validados solo se pueden incorporar al importar el maestro.')
 b['reservados']=sorted(reservations)
 validate(new)

class SalesStore:
 def __init__(self,store):
  self.store=store
  with store.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS sales_catalog(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS sales_history(revision INTEGER PRIMARY KEY,created TEXT NOT NULL,payload TEXT NOT NULL)')
   if not db.execute('SELECT 1 FROM sales_catalog').fetchone():
    data=validate(json.loads((ROOT/'initial-ventas.json').read_text(encoding='utf8')))
    db.execute('INSERT INTO sales_catalog VALUES(1,1,?)',(json.dumps(data,ensure_ascii=False),))
   db.execute('CREATE TABLE IF NOT EXISTS sales_features(key TEXT PRIMARY KEY)')
   if not db.execute("SELECT 1 FROM sales_features WHERE key='pdv-a01-a22'").fetchone():
    rev,payload=db.execute('SELECT revision,payload FROM sales_catalog').fetchone();data=json.loads(payload);changed=False
    for r in data['state']['registros']:
     if r.get('modulo')=='000':
      module=resolve_pdv(r.get('originalModulo',''))
      if module!='000':r['modulo']=module;changed=True
    if changed:
     validate(data);db.execute('INSERT INTO sales_history VALUES(?,?,?)',(rev,datetime.datetime.now(datetime.timezone.utc).isoformat(),payload));db.execute('UPDATE sales_catalog SET revision=?,payload=?',(rev+1,json.dumps(data,ensure_ascii=False)))
    db.execute("INSERT INTO sales_features VALUES('pdv-a01-a22')")
 def get(self):
  with self.store.connect() as db:rev,payload=db.execute('SELECT revision,payload FROM sales_catalog').fetchone()
  return {**json.loads(payload),'revision':rev,'catalogos':{'TIP':TIP,'CAT':CAT,'SUB':SUB,'PDV':PDV}}
 def transact(self,revision,actor,change,importing=False):
  require_module(actor,'ventas')
  if importing:require_module(actor,'cargar_maestro')
  elif actor['role'] not in ('superadmin','auxti','ventas','alta'):raise PermissionError('Tu perfil no puede modificar ventas.')
  if type(revision) is not int:raise ValueError('Falta la revisión de ventas.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');rev,payload=db.execute('SELECT revision,payload FROM sales_catalog').fetchone()
   if rev!=revision:return None
   old=json.loads(payload);new=copy.deepcopy(old);change(old,new);validate(new)
   db.execute('INSERT INTO sales_history VALUES(?,?,?)',(rev,datetime.datetime.now(datetime.timezone.utc).isoformat(),payload))
   db.execute('UPDATE sales_catalog SET revision=?,payload=?',(rev+1,json.dumps(new,ensure_ascii=False)))
   db.execute('DELETE FROM sales_history WHERE revision < ?',(rev-99,))
  return {**new,'revision':rev+1,'catalogos':{'TIP':TIP,'CAT':CAT,'SUB':SUB,'PDV':PDV}}
 def put(self,data,actor):
  def change(old,new):
   new.update({'state':data.get('state'),'master':old['master']})
   validate(new);protected(old,new,actor)
   previous={r['id']:r for r in old['state']['registros']};allocation=copy.deepcopy(old['state'])
   allocation['reservados']=new['state']['reservados']
   for r in sorted(new['state']['registros'],key=lambda x:x['id']):
    before=previous.get(r['id'])
    if r['sku'] and not r['validado'] and (before is None or before['sku']!=r['sku']):
     if '00' in (r['tipo'],r['categoria'],r['subcategoria']):raise ValueError('Completa la clasificación antes de generar un SKU nuevo.')
     expected=copy.deepcopy(r);assign(allocation,expected)
     if r['sku']!=expected['sku']:raise ValueError('El sufijo debe ser el primer disponible en el orden 0–9 y A–Z.')
     allocation['registros'].append(expected)
  return self.transact(data.get('revision'),actor,change)
 def import_master(self,data,actor):
  incoming=initial(data.get('master',''))
  def change(old,new):
   state=new['state'];by_sku={r['sku']:r for r in state['registros'] if r['sku']}
   for item in incoming['state']['registros']:
    s=item['anterior'];existing=by_sku.get(s) if s else None
    if not s and any(not r['eliminado'] and row_identity(r)==row_identity(item) for r in state['registros']):continue
    if s in state['reservados'] and existing is None and new.get('historicosReinicio',{}).get(s)==list(row_identity(item)):
     state['reservados'].remove(s);new['historicosReinicio'].pop(s,None)
    if s in state['reservados'] and (existing is None or not existing['eliminado']):raise ValueError('El maestro contiene un SKU dado de baja o reservado: '+s)
    if existing:
     continue
    if s and any(x.get('anterior')==s for x in state['registros']):raise ValueError('SKU histórico ya utilizado: '+s)
    item['id']=state['maxId']+1;state['maxId']=item['id'];item['fila']=None;item['editado']=True
    if not s:
     item['sku']='';item['clave']='';item['digito']=''
     if '00' not in (item['tipo'],item['categoria'],item['subcategoria']):assign(state,item)
    state['registros'].append(item)
   validate(new)
  return self.transact(data.get('revision'),actor,change,importing=True)

def export_master(data):
 raw,path,xml,rows=read_master(data['master']);by_row={r['fila']:r for r in data['state']['registros'] if r.get('fila')};new_rows=[r for r in data['state']['registros'] if not r.get('fila') and not r['eliminado']]
 # Parches de celdas conservan las partes y etiquetas originales del archivo.
 def cell(address,value,numeric=False):
  from xml.sax.saxutils import escape
  if numeric and re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',str(value)):return '<c r="'+address+'"><v>'+str(value)+'</v></c>'
  return '<c r="'+address+'" t="inlineStr"><is><t xml:space="preserve">'+escape(str(value))+'</t></is></c>'
 def patch(address,value,numeric=False):
  nonlocal xml
  pattern=r'<c\b[^>]*\br="'+address+r'"[^>]*?(?:/>|>[\s\S]*?</c>)'
  match=re.search(pattern,xml);replacement=cell(address,value,numeric)
  if match:
   style=re.search(r'\bs="(\d+)"',match.group())
   if style:replacement=replacement.replace('r="'+address+'"','r="'+address+'" s="'+style[1]+'"',1)
   xml=xml[:match.start()]+replacement+xml[match.end():]
  else:
   row=re.search(r'(<row\b[^>]*\br="'+re.sub(r'\D','',address)+r'"[^>]*>)([\s\S]*?)(</row>)',xml)
   if not row:raise ValueError('No existe la fila de ventas para exportar.')
   col=lambda x:sum((ord(c)-64)*26**i for i,c in enumerate(reversed(re.sub(r'\d','',x))))
   after=next((c for c in re.finditer(r'<c\b[^>]*\br="([A-Z]+\d+)"',row[2]) if col(c[1])>col(address)),None)
   body=row[2];pos=after.start() if after else len(body);xml=xml[:row.start(2)]+body[:pos]+replacement+body[pos:]+xml[row.end(2):]
 for row in rows:
  r=by_row.get(row['fila'])
  if not r:continue
  # A de artículos históricos nunca se toca, ni siquiera al dar de baja.
  if not row.get('A') and r['sku']:patch('A'+str(r['fila']),r['sku'])
  if r.get('editado'):
   patch('H'+str(r['fila']),r['nombre'])
   for col,key,table,orig in [('B','tipo',TIP,'originalTipo'),('C','categoria',CAT,'originalCategoria'),('D','subcategoria',SUB,'originalSubcategoria')]:patch(col+str(r['fila']),table.get(r[key],r.get(orig,'')))
   patch('F'+str(r['fila']),PDV.get(r['modulo'],r.get('originalModulo','') or 'SIN ASIGNAR'))
  if r['eliminado'] or r.get('editado'):patch('S'+str(r['fila']),'INACTIVO' if r['eliminado'] else r['estado'])
 last=max([r['fila'] for r in rows]+[1])
 for r in new_rows:
  last+=1;values={**r.get('camposExcel',{}),'A':r['sku'],'B':TIP.get(r['tipo'],r.get('originalTipo','')),'C':CAT.get(r['categoria'],r.get('originalCategoria','')),'D':SUB.get(r['subcategoria'],r.get('originalSubcategoria','')),'F':PDV.get(r['modulo'],r.get('originalModulo','') or 'SIN ASIGNAR'),'H':r['nombre'],'S':r['estado']};values={k:v for k,v in values.items() if re.fullmatch('[A-Z]+',k)}
  if last>1048576:raise ValueError('El maestro alcanzó el límite de filas de Excel.')
  if re.search(r'<row\b[^>]*\br="'+str(last)+r'"',xml):
   for col,value in values.items():patch(col+str(last),value,col not in ('A','B','C','D','F','H','S') and r.get('tiposExcel',{}).get(col)=='n')
  else:
   def col_number(c):return sum((ord(x)-64)*26**i for i,x in enumerate(reversed(c)))
   added='<row r="'+str(last)+'">'+''.join(cell(c+str(last),values[c],c not in ('A','B','C','D','F','H','S') and r.get('tiposExcel',{}).get(c)=='n') for c in sorted(values,key=col_number))+'</row>'
   after=next((m for m in re.finditer(r'<row\b[^>]*\br="(\d+)"',xml) if int(m[1])>last),None)
   if after:xml=xml[:after.start()]+added+xml[after.start():]
   else:xml=xml.replace('</sheetData>',added+'</sheetData>')
 if new_rows:
  dimension=re.search(r'<dimension\b[^>]*\bref="([A-Z]+\d+):([A-Z]+)(\d+)"',xml)
  if dimension and int(dimension[3])<last:xml=xml[:dimension.start(3)]+str(last)+xml[dimension.end(3):]
 output=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(raw)) as original,zipfile.ZipFile(output,'w') as result:
  for info in original.infolist():result.writestr(info,xml.encode('utf8') if info.filename==path else original.read(info.filename))
 return output.getvalue()
