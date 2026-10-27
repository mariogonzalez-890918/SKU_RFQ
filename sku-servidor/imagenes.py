"""Imágenes PNG por material; los respaldos las conservan junto a requisiciones."""
import base64,collections,functools,io,json,pathlib,uuid,warnings
from PIL import Image,UnidentifiedImageError
from requisiciones import now,text,MANAGERS
LIMIT=2*1024*1024

def validate_png(raw,filename='imagen.png'):
 if not isinstance(filename,str) or not filename.lower().endswith('.png'):raise ValueError('Solo se permiten archivos PNG.')
 if not raw or len(raw)>LIMIT:raise ValueError('Máximo 2 MB por imagen.')
 try:
  with warnings.catch_warnings():
   warnings.simplefilter('error',Image.DecompressionBombWarning)
   with Image.open(io.BytesIO(raw)) as image:
    if image.format!='PNG' or getattr(image,'n_frames',1)!=1:raise ValueError('Debe ser un PNG estático válido.')
    width,height=image.size
    if width<225 or height<165:raise ValueError('Dimensiones mínimas: 225 × 165 píxeles.')
    if width*height>25000000:raise ValueError('La imagen supera 25 megapíxeles.')
    image.verify()
   with Image.open(io.BytesIO(raw)) as image:image.load()
  return width,height
 except (Image.DecompressionBombError,Image.DecompressionBombWarning):raise ValueError('La imagen tiene demasiados píxeles.')
 except (OSError,SyntaxError,UnidentifiedImageError):raise ValueError('El archivo no es un PNG válido.')

class ImageStore:
 def __init__(self,store,requisitions):
  self.store=store;self.requisitions=requisitions
  with store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS req_images(material_id INTEGER PRIMARY KEY,image_id TEXT NOT NULL UNIQUE,payload TEXT NOT NULL,contenido TEXT NOT NULL)')
 def list(self,actor):
  with self.store.connect() as db:rows=db.execute('SELECT material_id,image_id,payload FROM req_images').fetchall()
  return {'puedeEditar':actor['role'] in MANAGERS,'imagenes':[{'materialId':id,'imagenId':key,**{k:v for k,v in json.loads(payload).items() if k!='contenido'}} for id,key,payload in rows]}
 def get(self,id,thumbnail=False):
  with self.store.connect() as db:
   row=db.execute('SELECT image_id FROM req_images WHERE material_id=?',(id,)).fetchone()
   if not row:return None
   if thumbnail:return self._thumbnail(id,row[0])
   content=db.execute('SELECT contenido FROM req_images WHERE material_id=?',(id,)).fetchone()
   return base64.b64decode(content[0]) if content else None
 @functools.lru_cache(maxsize=256)
 def _thumbnail(self,id,key):
  with self.store.connect() as db:row=db.execute('SELECT contenido FROM req_images WHERE material_id=? AND image_id=?',(id,key)).fetchone()
  if not row:return None
  with Image.open(io.BytesIO(base64.b64decode(row[0]))) as image:
   image.thumbnail((450,330),Image.Resampling.LANCZOS);out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()
 def upload(self,data,actor):
  if actor['role'] not in MANAGERS:raise PermissionError('Solo Superadministrador, Compras y Alta de productos pueden cargar imágenes.')
  files=data.get('archivos')
  if not isinstance(files,list) or not 1<=len(files)<=5:raise ValueError('Carga entre una y cinco imágenes por lote.')
  replace=data.get('reemplazar',False)
  if type(replace) is not bool:raise ValueError('Opción de reemplazo inválida.')
  results=[];seen=set()
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE')
   materials=[{'id':id,**json.loads(payload)} for id,payload in db.execute('SELECT id,payload FROM req_materials')];by_id={r['id']:r for r in materials};by_sku=collections.defaultdict(list)
   for r in materials:
    if r['sku']:by_sku[r['sku'].upper()].append(r)
   for file in files:
    filename=''
    try:
     if not isinstance(file,dict):raise ValueError('Archivo inválido.')
     filename=text(file.get('archivo',''),240);id=file.get('materialId')
     if id is not None:
      if type(id) is not int or id not in by_id:raise ValueError('Material no disponible.')
      material=by_id[id]
     else:
      candidates=by_sku.get(pathlib.PureWindowsPath(filename).stem.upper(),[])
      if len(candidates)!=1:raise ValueError('El nombre debe ser un SKU único existente. Si se repite, usa la carga individual.')
      material=candidates[0];id=material['id']
     if not material['sku']:raise ValueError('Asigna primero un SKU a este producto.')
     if id in seen:raise ValueError('El material está repetido en este lote.')
     if not replace and db.execute('SELECT 1 FROM req_images WHERE material_id=?',(id,)).fetchone():raise ValueError('Ya tiene imagen. Activa reemplazar para cambiarla.')
     encoded=file.get('contenido','')
     if not isinstance(encoded,str) or len(encoded)>4*((LIMIT+2)//3):raise ValueError('Máximo 2 MB por imagen.')
     try:raw=base64.b64decode(encoded,validate=True)
     except ValueError:raise ValueError('Contenido de imagen inválido.')
     width,height=validate_png(raw,filename);key=uuid.uuid4().hex
     value={'skuAlCargar':material['sku'],'archivo':filename,'ancho':width,'alto':height,'bytes':len(raw),'actualizado':now(),'cargadoPor':actor['email']}
     db.execute('INSERT INTO req_images VALUES(?,?,?,?) ON CONFLICT(material_id) DO UPDATE SET image_id=excluded.image_id,payload=excluded.payload,contenido=excluded.contenido',(id,key,json.dumps(value,ensure_ascii=False),base64.b64encode(raw).decode()));seen.add(id);results.append({'archivo':filename,'ok':True,'materialId':id,'sku':material['sku']})
    except (ValueError,TypeError,KeyError) as error:results.append({'archivo':filename,'ok':False,'error':str(error)})
  return {'resultados':results,'guardadas':sum(r['ok'] for r in results),'rechazadas':sum(not r['ok'] for r in results)}
 def remove(self,id,actor):
  if actor['role'] not in MANAGERS:raise PermissionError('Tu perfil no puede quitar imágenes.')
  with self.store.connect() as db:db.execute('DELETE FROM req_images WHERE material_id=?',(id,))
  return {'ok':True}
