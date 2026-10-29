"""Proveedores, layout revisado y correo SMTP privado de GMP ERP."""
import copy,json,re,smtplib,ssl,uuid
from email.message import EmailMessage
from clientes_comerciales import read_table
from comercial import ADMINS,dumps,fingerprint
from requisiciones import Conflict,now,text
from pedidos_compra import email,SERIES_EDITORS

HEADERS=['CODIGO','NOMBRE','RFC','CORREO','CONTACTO','TELEFONO','DOMICILIO','REFERENCIA','CONDICIONES','ACTIVO']
def import_vendors(po,data,actor):
 company=data.get('empresa');po.scope(actor,company)
 if actor['role'] not in SERIES_EDITORS:raise PermissionError('Solo Compras, Gerencia y administración cargan proveedores.')
 rows=read_table(data,'PROVEEDORES');header=[re.sub(r'\s+','_',str(v).strip().upper()) for v in rows[0]]
 if header!=HEADERS:raise ValueError('Conserva los encabezados del layout PROVEEDORES.')
 with po.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');existing=[{'id':i,'codigo':c,'revision':r,**json.loads(p)} for i,c,r,p in db.execute('SELECT id,code,revision,payload FROM po_vendors WHERE company=? ORDER BY id',(company,))];stamp=fingerprint(existing)
  if not data.get('revisar') and data.get('huellaActual')!=stamp:raise Conflict('Los proveedores cambiaron. Revisa de nuevo el archivo.')
  prepared=[];seen=set();created=updated=omitted=0
  for n,row in enumerate(rows[1:],2):
   if not any(str(v).strip() for v in row):continue
   if len(row)>len(header) and any(row[len(header):]):raise ValueError(f'Fila {n}: sobran columnas.')
   values=dict(zip(header,(row+['']*len(header))[:len(header)]));code=str(values['CODIGO']).strip().upper();name=str(values['NOMBRE']).strip();rfc=str(values['RFC']).strip().upper();identity=code or rfc or name.upper()
   if not name or identity in seen:raise ValueError(f'Fila {n}: nombre vacío o proveedor repetido.')
   seen.add(identity);matches=[v for v in existing if v['codigo']==code] if code else [v for v in existing if rfc and v.get('rfc')==rfc or not rfc and v['nombre'].upper()==name.upper()]
   if len(matches)>1 or code and not matches:raise ValueError(f'Fila {n}: código inexistente o coincidencia ambigua; conserva el código del archivo exportado.')
   old=matches[0] if matches else None;active=str(values['ACTIVO'] or 'SI').strip().upper()
   if active not in ('SI','NO'):raise ValueError(f'Fila {n}: ACTIVO debe ser SI o NO.')
   value={'empresa':company,'nombre':name,'rfc':rfc,'correo':email(values['CORREO']),'contacto':str(values['CONTACTO']),'telefono':str(values['TELEFONO']),'domicilio':str(values['DOMICILIO']),'referencia':str(values['REFERENCIA']),'condiciones':str(values['CONDICIONES']),'activo':active=='SI'}
   if old and not data.get('actualizar'):omitted+=1;continue
   if old:value.update({'id':old['id'],'revision':old['revision']});updated+=1
   else:created+=1
   result=po.save_vendor(value,actor,db);prepared.append({'codigo':result['codigo'],'nombre':name})
  if data.get('revisar'):db.rollback()
 return {'ok':True,'nuevos':created,'actualizados':updated,'omitidos':omitted,'detalle':prepared,'huellaActual':stamp}

def smtp_config(po,actor):
 po.scope(actor)
 if actor['role'] not in ADMINS:raise PermissionError('Solo Sistemas y AUXTI configuran correo.')
 with po.store.connect() as db:revision,payload=db.execute('SELECT revision,payload FROM po_settings WHERE id=1').fetchone()
 value=json.loads(payload).get('smtp',{});return {'revision':revision,**{k:v for k,v in value.items() if k!='password'},'passwordConfigurada':bool(value.get('password'))}

