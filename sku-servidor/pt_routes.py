"""API PT independiente del inventario de materias primas y sin precios."""
from pt import PTStore,BRANCHES,MANAGERS,MIME,qr_value
from pt_onedrive import OneDrivePT
from requisiciones import now,Conflict
import json

class PTAPI:
 def __init__(self,store):self.pt=PTStore(store);self.cloud=OneDrivePT(self.pt);self.cloud.kick()
 def get(self,path,query,actor):
  pt=self.pt;pt.scope(actor);action=path.removeprefix('/api/pt/');q={k:v[0] for k,v in query.items()}
  if action=='meta':return {'sucursales':pt.scope(actor),'mes':now()[:7],'administra':actor['role'] in MANAGERS,'configura':actor['role']=='superadmin','etiquetas':actor['role'] in MANAGERS or actor['role']=='ventas'}
  if action=='productos':
   search=q.get('buscar','').upper();return {'productos':[p for p in pt.catalog().values() if search in p['sku'] or search in p['descripcion'].upper()][:2000]}
  if action=='producto':return pt.product(q.get('sku',''),actor)
  if action=='ingresos':return pt.entries(actor,q)
  if action=='excel':return pt.workbook(actor,q),MIME
  if action=='etiquetas/pdf':return pt.labels(actor,q),'application/pdf'
  if action=='codigo/svg':
   from reportlab.graphics.barcode import createBarcodeDrawing
   from reportlab.graphics import renderSVG
   p=pt.product(q.get('sku',''),actor);drawing=createBarcodeDrawing('QR' if q.get('tipo')=='qr' else 'Code128',value=qr_value(p['sku'],q.get('servidor','')) if q.get('tipo')=='qr' else p['sku'],**({'width':200,'height':200,'barBorder':4} if q.get('tipo')=='qr' else {'barWidth':2,'barHeight':72,'quiet':True,'humanReadable':True}))
   return renderSVG.drawToString(drawing).encode(),'image/svg+xml'
  if action=='clave':
   with pt.store.connect() as db:row=db.execute('SELECT payload FROM pt_entries WHERE creator=? AND client_key=?',(actor['email'],q.get('clave',''))).fetchone()
   entry=json.loads(row[0]) if row else None
   if entry:pt.scope(actor,entry['sucursal'])
   return {'ingreso':entry}
  if action=='onedrive':return self.cloud.status(actor)
  raise ValueError('Opción PT no encontrada.')
 def mutate(self,path,data,actor):
  self.pt.scope(actor);action=path.removeprefix('/api/pt/')
  if action=='ingresos':return self.pt.create(data,actor)
  if action=='cancelar':return self.pt.cancel(data,actor)
  if action=='onedrive/configurar':return self.cloud.configure(data,actor)
  if action=='onedrive/probar-carpeta':return self.cloud.test_folder(actor)
  if action=='onedrive/conectar':return self.cloud.start_auth(actor)
  if action=='onedrive/verificar':return self.cloud.poll_auth(actor)
  if action=='onedrive/desconectar':return self.cloud.disconnect(actor)
  if action=='onedrive/publicar':return self.cloud.retry(actor)
  raise ValueError('Acción PT no encontrada.')
