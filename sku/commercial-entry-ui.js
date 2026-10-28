// Los accesos comerciales quedan antes del resto de herramientas de Inicio.
const commercialHome=document.createElement('section');commercialHome.id='gmpCommercialHome';commercialHome.className='gmp-commercial-home';commercialHome.setAttribute('aria-label','Ventas y expendios');
for(const [module,title,description,icon] of [['ventasins','Pedidos institucionales','Clientes, presupuestos y pedidos','sell'],['expendios','Expendios / TPV','Ejidos, San Pablo, Cuautitlan y Eje 8','buy']]){
 if(!currentUser.modulos.includes(module))continue;
 const href='/comercial?canal='+module,button=document.createElement('a');button.href=href;button.id='gmpHome-'+module;button.className='gmp-commercial-button';button.append(gmpIcon(icon));const content=document.createElement('span'),name=document.createElement('strong'),note=document.createElement('small');name.textContent=title;note.textContent=description;content.append(name,note);button.append(content,gmpIcon('arrow'));commercialHome.append(button);
 const link=document.createElement('a');link.href=href;link.textContent=title;link.className='gmp-commercial-nav';$('gmpModuleLinks').append(link);
}
if(commercialHome.childElementCount){$('gmpHome').prepend(commercialHome);$('gmpAccessCount').textContent=(Object.values(gmpAllowed).filter(Boolean).length-1+commercialHome.childElementCount)+' accesos disponibles';}
