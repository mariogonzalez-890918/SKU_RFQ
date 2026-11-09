"""Ingreso de producto terminado: catálogo de ventas, cantidades y exportación mensual."""
import hashlib,io,json,re,uuid,zipfile
from decimal import Decimal,InvalidOperation
from permissions import require_module
from requisiciones import Conflict,now,text
from comercial import dumps
from fechas import display_date
from urllib.parse import urlsplit,parse_qs,urlencode

BRANCHES=('EJIDOS','SAN PABLO','CUAUTITLAN')
MANAGERS={'superadmin','auxti','gerente'}
MIME='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

def scan_sku(value):
 code=str(value).strip()
 if code.lower().startswith(('http://','https://')):
  url=urlsplit(code);q=parse_qs(url.query)
  if not url.hostname or url.username or url.password or url.path!='/pt' or url.fragment or set(q)!={'sku'} or len(q['sku'])!=1:raise ValueError('El QR no es un enlace de producto PT válido.')
  code=q['sku'][0]
 code=code.upper()
 if not re.fullmatch('[A-Z0-9]{14}',code):raise ValueError('El código debe contener el SKU de ventas de 14 caracteres. Escanea la etiqueta PT.')
 return code

def qr_value(sku,base=''):
 if not base:return sku
 url=urlsplit(base.strip())
 if len(base)>180 or url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('','/','/pt') or any(ord(c)<33 for c in base):raise ValueError('Indica la dirección HTTP o HTTPS de GMP accesible desde los celulares, sin usuario, contraseña ni parámetros.')
 return url.scheme+'://'+url.netloc+'/pt?'+urlencode({'sku':sku})

