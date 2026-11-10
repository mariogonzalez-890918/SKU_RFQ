"""Reportes SAE: catálogo cerrado de campos y transacciones Firebird de solo lectura."""
import base64,contextlib,datetime as dt,decimal,io,json,re,threading,zipfile
from xml.sax.saxutils import escape
from permissions import require_module
from requisiciones import Conflict,now
from pt_onedrive import crypt

TABLES={'FACTF01':'F','CLIE01':'C','FACTF_CLIB01':'L','CFDI01':'D'}
MIME='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
NUMERIC={7,8,10,16,27};DATES={12,35}
DEFAULT_COLUMNS=[('FACTF01.CVE_DOC','Documento'),('FACTF01.FECHA_DOC','Fecha'),('CLIE01.NOMBRE','Cliente'),('FACTF01.IMPORTE','Importe')]

def admin(actor):
 if actor['role']!='superadmin':raise PermissionError('Solo Superadministrador configura la conexión y el reporte contable.')

def access(actor):
 require_module(actor,'contabilidad')
 if actor['role'] not in ('superadmin','contabilidad'):raise PermissionError('Este reporte es exclusivo de Superadministrador y Contabilidad.')

def date(value):
 if not isinstance(value,str) or not re.fullmatch(r'\d{2}/\d{2}/\d{4}',value):raise ValueError('Usa fechas dd/mm/aaaa.')
 try:return dt.datetime.strptime(value,'%d/%m/%Y').date()
 except ValueError:raise ValueError('La fecha no es válida. Usa dd/mm/aaaa.')

def filters(data):
 start=date(data.get('desde',''));end=date(data.get('hasta',''))
 if end<start:raise ValueError('La fecha final debe ser igual o posterior a la inicial.')
 if (end-start).days>3660:raise ValueError('Consulta un periodo de hasta diez años.')
 result={'desde':start.strftime('%d/%m/%Y'),'hasta':end.strftime('%d/%m/%Y')}
 for key in ('cliente','documento','estado','formaPagoSat'):
  value=data.get(key,'')
  if not isinstance(value,str) or len(value)>100:raise ValueError('Filtro inválido.')
  result[key]=value.strip()
 return result,start,end

def connection_config(data):
 result={key:str(data.get(key,'')).strip() for key in ('host','database','user','charset')}
 result['charset']=result['charset'] or 'WIN1252'
 if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,253}',result['host']):raise ValueError('Indica el servidor Firebird sin ruta compartida.')
 if not result['database'] or len(result['database'])>1000 or result['database'].startswith(('\\\\','//')):raise ValueError('Indica la ruta local del servidor o el alias Firebird. Usa Detectar ruta para una carpeta compartida.')
 if not 1<=len(result['user'])<=100 or result['charset'] not in ('WIN1252','UTF8','ISO8859_1','NONE'):raise ValueError('Usuario o codificación inválidos.')
 try:result['port']=int(data.get('port',3050))
 except (ValueError,TypeError):raise ValueError('Puerto inválido.')
 if not 1<=result['port']<=65535:raise ValueError('Puerto inválido.')
 return result

@contextlib.contextmanager
def connect(config,password):
 import firebirdsql
 conn=None
 try:
  conn=firebirdsql.connect(host=config['host'],port=config['port'],database=config['database'],user=config['user'],password=password,charset=config['charset'],timeout=12,readonly=True,isolation_level=firebirdsql.ISOLATION_LEVEL_READ_COMMITED_RO)
  yield conn
 except (firebirdsql.Error,OSError,TimeoutError,UnicodeError) as error:
  raise ValueError('Aspel no completó la consulta. Revisa servidor, ruta, usuario, contraseña y disponibilidad de Firebird.') from error
 finally:
  if conn:
   try:conn.rollback()
   finally:conn.close()

