registerJobDetailExtension(async({id,job,dialog,actions})=>{
  const gate=job.metadata?.quality_gate;
  if(!gate){
    if(['awaiting_approval','approved','rejected'].includes(job.status)){
      const block=document.createElement('div');block.className='verification warning';
      block.innerHTML='<span>! AUDITORIA PENDENTE</span><b>Este pacote foi criado por uma versão anterior.</b><small>Execute a conferência antes de aprovar, preparar ou reutilizar o vídeo.</small>';
      dialog.querySelector('.timeline')?.before(block);
      const button=document.createElement('button');button.className='primary';button.textContent='Executar auditoria';
      button.onclick=async()=>{
        button.disabled=true;
        try{await api(`/api/jobs/${encodeURIComponent(id)}/quality-audit`,{method:'POST',body:'{}',timeoutMs:120000});toast('Auditoria concluída.');dialog.close();await openJob(id);await load()}
        catch(error){toast(error.message,'error')}finally{button.disabled=false}
      };
      actions?.prepend(button);
    }
    return;
  }
  const checks=(gate.checks||[]).map(check=>`<span>${check.passed?'✓':'!'} ${esc(check.label)}</span>`).join('');
  const block=document.createElement('div');block.className=`verification ${gate.passed?'':'warning'}`;
  block.innerHTML=`<span>${gate.passed?'✓ CONTROLE AUTOMÁTICO APROVADO':'! PACOTE BLOQUEADO'}</span><b>${Number(gate.score||0)}/100 · câmera, imagem, movimento e áudio</b><small class="quality-checks">${checks}</small>`;
  dialog.querySelector('.timeline')?.before(block);
  const link=document.createElement('a');link.className='secondary';link.target='_blank';link.rel='noopener';
  link.href=`/api/jobs/${encodeURIComponent(id)}/artifacts/quality-gate.json`;link.textContent='Controle de qualidade';actions?.append(link);
});
