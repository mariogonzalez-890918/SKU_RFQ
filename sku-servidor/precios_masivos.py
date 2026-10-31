"""Carga transaccional de precios por cliente; importes finales con impuesto incluido."""
import json
from decimal import Decimal,ROUND_HALF_UP
from comercial import dumps,now,fingerprint,tax_name
from clientes_comerciales import read_table
from productos_comerciales import optional_price
from requisiciones import Conflict
from ventas import norm

HEADERS=['CODIGO_CLIENTE','SKU','PRECIO_CON_IMPUESTO','PRECIO_ANTES_IMPUESTO']
def import_prices(cm,data,actor):
 cm.admin(actor);company=data.get('empresa');cm.company(company,actor,True);rows=read_table(data,'PRECIOS');header=[norm(v).replace(' ','_') for v in rows[0]]
 if header!=HEADERS:raise ValueError('Usa los encabezados del layout PRECIOS sin modificarlos.')
 with cm.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');state=[list(r) for r in db.execute("SELECT sku,customer,revision,payload FROM cm_prices WHERE company=? ORDER BY sku,customer",(company,))]+[list(r) for r in db.execute('SELECT sku,revision FROM cm_products ORDER BY sku')]+[list(r) for r in db.execute('SELECT id,revision FROM cm_customers WHERE company=? ORDER BY id',(company,))];stamp=fingerprint(state)
  if not data.get('revisar') and data.get('huellaActual')!=stamp:raise Conflict('Cambió el catálogo, cliente o precio. Revisa la carga nuevamente.')
  prepared=[];seen=set()
  for n,row in enumerate(rows[1:],2):
   if not any(str(v).strip() for v in row):continue
   if len(row)>4 and any(row[4:]):raise ValueError(f'Fila {n}: sobran columnas.')
   row=(row+['']*4)[:4];code,sku=norm(row[0]),norm(row[1]);key=(code,sku)
   if key in seen:raise ValueError(f'Fila {n}: cliente/SKU repetido.')
   seen.add(key);client=db.execute('SELECT id,payload FROM cm_customers WHERE company=? AND code=?',(company,code)).fetchone();product=db.execute('SELECT payload FROM cm_products WHERE sku=?',(sku,)).fetchone()
   if not client or not product:raise ValueError(f'Fila {n}: código de cliente o SKU inexistente.')
   cm.customer(db,client[0],company,actor);product=json.loads(product[0])
   if not product.get('institucional',True) or not product.get('activo'):raise ValueError(f'Fila {n}: producto no disponible para institucionales.')
   if product.get('iva') is None:raise ValueError(f'Fila {n}: completa el impuesto del SKU en el maestro.')
   final=optional_price(row[2]);base=optional_price(row[3]);factor=Decimal(1)+Decimal(product['iva'])/100
   if final is None and base is None:raise ValueError(f'Fila {n}: indica al menos un precio.')
   if final is not None and base is not None and abs(Decimal(final)-Decimal(base)*factor)>Decimal('0.01'):raise ValueError(f'Fila {n}: los precios antes y después de impuesto no coinciden con el maestro.')
   final=final if final is not None else optional_price(Decimal(base)*factor);base=format((Decimal(final)/factor).quantize(Decimal('.000001'),rounding=ROUND_HALF_UP),'f')
   previous=db.execute("SELECT revision FROM cm_prices WHERE company=? AND list='PUBLICO' AND sku=? AND customer=?",(company,sku,client[0])).fetchone();prepared.append({'cliente':client[0],'codigoCliente':code,'sku':sku,'precio':final,'precioAntesImpuesto':base,'tipoImpuesto':tax_name(product['iva']),'tasa':product['iva'],'revision':previous[0] if previous else 0})
  if not prepared:raise ValueError('No hay precios para cargar.')
  if not data.get('revisar'):
   for r in prepared:db.execute("INSERT INTO cm_prices VALUES(?,'PUBLICO',?,?,?,?) ON CONFLICT(company,list,sku,customer) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",(company,r['sku'],r['cliente'],r['revision']+1,dumps({'precio':r['precio'],'origen':'CLIENTE','fecha':now()})))
   cm.audit(db,actor,company,'precios_clientes_masivos',{'precios':len(prepared)})
  else:db.rollback()
 return {'ok':True,'precios':len(prepared),'huellaActual':stamp,'detalle':prepared}