def schema(conn):
 cur=conn.cursor();cur.execute("SELECT TRIM(rf.RDB$RELATION_NAME),TRIM(rf.RDB$FIELD_NAME),f.RDB$FIELD_TYPE,f.RDB$FIELD_SUB_TYPE FROM RDB$RELATION_FIELDS rf JOIN RDB$FIELDS f ON rf.RDB$FIELD_SOURCE=f.RDB$FIELD_NAME WHERE rf.RDB$RELATION_NAME IN ('FACTF01','CLIE01','FACTF_CLIB01','CFDI01') ORDER BY rf.RDB$RELATION_NAME,rf.RDB$FIELD_POSITION")
 fields={}
 for table,name,kind,subtype in cur.fetchall():
  if table in TABLES and re.fullmatch(r'[A-Z][A-Z0-9_$]*',name):fields[table+'.'+name]={'tabla':table,'campo':name,'tipo':kind,'subtipo':subtype}
 required=('CFDI01.TIPO_DOC','CFDI01.CVE_DOC','FACTF01.TIP_DOC','FACTF01.CVE_DOC','FACTF01.CVE_CLPV','FACTF01.FECHA_DOC','CLIE01.CLAVE','FACTF_CLIB01.CLAVE_DOC')
 if any(k not in fields for k in required):raise ValueError('Faltan tablas o campos necesarios de SAE Empresa01.')
 cur.execute("SELECT TRIM(i.RDB$RELATION_NAME),TRIM(i.RDB$INDEX_NAME),TRIM(s.RDB$FIELD_NAME) FROM RDB$INDICES i JOIN RDB$INDEX_SEGMENTS s ON i.RDB$INDEX_NAME=s.RDB$INDEX_NAME WHERE i.RDB$RELATION_NAME IN ('CLIE01','FACTF_CLIB01','CFDI01') AND i.RDB$UNIQUE_FLAG=1 AND (i.RDB$INDEX_INACTIVE IS NULL OR i.RDB$INDEX_INACTIVE=0)")
 indexes={}
 for table,index,field in cur.fetchall():indexes.setdefault((table,index),[]).append(field)
 for table,keys in [('CLIE01',{'CLAVE'}),('FACTF_CLIB01',{'CLAVE_DOC'}),('CFDI01',{'TIPO_DOC','CVE_DOC'})]:
  if not any(t==table and set(cols)==keys and len(cols)==len(keys) for (t,i),cols in indexes.items()):raise ValueError('No se confirmó una clave única en '+table+'. No se ejecutan uniones que puedan duplicar documentos.')
 return fields

def definition(data,fields):
 name=data.get('nombre','');columns=data.get('columnas');datefield=data.get('campoFecha','FACTF01.FECHA_DOC')
 if not isinstance(name,str) or not 1<=len(name.strip())<=120:raise ValueError('Indica un nombre de reporte de hasta 120 caracteres.')
 if datefield not in fields or fields[datefield]['tipo'] not in DATES or not datefield.startswith('FACTF01.'):raise ValueError('Selecciona un campo de fecha de FACTF01.')
 if not isinstance(columns,list) or not 1<=len(columns)<=60:raise ValueError('Selecciona entre 1 y 60 columnas.')
 seen=set();result=[]
 for col in columns:
  key=col.get('campo');label=col.get('titulo')
  if key not in fields or key in seen or not isinstance(label,str) or not 1<=len(label.strip())<=100:raise ValueError('Campo o encabezado inválido/repetido.')
  field=fields[key]
  if field['tipo']==261 and field['subtipo']!=1:raise ValueError('No se pueden mostrar campos binarios.')
  seen.add(key);result.append({'campo':key,'titulo':label.strip()})
 return {'nombre':name.strip(),'columnas':result,'campoFecha':datefield}

def expression(key,fields):
 if key not in fields:raise ValueError('El maestro SAE cambió: configura de nuevo el reporte.')
 table,name=key.split('.');field=fields[key];sql=TABLES[table]+'."'+name+'"'
 return 'CAST(SUBSTRING('+sql+' FROM 1 FOR 4096) AS VARCHAR(4096))' if field['tipo']==261 else sql

