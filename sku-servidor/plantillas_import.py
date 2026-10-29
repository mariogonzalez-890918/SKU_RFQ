"""Layouts de plantillas por cliente y proveedor con revisión y aplicación atómica."""
import json,uuid
from comercial import ADMINS,SUPERVISORS,dumps,fingerprint,now
from clientes_comerciales import read_table
from productos_comerciales import optional_price
from pedidos_compra import SERIES_EDITORS,number,rate
from requisiciones import Conflict,text

CLIENT_HEADERS=['CODIGO_CLIENTE','NOMBRE_PLANTILLA','SKU','CANTIDAD','OBSERVACIONES_PARTIDA','CONDICIONES']
VENDOR_HEADERS=['CODIGO_PROVEEDOR','NOMBRE_PLANTILLA','SKU','ID_MATERIAL','CANTIDAD','TIPO_UNIDAD','PRECIO_ANTES_IMPUESTO','IMPUESTO','OBSERVACIONES_PARTIDA','OBSERVACIONES','CONDICIONES']

def read(data,sheet,headers):
 rows=read_table(data,sheet)
 if [str(v).strip().upper() for v in rows[0]]!=headers:raise ValueError('Conserva los encabezados del layout '+sheet+'.')
 result=[]
 for n,row in enumerate(rows[1:],2):
  if not any(str(v).strip() for v in row):continue
  if len(row)>len(headers) and any(row[len(headers):]):raise ValueError(f'Fila {n}: sobran columnas.')
  result.append((n,{k:str(row[i]).strip() if i<len(row) else '' for i,k in enumerate(headers)}))
 if not result:raise ValueError('No hay partidas de plantillas para cargar.')
 return result

def same_value(group,key,value,n):
 if value and group.get(key) and group[key]!=value:raise ValueError(f'Fila {n}: las condiciones u observaciones de la misma plantilla no coinciden.')
 if value:group[key]=value

def customer_import(cm,data,actor):
 company=data.get('empresa');cm.module(actor,'ventasins')
 if actor['role'] not in ADMINS|{'gerente'}:raise PermissionError('Solo Gerencia, AUXTI y Superadministrador cargan plantillas.')
 cm.company(company,actor,True);rows=read(data,'PLANTILLAS_CLIENTES',CLIENT_HEADERS)
 with cm.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');clients={c:{'id':i,**json.loads(p)} for i,c,p in db.execute('SELECT id,code,payload FROM cm_customers WHERE company=?',(company,))};products={s:json.loads(p) for s,p in db.execute('SELECT sku,payload FROM cm_products')};existing=[{'id':i,'creador':c,'revision':r,**json.loads(p)} for i,c,r,p in db.execute('SELECT id,creator,revision,payload FROM cm_templates WHERE company=?',(company,)) if actor['role'] in SUPERVISORS or c==actor['email']];stamp=fingerprint([clients,products,existing]);groups={};seen=set()
  if not data.get('revisar') and data.get('huellaActual')!=stamp:raise Conflict('Cambiaron clientes, productos o plantillas. Revisa de nuevo.')
  for n,r in rows:
   name=text(r['NOMBRE_PLANTILLA'],160);code=r['CODIGO_CLIENTE'].upper();client=clients.get(code) if code else None;sku=r['SKU'].upper();product=products.get(sku)
   if not name or code and (not client or not client.get('activo') or 'ventasins' not in client.get('canales',['ventasins','expendios'])):raise ValueError(f'Fila {n}: nombre o código de cliente inválido.')
   if not product or not product.get('activo') or not product.get('institucional',True):raise ValueError(f'Fila {n}: SKU no disponible para institucionales.')
   key=(client['id'] if client else '',name.upper());identity=(*key,sku)
   if identity in seen:raise ValueError(f'Fila {n}: SKU repetido en la misma plantilla.')
   seen.add(identity);g=groups.setdefault(key,{'nombre':name,'cliente':key[0],'partidas':[],'condiciones':''});g['partidas'].append({'sku':sku,'cantidad':format(number(r['CANTIDAD'],True),'f'),'observaciones':text(r['OBSERVACIONES_PARTIDA'],500)});same_value(g,'condiciones',text(r['CONDICIONES'],1000),n)
  created=updated=omitted=0
  for key,g in groups.items():
   if len(g['partidas'])>200:raise ValueError('Máximo 200 partidas por plantilla.')
   matches=[t for t in existing if t['cliente']==key[0] and t['nombre'].upper()==key[1]]
   if len(matches)>1:raise ValueError('Hay plantillas con el mismo cliente y nombre; usa un nombre único.')
   old=matches[0] if matches else None
   if old and not data.get('actualizar'):omitted+=1;continue
   if old:updated+=1
   else:created+=1
   if not data.get('revisar'):
    if old:db.execute('UPDATE cm_templates SET revision=revision+1,payload=? WHERE id=?',(dumps(g),old['id']))
    else:db.execute('INSERT INTO cm_templates VALUES(?,?,?,1,?)',(uuid.uuid4().hex,company,actor['email'],dumps(g)))
  if not data.get('revisar'):cm.audit(db,actor,company,'plantillas_clientes_importadas',{'nuevas':created,'actualizadas':updated})
  else:db.rollback()
 return {'ok':True,'nuevas':created,'actualizadas':updated,'omitidas':omitted,'huellaActual':stamp}

