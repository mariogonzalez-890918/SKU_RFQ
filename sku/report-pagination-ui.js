// El CSV conserva el detalle completo; la pantalla dibuja solo 200 partidas a la vez.
const rpRenderDetailRows=rpRenderDetails;let rpDetailRows=[],rpDetailPage=0,rpDetailCaption='';
function rpDrawDetailPage(){const pages=Math.max(1,Math.ceil(rpDetailRows.length/200));rpDetailPage=Math.min(rpDetailPage,pages-1);rpRenderDetailRows(rpDetailRows.slice(rpDetailPage*200,(rpDetailPage+1)*200),rpDetailCaption);$('rpDetallePagina').textContent='Página '+(rpDetailPage+1)+' de '+pages+' · '+rpDetailRows.length+' partidas';$('rpDetalleAnterior').disabled=rpDetailPage===0;$('rpDetalleSiguiente').disabled=rpDetailPage+1>=pages;}
rpRenderDetails=function(lines,label='Todas las partidas del reporte'){rpDetailRows=lines;rpDetailCaption=label;rpDetailPage=0;rpDrawDetailPage();};
$('rpDetalleAnterior').onclick=()=>{if(rpDetailPage>0){rpDetailPage--;rpDrawDetailPage();}};$('rpDetalleSiguiente').onclick=()=>{if((rpDetailPage+1)*200<rpDetailRows.length){rpDetailPage++;rpDrawDetailPage();}};