def query_sql(report,fields,data,offset,limit):
 f,start,end=filters(data)
 if type(offset) is not int or not 0<=offset<=1000000 or type(limit) is not int or not 1<=limit<=20001:raise ValueError('Página inválida.')
 columns=report['columnas'];selected=','.join(expression(c['campo'],fields) for c in columns)
 # All identifiers come from the saved, validated schema; all filter values are parameters.
 sql='SELECT FIRST '+str(limit)+' SKIP '+str(offset)+' '+selected+' FROM FACTF01 F LEFT JOIN CLIE01 C ON F.CVE_CLPV=C.CLAVE LEFT JOIN FACTF_CLIB01 L ON F.CVE_DOC=L.CLAVE_DOC LEFT JOIN CFDI01 D ON F.TIP_DOC=D.TIPO_DOC AND F.CVE_DOC=D.CVE_DOC WHERE '+expression(report['campoFecha'],fields)+' >= ? AND '+expression(report['campoFecha'],fields)+' < ?'
 try:after=end+dt.timedelta(days=1)
 except OverflowError:raise ValueError('La fecha final está fuera del rango permitido.')
 params=[start,after]
 for key,column in [('cliente','C.NOMBRE'),('documento','F.CVE_DOC'),('estado','F.STATUS')]:
  if f[key]:sql+=' AND '+column+' CONTAINING ?';params.append(f[key])
 if f['formaPagoSat']:
  if 'FACTF01.FORMADEPAGOSAT' not in fields:raise ValueError('Actualiza la conexión para reconocer FORMADEPAGOSAT de FACTF01.')
  sql+=' AND TRIM(F.FORMADEPAGOSAT)=?';params.append(f['formaPagoSat'])
 sql+=' ORDER BY F.FECHA_DOC,F.CVE_DOC';return sql,params,f

def value(v,field):
 if v is None:return None
 if isinstance(v,(dt.date,dt.datetime)):return v.strftime('%d/%m/%Y')+(' '+v.strftime('%H:%M:%S') if isinstance(v,dt.datetime) else '')
 if isinstance(v,(float,decimal.Decimal)):
  n=decimal.Decimal(str(v))
  if not n.is_finite():return None
  return str(n)
 return v.rstrip()[:4096] if isinstance(v,str) else v

