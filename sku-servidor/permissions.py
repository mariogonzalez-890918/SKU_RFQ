MODULES={'ventas':'Generador SKU Ventas','compras':'Generador SKU Compras','requisiciones':'Requisición de materiales','imagenes':'Imágenes de materiales','cargar_maestro':'Cargar maestros'}
DEFAULTS={'superadmin':list(MODULES),'auxti':list(MODULES),'visualizador':['ventas','compras','requisiciones'],'ventas':['ventas','requisiciones','cargar_maestro'],'compras':['compras','requisiciones','cargar_maestro'],'alta':['ventas','compras','requisiciones','cargar_maestro'],'gerente':['requisiciones'],'almacenista':['requisiciones']}

def enabled_modules(actor):return actor.get('modulos',DEFAULTS.get(actor['role'],[]))

def require_module(actor,module):
 if module not in enabled_modules(actor):raise PermissionError('El superadministrador no ha habilitado este acceso para tu perfil.')
