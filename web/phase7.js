registerJobDetailExtension(async({id,job,dialog,actions})=>{
  if(job.status==='approved'){
    const prepare=document.createElement('button');
    prepare.className='secondary';prepare.textContent='Preparar YouTube privado';
    prepare.onclick=async()=>{
      prepare.disabled=true;
      try{await api(`/api/jobs/${encodeURIComponent(id)}/youtube-package`,{method:'POST',body:'{}',timeoutMs:60000});toast('Pacote privado preparado. Nenhum upload foi feito.')}
      catch(error){toast(error.message,'error')}finally{prepare.disabled=false}
    };
    actions?.append(prepare);
  }
  const form=dialog.querySelector('#metric-form');
  if(!form)return;
  const button=form.querySelector('button');
  const fields=document.createElement('div');
  fields.className='metric-extended';
  fields.innerHTML=`<input name="impressions" type="number" min="0" placeholder="Impressões"><input name="clicks" type="number" min="0" placeholder="Cliques"><input name="average_view_seconds" type="number" min="0" placeholder="Média assistida (s)"><select name="thumbnail_variant" aria-label="Capa usada"><option value="${esc(job.thumbnail_variant||'a')}">Capa ${(job.thumbnail_variant||'a').toUpperCase()}</option><option value="${(job.thumbnail_variant||'a')==='a'?'b':'a'}">Capa ${(job.thumbnail_variant||'a')==='a'?'B':'A'}</option></select><input name="conversions" type="number" min="0" placeholder="Conversões"><input name="revenue" type="number" min="0" step="0.01" placeholder="Receita R$">`;
  button.before(fields);
});

saveMetrics=async function(event,id){
  event.preventDefault();
  const form=event.target;const submit=form.querySelector('button');const data=new FormData(form);
  const number=name=>Number(data.get(name)||0);
  submit.disabled=true;
  try{
    await api(`/api/jobs/${encodeURIComponent(id)}/metrics`,{method:'POST',body:JSON.stringify({
      platform:data.get('platform')||'youtube',views:number('views'),likes:number('likes'),watch_minutes:number('watch_minutes'),
      impressions:number('impressions'),clicks:number('clicks'),average_view_seconds:number('average_view_seconds'),
      thumbnail_variant:data.get('thumbnail_variant')||'a',conversions:number('conversions'),revenue:number('revenue')
    })});
    toast('Métricas, CTR e retenção registrados.');document.querySelector('#job-dialog').close();await load();await loadThumbnailInsights();
  }catch(error){toast(error.message,'error')}finally{submit.disabled=false}
};

async function loadThumbnailInsights(){
  try{
    const rows=await api('/api/thumbnail-insights');const winners=new Map();
    rows.forEach(row=>{if(!winners.has(row.series_id))winners.set(row.series_id,row)});
    document.querySelectorAll('.thumbnail-winner').forEach(item=>item.remove());
    for(const winner of winners.values()){
      const card=document.createElement('article');card.className='insight safe thumbnail-winner';
      card.innerHTML=`<h3>Capa ${esc(winner.thumbnail_variant.toUpperCase())} lidera ${esc(winner.series_id)}</h3><p>${esc(winner.ctr)}% de CTR em ${Number(winner.impressions).toLocaleString('pt-BR')} impressões. Use como referência, sem trocar capas automaticamente.</p>`;
      document.querySelector('#recommendations')?.append(card);
    }
  }catch(error){console.warn('Falha ao carregar insights de thumbnail',error)}
}
loadThumbnailInsights();