def signature(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def quantity(value,unit):
 if isinstance(value,bool) or not isinstance(value,(str,int)):raise ValueError('Cantidad inválida.')
 try:q=Decimal(str(value))
 except InvalidOperation:raise ValueError('Cantidad inválida.')
 if not q.is_finite() or q<=0 or q>Decimal('999999999') or q.as_tuple().exponent < -3:raise ValueError('La cantidad debe ser mayor a cero, con hasta tres decimales.')
 if unit.strip().upper() in ('PIEZA','PIEZAS','PZA','PZ','UNIDAD','UNIDADES') and q!=q.to_integral():raise ValueError('Las piezas se registran en cantidades enteras.')
 return format(q,'f').rstrip('0').rstrip('.') if '.' in format(q,'f') else str(q)

class PTStore:
 def __init__(self,store):
  self.store=store;self.publisher=None
  with store.connect() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS pt_entries(id TEXT PRIMARY KEY,branch TEXT NOT NULL,month TEXT NOT NULL,creator TEXT NOT NULL,client_key TEXT NOT NULL,fingerprint TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(creator,client_key));
CREATE TABLE IF NOT EXISTS pt_original_workbooks(branch TEXT NOT NULL,month TEXT NOT NULL,original BLOB NOT NULL,PRIMARY KEY(branch,month));
CREATE INDEX IF NOT EXISTS pt_entries_scope ON pt_entries(branch,month);
CREATE TABLE IF NOT EXISTS pt_exports(branch TEXT NOT NULL,month TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,synced INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'PENDIENTE',attempts INTEGER NOT NULL DEFAULT 0,retry_at REAL NOT NULL DEFAULT 0,lease REAL NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',payload TEXT NOT NULL DEFAULT '{}',PRIMARY KEY(branch,month));
CREATE TRIGGER IF NOT EXISTS pt_entries_no_delete BEFORE DELETE ON pt_entries BEGIN SELECT RAISE(ABORT,'El historial PT no se elimina.'); END;''')
   if 'last_attempt' not in {r[1] for r in db.execute('PRAGMA table_info(pt_exports)')}:db.execute('ALTER TABLE pt_exports ADD COLUMN last_attempt REAL NOT NULL DEFAULT 0')
 def scope(self,actor,branch=None):
  require_module(actor,'pt')
  allowed=list(BRANCHES) if actor['role'] in MANAGERS else [b for b in actor.get('sucursales',[]) if b in BRANCHES]
  if branch is not None and branch not in allowed:raise PermissionError('No tienes acceso PT a esa sucursal.')
  return allowed
 def catalog(self):
  result={};seen=set()
  with self.store.connect() as db:
   for sku,payload in db.execute('SELECT sku,payload FROM cm_products'):
    p=json.loads(payload);seen.add(sku)
    if p.get('activo',True):result[sku]={'sku':sku,'descripcion':p['nombre'],'unidad':p.get('unidad') or 'PIEZA','tipo':p.get('tipo',''),'categoria':p.get('categoria','')}
   row=db.execute('SELECT payload FROM sales_catalog WHERE id=1').fetchone()
   if row:
    for p in json.loads(row[0])['state']['registros']:
     sku=p.get('sku','')
     if sku in seen or p.get('eliminado') or p.get('estado')!='ACTIVO':continue
     result[sku]={'sku':sku,'descripcion':p['nombre'],'unidad':p.get('unidad') or 'PIEZA','tipo':p.get('tipo',''),'categoria':p.get('categoria','')}
  return {s:{**p,'revision':signature(p)} for s,p in result.items() if re.fullmatch('[A-Z0-9]{14}',s)}
 def product(self,code,actor):
  self.scope(actor);code=scan_sku(text(code,500))
  p=self.catalog().get(code)
  if not p:raise ValueError('El SKU no existe o está inactivo en el maestro de ventas.')
  return p
 def queued(self,db,branch,month):
  db.execute("INSERT INTO pt_exports(branch,month,revision) VALUES(?,?,1) ON CONFLICT(branch,month) DO UPDATE SET revision=revision+1,state='PENDIENTE',retry_at=0,attempts=0,error=''",(branch,month))
 def create(self,data,actor):
  branch=data.get('sucursal');self.scope(actor,branch)
  if set(data)-{'sucursal','sku','cantidad','revisionProducto','clave','referencia'}:raise ValueError('SKU, descripción, unidad, usuario y fecha se validan en servidor; solo captura la cantidad.')
  key=text(data.get('clave',''),100)
  if not re.fullmatch('[A-Za-z0-9_-]{12,100}',key):raise ValueError('Clave de captura inválida.')
  stamp=signature(data)
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT fingerprint,payload FROM pt_entries WHERE creator=? AND client_key=?',(actor['email'],key)).fetchone()
   if old:
    if old[0]!=stamp:raise Conflict('La misma clave de captura corresponde a otra cantidad. Revisa el historial.')
    return {'ok':True,'repetido':True,'ingreso':json.loads(old[1])}
   p=self.product(data.get('sku',''),actor)
   if p['revision']!=data.get('revisionProducto'):raise Conflict('El producto cambió. Escanéalo de nuevo antes de registrar la cantidad.')
   qty=quantity(data.get('cantidad'),p['unidad']);date=now();month=date[:7];id=uuid.uuid4().hex;number=db.execute('SELECT COUNT(*)+1 FROM pt_entries').fetchone()[0]
   entry={'id':id,'folio':'PT-'+{'EJIDOS':'EJI','SAN PABLO':'SP','CUAUTITLAN':'CUA'}[branch]+'-'+str(number).zfill(7),'fecha':date,'mes':month,'sucursal':branch,**p,'revisionMaestro':p['revision'],'cantidad':qty,'estado':'REGISTRADO','usuario':actor['email'],'capturo':actor['name'],'referencia':text(data.get('referencia',''),100),'revision':1}
   db.execute('INSERT INTO pt_entries VALUES(?,?,?,?,?,?,?)',(id,branch,month,actor['email'],key,stamp,dumps(entry)));self.queued(db,branch,month)
  if self.publisher:self.publisher.kick()
  return {'ok':True,'repetido':False,'ingreso':entry}
 def cancel(self,data,actor):
  self.scope(actor)
  if actor['role'] not in MANAGERS:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador corrigen ingresos PT.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM pt_entries WHERE id=?',(data.get('id'),)).fetchone()
   if not row:raise ValueError('Ingreso no encontrado.')
   entry=json.loads(row[0]);self.scope(actor,entry['sucursal'])
   if entry['revision']!=data.get('revision') or entry['estado']!='REGISTRADO':raise Conflict('El ingreso cambió o ya fue cancelado.')
   entry.update({'estado':'CANCELADO','revision':entry['revision']+1,'cancelacion':{'fecha':now(),'usuario':actor['email'],'motivo':text(data.get('motivo',''),500)}});db.execute('UPDATE pt_entries SET payload=? WHERE id=?',(dumps(entry),entry['id']));self.queued(db,entry['sucursal'],entry['mes'])
  if self.publisher:self.publisher.kick()
  return {'ok':True,'ingreso':entry}
 def entries(self,actor,q):
  allowed=self.scope(actor);branch=q.get('sucursal');month=q.get('mes',now()[:7])
  if branch:self.scope(actor,branch);allowed=[branch]
  if not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])',month):raise ValueError('Selecciona un mes válido.')
  with self.store.connect() as db:
   rows=[json.loads(p) for b,c,p in db.execute('SELECT branch,creator,payload FROM pt_entries WHERE month=? ORDER BY rowid DESC',(month,)) if b in allowed and (actor['role'] in MANAGERS or c==actor['email'])]
  totals={}
  for e in rows:
   if e['estado']!='REGISTRADO':continue
   k=(e['sucursal'],e['sku'],e['unidad']);r=totals.setdefault(k,{'sucursal':e['sucursal'],'sku':e['sku'],'descripcion':e['descripcion'],'unidad':e['unidad'],'cantidad':Decimal(0)});r['cantidad']+=Decimal(e['cantidad'])
  return {'ingresos':rows,'resumen':[{**r,'cantidad':str(r['cantidad'])} for r in totals.values()],'mes':month}
 def workbook(self,actor,q):
  from comercial_print import report_xlsx
  result=self.entries(actor,q);rows=[['ID_MOVIMIENTO','Folio','Fecha','Sucursal','SKU','Descripción','Unidad','Cantidad capturada','Cantidad','Estado','Usuario','Referencia']]
  for e in reversed(result['ingresos']):rows.append([e['id'],e['folio'],display_date(e['fecha']),e['sucursal'],e['sku'],e['descripcion'],e['unidad'],e['cantidad'],e['cantidad'] if e['estado']=='REGISTRADO' else '0',e['estado'],e['usuario'],e['referencia']])
  totals=[['Sucursal','SKU','Descripción','Unidad','Cantidad']]+[[r[k] for k in ('sucursal','sku','descripcion','unidad','cantidad')] for r in result['resumen']]
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dest:
   with zipfile.ZipFile(io.BytesIO(report_xlsx(rows,'INGRESOS_PT'))) as first:
    for name in first.namelist():
     raw=first.read(name)
     if name=='xl/workbook.xml':raw=raw.replace(b'</sheets>',b'<sheet name="RESUMEN_PT" sheetId="2" r:id="rId2"/></sheets>')
     elif name=='xl/_rels/workbook.xml.rels':raw=raw.replace(b'</Relationships>',b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
     elif name=='[Content_Types].xml':raw=raw.replace(b'</Types>',b'<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
     dest.writestr(name,raw)
   with zipfile.ZipFile(io.BytesIO(report_xlsx(totals,'RESUMEN_PT'))) as second:dest.writestr('xl/worksheets/sheet2.xml',second.read('xl/worksheets/sheet1.xml'))
  return out.getvalue()
 def labels(self,actor,q):
  self.scope(actor)
  if actor['role'] not in MANAGERS and actor['role']!='ventas':raise PermissionError('Solicita las etiquetas a Gerencia, AUXTI o Superadministrador.')
  from reportlab.pdfgen import canvas
  from reportlab.lib.pagesizes import A4
  from reportlab.graphics import renderPDF
  from reportlab.graphics.barcode import createBarcodeDrawing
  from reportlab.pdfbase.pdfmetrics import stringWidth
  products=self.catalog();selected=q.get('skus','').split(',') if q.get('skus') else list(products)
  if not selected or len(selected)>2000 or len(set(selected))!=len(selected) or any(s not in products for s in selected):raise ValueError('Selecciona hasta 2,000 productos activos diferentes.')
  out=io.BytesIO();c=canvas.Canvas(out,pagesize=A4);width,height=A4
  for index,sku in enumerate(selected):
   if index and index%10==0:c.showPage()
   x=20+(index%2)*(width/2);y=height-20-(index%10//2)*155
   c.setStrokeColorRGB(.85,.85,.85);c.rect(x,y-145,width/2-25,140)
   qr=createBarcodeDrawing('QR',value=qr_value(sku,q.get('servidor','')),width=84,height=84,barBorder=4);renderPDF.draw(qr,c,x+3,y-92)
   p=products[sku];c.setFont('Helvetica-Bold',9);c.drawString(x+90,y-22,sku);c.setFont('Helvetica',8);name=p['descripcion'];words=name.split();line='';lines=[]
   for word in words:
    if stringWidth((line+' '+word).strip(),'Helvetica',8)>165:lines.append(line);line=word
    else:line=(line+' '+word).strip()
   lines.append(line)
   for n,line in enumerate(lines[:4]):c.drawString(x+90,y-36-10*n,line[:45])
   c.drawString(x+90,y-83,p['unidad'][:35]);bars=createBarcodeDrawing('Code128',value=sku,barHeight=25,barWidth=.8,humanReadable=True,quiet=True);bars.width
   c.saveState();c.translate(x+7,y-133);scale=min(1,(width/2-40)/bars.width);c.scale(scale,1);renderPDF.draw(bars,c,0,0);c.restoreState()
  c.save();return out.getvalue()
