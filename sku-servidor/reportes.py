"""Reportes configurables: importes decimales, equivalencias explícitas y alcance por usuario."""
import base64,collections,datetime,decimal,json,re,uuid
from requisiciones import BRANCHES,AREAS,Conflict,norm,now,parse_master,visible_branches,csv_bytes,text
D=decimal.Decimal
EDITORS={'superadmin','auxti','gerente'}
CENT=D('.01')
def dec(value,positive=False):
 try:
  if isinstance(value,bool):raise ValueError()
  result=D(str(value))
  if not result.is_finite() or result<0 or result>D('1000000000000000') or result.as_tuple().exponent < -18 or positive and result<=0:raise ValueError()
  return result
 except (ValueError,decimal.InvalidOperation,TypeError):raise ValueError('Importe o equivalencia inválidos.')
def quantity_totals(details):
 groups={}
 for d in details:
  key=d['unidad'];g=groups.setdefault(key,{'unidad':key,'requisitado':D(0),'surtido':D(0)})
  g['requisitado']+=D(d['cantidadRequisitada']);g['surtido']+=D(d['cantidadSurtida'])
 return [{k:format(v,'f') if isinstance(v,D) else v for k,v in g.items()} for g in groups.values()]

def money(value):return str(value.quantize(CENT,rounding=decimal.ROUND_HALF_UP))
def unit(value):
 n=norm(value);aliases={'PIEZAS':'PIEZA','PZA':'PIEZA','PZAS':'PIEZA','PZS':'PIEZA','KG':'KILOGRAMO','KGS':'KILOGRAMO','KILO':'KILOGRAMO','KILOS':'KILOGRAMO','KILOGRAMOS':'KILOGRAMO','LT':'LITRO','LTS':'LITRO','LITROS':'LITRO','GR':'GRAMO','GRS':'GRAMO','GRAMOS':'GRAMO','ML':'MILILITRO','MILILITROS':'MILILITRO','PAQ':'PAQUETE','BOLSAS':'BOLSA'}
 return aliases.get(n,n)
def dimension(value):
 u=unit(value);simple={'KILOGRAMO':('masa',D(1000)),'GRAMO':('masa',D(1)),'LITRO':('volumen',D(1000)),'MILILITRO':('volumen',D(1)),'PIEZA':('pieza',D(1)),'MILLAR':('pieza',D(1000))}
 if u in simple:return simple[u]
 s=str(value).upper().replace(',','.')
 if len(re.findall(r'\d+(?:\.\d+)?',s))!=1:return None
 matches=re.findall(r'(\d+(?:\.\d+)?)\s*(KILOGRAMOS?|KGS?|GRAMOS?|GRS?|LITROS?|LTS?|MILILITROS?|ML|PIEZAS?|PZAS?|PZS)\b',s)
 if len(matches)!=1:return None
 number,label=matches[0]
 try:amount=D(number.replace(' ','.'))
 except decimal.InvalidOperation:return None
 dim=simple.get(unit(label))
 return (dim[0],amount*dim[1]) if dim and amount>0 else None
def infer_factor(material):
 purchase=material.get('unidadCompra','');requested=material.get('unidad','')
 if str(material.get('factorMaestro','')).strip() in ('0','0.0','0.00'):return None,'Equivalencia U_M en cero; pendiente de corregir.'
 if not purchase or not requested:return None,'Falta unidad de compra o entrega.'
 if unit(purchase)==unit(requested):return '1','Misma unidad de compra y solicitud.'
 if unit(requested) in {'CAJA','BOLSA','BULTO','BOTE','CUBETA','PAQUETE','PIEZA','GALON','BOTELLA','BIDON','PORRON'} and norm(purchase).startswith(unit(requested)+' '):return '1','Misma presentación del producto.'
 p=dimension(purchase);q=dimension(requested)
 if not p or not q or p[0]!=q[0]:return None,'Confirma cuántas unidades solicitadas contiene una unidad de compra.'
 factor=p[1]/q[1]
 # Cuando la presentación y el factor del maestro se contradicen no se inventa una conversión.
 raw=material.get('factorMaestro','')
 if raw and unit(purchase) not in ('KILOGRAMO','GRAMO','LITRO','MILILITRO','PIEZA'):
  try:
   source=dec(raw,True);base=p[1]/D(1000) if p[0] in ('masa','volumen') else p[1]
   if abs(source-base)>D('.000001'):return None,'La presentación y U_M no coinciden; confirma la equivalencia.'
  except ValueError:return None,'El factor U_M requiere revisión.'
 return format(factor,'f'),'Equivalencia de unidades de la presentación.'
