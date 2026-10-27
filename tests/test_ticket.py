"""Dos formatos de impresión sin costos y con los mismos permisos de requisición."""
import unittest,uuid
import test_backup_import as fixture
from requisiciones import print_document
class TicketTests(unittest.TestCase):
 def setUp(self):
  self.case=fixture.ModuleBackupTests();self.case.setUp();self.case.import_req([fixture.product(B='SKU00000000001')]);self.material=self.case.value('/api/requisiciones/materiales')['materiales'][0]
 def tearDown(self):self.case.tearDown()
 def user(self,email):
  self.case.value('/api/users',{'email':email,'name':'Captura','role':'requisicion','active':True,'password':self.case.password,'sucursales':['EJIDOS']});return self.case.login(email)
 def create(self,actor):return self.case.value('/api/requisiciones',{'sucursal':'EJIDOS','area':'Produccion Donas','solicitante':'Solicitante prueba','observaciones':'Observaciones finales','claveCliente':uuid.uuid4().hex,'partidas':[{'materialId':self.material['id'],'cantidad':'3.5','observaciones':'Indicaciones de entrega'}]},actor)['documento']
 def test_both_formats_preserve_document_and_signatures(self):
  actor=self.user('capture@example.com');doc=self.create(actor);base='/api/requisiciones/'+doc['id']+'/imprimir';actual=self.case.call(base,actor=actor);ticket=self.case.call(base+'?formato=ticket',actor=actor)
  self.assertEqual((actual[0],ticket[0]),(200,200));self.assertIn('text/html',ticket[2]['Content-Type']);old=actual[1].decode();small=ticket[1].decode();self.assertIn('width:80mm',small);self.assertIn('padding:4mm 4mm 6mm',small);self.assertIn('size:80mm',small);self.assertIn('Bixolon',small);self.assertNotIn('Epson',small);self.assertIn('<table>',old);self.assertNotIn('ticket-page',old)
  for text in (doc['numero'],'Solicitante prueba','Observaciones finales','Indicaciones de entrega','Solicita','Entrega','Recibe','3.5','KILO'):self.assertIn(text,small)
  self.assertLess(small.index('Observaciones finales'),small.index('class="signatures"'));self.assertNotIn('costo',small.lower());self.assertNotIn('precio',small.lower());self.assertEqual(self.case.value('/api/requisiciones/'+doc['id'],actor=actor),doc)
 def test_ticket_obeys_own_document_and_branch_access(self):
  actor=self.user('capture@example.com');other=self.user('other@example.com');doc=self.create(actor);path='/api/requisiciones/'+doc['id']+'/imprimir?formato=ticket';self.assertEqual(self.case.call(path,actor=other)[0],404)
  self.case.value('/api/users',{'email':'capture@example.com','name':'Captura','role':'requisicion','active':True,'sucursales':['SAN PABLO']});self.assertEqual(self.case.call(path,actor=actor)[0],404)
 def test_html_escaping_and_invalid_format(self):
  doc=self.create(self.case.admin);doc['partidas'][0]['nombre']='<script>alert(1)</script>';doc['observaciones']='<img src=x onerror=alert(1)>'
  raw=print_document(doc,'ticket').decode();self.assertIn('&lt;script&gt;',raw);self.assertNotIn('<script>alert(1)',raw);self.assertIn('&lt;img src=x',raw)
  self.assertEqual(self.case.call('/api/requisiciones/'+doc['id']+'/imprimir?formato=invalido')[0],400)

if __name__=='__main__':unittest.main()
