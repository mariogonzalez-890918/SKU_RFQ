import assert from 'node:assert/strict';import fs from 'node:fs/promises';import vm from 'node:vm';import {randomFillSync} from 'node:crypto';
const keySource=await fs.readFile('sku/commercial-key-ui.js','utf8'),source=await fs.readFile('sku/commercial-ui.js','utf8');
// HTTP por IP no expone randomUUID. Se ejecuta el arranque real sin esa API.
for(const channel of ['ventasins','expendios']){
 const context=vm.createContext({crypto:{getRandomValues:bytes=>randomFillSync(bytes)},URLSearchParams,location:{search:'?canal='+channel}});
 vm.runInContext(keySource+'\n'+source.slice(0,source.indexOf('async function api')),context);
 assert.match(vm.runInContext('key',context),/^[a-f0-9]{32}$/);assert.equal(vm.runInContext('channel',context),channel);
 const keys=vm.runInContext('Array.from({length:1000},()=>commercialKey())',context);assert.equal(new Set(keys).size,1000);
 assert(!source.includes('crypto.randomUUID'),'Ningún reinicio de captura debe requerir HTTPS.');
}
class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};}append(...nodes){this.children.push(...nodes);}prepend(...nodes){this.children.unshift(...nodes);}setAttribute(k,v){this.attributes[k]=v;}get childElementCount(){return this.children.length;}}
const entry=await fs.readFile('sku/commercial-entry-ui.js','utf8');
for(const modules of [['ventasins','expendios'],['expendios'],['requisiciones']]){
 const elements=Object.fromEntries(['gmpHome','gmpModuleLinks','gmpAccessCount'].map(id=>[id,new Element('div')]));const hero=new Element('hero');elements.gmpHome.append(hero);
 vm.runInNewContext(entry,{currentUser:{modulos:modules},document:{createElement:tag=>new Element(tag)},$:id=>elements[id],gmpIcon:()=>new Element('svg'),gmpAllowed:{inicio:true}});
 const expected=modules.filter(m=>['ventasins','expendios'].includes(m));
 if(!expected.length){assert.equal(elements.gmpHome.children[0],hero);continue;}
 const home=elements.gmpHome.children[0];assert.equal(home.id,'gmpCommercialHome');assert.equal(home.childElementCount,expected.length);assert.equal(elements.gmpHome.children[1],hero);
 assert.deepEqual(home.children.map(e=>e.href),expected.map(m=>'/comercial?canal='+m));assert.equal(elements.gmpModuleLinks.childElementCount,expected.length);
}
console.log('PASS: arranque y claves de envío por HTTP/IP sin randomUUID; accesos comerciales al principio de Inicio y permisos de visibilidad respetados.');
