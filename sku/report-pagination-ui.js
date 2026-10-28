// El CSV conserva el detalle completo; la pantalla dibuja solo 200 partidas a la vez.
const rpRenderDetailRows=rpRenderDetails;let rpDetailRows=[],rpDetailPage=0,rpDetailCaption='',rpDetailSelection=null;
function rpDrawDetailPage(){const pages=Math.max(1,Math.ceil(rpDetailRows.length/200));rpDetailPage=Math.min(rpDetailPage,pages-1);rpRenderDetailRows(rpDetailRows.slice(rpDetailPage*200,(rpDetailPage+1)*200),rpDetailCaption);$('rpDetallePagina').textContent='Página '+(rpDetailPage+1)+' de '+pages+' · '+rpDetailRows.length+' partidas';$('rpDetalleAnterior').disabled=rpDetailPage===0;$('rpDetalleSiguiente').disabled=rpDetailPage+1>=pages;}
rpRenderDetails=function(lines,label='Todas las partidas del reporte',selection=null){rpDetailSelection=selection;rpUpdateDetailTotal(lines);rpDetailRows=lines;rpDetailCaption=label;rpDetailPage=0;rpDrawDetailPage();};
$('rpDetalleAnterior').onclick=()=>{if(rpDetailPage>0){rpDetailPage--;rpDrawDetailPage();}};$('rpDetalleSiguiente').onclick=()=>{if((rpDetailPage+1)*200<rpDetailRows.length){rpDetailPage++;rpDrawDetailPage();}};

function rpUpdateDetailTotal(lines){
 const sum=key=>{let cents=0n;for(const line of lines){if(line[key]===null||line[key]===undefined)continue;const [whole,fraction='']=String(line[key]).split('.');cents+=BigInt(whole)*100n+BigInt(fraction.padEnd(2,'0').slice(0,2));}return (cents/100n).toString()+'.'+(cents%100n).toString().padStart(2,'0');};
 const pending=lines.filter(line=>line.pendiente).length;
 $('rpGranTotalEtiqueta').textContent=pending?'Total surtido parcial':'Total surtido';
 $('rpGranTotal').textContent=rpMoney(sum('total'));
 $('rpTotalDesglose').textContent=lines.length+' partidas · Total requisitado: '+rpMoney(sum('totalRequisitado'))+' · Costo surtido: '+rpMoney(sum('costoCompra'))+' · Impuestos: '+rpMoney(sum('importeImpuestos'))+(pending?' · '+pending+' partidas pendientes de costeo':'')+' · Incluye todas las páginas del detalle seleccionado.';
 $('rpDetalleExcel').disabled=!lines.length;
}
