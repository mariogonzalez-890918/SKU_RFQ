// Cada módulo muestra una tarea a la vez y sus opciones se eligen en el menú lateral.
function gmpSubviewHeading(parent,title){const heading=document.createElement('div');heading.className='section-heading';const h=document.createElement('h3');h.textContent=title;heading.append(h);parent.querySelector(':scope > summary')?.after(heading);if(!heading.parentNode)parent.prepend(heading);}
const reportPanel=$('rpPanel'),reportNotes=[...reportPanel.querySelectorAll(':scope > p')],reportSelection=$('rpSeleccion').closest('.grid'),reportActions=$('rpVer').closest('.actions');
gmpSubviewHeading(reportPanel,'Reportes de requisición');gmpTabs(reportPanel,'reportes',[
 ['consulta','Consultar y descargar',[reportNotes[0],reportSelection,reportActions,reportNotes[1],$('rpResultado')]],
 ['configurar','Configurar reportes',[$('gmpReportBuilder')],rpCanEdit],
 ['costos','Costos y unidades',[$('rpCostosPanel')],rpCanEdit]
],'consulta');
$('rpCostosPanel').ontoggle=null;$('rpCostosPanel').classList.add('gmp-flat-panel');
$('gmpReportBuilder').open=true;$('gmpReportBuilder').classList.add('gmp-flat-panel');
for(const id of ['rpNuevo','rpCopia']){const old=$(id).onclick;$(id).onclick=async e=>{await old(e);gmpNavigate('reportes','configurar');};}
const gmpShowReport=rpShow;rpShow=function(result){gmpShowReport(result);gmpNavigate('reportes','consulta');};
const backupPage=$('gmpBackupsPage'),backupCards=[...backupPage.querySelectorAll('.gmp-backup-card')],backupShared=document.createElement('div');backupShared.className='gmp-catalog-toolbar';backupShared.append($('bkModulo').closest('label'),$('bkMensaje'),$('bkPrevio'));backupPage.querySelector('.gmp-page-intro').after(backupShared);gmpSubviewHeading(backupPage,'Administrar datos');gmpTabs(backupPage,'respaldos',[
 ['descargar','Descargar respaldo',[backupCards[0]]],['restaurar','Restaurar respaldo',[backupCards[1]]],['reiniciar','Vaciar módulo',[backupCards[2]]]
],'descargar');
const gmpSubmenus={},gmpSubButtons={};
for(const [route,group] of Object.entries(gmpSegments)){
 const parent=gmpButtons[route];if(!parent||!gmpAllowed[route])continue;
 const originalTabs=Object.values(group.buttons)[0]?.parentElement;if(originalTabs)originalTabs.hidden=true;
 const panel=document.createElement('div');panel.id='gmpSubmenu-'+route;panel.className='gmp-submenu';panel.setAttribute('aria-label','Opciones de '+gmpNames[route]);panel.hidden=true;parent.after(panel);parent.classList.add('gmp-nav-parent');parent.setAttribute('aria-controls',panel.id);parent.setAttribute('aria-expanded','false');const chevron=document.createElement('span');chevron.className='gmp-nav-chevron';chevron.textContent='⌄';chevron.setAttribute('aria-hidden','true');parent.append(chevron);gmpSubmenus[route]=panel;gmpSubButtons[route]={};
 for(const [id,tab] of Object.entries(group.buttons)){if(tab.hidden)continue;const button=document.createElement('button');button.type='button';button.id='gmp-nav-'+route+'-'+id;button.textContent=tab.textContent;button.onclick=()=>gmpNavigate(route,id);panel.append(button);gmpSubButtons[route][id]=button;}
 parent.onclick=()=>{if(gmpMobileNav.matches){const opening=panel.hidden;for(const [other,view] of Object.entries(gmpSubmenus)){view.hidden=true;gmpButtons[other].setAttribute('aria-expanded','false');}panel.hidden=!opening;parent.setAttribute('aria-expanded',String(opening));return;}if(document.body.classList.contains('gmp-compact'))document.body.classList.remove('gmp-compact');gmpNavigate(route,group.active);};
}
function gmpSyncSubmenus(){for(const [route,panel] of Object.entries(gmpSubmenus)){const active=route===gmpActive;panel.hidden=!active;gmpButtons[route].setAttribute('aria-expanded',String(active));gmpButtons[route].removeAttribute('aria-current');gmpButtons[route].classList.toggle('gmp-parent-active',active);for(const [id,button] of Object.entries(gmpSubButtons[route])){if(active&&gmpSegments[route].active===id)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}}if(gmpSegments[gmpActive]){const tab=gmpSegments[gmpActive].buttons[gmpSegments[gmpActive].active];$('gmpPageTitle').textContent=tab.textContent;$('gmpBreadcrumb').textContent='GMP / '+gmpNames[gmpActive];}}
const gmpSelectWithSidebar=gmpSelect;gmpSelect=function(key,id){gmpSelectWithSidebar(key,id);gmpSyncSubmenus();};
const gmpRouteWithSidebar=gmpRenderRoute;gmpRenderRoute=async function(){await gmpRouteWithSidebar();gmpSyncSubmenus();if(gmpActive==='requisiciones'&&gmpSegments.requisiciones.active==='imagenes')await rqImagesLoad();if(gmpActive==='reportes'&&gmpSegments.reportes.active==='costos'){const panel=$('rpCostosPanel');if(!panel.open)panel.open=true;await rpLoadCosts();}};
for(const id of ['rqCargarPanel','cpMasterPanel','ventasImportarPanel','ventasLotePanel']){const panel=$(id);if(panel){panel.open=true;panel.classList.add('gmp-flat-panel');}}
await gmpRenderRoute();document.documentElement.setAttribute('data-submenus-ready','true');
