import contextlib,datetime as dt,io,json,unittest,zipfile
from unittest.mock import patch
import test_backup_import as fixture
import contabilidad as ac

FIELDS={key:{'tabla':key.split('.')[0],'campo':key.split('.')[1],'tipo':kind,'subtipo':1 if kind==261 else 0} for key,kind in [('FACTF01.CVE_DOC',37),('FACTF01.CVE_CLPV',37),('FACTF01.FECHA_DOC',35),('FACTF01.IMPORTE',27),('CLIE01.CLAVE',37),('CLIE01.NOMBRE',37),('FACTF_CLIB01.CLAVE_DOC',37),('FACTF_CLIB01.CAMPLIB1',261)]}
class Fake:
 def __init__(self,rows=None):self.rows=rows or [('F001',dt.datetime(2026,11,10,12,30),'CLIENTE DEMO',116.0)];self.queries=[]
 def cursor(self):return self
 def execute(self,sql,params=()):self.queries.append((sql,params))
 def fetchmany(self,size):return self.rows[:size]

class AccountingTests(unittest.TestCase):
 setUp=fixture.ModuleBackupTests.setUp;tearDown=fixture.ModuleBackupTests.tearDown;call=fixture.ModuleBackupTests.call;value=fixture.ModuleBackupTests.value;login=fixture.ModuleBackupTests.login
 def user(self,role):
  email=role+'@example.test';self.value('/api/users',{'email':email,'name':role,'role':role,'password':self.password,'active':True,'sucursales':['EJIDOS'] if role=='gerente' else [],'almacenes':[]});return self.login(email)
 def config(self):return {'host':'sae.example.test','database':'SAE_TEST','port':3050,'charset':'WIN1252','user':'REPORT_TEST','password':'only-test-secret','revision':1}
 def configure(self):
  with patch('contabilidad.connect'),patch('contabilidad.schema',return_value=FIELDS):r=self.value('/api/contabilidad/conexion',self.config())
  return self.value('/api/contabilidad/reporte',{'revision':r['revisionReporte'],'revisionConexion':r['revision'],'nombre':'Contabilidad demo','campoFecha':'FACTF01.FECHA_DOC','columnas':[{'campo':k,'titulo':title} for k,title in ac.DEFAULT_COLUMNS]})
 def params(self,meta):return {'desde':'01/11/2026','hasta':'30/11/2026','revisionReporte':meta['revisionReporte']}
 def test_accounting_only_report_cannot_enter_other_modules_or_change_config(self):
  reader=self.user('contabilidad');self.assertEqual(self.value('/api/me',actor=reader)['user']['modulos'],['contabilidad']);self.assertEqual(self.call('/',actor=reader)[0],200)
  for path in ('/api/catalogo','/api/users','/api/perfiles','/app.js','/pt','/compras','/inventarios','/comercial','/api/pt/meta','/api/requisiciones/materiales'):
   self.assertEqual(self.call(path,actor=reader)[0],403,path)
  meta=self.value('/api/contabilidad/meta',actor=reader);self.assertNotIn('configuracion',meta);self.assertNotIn('campos',meta)
  for action in ('conexion','detectar','reporte'):
   self.assertEqual(self.call('/api/contabilidad/'+action,{},reader)[0],403)
  self.assertEqual(self.call('/api/contabilidad/meta',actor=self.user('auxti'))[0],403)
  profile=next(p for p in self.value('/api/perfiles')['perfiles'] if p['perfil']=='contabilidad')
  self.assertEqual(self.call('/api/perfiles',{'perfil':'contabilidad','revision':profile['revision'],'modulos':['contabilidad','compras']},method='PUT')[0],400)
 def test_secret_encrypted_saved_report_and_parameterized_inclusive_dates(self):
  meta=self.configure();reader=self.user('contabilidad');fake=Fake()
  @contextlib.contextmanager
  def connected(c,p):self.assertEqual(p,'only-test-secret');yield fake
  data={**self.params(meta),'cliente':"O'BRIEN; DROP TABLE CLIE01 --",'columnas':[{'campo':'CLIE01.SALDO'}]}
  with patch('contabilidad.connect',connected):result=self.value('/api/contabilidad/consultar',data,reader)
  sql,params=fake.queries[-1];self.assertTrue(sql.startswith('SELECT FIRST 201 SKIP 0'));self.assertNotIn(data['cliente'],sql);self.assertNotIn('SALDO',sql);self.assertIn(data['cliente'],params);self.assertEqual(params[:2],[dt.date(2026,11,1),dt.date(2026,12,1)]);self.assertEqual(result['filas'][0][1],'10/11/2026 12:30:00')
  status=self.value('/api/contabilidad/meta',actor=reader);self.assertNotIn('secret',json.dumps(status));self.assertNotIn('host',json.dumps(status))
  with self.store.connect() as db:secret=db.execute('SELECT secret FROM accounting_config').fetchone()[0]
  self.assertNotIn('only-test-secret',secret);self.assertTrue(secret)
 def test_invalid_dates_columns_stale_revision_and_unsaved_report(self):
  self.assertEqual(self.call('/api/contabilidad/consultar',{'desde':'01/11/2026','hasta':'30/11/2026','revisionReporte':1})[0],400);meta=self.configure()
  for f in ({'desde':'2026-11-01'},{'desde':'31/11/2026'},{'hasta':'01/10/2026'},{'offset':-1}):
   self.assertEqual(self.call('/api/contabilidad/consultar',{**self.params(meta),**f})[0],400)
  self.assertEqual(self.call('/api/contabilidad/consultar',{**self.params(meta),'revisionReporte':1})[0],409)
  data={'revision':meta['revisionReporte'],'revisionConexion':meta['revision'],'nombre':'Prueba','campoFecha':'FACTF01.FECHA_DOC','columnas':[{'campo':'FACTF01.CVE_DOC; DELETE','titulo':'x'}]}
  self.assertEqual(self.call('/api/contabilidad/reporte',data)[0],400)
 def test_excel_all_pages_formula_safe_numeric_and_filters(self):
  meta=self.configure();reader=self.user('contabilidad');fake=Fake([('=HYPERLINK("bad")',dt.datetime(2026,11,30,23,59),'CLIENTE',116.5)]*250)
  @contextlib.contextmanager
  def connected(c,p):yield fake
  with patch('contabilidad.connect',connected):status,raw,_=self.call('/api/contabilidad/excel',self.params(meta),reader)
  self.assertEqual(status,200)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   xml=z.read('xl/worksheets/sheet1.xml').decode();self.assertNotIn('<f>',xml);self.assertIn('HYPERLINK',xml);self.assertIn('<v>116.5</v>',xml);self.assertIn('r="A251"',xml);self.assertIn('30/11/2026',z.read('xl/worksheets/sheet2.xml').decode())
  self.assertIn('FIRST 20001 SKIP 0',fake.queries[0][0])
 def test_export_limit_no_partial_report(self):
  meta=self.configure();fake=Fake([('a',None,'x',1)]*20001)
  @contextlib.contextmanager
  def connected(c,p):yield fake
  with patch('contabilidad.connect',connected):self.assertEqual(self.call('/api/contabilidad/excel',self.params(meta))[0],400)
 def test_driver_transactions_readonly_rollback_close(self):
  c=self.config();c.pop('password');c.pop('revision')
  with patch('firebirdsql.connect') as driver:
   with ac.connect(c,'TEST') as conn:pass
   self.assertTrue(driver.call_args.kwargs['readonly']);import firebirdsql;self.assertEqual(driver.call_args.kwargs['isolation_level'],firebirdsql.ISOLATION_LEVEL_READ_COMMITED_RO);conn.rollback.assert_called_once();conn.close.assert_called_once()
 def test_schema_requires_unique_keys_to_avoid_duplicated_amounts(self):
  class Cur:
   def execute(self,*args):pass
   def fetchall(self):
    self.n=getattr(self,'n',0)+1
    return [(f['tabla'],f['campo'],f['tipo'],f['subtipo']) for f in FIELDS.values()] if self.n==1 else [('CLIE01','KEY1','CLAVE')]
  class C:
   def cursor(self):return Cur()
  with self.assertRaisesRegex(ValueError,'clave única'):ac.schema(C())