class ReportStore:
 def __init__(self,store,requisitions):
  self.store=store;self.requisitions=requisitions
  with store.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS req_costs(material_id INTEGER PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS req_reports(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS req_report_features(key TEXT PRIMARY KEY)')
   if not db.execute("SELECT 1 FROM req_report_features WHERE key='costos-compra-v1'").fetchone():
    records={json.loads(p)['source_key']:(id,json.loads(p)) for id,p in db.execute('SELECT id,payload FROM req_materials')};pending=set(records)
    for filename,content in db.execute('SELECT filename,content FROM req_masters ORDER BY id DESC').fetchall():
     if not pending:break
     try:parsed=parse_master(base64.b64decode(content),filename)
     except ValueError:continue
     for source in parsed['materiales']:
      key=source['source_key']
      if key not in pending or source.get('precioCompra','')=='':continue
      id,old=records[key];config=self.from_material({**old,**source},'Maestro: '+filename)
      db.execute('INSERT OR IGNORE INTO req_costs VALUES(?,1,?)',(id,json.dumps(config,ensure_ascii=False)));pending.remove(key)
    db.execute("INSERT INTO req_report_features VALUES('costos-compra-v1')")
   if not db.execute('SELECT 1 FROM req_reports').fetchone():
    config={'id':'general','nombre':'Reporte general de requisiciones','desde':'','hasta':'','sucursales':[],'areas':[],'solicitante':'','material':'','folios':'','agrupacion':'sucursal','impuestos':[],'actualizado':now(),'editor':'CARGA INICIAL'}
    db.execute('INSERT INTO req_reports VALUES(?,1,?)',('general',json.dumps(config,ensure_ascii=False)))
   needs_units=not db.execute("SELECT 1 FROM req_report_features WHERE key='costos-um-entrega-v3-costo'").fetchone()
  if needs_units:
   self.sync_import(None)
   with store.connect() as db:
    for key in ('costos-um-entrega-v2','costos-um-entrega-v3-costo'):db.execute('INSERT OR IGNORE INTO req_report_features VALUES(?)',(key,))
 @staticmethod
 def from_material(material,origin):
  factor,reason=infer_factor(material)
  direct=material.get('costoBaseMaestro','')
  return {'precioCompra':material.get('precioCompra',''),'costoEntrega':direct,'unidadCompra':material.get('unidadCompra',''),'unidadSolicitud':material['unidad'],'factor':factor,'motivo':reason,'origen':origin+(' · COSTO por UM_ENTREGA' if direct!='' else ' · Precio/equivalencia'),'actualizado':now()}
 def sync_import(self,actor):
  # Nuevos materiales reciben costo inicial; solo editores pueden cambiar el costo de referencias existentes.
  materials={r['source_key']:r for r in self.requisitions.materials()}
  by_name=collections.defaultdict(list)
  for r in materials.values():by_name[(norm(r['nombre']),norm(r['proveedor']))].append(r)
  name,raw=self.requisitions.master_file()
  try:parsed=parse_master(raw,name)
  except ValueError:
   if not materials:return
   raise
  with self.store.connect() as db:
   for source in parsed['materiales']:
    material=materials.get(source['source_key'])
    if material is None:
     candidates=by_name.get((norm(source['nombre']),norm(source['proveedor'])),[])
     if len(candidates)>1:candidates=[r for r in candidates if r.get('fila')==source.get('fila')]
     material=candidates[0] if len(candidates)==1 else None
    if not material or source.get('precioCompra','')=='' and source.get('costoBaseMaestro','')=='':continue
    previous=db.execute('SELECT revision,payload FROM req_costs WHERE material_id=?',(material['id'],)).fetchone()
    config=self.from_material({**material,**source},'Maestro: '+name)
    if previous:
     old=json.loads(previous[1])
     if old.get('origen')=='Configuración del reporte':
      if old['unidadSolicitud']==material['unidad']:continue
      config={**old,'unidadSolicitud':material['unidad'],'factor':None,'motivo':'Cambió UM_ENTREGA; confirma de nuevo la equivalencia manual.','actualizado':now()}
     db.execute('UPDATE req_costs SET revision=?,payload=? WHERE material_id=?',(previous[0]+1,json.dumps(config,ensure_ascii=False),material['id']))
    else:db.execute('INSERT INTO req_costs VALUES(?,1,?)',(material['id'],json.dumps(config,ensure_ascii=False)))
 def costs(self):
  with self.store.connect() as db:configs={id:{**json.loads(payload),'revision':rev} for id,rev,payload in db.execute('SELECT material_id,revision,payload FROM req_costs')}
  result=[]
  for r in self.requisitions.materials():
   c=configs.get(r['id'],{'revision':0,'precioCompra':'','unidadCompra':'','unidadSolicitud':r['unidad'],'factor':None,'motivo':'Falta costo de compra.','origen':'Sin costo','actualizado':''})
   price=None
   try:
    factor=dec(c['factor'],True);price=dec(c['costoEntrega']) if c.get('costoEntrega') not in (None,'') else dec(c['precioCompra'])/factor
   except ValueError:pass
   result.append({'materialId':r['id'],'sku':r['sku'],'nombre':r['nombre'],'unidad':r['unidad'],**c,'costoUnitario':format(price,'f') if price is not None else None})
  return result
 def save_cost(self,data,actor):
  if actor['role'] not in EDITORS:raise PermissionError('Solo Gerente y Superadministrador pueden modificar costos y equivalencias del reporte.')
  id=data.get('materialId');rev=data.get('revision')
  if type(id) is not int or type(rev) is not int:raise ValueError('Material o revisión inválidos.')
  direct=data.get('costoEntrega','');direct=format(dec(direct),'f') if direct not in (None,'') else '';price=dec(data.get('precioCompra')) if data.get('precioCompra') not in (None,'') else None;factor=dec(data.get('factor'));purchase=text(data.get('unidadCompra',''),160)
  if price is None and direct=='':raise ValueError('Indica COSTO de entrega o precio de compra.')
  if factor and factor<D('0.000000000001'):raise ValueError('La equivalencia es demasiado pequeña.')
  if not purchase:raise ValueError('Indica la unidad de compra.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM req_materials WHERE id=?',(id,)).fetchone()
   if not row:raise ValueError('Material no disponible.')
   previous=db.execute('SELECT revision FROM req_costs WHERE material_id=?',(id,)).fetchone()
   if (previous[0] if previous else 0)!=rev:raise Conflict('El costo cambió. Actualiza antes de guardar.')
   c={'precioCompra':format(price,'f') if price is not None else '','costoEntrega':direct,'unidadCompra':purchase,'unidadSolicitud':json.loads(row[0])['unidad'],'factor':format(factor,'f'),'motivo':'Equivalencia cero: pendiente de corregir; excluida del importe valorizado.' if not factor else 'Equivalencia confirmada por '+actor['email'],'origen':'Configuración del reporte','actualizado':now()}
   db.execute('INSERT INTO req_costs VALUES(?,?,?) ON CONFLICT(material_id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(id,rev+1,json.dumps(c,ensure_ascii=False)))
  return {'ok':True}
 def definitions(self):
  with self.store.connect() as db:rows=db.execute('SELECT revision,payload FROM req_reports ORDER BY rowid').fetchall()
  return [{**json.loads(payload),'revision':rev} for rev,payload in rows]
 def config(self,data,area_names=None):
  name=text(data.get('nombre',''),120)
  if not name:raise ValueError('Escribe un nombre para el reporte.')
  c={'nombre':name}
  for key,allowed in [('sucursales',BRANCHES),('areas',self.requisitions.areas.names(historical=True) if area_names is None else area_names)]:
   values=data.get(key,[])
   if not isinstance(values,list) or any(not isinstance(v,str) or v not in allowed for v in values) or len(set(values))!=len(values):raise ValueError('Filtro inválido: '+key)
   c[key]=values
  for key in ('desde','hasta'):
   value=text(data.get(key,''),10)
   if value:
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Usa fecha AAAA-MM-DD.')
    try:datetime.date.fromisoformat(value)
    except ValueError:raise ValueError('Fecha de filtro inválida.')
   c[key]=value
  if c['desde'] and c['hasta'] and c['desde']>c['hasta']:raise ValueError('El rango de fechas es inválido.')
  for key in ('solicitante','material','folios'):c[key]=text(data.get(key,''),200)
  c['agrupacion']=data.get('agrupacion','sucursal')
  if c['agrupacion'] not in ('general','sucursal','area','requisicion','material','unidad'):raise ValueError('Agrupación inválida.')
  taxes=data.get('impuestos',[])
  if not isinstance(taxes,list) or len(taxes)>8:raise ValueError('Se admiten hasta ocho impuestos.')
  c['impuestos']=[]
  for tax in taxes:
   if not isinstance(tax,dict):raise ValueError('Impuesto inválido.')
   label=text(tax.get('nombre',''),40);rate=dec(tax.get('tasa'))
   if not label or rate>100:raise ValueError('Indica nombre y porcentaje de impuesto entre 0 y 100.')
   c['impuestos'].append({'nombre':label,'tasa':format(rate,'f')})
  return c
 def save(self,data,actor):
  if actor['role'] not in EDITORS:raise PermissionError('Solo Gerente y Superadministrador pueden crear o modificar reportes.')
  c=self.config(data);id=data.get('id') or uuid.uuid4().hex;rev=data.get('revision',0)
  if not isinstance(id,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,64}',id) or type(rev) is not int:raise ValueError('Reporte inválido.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT revision FROM req_reports WHERE id=?',(id,)).fetchone()
   if (old[0] if old else 0)!=rev:raise Conflict('El reporte cambió. Actualiza antes de guardar.')
   c.update({'id':id,'actualizado':now(),'editor':actor['email']});db.execute('INSERT INTO req_reports VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(id,rev+1,json.dumps(c,ensure_ascii=False)))
  return {**c,'revision':rev+1}
 def run(self,actor,id=None,preview=None):
  with decimal.localcontext() as context:
   context.prec=60
   return self._run(actor,id,preview)
 def _run(self,actor,id=None,preview=None):
  if actor['role']=='requisicion':raise PermissionError('Este perfil solo puede consultar sus propias requisiciones.')
  if preview is not None:
   if actor['role'] not in EDITORS:raise PermissionError('Solo los editores pueden armar un reporte.')
   c=self.config(preview)
  else:
   with self.store.connect() as db:row=db.execute('SELECT payload FROM req_reports WHERE id=?',(id,)).fetchone()
   if not row:raise ValueError('Reporte no disponible.')
   c=json.loads(row[0])
  branches=[b for b in visible_branches(actor) if not c['sucursales'] or b in c['sucursales']]
  clauses=['branch IN ('+','.join('?' for _ in branches)+')'];params=list(branches)
  if c['desde']:clauses.append('created_at>=?');params.append(c['desde'])
  if c['hasta']:clauses.append('created_at<?');params.append((datetime.date.fromisoformat(c['hasta'])+datetime.timedelta(days=1)).isoformat())
  with self.store.connect() as db:
   cursor=db.execute('SELECT payload FROM req_documents WHERE '+' AND '.join(clauses)+' ORDER BY created_at, rowid',params)
   docs=[];cancelled=0
   for row in cursor:
    doc=json.loads(row[0])
    if c['areas'] and doc['area'] not in c['areas'] or c['solicitante'] and norm(c['solicitante']) not in norm(doc['solicitante']) or c['folios'] and norm(c['folios']) not in norm(doc['numero']):continue
    if doc.get('estado')=='CANCELADA':
     if not c['material'] or any(norm(c['material']) in norm(line['nombre']+' '+line['sku']) for line in doc['partidas']):cancelled+=1
     continue
    docs.append(doc)
    if len(docs)>20000:raise ValueError('El reporte supera 20,000 requisiciones. Reduce el rango de fechas.')
  costs={r['materialId']:r for r in self.costs()};details=[];groups={};totals={'baseRequisitado':D(0),'totalRequisitado':D(0),'base':D(0),'impuestos':D(0),'total':D(0),'pendientes':0,'partidas':0};doc_ids=set()
  for doc in docs:
   for index,line in enumerate(doc['partidas']):
    if c['material'] and norm(c['material']) not in norm(line['nombre']+' '+line['sku']):continue
    if len(details)>=100000:raise ValueError('El reporte supera 100,000 partidas. Reduce los filtros.')
    cost=costs.get(line['materialId']);value=None;factor_line=None;numerator=None;reason='Falta costo de compra o equivalencia.'
    if cost and cost['costoUnitario'] is not None:
     if unit(cost['unidadSolicitud'])==unit(line['unidad']):factor_line=dec(cost['factor'],True)
     elif unit(cost['unidadCompra'])==unit(line['unidad']):factor_line=D(1)
     else:
      current=dimension(cost['unidadSolicitud']);previous=dimension(line['unidad'])
      if current and previous and current[0]==previous[0]:factor_line=dec(cost['factor'],True)*current[1]/previous[1]
     if factor_line is not None:
      numerator=dec(cost['costoEntrega'])*dec(cost['factor'],True) if cost.get('costoEntrega') not in (None,'') else dec(cost['precioCompra']);value=numerator/factor_line;reason=''
     else:reason='La unidad histórica de la requisición requiere confirmar su equivalencia.'
    elif cost:reason=cost['motivo']
    requested=dec(line['cantidad'],True);quantity=dec(line.get('cantidadSurtida','0'));requested_base=(requested*numerator/factor_line).quantize(CENT,rounding=decimal.ROUND_HALF_UP) if value is not None else None
    requested_total=requested_base+sum(((requested_base*dec(t['tasa'])/100).quantize(CENT,rounding=decimal.ROUND_HALF_UP) for t in c['impuestos']),D(0)) if requested_base is not None else None
    base=D(0) if quantity==0 else (quantity*numerator/factor_line).quantize(CENT,rounding=decimal.ROUND_HALF_UP) if value is not None else None
    tax_values=[{'nombre':t['nombre'],'tasa':t['tasa'],'importe':money(base*dec(t['tasa'])/100) if base is not None else None} for t in c['impuestos']]
    tax=sum((D(t['importe']) for t in tax_values),D(0)) if base is not None else None;total=base+tax if base is not None else None
    detail={'requisicionId':doc['id'],'folio':doc['numero'],'fecha':doc['fecha'],'sucursal':doc['sucursal'],'area':doc['area'],'solicitante':doc['solicitante'],'materialId':line['materialId'],'sku':line['sku'],'descripcion':line['nombre'],'estado':doc['estado'],'cantidadRequisitada':line['cantidad'],'cantidadSurtida':format(quantity,'f'),'cantidad':format(quantity,'f'),'costoRequisitado':money(requested_base) if requested_base is not None else None,'totalRequisitado':money(requested_total) if requested_total is not None else None,'unidad':line['unidad'],'costoUnitario':format(value,'f') if value is not None else None,'costoCompra':money(base) if base is not None else None,'impuestos':tax_values,'importeImpuestos':money(tax) if tax is not None else None,'total':money(total) if total is not None else None,'pendiente':reason,'origenCosto':cost['origen'] if cost else 'Sin costo'}
    details.append(detail);doc_ids.add(doc['id']);totals['partidas']+=1;totals['pendientes']+=int(value is None)
    label={'general':'General','sucursal':doc['sucursal'],'area':doc['area'],'requisicion':doc['numero'],'material':line['nombre'],'unidad':line['unidad']}[c['agrupacion']]
    key=(label,line['materialId'] if c['agrupacion']=='material' else None,line['unidad'] if c['agrupacion'] in ('material','unidad') else None)
    g=groups.setdefault(key,{'grupo':label,'materialId':line['materialId'] if c['agrupacion']=='material' else None,'unidad':line['unidad'] if c['agrupacion'] in ('material','unidad') else '', 'cantidadRequisitada':D(0) if c['agrupacion'] in ('material','unidad') else None,'baseRequisitado':D(0),'totalRequisitado':D(0),'cantidad':D(0) if c['agrupacion'] in ('material','unidad') else None,'base':D(0),'impuestos':D(0),'total':D(0),'pendientes':0,'partidas':0,'requisiciones':set()})
    g['partidas']+=1;g['pendientes']+=int(value is None);g['requisiciones'].add(doc['id'])
    if g['cantidad'] is not None:g['cantidad']+=quantity;g['cantidadRequisitada']+=requested
    if requested_base is not None:
     for obj in (totals,g):obj['baseRequisitado']+=requested_base;obj['totalRequisitado']+=requested_total
    if base is not None:
     for obj in (totals,g):obj['base']+=base;obj['impuestos']+=tax;obj['total']+=total
  result_groups=[]
  for g in groups.values():result_groups.append({**g,'cantidad':format(g['cantidad'],'f') if g['cantidad'] is not None else None,'cantidadSurtida':format(g['cantidad'],'f') if g['cantidad'] is not None else None,'cantidadRequisitada':format(g['cantidadRequisitada'],'f') if g['cantidadRequisitada'] is not None else None,'totalSurtido':money(g['total']),'requisiciones':len(g['requisiciones']),**{k:money(g[k]) for k in ('base','impuestos','total','baseRequisitado','totalRequisitado')}})
  summary={**totals,**{k:money(totals[k]) for k in ('base','impuestos','total','baseRequisitado','totalRequisitado')},'totalSurtido':money(totals['total']),'cantidadesPorUnidad':quantity_totals(details),'requisiciones':len(doc_ids),'canceladasExcluidas':cancelled,'completo':totals['pendientes']==0}
  return {'configuracion':c,'generado':now(),'baseValuacion':'COSTO del maestro por UM/UOM_ENTREGA × cantidad realmente surtida. Se compara total requisitado contra total surtido; sin entrega registrada, surtido es cero. Si COSTO está vacío se calcula con precio de compra/equivalencia. Costo vigente, no histórico de emisión.','alcance':branches,'resumen':summary,'grupos':result_groups,'detalle':details}
def report_csv(report):
 rows=[['FOLIO','FECHA','SUCURSAL','AREA','SOLICITANTE','SKU','DESCRIPCION','REQUISITADO','SURTIDO','UNIDAD','ESTADO','COSTO UNITARIO','TOTAL REQUISITADO','COSTO SURTIDO','TOTAL SURTIDO']]
 rows += [[r[k] if r[k] is not None else '' for k in ('folio','fecha','sucursal','area','solicitante','sku','descripcion','cantidadRequisitada','cantidadSurtida','unidad','estado','costoUnitario','totalRequisitado','costoCompra','total')] for r in report['detalle']]
 return csv_bytes(rows)
