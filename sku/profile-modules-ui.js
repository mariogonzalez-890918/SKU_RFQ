let moduleProfilesData=null;
function profileModuleAllowed(role,module){const only={contabilidad:'contabilidad',pt:'pt',requisicion:'requisiciones',ventaspasteleria:'ventasins'};return role==='superadmin'||((!only[role]||only[role]===module)&&(module!=='contabilidad'||role==='contabilidad'));}
function renderModuleProfiles(){
 const data=moduleProfilesData;if(!data)return;
 const modules=Object.entries(data.modulos),filter=$('perfilesModulosFiltro').value,head=document.createElement('tr');
 for(const [key,title] of [['perfil','Perfil'],...modules,['acciones','Acciones']]){const th=document.createElement('th');th.scope='col';th.dataset.module=key;th.textContent=title;head.append(th);}
 $('perfilesModulosEncabezados').replaceChildren(head);$('perfilesModulosTabla').replaceChildren();
 const rank=role=>role==='superadmin'?0:role==='contabilidad'?1:role==='pt'?2:3;
 const profiles=[...data.perfiles].sort((a,b)=>rank(a.perfil)-rank(b.perfil)||a.nombre.localeCompare(b.nombre,'es'));
 $('perfilesModulosResumen').textContent=data.perfiles.length+' perfiles · '+modules.length+' módulos · '+(filter?'Mostrando un perfil':'Todos los perfiles')+'. Desplaza la tabla horizontalmente para ver todos los módulos.';
 for(const profile of profiles){
  if(filter&&profile.perfil!==filter)continue;
  const tr=document.createElement('tr');tr.dataset.profile=profile.perfil;const name=td(tr,profile.nombre);name.className='gmp-profile-name';const checks={};
  for(const [key,label] of modules){const cell=td(tr,''),input=document.createElement('input'),allowed=profileModuleAllowed(profile.perfil,key);cell.dataset.module=key;input.type='checkbox';input.checked=allowed&&profile.modulos.includes(key);input.disabled=profile.perfil==='superadmin'||currentUser.role!=='superadmin'||!allowed;input.dataset.module=key;input.setAttribute('aria-label',profile.nombre+' · '+label);if(!allowed)input.title='Este módulo no corresponde a las funciones de este perfil.';checks[key]=input;cell.append(input);}
  const action=td(tr,''),status=document.createElement('span');action.dataset.module='acciones';status.className='note';
  if(profile.perfil!=='superadmin'&&currentUser.role==='superadmin'){
   const button=document.createElement('button');button.textContent='Guardar accesos';button.className='secondary';button.onclick=async()=>{button.disabled=true;const selected=Object.keys(checks).filter(k=>checks[k].checked);try{const result=await fetch('/api/perfiles',{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':currentUser.csrf},body:JSON.stringify({perfil:profile.perfil,revision:profile.revision,modulos:selected})}),updated=await result.json();if(!result.ok)throw Error(updated.error);const saved=updated.perfiles.find(p=>p.perfil===profile.perfil);profile.revision=saved.revision;profile.modulos=saved.modulos;status.textContent='Guardado. Actualiza las otras sesiones para ver sus accesos.';}catch(err){status.textContent=err.message;}finally{button.disabled=false;}};action.append(button);
  }else status.textContent=profile.perfil==='superadmin'?'Acceso completo':'Consulta; solo Sistemas modifica accesos';
  action.append(status);$('perfilesModulosTabla').append(tr);
 }
}
async function loadModuleProfiles(){const response=await fetch('/api/perfiles',{cache:'no-store'}),data=await response.json();if(!response.ok)throw Error(data.error);const previous=$('perfilesModulosFiltro').value;moduleProfilesData=data;$('perfilesModulosFiltro').replaceChildren(new Option('Todos los perfiles',''));for(const p of [...data.perfiles].sort((a,b)=>a.nombre.localeCompare(b.nombre,'es')))$('perfilesModulosFiltro').add(new Option(p.nombre,p.perfil));$('perfilesModulosFiltro').value=data.perfiles.some(p=>p.perfil===previous)?previous:'';$('perfilesModulosError').textContent='';renderModuleProfiles();}
$('perfilesModulosFiltro').onchange=renderModuleProfiles;$('perfilesModulosPanel').hidden=!canDelete;$('perfilesModulosActualizar').onclick=async()=>{try{await loadModuleProfiles();}catch(err){$('perfilesModulosError').textContent=err.message;}};if(canDelete){try{await loadModuleProfiles();}catch(err){$('perfilesModulosError').textContent=err.message;}}

$('perfilesModulosAnterior').onclick=()=>$('perfilesModulosScroll').scrollBy({left:-Math.max(250,$('perfilesModulosScroll').clientWidth*.7),behavior:'smooth'});$('perfilesModulosSiguiente').onclick=()=>$('perfilesModulosScroll').scrollBy({left:Math.max(250,$('perfilesModulosScroll').clientWidth*.7),behavior:'smooth'});
