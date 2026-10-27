MODULES={'ventas':'Generador SKU Ventas','compras':'Generador SKU Compras','requisiciones':'Requisición de materiales'}
DEFAULTS={'superadmin':list(MODULES),'visualizador':list(MODULES),'ventas':['ventas','requisiciones'],'compras':['compras','requisiciones'],'alta':list(MODULES),'gerente':['requisiciones'],'almacenista':['requisiciones']}
def enabled_modules(actor):return actor.get('modulos',DEFAULTS.get(actor['role'],[]))
def require_module(actor,module):
 if module not in enabled_modules(actor):raise PermissionError('El superadministrador no ha habilitado este módulo para tu perfil.')
