// Presentación y navegación. Los permisos y las operaciones siguen en el servidor.
const gmpPaths={brain:'<path d="M12 5a4 4 0 0 0-7-2 4 4 0 0 0-3 6 4 4 0 0 0 0 6 4 4 0 0 0 4 6 4 4 0 0 0 6-2V5Zm0 0a4 4 0 0 1 7-2 4 4 0 0 1 3 6 4 4 0 0 1 0 6 4 4 0 0 1-4 6 4 4 0 0 1-6-2M5 7l3 2v4M4 16l4-1M19 7l-3 2v4M20 16l-4-1"/>',currency:'<path d="M12 2v20M18 6H9a4 4 0 0 0 0 8h6a3 3 0 0 1 0 6H5"/>',computer:'<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 22h8M12 17v5M6 7h12"/>',warehouse:'<path d="m2 9 10-7 10 7v13H2V9Zm5 13V11h10v11M7 15h10M7 19h10"/>',pos:'<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M7 6h10v4H7zM8 14h1M12 14h1M16 14h1M8 18h1M12 18h5"/>',home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',buy:'<path d="M3 3h2l2.5 12h11L21 6H6"/><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',sell:'<path d="M20 13 11 22 2 13V3h10z"/><circle cx="7" cy="8" r="1"/>',box:'<path d="m3 7 9-5 9 5v10l-9 5-9-5zM3 7l9 5 9-5M12 12v10M7.5 4.5l9 5"/>',chart:'<path d="M4 3v18h17M8 16v-4M13 16V7M18 16V4"/>',check:'<path d="m9 12 2 2 4-5"/><path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6z"/>',users:'<circle cx="9" cy="8" r="4"/><path d="M2 21v-3a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v3M17 4a4 4 0 0 1 0 8M22 21v-3a5 5 0 0 0-3-4.6"/>',lock:'<rect x="4" y="10" width="16" height="12" rx="3"/><path d="M8 10V6a4 4 0 0 1 8 0v4M12 15v3"/>',menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',logout:'<path d="M10 4H4v16h6M9 12h12m-4-4 4 4-4 4"/>',plus:'<path d="M12 4v16M4 12h16"/>',branch:'<circle cx="5" cy="4" r="2"/><circle cx="5" cy="20" r="2"/><circle cx="19" cy="4" r="2"/><path d="M5 6v12M19 6v2a4 4 0 0 1-4 4H5"/>',list:'<rect x="5" y="3" width="14" height="19" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>'};
function gmpIcon(name){const span=document.createElement('span');span.innerHTML='<svg class="gmp-icon" viewBox="0 0 24 24" aria-hidden="true">'+(gmpPaths[name]||gmpPaths.box)+'</svg>';return span.firstChild;}
function gmpLabel(button,label,icon){button.replaceChildren(gmpIcon(icon));const text=document.createElement('span');text.className='gmp-nav-text';text.textContent=label;button.append(text);button.title=label;button.setAttribute('aria-label',label);}
const gmpAllowed={inicio:true,compras:canReadPurchases,ventas:salesRead,requisiciones:currentUser.modulos.includes('requisiciones'),reportes:currentUser.modulos.includes('requisiciones')&&currentUser.role!=='requisicion',autorizaciones:canDelete||currentUser.role!=='requisicion'&&currentUser.modulos.includes('requisiciones')&&rwEnabled,usuarios:canDelete,perfiles:canDelete,respaldos:canDelete};
const gmpNames={inicio:'Inicio',compras:'SKU Compras',ventas:'SKU Ventas',requisiciones:'Requisición de materiales',reportes:'Reportes de requisición',autorizaciones:'Autorizaciones',usuarios:'Usuarios',perfiles:'Accesos por perfil',respaldos:'Respaldo y restauración'};
const gmpViews={inicio:$('gmpHome'),compras:$('comprasPanel'),ventas:$('ventasPanel'),requisiciones:$('requisicionesPanel'),reportes:$('gmpReportsPage'),autorizaciones:$('gmpApprovalsPage'),usuarios:$('gmpUsersPage'),perfiles:$('gmpProfilesPage'),respaldos:$('gmpBackupsPage')};
const gmpButtons={inicio:$('gmpNavHome'),compras:$('tabCompras'),ventas:$('tabVentas'),requisiciones:$('tabRequisiciones'),reportes:$('gmpNavReports'),autorizaciones:$('gmpNavApprovals'),usuarios:$('gmpNavUsers'),perfiles:$('gmpNavProfiles'),respaldos:$('gmpNavBackups')};
const gmpIcons={inicio:'home',compras:'brain',ventas:'currency',requisiciones:'box',reportes:'chart',autorizaciones:'check',usuarios:'users',perfiles:'computer',respaldos:'lock'};
let gmpActive='inicio',gmpNavGeneration=0;
$('gmpNav').append($('gmpNavBackups'));
for(const route of ['compras','ventas','requisiciones'])$('gmpModuleLinks').append(gmpButtons[route]);
for(const [route,button] of Object.entries(gmpButtons)){button.hidden=!gmpAllowed[route];button.removeAttribute('role');button.removeAttribute('aria-selected');button.type='button';button.dataset.route=route;gmpLabel(button,gmpNames[route],gmpIcons[route]);button.onclick=()=>gmpNavigate(route);}
$('gmpAdminCaption').hidden=!canDelete;
$('gmpAppVersion').textContent=appInfo.titulo+' · Versión '+appInfo.version;$('gmpAppSupport').textContent=appInfo.soporte;
$('gmpMenuToggle').append(gmpIcon('menu'));
$('gmpAccountName').textContent=currentUser.name;$('gmpAccountName').title=currentUser.email;$('gmpAccountRole').textContent=roleNames[currentUser.role];$('gmpRoleBadge').textContent=roleNames[currentUser.role];$('gmpAvatar').textContent=currentUser.name.split(/\s+/).slice(0,2).map(w=>w[0]).join('').toUpperCase();
$('gmpLogout').append($('salir'));$('salir').prepend(gmpIcon('logout'));
for(const [target,panel] of [['gmpReportsPage','rpPanel'],['gmpApprovalsPage','rwPanel'],['gmpUsersPage','usuariosPanel'],['gmpProfilesPage','perfilesModulosPanel']]){const detail=$(panel);$(target).append(detail);detail.classList.add('gmp-flat-panel');if(['rpPanel','rwPanel'].includes(panel))detail.ontoggle=null;detail.open=true;}
for(const dialog of document.querySelectorAll('main dialog'))$('gmpMain').append(dialog);
const gmpBuilder=document.createElement('details');gmpBuilder.id='gmpReportBuilder';const gmpBuilderSummary=document.createElement('summary');gmpBuilderSummary.textContent='Configurar filtros e impuestos';gmpBuilder.append(gmpBuilderSummary);$('rpEditor').before(gmpBuilder);gmpBuilder.append($('rpEditor'));gmpBuilder.hidden=!rpCanEdit;
for(const id of ['rpNuevo','rpCopia']){const original=$(id).onclick;$(id).onclick=async e=>{await original(e);gmpBuilder.open=true;gmpBuilder.scrollIntoView({behavior:'smooth',block:'start'});};}
const gmpSegments={};
function gmpTabs(parent,key,definitions,defaultTab){
 const nav=document.createElement('div');nav.className='gmp-segments';nav.setAttribute('role','tablist');nav.setAttribute('aria-label','Opciones de '+gmpNames[key]);parent.querySelector('.section-heading').after(nav);
 const views={},buttons={};
 for(const [id,label,nodes,allowed=true] of definitions){const view=document.createElement('div');view.id='gmp-'+key+'-'+id;view.className='gmp-subview';view.setAttribute('role','tabpanel');view.setAttribute('aria-labelledby','gmp-tab-'+key+'-'+id);for(const node of nodes.filter(Boolean))view.append(node);parent.append(view);views[id]=view;
  const button=document.createElement('button');button.type='button';button.id='gmp-tab-'+key+'-'+id;button.setAttribute('role','tab');button.setAttribute('aria-controls',view.id);button.textContent=label;button.hidden=!allowed;button.onclick=()=>gmpSelect(key,id);nav.append(button);buttons[id]=button;
 }
 gmpSegments[key]={views,buttons};gmpSelect(key,defaultTab);
}
function gmpSelect(key,id){const group=gmpSegments[key];if(!group||!group.views[id]||group.buttons[id].hidden)return;for(const [name,view] of Object.entries(group.views)){view.hidden=name!==id;group.buttons[name].setAttribute('aria-selected',String(name===id));group.buttons[name].tabIndex=name===id?0:-1;}group.active=id;}
// Accesibilidad de las pestañas secundarias: flechas, Inicio y Fin.
document.addEventListener('keydown',e=>{if(!e.target.matches('.gmp-segments [role=tab]'))return;const buttons=[...e.target.parentElement.querySelectorAll('button:not([hidden])')];let index=buttons.indexOf(e.target);if(e.key==='ArrowRight')index=(index+1)%buttons.length;else if(e.key==='ArrowLeft')index=(index+buttons.length-1)%buttons.length;else if(e.key==='Home')index=0;else if(e.key==='End')index=buttons.length-1;else return;e.preventDefault();buttons[index].click();buttons[index].focus();});
const purchaseNotes=[...$('comprasPanel').querySelectorAll(':scope > p')];const purchaseHelp=document.createElement('div');purchaseHelp.className='gmp-help';for(const p of purchaseNotes)purchaseHelp.append(p);
gmpTabs($('comprasPanel'),'compras',[
 ['catalogo','Catálogo',[$('excel').closest('.actions'),$('buscar').closest('.grid'),$('total'),$('registros').closest('.scroll')]],
 ['nuevo','Nuevo artículo',[$('nuevo').closest('details')],canEdit],
 ['cargar','Carga de lista',[$('listaTexto').closest('details')],canEdit],
 ['maestro','Maestro de compras',[$('maestroArchivo').closest('details')],canLoadMasters&&canReadPurchases],
 ['ayuda','Ayuda y códigos',[purchaseHelp,$('skuVerificar').closest('details'),$('catalogos').closest('details')]]
],'catalogo');
const salesNotes=[...$('ventasPanel').querySelectorAll(':scope > p:not([id])')],salesHelp=document.createElement('div');salesHelp.className='gmp-help';for(const p of salesNotes)salesHelp.append(p);
gmpTabs($('ventasPanel'),'ventas',[
 ['catalogo','Catálogo',[$('ventasActualizar').closest('.actions'),$('vBuscar').closest('.grid'),$('vTotal'),$('vRegistros').closest('.scroll')]],
 ['nuevo','Nuevo artículo',[$('ventasAltaPanel')],salesWrite&&salesRead],
 ['cargar','Carga de lista',[$('ventasLotePanel')],salesWrite&&salesRead],
 ['maestro','Maestro de ventas',[$('ventasImportarPanel')],canLoadMasters&&salesRead],
 ['ayuda','Ayuda y códigos',[salesHelp,$('vCatalogos').closest('details')]]
],'catalogo');
const gmpOriginalEdit=vEdit;vEdit=function(record){gmpSelect('ventas','nuevo');gmpOriginalEdit(record);};
const reqHistoryHeading=$('rqHistSucursal').closest('.section-heading');if(currentUser.role==='requisicion')reqHistoryHeading.querySelector('h3').textContent='Mis requisiciones emitidas';
gmpTabs($('requisicionesPanel'),'requisiciones',[
 ['nueva','Nueva solicitud',[$('rqAlta')],rqCanWrite],
 ['historial',currentUser.role==='requisicion'?'Mis requisiciones':'Historial',[reqHistoryHeading,$('rqHistTotal'),$('rqHistorial').closest('.scroll'),$('rqAnterior').closest('.actions')]],
 ['catalogo','Consultar materiales',[$('rqMasterInfo'),$('rqBuscarCatalogo').closest('details')],currentUser.role!=='requisicion'],
 ['maestro','Cargar maestro',[$('rqCargarPanel')],rqCanImport],
 ['imagenes','Imágenes por SKU',[$('rqImagesPanel')],currentUser.modulos.includes('imagenes')],
 ['series','Series y folios',[$('rqSeriesPanel')],rqCanConfigure],
 ['areas','Áreas solicitantes',[$('rqAreasPanel')],rqCanConfigure]
],rqCanWrite?'nueva':'historial');
for(const panel of [$('rqAlta'),$('ventasAltaPanel'),$('nuevo').closest('details')]){panel.classList.add('gmp-flat-panel');panel.open=true;}
$('rqBuscarCatalogo').closest('details').open=true;$('rqSeriesPanel').open=true;
const gmpMasterDownloads=document.createElement('div');gmpMasterDownloads.className='actions';gmpMasterDownloads.append($('rqCatalogoCSV'),$('rqMaestroOriginal'));gmpSegments.requisiciones.views.catalogo.prepend(gmpMasterDownloads);
const gmpOriginalMaterials=rqRenderMaterials;rqRenderMaterials=function(){gmpOriginalMaterials();const select=$('rqMaterial');select.size=Math.min(5,Math.max(1,select.options.length));select.style.height=select.options.length<=1?'48px':'145px';};
$('rqBuscarMaterial').oninput=rqRenderMaterials;
function gmpStatusCell(cell,state){const badge=document.createElement('span');badge.className='gmp-status gmp-status-'+state.toLowerCase();badge.textContent=state;cell.replaceChildren(badge);}
const gmpHistoryOriginal=rqHistory;rqHistory=async function(){await gmpHistoryOriginal();for(const row of $('rqHistorial').rows){const cell=row.cells[5];if(cell)gmpStatusCell(cell,cell.textContent.trim());}};
const gmpChangesOriginal=rwLoad;rwLoad=async function(){await gmpChangesOriginal();for(const row of $('rwTabla').rows){const cell=row.cells[0],parts=cell.textContent.split(' · '),status=parts.pop(),stamp=parts.join(' · ');const date=document.createElement('small');date.textContent=stamp;date.className='gmp-status-date';gmpStatusCell(cell,status);cell.prepend(date);}};
// Los maestros y la ayuda no compiten visualmente con la acción principal.
for(const id of ['excel','ventasActualizar','rqActualizar']){const actions=$(id).closest('.actions');if(actions){actions.classList.add('gmp-section-tools');}}
// La media query coincide con CSS; los cambios de altura del navegador no cierran el menú.
const gmpMobileNav=window.matchMedia('(max-width: 1024px)');
function gmpSetMenu(open=false){
 const mobile=gmpMobileNav.matches,expanded=mobile&&open;
 document.body.classList.toggle('gmp-menu-open',expanded);
 $('gmpShade').hidden=!expanded;$('gmpSidebar').inert=mobile&&!expanded;
 $('gmpMenuToggle').setAttribute('aria-expanded',String(mobile?expanded:!document.body.classList.contains('gmp-compact')));
 $('gmpMenuClose').hidden=!mobile;
}
function gmpCloseMenu(){gmpSetMenu(false);}
$('gmpMenuToggle').onclick=()=>{if(gmpMobileNav.matches){document.body.classList.remove('gmp-compact');gmpSetMenu(!document.body.classList.contains('gmp-menu-open'));}else{document.body.classList.toggle('gmp-compact');gmpSetMenu();}};
$('gmpMenuClose').onclick=()=>{gmpCloseMenu();$('gmpMenuToggle').focus({preventScroll:true});};
$('gmpShade').onclick=gmpCloseMenu;document.addEventListener('keydown',e=>{if(e.key==='Escape')gmpCloseMenu();});
gmpMobileNav.addEventListener('change',()=>{document.body.classList.remove('gmp-compact');gmpCloseMenu();});gmpCloseMenu();
function gmpNavigate(route,sub){if(!gmpAllowed[route])route='inicio';const value=route+(sub?'/'+sub:'');if(location.hash.slice(1)===value)void gmpRenderRoute();else location.hash=value;}
async function gmpRenderRoute(){
 const generation=++gmpNavGeneration;let [route,sub]=location.hash.slice(1).split('/');if(!gmpAllowed[route]){route='inicio';history.replaceState(null,'','#inicio');}gmpActive=route;
 for(const [name,view] of Object.entries(gmpViews))view.hidden=name!==route;
 $('sinModulos').hidden=true;for(const [name,button] of Object.entries(gmpButtons)){if(name===route)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}
 $('gmpPageTitle').textContent=gmpNames[route];$('gmpBreadcrumb').textContent='GMP / '+(['usuarios','perfiles','respaldos'].includes(route)?'Administración':route==='inicio'?'Mi espacio':'Operación');gmpCloseMenu();window.scrollTo({top:0,behavior:'instant'});
 if(sub&&gmpSegments[route])gmpSelect(route,sub);
 try{
  if(route==='ventas')await salesInit();
  if(['requisiciones','reportes','autorizaciones'].includes(route)&&currentUser.modulos.includes('requisiciones')&&!rqMeta)await rqLoad();
  if(route==='reportes')await rpInit();
  if(route==='autorizaciones'&&currentUser.modulos.includes('requisiciones'))await rwLoad();
  if(generation!==gmpNavGeneration)return;
 }catch(err){if(generation!==gmpNavGeneration)return;const id=route==='ventas'?'ventasMensaje':route==='reportes'?'rpMensaje':route==='autorizaciones'?'rwMensaje':'rqMensaje';$(id).textContent=err.message;}
}
const gmpCardDescriptions={compras:['Productos de compra','Consulta el catálogo y crea códigos para tus insumos.','Catálogo','#f1eaf4','#87618f'],ventas:['Productos de venta','Administra tus productos comerciales y sus códigos.','Catálogo','#e7f1f5','#4e879d'],requisiciones:['Requisición de materiales','Solicita materiales o consulta el historial por sucursal.','Operación','#fcf0e1','#bc8b46'],reportes:['Reportes y costos','Revisa el consumo y descarga reportes en Excel o PDF.','Análisis','#e8f1ec','#5b9275'],autorizaciones:['Autorizar cambios','Revisa modificaciones, cancelaciones y sus resoluciones.','Control','#f7e9ed','#b06e83'],usuarios:['Usuarios','Administra las cuentas y sus almacenes asignados.','Administración','#eaf0fa','#6b86b8'],perfiles:['Accesos por perfil','Configura qué módulos puede consultar cada perfil.','Administración','#f0eaf3','#9476a3'],respaldos:['Respaldo y restauración','Guarda o recupera los datos de compras, ventas o requisiciones.','Administración','#e8f1ec','#5b9275']};
$('gmpWelcome').textContent='Hola, '+currentUser.name+'.';
for(const [route,[title,description,category,fill,ink]] of Object.entries(gmpCardDescriptions)){if(!gmpAllowed[route])continue;const card=document.createElement('button');card.className='gmp-app-card';card.type='button';card.style.setProperty('--card-fill',fill);card.style.setProperty('--card-ink',ink);const icon=document.createElement('span');icon.className='gmp-card-icon';icon.append(gmpIcon(gmpIcons[route]));const h=document.createElement('strong'),p=document.createElement('small'),tag=document.createElement('span');h.textContent=title;p.textContent=description;if(route==='autorizaciones'&&!rwCanManage){h.textContent='Mis autorizaciones';p.textContent='Consulta el estado de tus propuestas de cambio.';}if(route==='requisiciones'&&!rqCanWrite)p.textContent='Consulta las solicitudes de tus sucursales autorizadas.';if(route==='compras'&&!canEdit||route==='ventas'&&!salesWrite)p.textContent='Consulta el catálogo y descarga el maestro actualizado.';tag.textContent=category;tag.className='gmp-card-category';card.append(icon,gmpIcon('arrow'),h,p,tag);card.onclick=()=>gmpNavigate(route);$('gmpHomeCards').append(card);}
$('gmpAccessCount').textContent=Object.values(gmpAllowed).filter(Boolean).length-1+' accesos disponibles';
const gmpQuick=[];if(rqCanWrite&&gmpAllowed.requisiciones)gmpQuick.push(['Nueva requisición','requisiciones','nueva','plus']);if(canEdit)gmpQuick.push(['Crear SKU de compra','compras','nuevo','plus']);if(!gmpQuick.length&&gmpAllowed.reportes)gmpQuick.push(['Consultar reportes','reportes',null,'chart']);if(!gmpQuick.length&&gmpAllowed.ventas)gmpQuick.push(['Abrir ventas','ventas',null,'sell']);
for(const [label,route,sub,icon] of gmpQuick.slice(0,2)){const button=document.createElement('button');button.type='button';button.append(gmpIcon(icon),document.createTextNode(label));button.onclick=()=>gmpNavigate(route,sub);$('gmpHeroActions').append(button);}
function gmpMetric(id,label,icon,value){const div=document.createElement('div');div.className='gmp-metric';const badge=document.createElement('span');badge.className='gmp-metric-icon';badge.append(gmpIcon(icon));const text=document.createElement('div'),strong=document.createElement('strong'),small=document.createElement('small');strong.id=id;strong.textContent=value;small.textContent=label;text.append(strong,small);div.append(badge,text);$('gmpMetrics').append(div);}
gmpMetric('gmpMetricModules','Módulos habilitados','box',currentUser.modulos.length);gmpMetric('gmpMetricProducts',canReadPurchases?'Artículos de compra':'Perfil de acceso','list',canReadPurchases?state.registros.filter(r=>!r.eliminado).length:roleNames[currentUser.role].toLowerCase());gmpMetric('gmpMetricRequests','Solicitudes visibles','chart',gmpAllowed.requisiciones?'…':'—');gmpMetric('gmpMetricBranches','Sucursales autorizadas','branch',gmpAllowed.requisiciones?'…':'—');
if(!currentUser.modulos.length)$('gmpHomeStatus').textContent='No tienes módulos asignados. Solicita acceso al superadministrador.';
if(gmpAllowed.requisiciones)void rqJSON('/meta').then(meta=>{$('gmpMetricRequests').textContent=meta.totalSolicitudes;$('gmpMetricBranches').textContent=meta.sucursales.length;}).catch(()=>{$('gmpMetricRequests').textContent=$('gmpMetricBranches').textContent='—';$('gmpHomeStatus').textContent='No se pudieron actualizar los indicadores. Abre Requisiciones para reintentar.';});
// Corrección de textos de ayuda para reflejar el flujo de autorización vigente.
const gmpOldLocations=renderUserLocations;renderUserLocations=function(values){gmpOldLocations(values);if($('usuarioRol').value==='gerente')$('usuarioAccesosNota').textContent='Tiene acceso a las cuatro sucursales. Puede crear requisiciones, cargar maestros, modificar series y folios, editar reportes y autorizar cambios.';if($('usuarioRol').value==='almacenista')$('usuarioAccesosNota').textContent='Selecciona sus almacenes. Puede consultar sus requisiciones y proponer modificaciones o cancelaciones para aprobación.';};
window.addEventListener('hashchange',()=>void gmpRenderRoute());await gmpRenderRoute();document.documentElement.setAttribute('data-erp-ready','true');


