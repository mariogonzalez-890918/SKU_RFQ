"""Entrega local/SMB de Excel PT; OneDrive de la PC puente realiza la sincronización."""
import hashlib,io,os,pathlib,tempfile,zipfile
from pt_registro import merge_workbook

def validate_root(value):
 if not isinstance(value,str) or not value or len(value)>500 or any(ord(c)<32 for c in value):raise ValueError('Indica una carpeta absoluta del servidor o una ruta compartida de Windows.')
 p=pathlib.Path(value)
 if not p.is_absolute() or '..' in p.parts or (str(p)==p.anchor and not p.anchor.startswith('\\\\')) or ':' in value[2:]:raise ValueError('Usa una carpeta completa, por ejemplo C:\\OneDrive\\GMP_PT o \\\\PC-PUENTE\\GMP_PT. No uses una liga web.')
 return str(p)

def workbook_hash(raw):
 if len(raw)>100*1024*1024:raise ValueError('El archivo supera el límite de publicación de 100 MB.')
 try:
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   if sum(i.file_size for i in archive.infolist())>256*1024*1024:raise ValueError('El archivo existente es demasiado grande para validarlo.')
   digest=hashlib.sha256()
   for name in sorted(archive.namelist()):digest.update(name.encode()+b'\0'+archive.read(name))
   return digest.hexdigest()
 except zipfile.BadZipFile:raise ValueError('El archivo de destino no es un Excel válido. No se sobrescribió.')

def publish_folder(config,branch,month,raw,old,entries=None,backup=None):
 root=pathlib.Path(validate_root(config.get('directorio','')))
 if not root.is_dir():raise ValueError('La carpeta compartida no está disponible. Revisa que la PC puente esté encendida y que Windows tenga permiso de escritura.')
 root=root.resolve();parts=config['carpetas'][branch].split('/');parent=root
 for part in parts:
  parent=parent/part
  if parent.exists() and not parent.resolve().is_relative_to(root):raise ValueError('La carpeta de la sucursal apunta fuera del destino autorizado.')
  parent.mkdir(exist_ok=True)
 if not parent.resolve().is_relative_to(root):raise ValueError('La carpeta de destino cambió. Revisa su configuración.')
 name='PT_'+branch.replace(' ','_')+'_'+month+'.xlsx';target=parent/name
 def existing():
  if not target.exists():return None
  if target.is_symlink() or not target.resolve().is_relative_to(root):raise ValueError('El Excel de destino apunta fuera de la carpeta autorizada.')
  with target.open('rb') as handle:return workbook_hash(handle.read(100*1024*1024+1))
 previous=existing();owned=old.get('cantidades') if old.get('modo')=='carpeta' else None
 if config.get('libroExistente') or (previous is not None and owned):
  if previous is None:raise ValueError('Prepara el libro mensual '+name+' en la carpeta de la sucursal. Debe tener REGISTRO ENTRADA, con D PRODUCTO, E CANTIDAD y F UOM.')
  original=target.read_bytes();raw=merge_workbook(original,entries or [],month,owned)
  if backup and not owned:backup(original)
 signature=workbook_hash(raw);result={'archivo':name,'modo':'carpeta','firma':signature}
 if config.get('libroExistente') or owned:old={**old,'firma':previous}
 if previous==signature:return result
 if previous and previous!=old.get('firma'):raise ValueError('El Excel fue modificado fuera de GMP o ya existía en el destino. Conserva esa copia y revisa el archivo; no se sobrescribió.')
 if previous is None and old.get('firma'):raise ValueError('El Excel publicado fue eliminado fuera de GMP. Restáuralo en la carpeta antes de reintentar.')
 temporary=None
 try:
  fd,temporary=tempfile.mkstemp(prefix='.gmp-pt-',suffix='.tmp',dir=parent)
  with os.fdopen(fd,'wb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
  if existing()!=previous:raise ValueError('El archivo cambió mientras se preparaba la publicación. No se sobrescribió.')
  if previous is None:
   if os.name=='nt':os.rename(temporary,target)
   else:os.link(temporary,target);os.unlink(temporary)
  else:os.replace(temporary,target)
  temporary=None;return result
 except OSError:raise ValueError('No se pudo guardar el Excel en la carpeta. Comprueba permisos, conexión con la PC puente y que Excel no tenga el archivo abierto.')
 finally:
  if temporary:
   try:os.unlink(temporary)
   except OSError:pass

def probe_folder(config):
 root=pathlib.Path(validate_root(config.get('directorio','')))
 if not root.is_dir():raise ValueError('La carpeta no está disponible para el usuario de Windows que ejecuta GMP.')
 temporary=None
 try:
  fd,temporary=tempfile.mkstemp(prefix='.gmp-pt-prueba-',suffix='.tmp',dir=root)
  with os.fdopen(fd,'wb') as handle:handle.write(b'GMP PT folder test');handle.flush();os.fsync(handle.fileno())
 except OSError:raise ValueError('Windows no permite escribir en esa carpeta. Revisa el recurso compartido y sus permisos.')
 finally:
  if temporary:
   try:os.unlink(temporary)
   except OSError:pass