def vendor_import(po,data,actor):
 company=data.get('empresa');po.scope(actor,company)
 if actor['role'] not in ADMINS|{'gerente'}:raise PermissionError('Tu perfil no puede cargar plantillas de proveedor.')
 rows=read(data,'PLANTILLAS_PROVEEDORES',VENDOR_HEADERS);materials={m['materialId']:m for m in po.materials(actor)['materiales']}
 with po.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');vendors={c:{'id':i,**json.loads(p)} for i,c,p in db.execute('SELECT id,code,payload FROM po_vendors WHERE company=?',(company,))};existing=[{'id':i,'revision':r,**json.loads(p)} for i,r,p in db.execute('SELECT id,revision,payload FROM po_templates WHERE company=?',(company,))];stamp=fingerprint([vendors,materials,existing]);groups={};seen=set()
  if not data.get('revisar') and data.get('huellaActual')!=stamp:raise Conflict('Cambiaron proveedores, materiales o plantillas. Revisa de nuevo.')
  for n,r in rows:
   name=text(r['NOMBRE_PLANTILLA'],160);vendor=vendors.get(r['CODIGO_PROVEEDOR'].upper());sku=r['SKU'].upper();id=r['ID_MATERIAL']
   if id:
    if not id.isdigit():raise ValueError(f'Fila {n}: ID_MATERIAL inválido.')
    matches=[materials[int(id)]] if int(id) in materials else []
    if matches and sku and matches[0]['sku']!=sku:raise ValueError(f'Fila {n}: ID y SKU no coinciden.')
   else:matches=[m for m in materials.values() if sku and m['sku']==sku]
   if not name or not vendor or not vendor.get('activo') or len(matches)!=1:raise ValueError(f'Fila {n}: proveedor, nombre o material inválido. Si el SKU es ambiguo utiliza ID_MATERIAL.')
   material=matches[0];unit=r['TIPO_UNIDAD'].upper() or 'COMPRA'
   if unit not in ('COMPRA','ENTREGA') or not material['activo']:raise ValueError(f'Fila {n}: unidad o material inactivo.')
   key=(vendor['id'],name.upper());identity=(*key,material['materialId'])
   if identity in seen:raise ValueError(f'Fila {n}: material repetido en la misma plantilla.')
   seen.add(identity);g=groups.setdefault(key,{'nombre':name,'proveedor':vendor['id'],'partidas':[],'observaciones':'','condiciones':''});g['partidas'].append({'materialId':material['materialId'],'tipoUnidad':unit,'cantidad':format(number(r['CANTIDAD'],True),'f'),'precio':optional_price(r['PRECIO_ANTES_IMPUESTO']),'impuesto':rate(r['IMPUESTO']),'observaciones':text(r['OBSERVACIONES_PARTIDA'],3000)});same_value(g,'observaciones',text(r['OBSERVACIONES'],100000),n);same_value(g,'condiciones',text(r['CONDICIONES'],20000),n)
  created=updated=omitted=0
  for key,g in groups.items():
   matches=[t for t in existing if t['proveedor']==key[0] and t['nombre'].upper()==key[1]]
   if len(matches)>1:raise ValueError('Nombre de plantilla de proveedor ambiguo.')
   old=matches[0] if matches else None
   if old and not data.get('actualizar'):omitted+=1;continue
   if old:g.update({'id':old['id'],'revision':old['revision']});updated+=1
   else:created+=1
   po.save_template({'empresa':company,**g},actor,db)
  if data.get('revisar'):db.rollback()
 return {'ok':True,'nuevas':created,'actualizadas':updated,'omitidas':omitted,'huellaActual':stamp}
