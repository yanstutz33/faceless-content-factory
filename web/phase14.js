async function loadConnections(){
  const root=document.querySelector('#connection-grid');
  root.setAttribute('aria-busy','true');
  try{
    const readiness=await api('/api/platforms');
    document.querySelector('#connection-badge').textContent=`${readiness.configured}/${readiness.total}`;
    root.innerHTML=readiness.platforms.map(platform=>{
      const configured=platform.connector_configured;
      return `<article class="connection-card ${configured?'configured':'waiting'}"><div class="connection-head"><div><span class="tag">${configured?'PRÉ-CONFIGURADA':'AGUARDANDO CONTA'}</span><h3>${esc(platform.label)}</h3></div><span class="connection-state">${configured?'✓':'○'}</span></div><p>${esc(platform.output)}</p><dl><div><dt>Pacote local</dt><dd>${platform.package_ready?'Pronto':'Em planejamento'}</dd></div><div><dt>Próxima etapa manual</dt><dd>${esc(platform.manual_step)}</dd></div></dl><button class="secondary" disabled>${configured?'Login necessário':'Configuração necessária'}</button></article>`;
    }).join('');
  }catch(error){
    root.innerHTML='<div class="publish-empty"><b>Não foi possível verificar as conexões.</b><p>O restante do Studio continua disponível.</p></div>';
    toast(error.message,'error');
  }finally{root.removeAttribute('aria-busy')}
}

document.querySelector('#refresh-connections').onclick=loadConnections;
loadConnections();