class Accounting:
 def __init__(self,store):
  self.store=store;self.lock=threading.BoundedSemaphore(2)
  with store.connect() as db:
   db.execute("CREATE TABLE IF NOT EXISTS accounting_config(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL,secret TEXT NOT NULL,schema TEXT NOT NULL)")
   db.execute("INSERT OR IGNORE INTO accounting_config VALUES(1,1,'{}','','{}')")
   db.execute("CREATE TABLE IF NOT EXISTS accounting_report(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL)")
   db.execute("INSERT OR IGNORE INTO accounting_report VALUES(1,1,'{}')")
   db.execute('CREATE TABLE IF NOT EXISTS accounting_audit(created TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL)')
 def read(self):
  with self.store.connect() as db:
   r,c,s,fields=db.execute('SELECT revision,payload,secret,schema FROM accounting_config').fetchone();rr,report=db.execute('SELECT revision,payload FROM accounting_report').fetchone()
  return r,json.loads(c),s,json.loads(fields),rr,json.loads(report)
 def secret(self,encrypted):
  try:return crypt(base64.b64decode(encrypted),True).decode()
  except Exception:raise ValueError('No se puede abrir la conexión con esta cuenta de Windows. Superadministrador debe guardar de nuevo la contraseña.')
 def status(self,actor):
  access(actor);r,c,s,fields,rr,report=self.read();result={'configura':actor['role']=='superadmin','reporte':report,'revisionReporte':rr,'conectado':bool(c and s and fields)}
  if actor['role']=='superadmin':result.update(configuracion=c,revision=r,campos=fields,claveGuardada=bool(s))
  return result
 def save_connection(self,data,actor):
  admin(actor);r,old,secret,fields,rr,report=self.read()
  if data.get('revision')!=r:raise Conflict('La conexión cambió. Actualiza la pantalla.')
  c=connection_config(data);password=data.get('password','')
  if not isinstance(password,str) or len(password)>200:raise ValueError('Contraseña inválida.')
  if not password:
   if not secret or c.get('host')!=old.get('host') or c.get('user')!=old.get('user'):raise ValueError('Indica la contraseña para esta conexión.')
   password=self.secret(secret)
  with connect(c,password) as conn:fields=schema(conn)
  encrypted=base64.b64encode(crypt(password.encode())).decode()
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT revision FROM accounting_config').fetchone()[0]!=r:raise Conflict('La conexión cambió durante la comprobación.')
   db.execute('UPDATE accounting_config SET revision=revision+1,payload=?,secret=?,schema=?',(json.dumps(c),encrypted,json.dumps(fields)))
   # A changed source requires deliberate report publication; old report must not expose a different company.
   if c!=old:db.execute("UPDATE accounting_report SET revision=revision+1,payload='{}'")
   db.execute('INSERT INTO accounting_audit VALUES(?,?,?,?)',(now(),actor['email'],'CONEXION','Conexión comprobada; solo lectura.'))
  return self.status(actor)
 def detect(self,data,actor):
  admin(actor);c=connection_config({**data,'database':'service_mgr'});password=data.get('password','')
  if not password:
   _,old,s,*_=self.read()
   if c.get('host')!=old.get('host') or c.get('user')!=old.get('user') or not s:raise ValueError('Indica la contraseña para detectar la ruta.')
   password=self.secret(s)
  from firebirdsql import services
  try:
   svc=services.connect(host=c['host'],port=c['port'],user=c['user'],password=password,timeout=8)
   try:paths=[p for p in svc.getAttachedDatabaseNames() if p.replace('\\','/').rsplit('/',1)[-1].upper()=='SAE90EMPRE01.FDB']
   finally:svc.close()
  except Exception:raise ValueError('No se pudo detectar la ruta. Indica la ruta local del servidor o un alias Firebird.')
  if len(paths)!=1:raise ValueError('No hay una única SAE90EMPRE01.FDB abierta en Firebird. Abre SAE Empresa01 o indica la ruta local.')
  return {'database':paths[0]}
 def save_report(self,data,actor):
  admin(actor);r,c,s,fields,rr,old=self.read()
  if not fields:raise ValueError('Primero comprueba y guarda la conexión.')
  report=definition(data,fields)
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   if db.execute('SELECT revision FROM accounting_report').fetchone()[0]!=data.get('revision') or db.execute('SELECT revision FROM accounting_config').fetchone()[0]!=data.get('revisionConexion'):raise Conflict('La configuración cambió. Actualiza antes de guardar.')
   db.execute('UPDATE accounting_report SET revision=revision+1,payload=?',(json.dumps(report),));db.execute('INSERT INTO accounting_audit VALUES(?,?,?,?)',(now(),actor['email'],'REPORTE',json.dumps(report)))
  return self.status(actor)
 def payment_forms(self,actor):
  access(actor);r,c,s,fields,rr,report=self.read()
  if not report or not c or not s or 'FACTF01.FORMADEPAGOSAT' not in fields:return {'formas':[]}
  if not self.lock.acquire(blocking=False):raise ValueError('Hay dos consultas contables en proceso. Escribe la clave de forma de pago o inténtalo nuevamente.')
  try:
   with connect(c,self.secret(s)) as conn:
    cur=conn.cursor();cur.execute("SELECT FIRST 1001 DISTINCT TRIM(FORMADEPAGOSAT) FROM FACTF01 WHERE FORMADEPAGOSAT IS NOT NULL AND TRIM(FORMADEPAGOSAT)<>'' ORDER BY 1");rows=cur.fetchmany(1001)
  finally:self.lock.release()
  if len(rows)>1000:raise ValueError('Hay demasiadas formas de pago distintas; escribe la clave exacta.')
  return {'formas':[str(row[0]).strip() for row in rows]}
 def run(self,data,actor,export=False):
  access(actor);r,c,s,fields,rr,report=self.read()
  if not report or not c or not s:raise ValueError('Superadministrador todavía no ha publicado el reporte.')
  if data.get('revisionReporte')!=rr:raise Conflict('El reporte cambió. Actualiza y consulta de nuevo.')
  offset=data.get('offset',0) if not export else 0;limit=20001 if export else 201
  sql,params,f=query_sql(report,fields,data,offset,limit)
  if not self.lock.acquire(blocking=False):raise ValueError('Hay dos consultas contables en proceso. Intenta nuevamente en unos segundos.')
  try:
   with connect(c,self.secret(s)) as conn:
    cur=conn.cursor();cur.execute(sql,params);rows=cur.fetchmany(limit)
  finally:self.lock.release()
  more=len(rows)==limit
  if export and more:raise ValueError('El resultado supera 20,000 filas. Reduce el periodo para exportar el reporte completo.')
  rows=rows if export else rows[:200];columns=[{**col,'numerico':fields[col['campo']]['tipo'] in NUMERIC} for col in report['columnas']]
  result={'nombre':report['nombre'],'columnas':columns,'filas':[[value(v,fields[col['campo']]) for v,col in zip(row,columns)] for row in rows],'filtros':f,'offset':offset,'hayMas':more,'generado':now(),'revisionReporte':rr}
  if export:
   with self.store.connect() as db:db.execute('INSERT INTO accounting_audit VALUES(?,?,?,?)',(now(),actor['email'],'EXCEL',json.dumps({'filtros':f,'filas':len(rows),'revision':rr})))
   return workbook(result),MIME
  return result

