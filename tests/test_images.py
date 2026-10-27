"""PNG reales, vinculación por SKU, permisos y respaldo/restauración de imágenes."""
import base64,copy,io,json,unittest,urllib.request
from PIL import Image
import test_backup_import as fixture
from imagenes import validate_image as validate_png
from respaldos import digest

def png(width=225,height=165,color='navy',format='PNG'):
 out=io.BytesIO();Image.new('RGB',(width,height),color).save(out,format=format);return out.getvalue()

class MaterialImageTests(unittest.TestCase):
 def setUp(self):
  self.case=fixture.ModuleBackupTests();self.case.setUp();self.case.import_req([fixture.product('UNO',B='SKU00000000001'),fixture.product('DOS',B='SKU00000000002')]);self.materials=self.case.value('/api/requisiciones/materiales')['materiales'];self.first=self.materials[0];self.second=self.materials[1]
 def tearDown(self):self.case.tearDown()
 def upload(self,files,**options):return self.case.value('/api/requisiciones/imagenes',{'archivos':files,**options})
 def image(self,file='foto.png',raw=None,id=None):return {'archivo':file,'contenido':base64.b64encode(png() if raw is None else raw).decode(),**({'materialId':id} if id is not None else {})}
 def test_valid_images_without_format_size_or_dimension_limits(self):
  self.assertEqual(validate_png(png(1,1)),(1,1))
  self.assertEqual(validate_png(png(10,12,format='JPEG'),'foto.jpg'),(10,12))
  self.assertEqual(validate_png(png()+b'0'*(3*1024*1024),'foto.cualquier'),(225,165))
  for raw in (b'not-an-image',png()[:40]):
   with self.assertRaises(ValueError):validate_png(raw)
  result=self.upload([self.image('foto.jpg',png(2,3,format='JPEG'),self.first['id'])]);self.assertEqual(result['guardadas'],1)
  self.assertEqual(self.case.call('/api/requisiciones/imagenes/'+str(self.first['id']))[2]['Content-Type'],'image/jpeg')
 def test_batch_matching_replace_and_direct_choice(self):
  result=self.upload([self.image(self.first['sku'].lower()+'.png'),self.image('NO-EXISTE.png'),self.image(self.second['sku']+'.png',b'not-an-image')]);self.assertEqual((result['guardadas'],result['rechazadas']),(1,2))
  self.assertEqual(self.upload([self.image(self.first['sku']+'.png')])['rechazadas'],1)
  red=png(color='red');self.assertEqual(self.upload([self.image('cualquier-nombre.png',red,self.first['id'])],reemplazar=True)['guardadas'],1)
  status,body,headers=self.case.call('/api/requisiciones/imagenes/'+str(self.first['id']));self.assertEqual((status,body,headers['Content-Type']),(200,red,'image/png'))
  meta=self.case.value('/api/requisiciones/imagenes')['imagenes'][0];self.assertNotIn('contenido',meta);self.assertEqual(meta['ancho'],225)
  self.assertEqual(self.upload([self.image('foto.png',id=self.first['id']),self.image('foto2.png',id=self.first['id'])],reemplazar=True)['rechazadas'],1)
  self.assertEqual(self.case.call('/api/requisiciones/imagenes/'+str(self.second['id']))[0],404)
 def test_search_thumbnail_preserves_original_and_refreshes(self):
  raw=png(1200,900);self.upload([self.image('grande.png',raw,self.first['id'])]);path='/api/requisiciones/imagenes/'+str(self.first['id'])
  small=self.case.call(path+'?miniatura=1')[1]
  with Image.open(io.BytesIO(small)) as image:self.assertEqual(image.size,(440,330))
  self.assertEqual(self.case.call(path)[1],raw)
  self.upload([self.image('nueva.png',png(color='red'),self.first['id'])],reemplazar=True)
  with Image.open(io.BytesIO(self.case.call(path+'?miniatura=1')[1])) as image:self.assertEqual(image.getpixel((0,0))[:3],(255,0,0))

 def test_access_control_and_csrf(self):
  self.upload([self.image(id=self.first['id'])])
  for role in ('visualizador','gerente','almacenista','compras','alta','auxti'):
   email=role+'@example.com';self.case.value('/api/users',{'email':email,'name':role,'role':role,'active':True,'password':self.case.password,'almacenes':['EJIDOS'],'sucursales':['EJIDOS','SAN PABLO','CUAUTITLAN','EJE 8']});actor=self.case.login(email)
   self.assertEqual(self.case.call('/api/requisiciones/imagenes',actor=actor)[0],200)
   expected=200 if role=='auxti' else 403
   self.assertEqual(self.case.call('/api/requisiciones/imagenes',{'archivos':[self.image(id=self.first['id'])],'reemplazar':True},actor)[0],expected)
   self.assertEqual(self.case.call('/api/requisiciones/imagenes/'+str(self.first['id']),actor=actor,method='DELETE')[0],expected)
   if expected==200:self.upload([self.image(id=self.first['id'])],reemplazar=True)
  with urllib.request.urlopen(urllib.request.Request(self.case.url+'/api/requisiciones/imagenes/'+str(self.first['id']),headers={'Cookie':self.case.admin['cookie']})) as response:self.assertEqual(response.headers['Cache-Control'],'no-store')
  forged={**self.case.admin,'csrf':'invalid'};self.assertEqual(self.case.call('/api/requisiciones/imagenes',{'archivos':[self.image(id=self.first['id'])]},forged)[0],403)
  profile=next(p for p in self.case.value('/api/perfiles')['perfiles'] if p['perfil']=='compras');self.case.value('/api/perfiles',{'perfil':'compras','modulos':['compras'],'revision':profile['revision']},method='PUT')
  actor=self.case.login('compras@example.com');self.assertEqual(self.case.call('/api/requisiciones/imagenes',actor=actor)[0],403)
 def test_backup_reset_restore_and_old_backup(self):
  self.upload([self.image(id=self.first['id'])]);backup=self.case.value('/api/respaldos?modulo=requisiciones');self.assertEqual(len(backup['datos']['tablas']['req_images']['filas']),1)
  current=self.case.value('/api/respaldos/vaciar/revisar',{'modulo':'requisiciones'});self.case.value('/api/respaldos/vaciar/confirmar',{'modulo':'requisiciones','huellaActual':current['huellaActual'],'texto':'VACIAR','confirmar':True});self.assertEqual(self.case.value('/api/requisiciones/imagenes')['imagenes'],[])
  review=self.case.review('requisiciones',backup);self.case.restore('requisiciones',backup,review);self.assertEqual(self.case.call('/api/requisiciones/imagenes/'+str(self.first['id']))[1],png())
  damaged=copy.deepcopy(backup);damaged['datos']['tablas']['req_images']['filas'][0][3]=base64.b64encode(b'not-png').decode();damaged['checksum']=digest({k:v for k,v in damaged.items() if k!='checksum'})
  self.assertEqual(self.case.call('/api/respaldos/restaurar/revisar',{'modulo':'requisiciones','respaldo':damaged})[0],400)
  old=copy.deepcopy(backup);del old['datos']['tablas']['req_images'];old['checksum']=digest({k:v for k,v in old.items() if k!='checksum'});review=self.case.review('requisiciones',old);self.case.restore('requisiciones',old,review);self.assertEqual(self.case.value('/api/requisiciones/imagenes')['imagenes'],[])

if __name__=='__main__':unittest.main()
