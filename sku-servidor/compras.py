from permissions import require_module
"""Actualización de compras en lote, por PRODUCTOS, sin comparar cada fila contra todo el catálogo."""
import base64,collections,copy,datetime,io,json,re,time,zipfile,xml.etree.ElementTree as ET
from requisiciones import Conflict,NS,norm,read_rows,text,now

ALIASES={'INSUMOS':'INSUMO','FIGURAS':'FIGURA','COBERTURA':'COBERTURA Y CONFITERIA','CONFITERIA Y COBERTURAS':'COBERTURA Y CONFITERIA','ARTCULOS DE LIMPIEZA':'ARTICULOS DE LIMPIEZA','EQUIPO DE PROTECCION BASICO':'EQUIPO DE PROTECCION'}
def resolve(value,table):
 value=ALIASES.get(norm(value),norm(value))
 return next((key for key,label in table.items() if value in (key,norm(label))),None)

def parse_products(raw,filename,catalogs):
 if not filename.lower().endswith('.xlsx'):raise ValueError('Carga un Excel XLSX con la pestaña PRODUCTOS.')
 rows,_=read_rows(raw,filename);headers=None
 for index,(_,row) in enumerate(rows[:25]):
  names={norm(v):k for k,v in row.items() if norm(v)}
  if 'DESCRIPCION' in names or 'ARTICULO' in names:headers=names;break
 if headers is None:raise ValueError('Falta DESCRIPCIÓN en la pestaña PRODUCTOS.')
 def col(*labels):return next((headers[label] for label in labels if label in headers),None)
 columns={'nombre':col('DESCRIPCION','ARTICULO','NOMBRE'),'proveedor':col('PROVEEDOR PRINCIPAL','PROVEEDOR'),'skuFuente':col('SKU NUEVO','SKU','CLAVE'),'anteriorFuente':col('SKU ANTIGUO','SKU ANTERIOR'),'estado':col('STATUS DE COMPRA','ESTADO','ESTATUS'),'tipo':col('PRODUCTO','TIPO DE PRODUCTO'),'categoria':col('CATEGORIA'),'subcategoria':col('SUBCATEGORIA'),'claveProveedor':col('CLAVE PROVEEDOR'),'unidadCompra':col('UOM COMPRA','UM COMPRA'),'unidadEntrega':col('UOM ENTREGA','UM ENTREGA')}
 result=[]
 for number,row in rows[index+1:]:
  item={key:str(row.get(c,'') or '').strip() if c else '' for key,c in columns.items()}
  if not item['nombre']:continue
  if len(item['nombre'])>300 or len(item['proveedor'])>500:raise ValueError('Fila '+str(number)+': nombre o proveedor demasiado largo.')
  item['camposExcel']=row;item['filaFuente']=number;item['clasificacion']={key:resolve(item[key],catalogs[table]) for key,table in [('tipo','TIP'),('categoria','CAT'),('subcategoria','SUB')]};result.append(item)
 if not result or len(result)>20000:raise ValueError('El maestro debe contener entre 1 y 20,000 productos.')
 return result

def original_fields(master):
 raw=base64.b64decode(master);wb=ET.fromstring(zipfile.ZipFile(io.BytesIO(raw)).read('xl/workbook.xml'));names=[s.get('name') for s in wb.findall('m:sheets/m:sheet',NS)]
 for name in (['PRODUCTOS'] if 'PRODUCTOS' in names else names):
  rows,_=read_rows(raw,'original.xlsx',sheet_name=name)
  if any(norm(row.get('H'))=='DESCRIPCION' for _,row in rows[:25]):return dict(rows)
 return {}

