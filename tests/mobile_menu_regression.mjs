// Regresión del controlador real: viewport CSS, altura variable, reapertura y escritorio.
import assert from 'node:assert/strict';import fs from 'node:fs/promises';import vm from 'node:vm';
const source=await fs.readFile('sku/erp-ui.js','utf8'),begin=source.indexOf('const gmpMobileNav='),end=source.indexOf('function gmpNavigate',begin);assert(begin>=0&&end>begin);
const classes=new Set(),listeners={},mediaListeners={},elements={};let focusCount=0;
const media={matches:true,addEventListener:(name,fn)=>mediaListeners[name]=fn};
for(const id of ['gmpShade','gmpSidebar','gmpMenuToggle','gmpMenuClose'])elements[id]={hidden:false,inert:false,attributes:{},setAttribute(name,value){this.attributes[name]=value;},focus(){focusCount++;}};
const document={body:{classList:{contains:name=>classes.has(name),remove:name=>classes.delete(name),toggle(name,value=!classes.has(name)){if(value)classes.add(name);else classes.delete(name);return value;}}},addEventListener:(name,fn)=>listeners[name]=fn};
const window={innerWidth:1400,innerHeight:844,matchMedia:query=>{assert.equal(query,'(max-width: 1024px)');return media;},addEventListener:(name,fn)=>listeners[name]=fn};
vm.runInNewContext(source.slice(begin,end),{window,document,$:id=>elements[id]});
function opened(value){assert.equal(classes.has('gmp-menu-open'),value);assert.equal(elements.gmpSidebar.inert,!value);assert.equal(elements.gmpShade.hidden,!value);assert.equal(elements.gmpMenuToggle.attributes['aria-expanded'],String(value));}
opened(false);elements.gmpMenuToggle.onclick();opened(true);
// innerWidth puede incluir desbordamiento; debe prevalecer la media query de CSS.
assert.equal(window.innerWidth,1400);window.innerHeight=700;listeners.resize?.();opened(true);
elements.gmpMenuClose.onclick();opened(false);assert.equal(focusCount,1);elements.gmpMenuToggle.onclick();opened(true);elements.gmpShade.onclick();opened(false);elements.gmpMenuToggle.onclick();listeners.keydown({key:'Escape'});opened(false);
elements.gmpMenuToggle.onclick();media.matches=false;mediaListeners.change();assert.equal(elements.gmpSidebar.inert,false);assert.equal(elements.gmpMenuClose.hidden,true);assert.equal(elements.gmpMenuToggle.attributes['aria-expanded'],'true');elements.gmpMenuToggle.onclick();assert(classes.has('gmp-compact'));
media.matches=true;mediaListeners.change();opened(false);assert(!classes.has('gmp-compact'));elements.gmpMenuToggle.onclick();opened(true);
console.log('PASS: menú celular/tablet usa viewport CSS, no se cierra con altura variable, reabre y conserva navegación de escritorio.');