def workbook(result):
 """Static XLSX; untrusted text is always an inline string, never an Excel formula."""
 def col(n):
  out=''
  while n:n,k=divmod(n-1,26);out=chr(65+k)+out
  return out
 def cell(v,address,numeric=False):
  if v is None:return '<c r="'+address+'"/>'
  if numeric:
   try:
    n=decimal.Decimal(str(v))
    if n.is_finite() and len(n.as_tuple().digits)<=15:return '<c r="'+address+'"><v>'+str(n)+'</v></c>'
   except decimal.InvalidOperation:pass
  text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(v))[:32767]
  return '<c r="'+address+'" t="inlineStr"><is><t xml:space="preserve">'+escape(text)+'</t></is></c>'
 header=[c['titulo'] for c in result['columnas']];rows=[header]+result['filas'];ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
 xml='<worksheet xmlns="'+ns+'"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols>'+''.join('<col min="'+str(i+1)+'" max="'+str(i+1)+'" width="25" customWidth="1"/>' for i in range(len(header)))+'</cols><sheetData>'
 xml+=''.join('<row r="'+str(i+1)+'">'+''.join(cell(v,col(j+1)+str(i+1),i>0 and result['columnas'][j]['numerico']) for j,v in enumerate(row))+'</row>' for i,row in enumerate(rows))+'</sheetData><autoFilter ref="A1:'+col(len(header))+str(len(rows))+'"/></worksheet>'
 meta=[['Reporte',result['nombre']],['Fecha inicial',result['filtros']['desde']],['Fecha final',result['filtros']['hasta']],['Cliente contiene',result['filtros']['cliente']],['Documento contiene',result['filtros']['documento']],['Estado contiene',result['filtros']['estado']],['Forma de pago SAT',result['filtros'].get('formaPagoSat','')],['Filas',len(result['filas'])],['Fuente','Aspel SAE · Solo lectura']]
 meta_xml='<worksheet xmlns="'+ns+'"><sheetData>'+''.join('<row r="'+str(i+1)+'">'+''.join(cell(v,col(j+1)+str(i+1)) for j,v in enumerate(row))+'</row>' for i,row in enumerate(meta))+'</sheetData></worksheet>'
 output=io.BytesIO()
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+''.join('<Override PartName="/xl/worksheets/sheet'+str(i)+'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in (1,2))+'</Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="'+ns+'" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Reporte" sheetId="1" r:id="rId1"/><sheet name="Filtros" sheetId="2" r:id="rId2"/></sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join('<Relationship Id="rId'+str(i)+'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'+str(i)+'.xml"/>' for i in (1,2))+'</Relationships>')
  z.writestr('xl/worksheets/sheet1.xml',xml);z.writestr('xl/worksheets/sheet2.xml',meta_xml)
 return output.getvalue()
