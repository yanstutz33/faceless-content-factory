const qualityOpenJob=openJob;
openJob=async function(id){
  await qualityOpenJob(id);
  const job=await api(`/api/jobs/${encodeURIComponent(id)}`);
  const gate=job.metadata?.quality_gate;
  if(!gate){
    if(['awaiting_approval','approved','rejected'].includes(job.status)){
      const block=document.createElement('div');block.className='verification warning';
      block.innerHTML='<span>! AUDITORIA V0.9 PENDENTE</span><b>Este pacote foi criado por uma versão anterior.</b><small>Execute a conferência antes de aprovar, preparar ou reutilizar o vídeo.</small>';
      document.querySelector('#job-dialog .timeline')?.before(block);
      const button=document.createElement('button');button.className='primary';button.textContent='Executar auditoria';
      button.onclick=async()=>{button.disabled=true;try{await api(`/api/jobs/${encodeURIComponent(id)}/quality-audit`,{method:'POST',body:'{}'});toast('Auditoria concluída.');document.querySelector('#job-dialog').close();await openJob(id);load()}catch(error){toast(error.message)}finally{button.disabled=false}};
      document.querySelector('#job-dialog .detail-actions')?.prepend(button);
    }
    return;
  }
  const checks=(gate.checks||[]).map(check=>`<span>${check.passed?'✓':'!'} ${esc(check.label)}</span>`).join('');
  const block=document.createElement('div');
  block.className=`verification ${gate.passed?'':'warning'}`;
  block.innerHTML=`<span>${gate.passed?'✓ CONTROLE AUTOMÁTICO APROVADO':'! PACOTE BLOQUEADO'}</span><b>${Number(gate.score||0)}/100 · câmera, imagem, movimento e áudio</b><small class="quality-checks">${checks}</small>`;
  document.querySelector('#job-dialog .timeline')?.before(block);
  const actions=document.querySelector('#job-dialog .detail-actions');
  const link=document.createElement('a');link.className='secondary';link.target='_blank';
  link.href=`/api/jobs/${encodeURIComponent(id)}/artifacts/quality-gate.json`;link.textContent='Controle de qualidade';
  actions?.append(link);
};

