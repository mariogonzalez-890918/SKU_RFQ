"""Catálogo editable de áreas; conserva los nombres usados por documentos emitidos."""
import json
from permissions import require_module
from requisiciones import Conflict,norm,text
MANAGERS={'superadmin','auxti','gerente'}
def default_catalog(defaults):return {'maxId':len(defaults),'areas':[{'id':i+1,'nombre':name} for i,name in enumerate(defaults)],'historicos':[]}
def validate_catalog(data):
 if not isinstance(data,dict) or set(data)!={'maxId','areas','historicos'} or type(data['maxId']) is not int or data['maxId']<1 or not isinstance(data['areas'],list) or not data['areas'] or not isinstance(data['historicos'],list):raise ValueError('Catálogo de áreas inválido.')
 if len(data['areas'])+len(data['historicos'])>20000:raise ValueError('El catálogo de áreas es demasiado grande.')
 ids=set();names={}
 for row in data['areas']:
  if not isinstance(row,dict) or set(row)!={'id','nombre'} or type(row['id']) is not int or not 1<=row['id']<=data['maxId'] or row['id'] in ids or not isinstance(row['nombre'],str) or not 1<=len(row['nombre'])<=160 or not norm(row['nombre']):raise ValueError('Área inválida o repetida.')
  key=norm(row['nombre'])
  if key in names:raise ValueError('Nombre de área repetido.')
  ids.add(row['id']);names[key]=row['id']
 for row in data['historicos']:
  if not isinstance(row,dict) or set(row)!={'id','nombre'} or row['id'] not in ids or not isinstance(row['nombre'],str) or not 1<=len(row['nombre'])<=160 or not norm(row['nombre']):raise ValueError('Nombre histórico de área inválido.')
  key=norm(row['nombre'])
  if key in names and names[key]!=row['id']:raise ValueError('Un nombre histórico pertenece a otra área.')
  names[key]=row['id']
 return list(dict.fromkeys(r['nombre'] for r in data['areas']+data['historicos']))
class AreaStore:
 def __init__(self,store,defaults):
  self.store=store
  with store.connect() as db:
   db.execute('CREATE TABLE IF NOT EXISTS req_areas(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL)')
   db.execute('INSERT OR IGNORE INTO req_areas VALUES(1,1,?)',(json.dumps(default_catalog(defaults),ensure_ascii=False),))
 def catalog(self,db=None):
  if db is None:
   with self.store.connect() as conn:return self.catalog(conn)
  revision,payload=db.execute('SELECT revision,payload FROM req_areas WHERE id=1').fetchone();return {'revision':revision,**json.loads(payload)}
 def names(self,historical=False,db=None):
  data=self.catalog(db);return list(dict.fromkeys(r['nombre'] for r in data['areas']+(data['historicos'] if historical else [])))
 def authorize(self,actor):
  require_module(actor,'requisiciones')
  if actor['role'] not in MANAGERS:raise PermissionError('Solo Superadministrador, AUXTI y Gerente pueden administrar áreas solicitantes.')
 def list(self,actor):
  self.authorize(actor);data=self.catalog();return {'revision':data['revision'],'areas':data['areas']}
 def save(self,data,actor,id=None):
  self.authorize(actor);name=' '.join(text(data.get('nombre',''),160).split())
  if not norm(name):raise ValueError('Escribe el nombre del área.')
  if type(data.get('revision')) is not int:raise ValueError('Falta la revisión del catálogo de áreas.')
  with self.store.connect() as db:
   db.execute('BEGIN IMMEDIATE');catalog=self.catalog(db);revision=catalog.pop('revision')
   if revision!=data['revision']:raise Conflict('Las áreas cambiaron. Actualiza el catálogo antes de guardar.')
   if any(norm(r['nombre'])==norm(name) and r['id']!=id for r in catalog['areas']+catalog['historicos']):raise ValueError('Ese nombre de área ya existe o está reservado en el historial.')
   if id is None:
    catalog['maxId']+=1;catalog['areas'].append({'id':catalog['maxId'],'nombre':name})
   else:
    row=next((r for r in catalog['areas'] if r['id']==id),None)
    if row is None:raise ValueError('Área no encontrada.')
    if row['nombre']==name:return {'revision':revision,'areas':catalog['areas']}
    previous=dict(row)
    if previous not in catalog['historicos']:catalog['historicos'].append(previous)
    row['nombre']=name
   validate_catalog(catalog);db.execute('UPDATE req_areas SET revision=?,payload=? WHERE id=1',(revision+1,json.dumps(catalog,ensure_ascii=False)))
  return {'revision':revision+1,'areas':catalog['areas']}
