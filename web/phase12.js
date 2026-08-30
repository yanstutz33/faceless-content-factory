let publishingState={summary:{total:0,eligible:0,ready:0,blocked:0},items:[]};

function publishStatus(item){
  if(item.release_ready)return {label:'PACOTE COMPLETO',tone:'ready'};
  if(item.eligible)return {label:'PRONTO PARA PREPARAR',tone:'eligible'};
  return {label:'AÇÃO NECESSÁRIA',tone:'blocked'};
}

async function loadPublishing(){
  try{
    publishingState=await api('/api/publishing');
    const s=publishingState.summary||{};
    document.querySelector('#publish-badge').textContent=String(s.eligible||0);
    document.querySelector('#publish-summary').innerHTML=[
      ['Na central',s.total||0,'Vídeos aprovados ou em revisão'],
      ['Liberados',s.eligible||0,'Direitos e qualidade conferidos'],
      ['Completos',s.ready||0,'YouTube, verticais e Bilibili preparados'],
      ['Pendências',s.blocked||0,'Precisam de aprovação ou auditoria']
    ].map(([label,value,detail])=>`<article><small>${esc(label)}</small><b>${Number(value).toLocaleString('pt-BR')}</b><span>${esc(detail)}</span></article>`).join('');
    const root=document.querySelector('#publish-list');
    root.innerHTML=publishingState.items.length?publishingState.items.map(item=>{
      const status=publishStatus(item);
      const checks=(item.checks||[]).map(check=>`<li class="${check.passed?'pass':'fail'}"><span>${check.passed?'✓':'!'}</span><div><b>${esc(check.label)}</b><small>${esc(check.detail)}</small></div></li>`).join('');
      const passedChecks=(item.checks||[]).filter(check=>check.passed).length;
      const packages=`<span class="package-pill ${item.packages.youtube_private?'done':''}">YouTube privado</span><span class="package-pill ${item.packages.vertical_manual?'done':''}">Shorts · Reels · TikTok</span><span class="package-pill ${item.packages.bilibili_manual?'done':''}">Bilibili 中文 · EN</span>`;
      const action=item.release_ready
        ?`<a class="secondary" target="_blank" rel="noopener" href="/api/jobs/${encodeURIComponent(item.job_id)}/artifacts/release-manifest.json">Abrir manifesto</a>`
        :item.eligible
          ?`<button class="primary" data-release-job="${esc(item.job_id)}">Preparar pacote completo</button>`
          :`<button class="secondary" data-review-job="${esc(item.job_id)}">Abrir para revisar</button>`;
      return `<article class="publish-item ${status.tone}"><img src="${artifactUrl(item.job_id,'thumbnail.jpg',item.updated_at)}" alt="Capa de ${esc(item.topic)}" loading="lazy"><div class="publish-main"><div class="publish-title"><span class="tag">${status.label}</span><h3>${esc(item.title)}</h3><p>${esc(item.topic)} · ${formatDuration(item.duration)}</p></div><div class="package-row">${packages}</div><details class="publish-audit"><summary>Verificação técnica · ${passedChecks}/${(item.checks||[]).length} itens</summary><ul class="publish-checks">${checks}</ul></details></div><div class="publish-action">${action}<small>Envio sempre manual</small></div></article>`;
    }).join(''):'<div class="publish-empty"><b>Nenhum vídeo longo está pronto para publicação.</b><p>Prévias e testes abaixo de 30 minutos ficam fora desta central automaticamente.</p></div>';
  }catch(error){toast(error.message)}
}

document.querySelector('#refresh-publishing').onclick=loadPublishing;
registerJobDetailExtension(({dialog})=>{
  const platform=dialog.querySelector('#metric-form select[name="platform"]');
  if(!platform||platform.querySelector('[value="bilibili"]'))return;
  platform.insertAdjacentHTML('beforeend','<option value="pinterest">Pinterest</option><option value="bilibili">Bilibili</option>');
});
document.querySelector('#publish-list').addEventListener('click',async event=>{
  const release=event.target.closest('[data-release-job]');
  if(release){
    release.disabled=true;release.textContent='Preparando formatos…';
    try{
      await api(`/api/jobs/${encodeURIComponent(release.dataset.releaseJob)}/release-package`,{method:'POST',body:JSON.stringify({vertical_duration:30})});
      toast('Pacote completo preparado. Nenhum upload foi realizado.');await loadPublishing();
    }catch(error){toast(error.message);release.disabled=false;release.textContent='Tentar novamente'}
    return;
  }
  const review=event.target.closest('[data-review-job]');
  if(review)openJob(review.dataset.reviewJob);
});

loadPublishing();