class PurchaseImporter:
 def __init__(self,store,make_sku,validate,protect):self.store=store;self.make_sku=make_sku;self.validate=validate;self.protect=protect
 def run(self,data,actor):
  require_module(actor,'compras');require_module(actor,'cargar_maestro')
  started=time.perf_counter();filename=text(data.get('archivo',''),200)
  try:raw=base64.b64decode(data.get('contenido',''),validate=True)
  except Exception:raise ValueError('Archivo inválido.')
  incoming=parse_products(raw,filename,self.store.catalogs)
  legacy_counts=collections.Counter(norm(item['anteriorFuente']) for item in incoming if item['anteriorFuente'])
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');revision,payload=db.execute('SELECT revision,payload FROM catalog WHERE id=1').fetchone()
   if data.get('revision')!=revision:raise Conflict('El catálogo cambió. Actualiza y vuelve a revisar el archivo.')
   old=json.loads(payload);new=copy.deepcopy(old);state=new['state'];fields=original_fields(old['master']);by_code={};by_name=collections.defaultdict(list)
   for r in state['registros']:
    if not r['eliminado'] and not r.get('camposExcel') and r.get('fila') in fields:r['camposExcel']=fields[r['fila']]
    r['fila']=None
    for key in (r['sku'],r.get('anterior','')):
     if key:by_code.setdefault(norm(key),[]).append(r)
    by_name[(norm(r['nombre']),norm(r.get('proveedor','')))].append(r)
   summary={'hoja':'PRODUCTOS','total':len(incoming),'agregados':0,'actualizados':0,'sinCambios':0,'skuActualizados':0,'omitidos':0,'conflictos':[]};changes=[];seen=set();before_changes={};source_rows={}
   for item in incoming:
    candidates=by_code.get(norm(item['skuFuente']),[]) if item['skuFuente'] else []
    if not candidates and item['anteriorFuente'] and legacy_counts[norm(item['anteriorFuente'])]==1:candidates=by_code.get(norm(item['anteriorFuente']),[])
    if not candidates:candidates=by_name.get((norm(item['nombre']),norm(item['proveedor'])),[])
    candidates=list({r['id']:r for r in candidates}.values())
    if candidates and not item['skuFuente']:
     keys=('claveProveedor','unidadCompra','unidadEntrega');exact=[r for r in candidates if all(norm(item[key])==norm(r.get(key,'')) for key in keys)]
     candidates=exact if exact else [r for r in candidates if all(not item[key] or key not in r or norm(item[key])==norm(r[key]) for key in keys)]
    if len(candidates)>1:
     filtered=[r for r in candidates if all(not code or r[key]==code for key,code in item['clasificacion'].items())]
     if len(filtered)==1:candidates=filtered
    if len(candidates)>1:
     summary['omitidos']+=1;summary['conflictos'].append({'fila':item['filaFuente'],'descripcion':item['nombre'],'motivo':'Coinciden varios productos; completa clasificación o SKU para identificarlo.'});continue
    r=candidates[0] if candidates else None
    if r and r['id'] in seen and not item['skuFuente'] and any(code and code!=r[key] for key,code in item['clasificacion'].items()):r=None
    if r and (r['id'] in seen or r['eliminado']):
     summary['omitidos']+=1;summary['conflictos'].append({'fila':item['filaFuente'],'descripcion':item['nombre'],'motivo':'Fila repetida o producto dado de baja; no se reactiva.'});continue
    before=copy.deepcopy(r) if r else None
    if r is None:
     if state['maxId']>=9999999:raise ValueError('Se agotaron los identificadores.')
     state['maxId']+=1;r={'id':state['maxId'],'eliminado':False,'fila':None,'anterior':item['skuFuente'] or item['anteriorFuente'],'tipo':'00','categoria':'00','subcategoria':'00'};state['registros'].append(r);summary['agregados']+=1
    seen.add(r['id'])
    before_changes[r['id']]=before;source_rows[r['id']]=item
    for key,code in item['clasificacion'].items():
     if code:r[key]=code
    r.update({'nombre':item['nombre'],'proveedor':item['proveedor'],'estado':item['estado'] or r.get('estado','ACTIVO'),'camposExcel':item['camposExcel'],'editado':True,**{key:item[key] for key in ('claveProveedor','unidadCompra','unidadEntrega')}})
    new_sku=self.make_sku(r)
    if before and before['sku']!=new_sku:
     state['reservados'].append(before['sku']);summary['skuActualizados']+=1;changes.append({'id':r['id'],'descripcion':r['nombre'],'anterior':before['sku'],'nuevo':new_sku})
    r['sku']=new_sku
    if before:
     relevant=('nombre','proveedor','estado','tipo','categoria','subcategoria','sku','camposExcel','claveProveedor','unidadCompra','unidadEntrega')
     if any(before.get(k)!=r.get(k) for k in relevant):summary['actualizados']+=1
     else:summary['sinCambios']+=1
    for key in (new_sku,r.get('anterior','')):
     if key:by_code[norm(key)]=[r]
    if before:
     old_key=(norm(before['nombre']),norm(before.get('proveedor','')));by_name[old_key]=[x for x in by_name[old_key] if x['id']!=r['id']]
    new_key=(norm(r['nombre']),norm(r['proveedor']));by_name[new_key]=[x for x in by_name[new_key] if x['id']!=r['id']]+[r]
   def fingerprint(r):return tuple(norm(r.get(k,'')) for k in ('tipo','categoria','subcategoria','nombre','proveedor','claveProveedor','unidadCompra','unidadEntrega'))
   groups=collections.defaultdict(list)
   for r in state['registros']:
    if not r['eliminado']:groups[fingerprint(r)].append(r)
   rejected=set()
   for group in groups.values():
    if len(group)<2:continue
    for r in group:
     if r['id'] not in before_changes:continue
     before=before_changes[r['id']]
     if before is not None and fingerprint(before)==fingerprint(r):continue
     rejected.add(r['id']);summary['omitidos']+=1;item=source_rows[r['id']];summary['conflictos'].append({'fila':item['filaFuente'],'descripcion':item['nombre'],'motivo':'El cambio coincide con otro producto del catálogo; se conserva el registro anterior.'})
     if before is None:summary['agregados']-=1
     else:
      summary['actualizados']-=1;r.clear();r.update(before)
   if rejected:
    state['registros']=[r for r in state['registros'] if r['id'] not in rejected or before_changes[r['id']] is not None];changes=[change for change in changes if change['id'] not in rejected];summary['skuActualizados']=len(changes)
    state['reservados']=old['state']['reservados']+[change['anterior'] for change in changes]
   state['reservados']=sorted(set(state['reservados']));new.update({'master':base64.b64encode(raw).decode(),'formatoMaestro':'PRODUCTOS','archivoMaestro':filename,'importadoEn':now()})
   self.protect(old,new);self.validate(new,self.store.catalogs);summary['cambiosSKU']=changes;summary['segundos']=round(time.perf_counter()-started,3)
   if data.get('revisar'):return {'resumen':summary,'revision':revision}
   db.execute('INSERT INTO history VALUES(?,?,?)',(revision,now(),payload));db.execute('UPDATE catalog SET revision=?,payload=?',(revision+1,json.dumps(new,ensure_ascii=False)));db.execute('DELETE FROM history WHERE revision < ?',(revision-99,))
  return {'resumen':summary,'revision':revision+1}

