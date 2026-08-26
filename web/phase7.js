const metricsOpenJob=openJob;
openJob=async function(id){
  await metricsOpenJob(id);
  const form=document.querySelector('#metric-form');
  const job=await api(`/api/jobs/${encodeURIComponent(id)}`);
  if(job.status==='approved'){
    const actions=document.querySelector('#job-dialog .detail-actions');
    const prepare=document.createElement('button');prepare.className='secondary';prepare.textContent='Preparar YouTube privado';
    prepare.onclick=async()=>{prepare.disabled=true;try{await api(`/api/jobs/${encodeURIComponent(id)}/youtube-package`,{method:'POST',body:'{}'});toast('Pacote privado preparado. Nenhum upload foi feito.')}catch(error){toast(error.message)}finally{prepare.disabled=false}};
    actions?.append(prepare);
  }
  if(!form)return;
  const button=form.querySelector('button');
  const fields=document.createElement('div');
  fields.className='metric-extended';
  fields.innerHTML=`<input name="impressions" type="number" min="0" placeholder="Impressões"><input name="clicks" type="number" min="0" placeholder="Cliques"><input name="average_view_seconds" type="number" min="0" placeholder="Média assistida (s)"><select name="thumbnail_variant" aria-label="Capa usada"><option value="${esc(job.thumbnail_variant||'a')}">Capa ${(job.thumbnail_variant||'a').toUpperCase()}</option><option value="${(job.thumbnail_variant||'a')==='a'?'b':'a'}">Capa ${(job.thumbnail_variant||'a')==='a'?'B':'A'}</option></select><input name="conversions" type="number" min="0" placeholder="Conversões"><input name="revenue" type="number" min="0" step="0.01" placeholder="Receita R$">`;
  button.before(fields);
};

saveMetrics=async function(event,id){
  event.preventDefault();
  const f=new FormData(event.target);
  const number=name=>Number(f.get(name)||0);
  try{
    await api(`/api/jobs/${id}/metrics`,{method:'POST',body:JSON.stringify({
      platform:f.get('platform')||'youtube',views:number('views'),likes:number('likes'),watch_minutes:number('watch_minutes'),
      impressions:number('impressions'),clicks:number('clicks'),average_view_seconds:number('average_view_seconds'),
      thumbnail_variant:f.get('thumbnail_variant')||'a',conversions:number('conversions'),revenue:number('revenue')
    })});
    toast('Métricas, CTR e retenção registrados.');document.querySelector('#job-dialog').close();load();loadThumbnailInsights();
  }catch(error){toast(error.message)}
};

async function loadThumbnailInsights(){
  try{
    const rows=await api('/api/thumbnail-insights');
    const winners=new Map();
    rows.forEach(row=>{if(!winners.has(row.series_id))winners.set(row.series_id,row)});
    document.querySelectorAll('.thumbnail-winner').forEach(item=>item.remove());
    for(const winner of winners.values()){
      const card=document.createElement('article');card.className='insight safe thumbnail-winner';
      card.innerHTML=`<h3>Capa ${esc(winner.thumbnail_variant.toUpperCase())} lidera ${esc(winner.series_id)}</h3><p>${esc(winner.ctr)}% de CTR em ${Number(winner.impressions).toLocaleString('pt-BR')} impressões. Use como referência, sem trocar capas automaticamente.</p>`;
      document.querySelector('#recommendations')?.append(card);
    }
  }catch(error){}
}
loadThumbnailInsights();
