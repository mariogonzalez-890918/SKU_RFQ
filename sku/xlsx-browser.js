// ZIP/OOXML nativo. Conserva todos los archivos internos del maestro y modifica solo celdas solicitadas.
const utf8=new TextEncoder(),decode=b=>new TextDecoder().decode(b);
async function openZip(bytes){
 const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);let end=bytes.length-22;
 while(end>=Math.max(0,bytes.length-65557)&&view.getUint32(end,true)!==0x06054b50)end--;
 if(end<Math.max(0,bytes.length-65557))throw Error('El archivo no es un XLSX válido.');
 const count=view.getUint16(end+10,true);let pos=view.getUint32(end+16,true);const files=new Map();
 if(count===65535)throw Error('No se admiten archivos ZIP64.');
 for(let i=0;i<count;i++){
  if(view.getUint32(pos,true)!==0x02014b50)throw Error('Directorio ZIP inválido.');
  const flags=view.getUint16(pos+8,true),method=view.getUint16(pos+10,true),crc=view.getUint32(pos+16,true),packed=view.getUint32(pos+20,true),size=view.getUint32(pos+24,true),nl=view.getUint16(pos+28,true),xl=view.getUint16(pos+30,true),cl=view.getUint16(pos+32,true),offset=view.getUint32(pos+42,true);
  if(flags&1||![0,8].includes(method)||size>100000000)throw Error('Archivo comprimido no compatible.');
  const name=decode(bytes.subarray(pos+46,pos+46+nl));const start=offset+30+view.getUint16(offset+26,true)+view.getUint16(offset+28,true);
  files.set(name,{name,method,crc,size,packed:bytes.slice(start,start+packed),time:view.getUint16(pos+12,true),date:view.getUint16(pos+14,true),attrs:view.getUint32(pos+38,true)});pos+=46+nl+xl+cl;
 }
 return files;
}
async function unzipText(files,name){const f=files.get(name);if(!f)throw Error('Falta una parte del archivo: '+name);if(f.method===0)return decode(f.packed);if(typeof DecompressionStream==='undefined')throw Error('Abre la página en una versión actual de Chrome o Edge.');const stream=new Blob([f.packed]).stream().pipeThrough(new DecompressionStream('deflate-raw'));const bytes=new Uint8Array(await new Response(stream).arrayBuffer());if(bytes.length!==f.size)throw Error('Parte ZIP incompleta.');return decode(bytes);}
const crcTable=Array.from({length:256},(_,n)=>{for(let k=0;k<8;k++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
function crc32(bytes){let n=0xffffffff;for(const b of bytes)n=crcTable[(n^b)&255]^(n>>>8);return (n^0xffffffff)>>>0;}
function zipBytes(files,replacements){
 const locals=[],central=[];let offset=0;
 for(const [name,f] of files){const changed=replacements.has(name),data=changed?utf8.encode(replacements.get(name)):f.packed,nameBytes=utf8.encode(name),method=changed?0:f.method,size=changed?data.length:f.size,crc=changed?crc32(data):f.crc;
  const h=new Uint8Array(30+nameBytes.length),v=new DataView(h.buffer);v.setUint32(0,0x04034b50,true);v.setUint16(4,20,true);v.setUint16(6,2048,true);v.setUint16(8,method,true);v.setUint16(10,f.time,true);v.setUint16(12,f.date,true);v.setUint32(14,crc,true);v.setUint32(18,data.length,true);v.setUint32(22,size,true);v.setUint16(26,nameBytes.length,true);h.set(nameBytes,30);locals.push(h,data);
  const c=new Uint8Array(46+nameBytes.length),w=new DataView(c.buffer);w.setUint32(0,0x02014b50,true);w.setUint16(4,20,true);w.setUint16(6,20,true);w.setUint16(8,2048,true);w.setUint16(10,method,true);w.setUint16(12,f.time,true);w.setUint16(14,f.date,true);w.setUint32(16,crc,true);w.setUint32(20,data.length,true);w.setUint32(24,size,true);w.setUint16(28,nameBytes.length,true);w.setUint32(38,f.attrs,true);w.setUint32(42,offset,true);c.set(nameBytes,46);central.push(c);offset+=h.length+data.length;
 }
 const length=central.reduce((n,b)=>n+b.length,0),end=new Uint8Array(22),v=new DataView(end.buffer);v.setUint32(0,0x06054b50,true);v.setUint16(8,files.size,true);v.setUint16(10,files.size,true);v.setUint32(12,length,true);v.setUint32(16,offset,true);return new Blob([...locals,...central,end],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
}
const xmlEscape=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&apos;');
function patchCell(xml,address,value){
 const rowNum=Number(address.match(/\d+/)[0]);const re=new RegExp(`<c\\b[^>]*\\br="${address}"[^>]*?(?:\\/>|>[\\s\\S]*?<\\/c>)`);
 const old=xml.match(re)?.[0];const style=old?.match(/\bs="(\d+)"/)?.[1];const cell=`<c r="${address}"${style?` s="${style}"`:''} t="inlineStr"><is><t xml:space="preserve">${xmlEscape(value)}</t></is></c>`;
 if(old)return xml.replace(re,()=>cell);
 const rr=new RegExp(`(<row\\b[^>]*\\br="${rowNum}"[^>]*>)([\\s\\S]*?)(<\\/row>)`);if(!rr.test(xml))throw Error('No existe la fila '+rowNum+' en el maestro.');
 const col=s=>s.match(/^[A-Z]+/)[0].split('').reduce((n,c)=>n*26+c.charCodeAt(0)-64,0);
 return xml.replace(rr,(_,start,body,end)=>{const next=[...body.matchAll(/<c\b[^>]*\br="([A-Z]+\d+)"/g)].find(m=>col(m[1])>col(address));return start+(next?body.slice(0,next.index)+cell+body.slice(next.index):body+cell)+end;});
}
function parseXML(s){const d=new DOMParser().parseFromString(s,'application/xml');if(d.getElementsByTagName('parsererror').length)throw Error('XML inválido.');return d;}
async function readMaster(bytes){
 const files=await openZip(bytes),wb=parseXML(await unzipText(files,'xl/workbook.xml')),rels=parseXML(await unzipText(files,'xl/_rels/workbook.xml.rels'));
 const relationships=new Map([...rels.getElementsByTagName('Relationship')].map(n=>[n.getAttribute('Id'),n.getAttribute('Target')]));
 const strings=files.has('xl/sharedStrings.xml')?[...parseXML(await unzipText(files,'xl/sharedStrings.xml')).getElementsByTagName('si')].map(n=>[...n.getElementsByTagName('t')].map(t=>t.textContent).join('')):[];
 for(const sheet of wb.getElementsByTagName('sheet')){
  const target=relationships.get(sheet.getAttribute('r:id'));if(!target)continue;const path=target.startsWith('/')?target.slice(1):'xl/'+target.replace(/^\.\//,'');const xml=await unzipText(files,path),doc=parseXML(xml),rows=[];
  for(const row of doc.getElementsByTagName('row')){const obj={fila:Number(row.getAttribute('r')),_tipos:{}};for(const c of row.getElementsByTagName('c')){const col=c.getAttribute('r').replace(/\d/g,''),type=c.getAttribute('t'),v=c.getElementsByTagName('v')[0]?.textContent??'';obj._tipos[col]=type||'n';obj[col]=type==='s'?strings[Number(v)]:type==='inlineStr'?[...c.getElementsByTagName('t')].map(t=>t.textContent).join(''):v;}rows.push(obj);}
  const header=rows.find(r=>norm(r.D)==='SKU NUEVO'&&['DESCRIPCION','ARTICULO'].includes(norm(r.H)));if(header)return {files,path,xml,hoja:sheet.getAttribute('name'),rows:rows.filter(r=>r.fila>header.fila&&r.H?.trim())};
 }
 throw Error('Se requiere SKU NUEVO en D y DESCRIPCIÓN en H, como en el maestro proporcionado.');
}
