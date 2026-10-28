"""Respaldo comercial completo; restauración sin borrar ventas ni movimientos posteriores."""
import json,re,sqlite3
from decimal import Decimal
from comercial import amount,tax_line,money
from requisiciones import BRANCHES,Conflict

TABLES=('cm_companies','cm_access','cm_products','cm_prices','cm_customers','cm_templates','cm_reports','cm_boxes','cm_sessions','cm_sequences','cm_sequence_registry','cm_documents','cm_versions','cm_cancellations','cm_cash_moves','cm_audit','cm_revision','cm_source')
def check(value,message):
 if not value:raise ValueError(message)
def dictionaries(data,table):
 t=data['tablas'][table];return [dict(zip(t['columnas'],r)) for r in t['filas']]
def validate(db,data):
 tables=data.get('tablas');check(isinstance(tables,dict) and set(tables)==set(TABLES),'El respaldo comercial debe incluir ambas operaciones, empresas, cajas, precios y folios.')
 with sqlite3.connect(':memory:') as scratch:
  for table in TABLES:
   info=db.execute('PRAGMA table_info('+table+')').fetchall();columns=[r[1] for r in info];value=tables[table]
   check(isinstance(value,dict) and value.get('columnas')==columns and isinstance(value.get('filas'),list) and len(value['filas'])<=200000,'Estructura comercial incompatible: '+table)
   scratch.execute(db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()[0])
   for row in value['filas']:
    check(isinstance(row,list) and len(row)==len(columns) and all(v is None or type(v) in (str,int,float) for v in row),'Fila comercial inválida.')
    r=dict(zip(columns,row))
    if 'revision' in r:check(type(r['revision']) is int and r['revision']>=0,'Revisión comercial inválida.')
    if 'payload' in r:check(isinstance(json.loads(r['payload']),dict),'Contenido comercial inválido.')
   scratch.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in columns)+')',value['filas'])
  for name in ('cm_open_box','cm_cancel_pending'):
   scratch.execute(db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?",(name,)).fetchone()[0])
 companies={r['id']:r for r in dictionaries(data,'cm_companies')};products={r['sku']:r for r in dictionaries(data,'cm_products')};customers={r['id']:r for r in dictionaries(data,'cm_customers')};boxes={r['id']:r for r in dictionaries(data,'cm_boxes')};sessions={r['id']:r for r in dictionaries(data,'cm_sessions')};docs={r['id']:r for r in dictionaries(data,'cm_documents')}
 for table in TABLES:
  for r in dictionaries(data,table):
   if 'company' in r and table!='cm_audit':check(r['company'] in companies,'Referencia a una razón social inexistente.')
 for r in companies.values():
  v=json.loads(r['payload']);check(type(r['id']) is int and r['id']>0 and isinstance(v.get('nombre'),str) and isinstance(v.get('sucursales'),list) and all(b in BRANCHES for b in v['sucursales']),'Razón social inválida.')
 for sku,r in products.items():
  p=json.loads(r['payload']);check(re.fullmatch('[A-Z0-9]{14}',sku) and p.get('nombre') and p.get('unidad') and (p.get('iva') is None or amount(p.get('iva')) in (0,8,16)),'Producto comercial inválido.')
 for r in dictionaries(data,'cm_prices'):
  check(r['sku'] in products and r['list'] in ('PUBLICO','RUTA','DESPACHO'),'Precio sin producto/lista.');amount(json.loads(r['payload'])['precio'])
  if r['customer']:check(r['customer'] in customers and customers[r['customer']]['company']==r['company'],'Precio de cliente de otra empresa.')
 for r in sessions.values():check(r['box'] in boxes and boxes[r['box']]['company']==r['company'] and r['state'] in ('ABIERTA','CERRADA'),'Sesión de caja inválida.')
 for r in docs.values():
  v=json.loads(r['payload']);check(r['channel'] in ('ventasins','expendios') and v.get('empresa')==r['company'] and v.get('estado')==r['state'] and v.get('folio')==r['number'],'Documento comercial incompatible.')
  check(isinstance(v.get('partidas'),list) and 1<=len(v['partidas'])<=200,'Partidas inválidas en documento.')
  for line in v['partidas']:
   check(line['sku'] in products,'Documento con producto inexistente.');calculated=tax_line(line['cantidad'],line['precio'],line['iva'],line.get('descuento','0'))
   check(all(calculated[k]==line[k] for k in ('base','impuesto','total')),'Importes incompatibles en documento.')
  check(all(money(sum(Decimal(p[k]) for p in v['partidas']))==v[k] for k in ('base','impuesto','total')),'Total comercial incorrecto.')
  if r['channel']=='expendios':check(r['session'] in sessions and sessions[r['session']]['company']==r['company'] and sessions[r['session']]['box']==r['box'],'Venta asociada a otra caja/empresa.')
 for r in dictionaries(data,'cm_cash_moves'):check(r['session'] in sessions and sessions[r['session']]['company']==r['company'],'Movimiento sin sesión de caja.')
 for r in dictionaries(data,'cm_cancellations'):check(r['document'] in docs and docs[r['document']]['company']==r['company'],'Cancelación sin venta.')
 for r in dictionaries(data,'cm_versions'):check(r['document'] in docs,'Versión sin documento.')
 for r in dictionaries(data,'cm_sequences'):check(type(r['next']) is int and r['next']>=1 and 1<=r['width']<=12,'Consecutivo comercial inválido.')
 check(len(dictionaries(data,'cm_revision'))==1 and dictionaries(data,'cm_revision')[0]['id']==1,'Falta revisión comercial.')
 check(len(dictionaries(data,'cm_source'))==1 and dictionaries(data,'cm_source')[0]['id']==1,'Falta configuración de fuente.')
 # La recuperación en una instalación vacía es completa. En una base activa no se
 # permite retroceder documentos, cierres, reembolsos ni decisiones ya registrados.
 for table in ('cm_documents','cm_sessions','cm_cash_moves','cm_cancellations'):
  incoming={row[0]:row for row in tables[table]['filas']}
  for row in db.execute('SELECT * FROM '+table):
   if incoming.get(row[0])!=list(row):raise Conflict('El respaldo es anterior a operaciones comerciales actuales. Restáuralo en una instalación vacía para no perder ventas, cierres ni reembolsos.')

def summary(data):
 docs=dictionaries(data,'cm_documents');return {'razonesSociales':len(dictionaries(data,'cm_companies')),'productos':len(dictionaries(data,'cm_products')),'clientes':len(dictionaries(data,'cm_customers')),'pedidosInstitucionales':sum(r['channel']=='ventasins' for r in docs),'ventasExpendios':sum(r['channel']=='expendios' for r in docs),'sesiones':len(dictionaries(data,'cm_sessions')),'movimientos':len(dictionaries(data,'cm_cash_moves')),'versionesHistoricas':len(dictionaries(data,'cm_versions'))}

def restore(db,incoming,current):
 old_sequences=dictionaries(current,'cm_sequences');old_registry=dictionaries(current,'cm_sequence_registry');old_audit=dictionaries(current,'cm_audit');old_revision=dictionaries(current,'cm_revision')[0]['revision'];old_source=dictionaries(current,'cm_source')[0]['revision']
 for table in reversed(TABLES):db.execute('DELETE FROM '+table)
 for table in TABLES:
  t=incoming['tablas'][table];db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in t['columnas'])+')',t['filas'])
 for r in old_sequences:
  db.execute('INSERT OR IGNORE INTO cm_sequences VALUES(?,?,?,?,?,?)',tuple(r.values()));db.execute('UPDATE cm_sequences SET next=MAX(next,?),revision=MAX(revision,?)+1 WHERE company=? AND kind=?',(r['next'],r['revision'],r['company'],r['kind']))
 for r in old_registry:
  existing=db.execute('SELECT kind FROM cm_sequence_registry WHERE company=? AND series=?',(r['company'],r['series'])).fetchone();check(not existing or existing[0]==r['kind'],'La serie restaurada pertenece a otra operación.');db.execute('INSERT OR IGNORE INTO cm_sequence_registry VALUES(?,?,?)',tuple(r.values()))
 known={tuple(r) for r in db.execute('SELECT company,actor,created,action,payload FROM cm_audit')}
 for r in old_audit:
  values=tuple(r[k] for k in ('company','actor','created','action','payload'))
  if values not in known:db.execute('INSERT INTO cm_audit(company,actor,created,action,payload) VALUES(?,?,?,?,?)',values);known.add(values)
 db.execute('UPDATE cm_revision SET revision=MAX(revision,?)+1 WHERE id=1',(old_revision,));row=db.execute('SELECT revision,payload FROM cm_source WHERE id=1').fetchone();source=json.loads(row[1]);source['habilitada']=False
 db.execute('UPDATE cm_source SET revision=?,payload=?,state=? WHERE id=1',(max(old_source,row[0])+1,json.dumps(source,ensure_ascii=False),json.dumps({'enProceso':False,'mensaje':'Fuente restaurada. Revisa y activa la sincronización cuando corresponda.'})))
