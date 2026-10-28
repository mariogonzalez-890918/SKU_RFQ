"""Layout CLIENTES y carga revisada por razón social y canal, sin duplicar códigos."""
import base64,csv,hashlib,io,json,re,uuid,zipfile,xml.etree.ElementTree as ET
from comercial import ADMINS,SUPERVISORS,dumps,now,fingerprint
from requisiciones import Conflict,text
from ventas import norm,N,NS

HEADERS=['CODIGO','NOMBRE','CANAL','RFC','CORREO','TELEFONO','DOMICILIO','DIRECCION_ENTREGA','CONDICIONES','ACTIVO']
CHANNEL_LABELS={'INSTITUCIONALES':['ventasins'],'EXPENDIOS':['expendios'],'AMBOS':['ventasins','expendios']}
def customer_channels(value):return value.get('canales',['ventasins','expendios'])

def read_table(data,sheet_name="CLIENTES"):
 try:raw=base64.b64decode(data.get('contenido',''),validate=True)
 except Exception:raise ValueError('Archivo de clientes inválido.')
 if not raw or len(raw)>15*1024*1024:raise ValueError('El archivo de clientes está vacío o supera 15 MB.')
 if raw.startswith(b'PK'):
  try:
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('Excel demasiado grande.')
    wb=ET.fromstring(z.read('xl/workbook.xml'));rels={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))};sheet=next((s for s in wb.findall('m:sheets/m:sheet',N) if norm(s.get('name'))==norm(sheet_name)),None)
    if sheet is None:raise ValueError('Se requiere la pestaña '+sheet_name+'.')
    target=rels[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];path=target.lstrip('/') if target.startswith('/') else 'xl/'+target.lstrip('./')
    strings=[''.join(t.text or '' for t in si.iter('{'+NS+'}t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
    rows=[]
    for r in ET.fromstring(z.read(path)).findall('m:sheetData/m:row',N):
     values={}
     for c in r.findall('m:c',N):
      col=0
      for letter in re.sub(r'\d','',c.get('r','')):col=col*26+ord(letter)-64
      v=c.findtext('m:v','',N);values[col-1]=strings[int(v)] if c.get('t')=='s' and v else ''.join(t.text or '' for t in c.iter('{'+NS+'}t')) if c.get('t')=='inlineStr' else v
     if values:rows.append([values.get(i,'') for i in range(max(values)+1)])
  except (zipfile.BadZipFile,KeyError,ET.ParseError):raise ValueError('El Excel de clientes no es válido.')
 else:
  try:content=raw.decode('utf-8-sig')
  except UnicodeError:raise ValueError('Guarda el CSV como UTF-8.')
  try:delimiter=csv.Sniffer().sniff(content[:8192],delimiters=';,\t').delimiter
  except csv.Error:delimiter=';'
  rows=list(csv.reader(io.StringIO(content),delimiter=delimiter))
 if not rows or len(rows)>20001:raise ValueError('Se admiten de 1 a 20000 clientes.')
 return rows

def read_rows(data):
 rows=read_table(data)
 header=[norm(h).replace(' ','_') for h in rows[0]]
 if len(set(header))!=len(header) or not {'NOMBRE','CANAL'}.issubset(header) or set(header)-set(HEADERS):raise ValueError('Encabezados inválidos. Descarga el layout CLIENTES y conserva la fila 1.')
 result=[];seen=set()
 for n,row in enumerate(rows[1:],2):
  if not any(str(v).strip() for v in row):continue
  if len(row)>len(header) and any(row[len(header):]):raise ValueError(f'Fila {n}: sobran columnas.')
  r={k:text(str(row[i]) if i<len(row) else '',700 if k in ('DOMICILIO','DIRECCION_ENTREGA') else 200) for i,k in enumerate(header)};code=norm(r.get('CODIGO'));name=r.get('NOMBRE');label=norm(r.get('CANAL'));email=r.get('CORREO','')
  if code and (not re.fullmatch('[A-Z0-9][A-Z0-9_-]{0,49}',code) or code in seen) or not name or label not in CHANNEL_LABELS:raise ValueError(f'Fila {n}: revisa código único, nombre y canal (INSTITUCIONALES, EXPENDIOS o AMBOS).')
  if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError(f'Fila {n}: correo inválido.')
  active=norm(r.get('ACTIVO','SI')) or 'SI'
  if active not in ('SI','NO','1','0','TRUE','FALSE','VERDADERO','FALSO'):raise ValueError(f'Fila {n}: ACTIVO debe ser SI o NO.')
  seen.add(code) if code else None;result.append({'codigo':code,'nombre':name,'canales':CHANNEL_LABELS[label],'rfc':r.get('RFC','').upper(),'correo':email,'telefono':r.get('TELEFONO',''),'domicilio':r.get('DOMICILIO',''),'entrega':r.get('DIRECCION_ENTREGA',''),'condiciones':r.get('CONDICIONES',''),'activo':active in ('SI','1','TRUE','VERDADERO')})
 if not result:raise ValueError('Agrega clientes en la pestaña CLIENTES. Los ejemplos no se importan.')
 return result

def import_customers(cm,data,actor,channel):
 cm.action(actor,channel,'clientes');company=data.get('empresa');cm.company(company,actor,True);rows=read_rows(data)
 for ch in set(c for r in rows for c in r['canales']):cm.action(actor,ch,'clientes')
 update=data.get('actualizar') is True
 with cm.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT id,code,creator,revision,payload FROM cm_customers WHERE company=? ORDER BY id',(company,)).fetchall();snapshot=fingerprint(old);known={r[1]:r for r in old};added=changed=skipped=0
  plan=[];identities=set()
  for r in rows:
   identity=(norm(r['nombre']),norm(r.get('rfc')),norm(r.get('correo')),norm(r.get('telefono')),norm(r.get('domicilio')))
   if not r['codigo'] and identity in identities:raise ValueError('Hay clientes repetidos en el archivo: '+r['nombre'])
   identities.add(identity);previous=known.get(r['codigo']) if r['codigo'] else None
   if not r['codigo']:
    matches=[v for v in old if (lambda p:(norm(p['nombre']),norm(p.get('rfc')),norm(p.get('correo')),norm(p.get('telefono')),norm(p.get('domicilio')))==identity)(json.loads(v[4]))]
    if len(matches)>1:raise ValueError('Cliente ambiguo; usa su código en la columna opcional CODIGO: '+r['nombre'])
    previous=matches[0] if matches else None
   plan.append((r,previous))
   if previous and not update:skipped+=1;continue
   if previous:changed+=1
   else:added+=1
  result={'ok':True,'clientes':len(rows),'nuevos':added,'actualizados':changed,'omitidos':skipped,'huellaActual':snapshot}
  if data.get('revisar'):return result
  if data.get('huellaActual')!=snapshot:raise Conflict('El catálogo de clientes cambió. Revisa el archivo nuevamente.')
  for r,previous in plan:
   if previous and not update:continue
   value={**(json.loads(previous[4]) if previous else {}),**{k:v for k,v in r.items() if v!=''}}
   previous_channels=set(json.loads(previous[4]).get('canales',['ventasins','expendios'])) if previous else set()
   for ch in set(r['canales'])^previous_channels:cm.action(actor,ch,'clientes')
   value['codigo']=previous[1] if previous else cm.next_customer_code(db,company)
   if previous:db.execute('UPDATE cm_customers SET revision=revision+1,payload=? WHERE id=?',(dumps(value),previous[0]))
   else:db.execute('INSERT INTO cm_customers VALUES(?,?,?,?,1,?)',(uuid.uuid4().hex,company,value['codigo'],actor['email'],dumps(value)))
  cm.audit(db,actor,company,'clientes_importados',{'nuevos':added,'actualizados':changed,'omitidos':skipped})
 return result
