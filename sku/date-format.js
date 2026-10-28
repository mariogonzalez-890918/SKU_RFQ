// Fechas visibles sin cambiar ISO en almacenamiento o peticiones.
function gmpDate(value){return String(value??'').replace(/(?<![0-9])([0-9]{4})-([0-9]{2})-([0-9]{2})(?:T([0-9]{2}:[0-9]{2}(?::[0-9]{2})?)(?:[.][0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?(?![0-9])/g,(_,y,m,d,t)=>`${d}/${m}/${y}${t?' '+t:''}`);}
function gmpDateISO(value){const s=String(value??'').trim();if(!s)return '';let m=s.match(/^([0-9]{2})\/([0-9]{2})\/([0-9]{4})$/);if(!m)throw Error('Usa la fecha dd/mm/yyyy.');const iso=`${m[3]}-${m[2]}-${m[1]}`,d=new Date(iso+'T12:00:00Z');if(!Number.isFinite(d.getTime())||d.toISOString().slice(0,10)!==iso)throw Error('La fecha no es válida. Usa dd/mm/yyyy.');return iso;}
function gmpReadDate(id){return gmpDateISO(document.getElementById(id).value);}
function gmpTax(rate){return Number(rate)===8?'IEPS':Number(rate)===16?'IVA':'Sin IVA';}