def export_products(data,catalogs):
 # Exporta el catálogo vigente en PRODUCTOS y el SKU generado en D.
 from xml.sax.saxutils import escape
 raw=base64.b64decode(data['master']);output=io.BytesIO();ns=NS['m']
 with zipfile.ZipFile(io.BytesIO(raw)) as source:
  wb=ET.fromstring(source.read('xl/workbook.xml'));rels=ET.fromstring(source.read('xl/_rels/workbook.xml.rels'));targets={r.get('Id'):r.get('Target') for r in rels};sheet=next((s for s in wb.findall('m:sheets/m:sheet',NS) if s.get('name')=='PRODUCTOS'),None)
  if sheet is None:raise ValueError('Actualiza primero el maestro con una pestaña PRODUCTOS.')
  target=targets[sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')];path=target.lstrip('/') if target.startswith('/') else 'xl/'+target.lstrip('./');xml=source.read(path).decode('utf8')
  rows,_=read_rows(raw,'maestro.xlsx');header=next(row for _,row in rows[:25] if norm(row.get('H'))=='DESCRIPCION');header={**header,'D':'SKU NUEVO'}
  def row_xml(number,values):
   def cell(col,value):
    address=col+str(number);v=str(value or '');numeric=col in {'I','J','K','L','R','S','T','X','Y'} and re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?',v)
    return '<c r="'+address+'">'+'<v>'+v+'</v></c>' if numeric else '<c r="'+address+'" t="inlineStr"><is><t xml:space="preserve">'+escape(v)+'</t></is></c>'
   def order(c):return sum((ord(x)-64)*26**i for i,x in enumerate(reversed(c)))
   return '<row r="'+str(number)+'">'+''.join(cell(col,values[col]) for col in sorted(values,key=order) if re.fullmatch('[A-Z]+',col))+'</row>'
  body=row_xml(1,header)
  for index,r in enumerate(data['state']['registros'],2):
   values={**r.get('camposExcel',{}),'D':'' if r['eliminado'] else r['sku'],'C':'INACTIVO' if r['eliminado'] else r['estado'],'E':catalogs['TIP'][r['tipo']],'F':catalogs['CAT'][r['categoria']],'G':catalogs['SUB'][r['subcategoria']],'H':r['nombre'],'O':r.get('proveedor','')};body+=row_xml(index,values)
  xml=re.sub(r'<sheetData\b[^>]*>[\s\S]*?</sheetData>','<sheetData>'+body+'</sheetData>',xml);last=len(data['state']['registros'])+1;xml=re.sub(r'<dimension\b[^>]*/>','<dimension ref="A1:AD'+str(last)+'"/>',xml);xml=re.sub(r'<autoFilter\b[^>]*/>','<autoFilter ref="A1:AD'+str(last)+'"/>',xml)
  with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as dest:
   for info in source.infolist():dest.writestr(info,xml.encode() if info.filename==path else source.read(info.filename))
 return output.getvalue()
