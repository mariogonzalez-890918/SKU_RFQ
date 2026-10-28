// Los módulos comerciales conservan una interfaz propia; comparten la sesión del servidor.
for(const [module,title] of [['ventasins','Pedidos institucionales'],['expendios','Expendios / Punto de venta']]){
 if(!currentUser.modulos.includes(module))continue;
 const link=document.createElement('a');link.href='/comercial?canal='+module;link.textContent=title;link.className='gmp-commercial-entry';link.style.cssText='display:block;padding:13px 16px;color:inherit;text-decoration:none;border-radius:8px;margin:5px 0;background:rgba(125,105,160,.12)';
 const nav=document.querySelector('.gmp-sidebar nav')||$('gmpSidebar')||document.querySelector('aside')||$('sinModulos');nav.append(link);
 if($('sinModulos')&&!currentUser.modulos.some(m=>['compras','ventas','requisiciones'].includes(m))){$('sinModulos').hidden=false;$('sinModulos').querySelector('h2').textContent='Módulos comerciales';$('sinModulos').querySelector('p').textContent='Selecciona Pedidos institucionales o Expendios para continuar.';if(nav!==$('sinModulos'))$('sinModulos').append(link.cloneNode(true));}
}
