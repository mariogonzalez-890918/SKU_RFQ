// getRandomValues funciona también por HTTP en IP local, Radmin y ZeroTier.
// La clave evita duplicar un guardado/cobro cuando se reintenta la misma solicitud.
function commercialKey(){
 const bytes=new Uint8Array(16);
 globalThis.crypto.getRandomValues(bytes);
 return Array.from(bytes,value=>value.toString(16).padStart(2,'0')).join('');
}
