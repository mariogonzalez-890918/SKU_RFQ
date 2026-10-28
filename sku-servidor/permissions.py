MODULES={'ventas':'Generador SKU Ventas','compras':'Generador SKU Compras','requisiciones':'Requisición de materiales','imagenes':'Imágenes de materiales','cargar_maestro':'Cargar maestros','ventasins':'Pedidos institucionales','expendios':'Expendios / Punto de venta'}
DEFAULTS={'superadmin':list(MODULES),'auxti':['ventas','compras','requisiciones','imagenes','cargar_maestro'],'visualizador':['ventas','compras','requisiciones'],'ventas':['ventas','requisiciones','cargar_maestro'],'compras':['compras','requisiciones','cargar_maestro'],'alta':['ventas','compras','requisiciones','cargar_maestro'],'gerente':['requisiciones','cargar_maestro'],'almacenista':['requisiciones'],'requisicion':['requisiciones'],'ventasins':['ventasins'],'expendios':['expendios']}

def enabled_modules(actor):
 modules=actor.get('modulos',DEFAULTS.get(actor['role'],[]))
 return [m for m in modules if m=='requisiciones'] if actor['role']=='requisicion' else modules

def require_module(actor,module):
 if module not in enabled_modules(actor):raise PermissionError('El superadministrador no ha habilitado este acceso para tu perfil.')
