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
class Element{constructor(tag){this.tagName=tag;this.children=[];this.attributes={};this.style={setProperty(){}};}append(...nodes){this.children.push(...nodes);}prepend(...nodes){this.children.unshift(...nodes);}setAttribute(k,v){this.attributes[k]=v;}get childElementCount(){return this.children.length;}}
const entry=await fs.readFile('sku/commercial-entry-ui.js','utf8');
for(const modules of [['ventasins','expendios','pedidoscompra'],['expendios'],['pedidoscompra'],['requisiciones']]){
 const elements=Object.fromEntries(['gmpHome','gmpHomeCards','gmpModuleLinks','gmpAccessCount'].map(id=>[id,new Element('div')]));const hero=new Element('hero');elements.gmpHome.append(hero);
 vm.runInNewContext(entry,{currentUser:{modulos:modules},document:{createElement:tag=>new Element(tag)},$:id=>elements[id],gmpIcon:()=>new Element('svg'),gmpAllowed:{inicio:true}});
 for(const link of elements.gmpModuleLinks.children){assert(link.title);assert.equal(link.attributes['aria-label'],link.title);assert.equal(link.children[1].className,'gmp-nav-text');}const expected=modules.filter(m=>['ventasins','expendios','pedidoscompra'].includes(m));assert.equal(elements.gmpHome.children[0],hero);assert.equal(elements.gmpHome.childElementCount,1);assert.equal(elements.gmpHomeCards.childElementCount,expected.length);assert.equal(elements.gmpModuleLinks.childElementCount,expected.length);assert.deepEqual(elements.gmpHomeCards.children.map(e=>e.href),expected.map(m=>m==='pedidoscompra'?'/compras':'/comercial?canal='+m));
}
console.log('PASS: HTTP/IP y accesos con iconos integrados en la cuadrícula, sin franjas superiores.');

const dates=await fs.readFile('sku/date-format.js','utf8');const dc=vm.createContext({});vm.runInContext(dates,dc);assert.equal(vm.runInContext("gmpDate('2026-10-28T13:40:00-06:00')",dc),'28/10/2026 13:40:00');assert.equal(vm.runInContext("gmpDateISO('29/02/2024')",dc),'2024-02-29');assert.throws(()=>vm.runInContext("gmpDateISO('31/02/2026')",dc));assert.equal(vm.runInContext("gmpTax('8')",dc),'IEPS');assert.equal(vm.runInContext("gmpTax('16')",dc),'IVA');console.log('PASS: fechas dd/mm/yyyy, validación de fechas e identificación de IEPS/IVA.');

const purchaseSource=await fs.readFile('sku/purchase-ui.js','utf8');const apiSource=purchaseSource.slice(purchaseSource.indexOf('async function api('),purchaseSource.indexOf('function captureState('));let cleared=0;const timeoutContext=vm.createContext({AbortController,URLSearchParams,company:1,branch:'EJIDOS',me:{csrf:'test'},setTimeout:fn=>{fn();return 1;},clearTimeout:()=>cleared++,fetch:async()=>{throw Error('Abort');}});vm.runInContext(apiSource,timeoutContext);await assert.rejects(vm.runInContext("api('materiales')",timeoutContext),/tardó demasiado/);assert.equal(cleared,1);console.log('PASS: la espera HTTP termina y libera su temporizador.');