def save_smtp(po,data,actor):
 old=smtp_config(po,actor);host=text(data.get('host',''),250);port=data.get('port',587);security=data.get('seguridad','STARTTLS');user=text(data.get('usuario',''),200);sender=email(data.get('remitente'))
 if not host or any(c.isspace() for c in host) or '/' in host or ':' in host or type(port) is not int or not 1<=port<=65535 or security not in ('STARTTLS','TLS') or not sender:raise ValueError('Host, puerto, TLS y remitente SMTP obligatorios.')
 with po.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');r,p=db.execute('SELECT revision,payload FROM po_settings WHERE id=1').fetchone()
  if r!=data.get('revision'):raise Conflict('Cambió la configuración de correo.')
  value=json.loads(p);password=data.get('password') or value.get('smtp',{}).get('password','');value['smtp']={'host':host,'port':port,'seguridad':security,'usuario':user,'remitente':sender,'password':text(password,2000)};db.execute('UPDATE po_settings SET revision=revision+1,payload=? WHERE id=1',(dumps(value),));po.audit(db,actor,'smtp_configurado',{'host':host})
 return {'ok':True}

def send_order(po,data,actor):
 from pedidos_compra_output import order_pdf
 id=data.get('id');key=str(data.get('clave',''))
 if not re.fullmatch('[A-Za-z0-9_-]{16,100}',key):raise ValueError('Falta clave única del envío.')
 with po.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');doc=po.document(db,id,actor);po.scope(actor,doc['empresa'],doc['sucursal'],capture=True,db=db)
  if doc['estado']=='CANCELADO':raise ValueError('No se envían pedidos cancelados.')
  repeat=db.execute('SELECT state,payload FROM po_mail WHERE client_key=?',(key,)).fetchone()
  if repeat:return {'ok':repeat[0]=='ENVIADO','repetido':True,'estado':repeat[0]}
  if doc['revision']!=data.get('revision'):raise Conflict('El pedido cambió. Revisa la vista previa antes de enviar.')
  recipient=email(data.get('destinatario') or doc['proveedor'].get('correo'));subject=text(data.get('asunto') or 'GMP ERP · '+doc['folio'],250);body=text(data.get('mensaje',''),20000)
  if not recipient or '\r' in subject or '\n' in subject:raise ValueError('Destinatario o asunto inválido.')
  config=json.loads(db.execute('SELECT payload FROM po_settings WHERE id=1').fetchone()[0]).get('smtp',{})
  if not config.get('host'):raise ValueError('Sistemas debe configurar SMTP antes de enviar al proveedor.')
  mid=uuid.uuid4().hex;value={'fecha':now(),'actor':actor['email'],'destinatario':recipient,'asunto':subject,'revisionDocumento':doc['revision'],'hashDocumento':fingerprint(doc),'mensaje':body};db.execute('INSERT INTO po_mail VALUES(?,?,?,?,?)',(mid,id,key,'ENVIANDO',dumps(value)))
 message=EmailMessage();message['From']=config['remitente'];message['To']=recipient;message['Subject']=subject;message['Message-ID']='<'+mid+'@gmp-erp.local>';message.set_content(body or 'Adjuntamos '+doc['folio']+'.')
 try:
  message.add_attachment(order_pdf(doc),maintype='application',subtype='pdf',filename=doc['folio']+'.pdf')
  if config['seguridad']=='TLS':connection=smtplib.SMTP_SSL(config['host'],config['port'],timeout=30,context=ssl.create_default_context())
  else:
   connection=smtplib.SMTP(config['host'],config['port'],timeout=30);connection.ehlo();connection.starttls(context=ssl.create_default_context());connection.ehlo()
  with connection:
   if config.get('usuario'):connection.login(config['usuario'],config.get('password',''))
   connection.send_message(message)
  state='ENVIADO'
 except Exception:
  state='REVISAR';value['error']='No se confirmó el envío. Verifica el correo del proveedor antes de intentar otro envío.'
 with po.store.connect() as db:
  db.execute('BEGIN IMMEDIATE');db.execute('UPDATE po_mail SET state=?,payload=? WHERE id=?',(state,dumps(value),mid));current=po.document(db,id,actor)
  if state=='ENVIADO' and current['estado']=='BORRADOR':current['estado']='ENVIADO';po.update_doc(db,current,actor,'correo_enviado')
  po.audit(db,actor,'correo_'+state.lower(),{'id':mid,'pedido':id,'destinatario':recipient})
 return {'ok':state=='ENVIADO','estado':state,'mensaje':value.get('error','Correo enviado al proveedor.')}
