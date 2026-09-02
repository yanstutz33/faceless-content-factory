let publishingState={summary:{total:0,eligible:0,ready:0,blocked:0},items:[]};
let pilotCertification=null;
let phase2Certification=null;
let guidedReviewIds=[];
let guidedReviewCurrent=null;

function publishStatus(item){
  if(item.release_ready)return {label:'PACOTE COMPLETO',tone:'ready'};
  if(item.eligible)return {label:'PRONTO PARA PREPARAR',tone:'eligible'};
  return {label:'AÇÃO NECESSÁRIA',tone:'blocked'};
}

async function loadPublishing(){
  try{
    [publishingState,pilotCertification,phase2Certification]=await Promise.all([
      api('/api/publishing'),api('/api/publishing/pilot-certification'),api('/api/operations/phase2-certification')
    ]);
    const certificate=document.querySelector('#pilot-certification');
    const certificateChecks=(pilotCertification.checks||[]).map(check=>`<li class="${check.passed?'pass':'fail'}"><span>${check.passed?'✓':'!'}</span><div><b>${esc(check.label)}</b><small>${esc(check.detail)}</small></div></li>`).join('');
    certificate.className=`pilot-certification ${esc(pilotCertification.status||'blocked')}`;
    certificate.innerHTML=`<div class="pilot-certificate-head"><div><span class="tag">CERTIFICAÇÃO DO LOTE PILOTO</span><h3>${esc(pilotCertification.label)}</h3><p>${esc(pilotCertification.next_action)}</p></div><strong>${Number(pilotCertification.approved_count||0)}<small>/${Number(pilotCertification.target||10)} aprovados</small></strong></div><ul>${certificateChecks}</ul>`;
    const phase2=document.querySelector('#phase2-certification');
    const showPhase2=pilotCertification.status==='certified'||(phase2Certification.batches||[]).length>0;
    phase2.hidden=!showPhase2;
    if(showPhase2){
      const phase2Labels={certified:'Fase 2 certificada',in_progress:'Lote autônomo em andamento',ready:'Pronto para o próximo lote',blocked_by_pilot:'Aguardando o piloto'};
      phase2.className=`phase2-certification ${esc(phase2Certification.status||'ready')}`;
      phase2.innerHTML=`<div><span class="tag">AUTOMAÇÃO LOCAL · SEM PUBLICAÇÃO</span><h3>${esc(phase2Labels[phase2Certification.status]||'Certificação da Fase 2')}</h3><p>${esc(phase2Certification.next_action)}</p></div><strong>${Number(phase2Certification.consecutive_successful_batches||0)}<small>/${Number(phase2Certification.target||3)} lotes</small></strong>`;
    }
    const s=publishingState.summary||{};
    const reviewItems=publishingState.items.filter(item=>item.status==='awaiting_approval');
    const reviewButton=document.querySelector('#start-pilot-review');
    reviewButton.disabled=!reviewItems.length;
    reviewButton.textContent=reviewItems.length?`▶ Revisar ${reviewItems.length} piloto${reviewItems.length===1?'':'s'}`:'✓ Revisão concluída';
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
document.querySelector('#start-pilot-review').onclick=()=>{
  guidedReviewIds=publishingState.items.filter(item=>item.status==='awaiting_approval').map(item=>item.job_id);
  guidedReviewCurrent=guidedReviewIds[0]||null;
  if(!guidedReviewCurrent)return toast('Não há pilotos aguardando revisão.');
  openJob(guidedReviewCurrent);
};
window.guidedReviewAdvance=async id=>{
  if(!guidedReviewIds.includes(id))return;
  const index=guidedReviewIds.indexOf(id);
  guidedReviewIds=guidedReviewIds.filter(jobId=>jobId!==id);
  await loadPublishing();
  if(!guidedReviewIds.length){guidedReviewCurrent=null;return toast('Revisão guiada concluída.','success')}
  guidedReviewCurrent=guidedReviewIds[Math.min(index,guidedReviewIds.length-1)];
  await openJob(guidedReviewCurrent);
};
registerJobDetailExtension(({id,dialog})=>{
  const platform=dialog.querySelector('#metric-form select[name="platform"]');
  if(platform&&!platform.querySelector('[value="bilibili"]'))platform.insertAdjacentHTML('beforeend','<option value="pinterest">Pinterest</option><option value="bilibili">Bilibili</option>');
  if(!guidedReviewIds.includes(id))return;
  guidedReviewCurrent=id;
  const index=guidedReviewIds.indexOf(id);
  const bar=document.createElement('div');
  bar.className='guided-review-bar';
  bar.innerHTML=`<div><span class="tag">REVISÃO GUIADA · DECISÃO HUMANA</span><b>Piloto ${index+1} de ${guidedReviewIds.length}</b></div><div><button class="secondary" type="button" data-guided-step="-1" ${guidedReviewIds.length<2?'disabled':''}>← Anterior</button><button class="secondary" type="button" data-guided-step="1" ${guidedReviewIds.length<2?'disabled':''}>Próximo →</button></div>`;
  dialog.querySelector('.detail-hero')?.before(bar);
  bar.onclick=async event=>{
    const button=event.target.closest('[data-guided-step]');if(!button)return;
    const target=(index+Number(button.dataset.guidedStep)+guidedReviewIds.length)%guidedReviewIds.length;
    guidedReviewCurrent=guidedReviewIds[target];dialog.close();await openJob(guidedReviewCurrent);
  };
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
