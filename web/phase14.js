let integrationState={platforms:[],backups:[],audit:[],deliveries:[]};

const integrationLabels={config_required:'CONFIGURAÇÃO NECESSÁRIA',login_required:'PRONTA PARA LOGIN',connected:'CONTA CONECTADA',planned:'NO ROADMAP'};
const deliveryLabels={blocked_auth:'Aguardando conta',blocked_package:'Aguardando pacote',manual_approval:'Aguardando sua confirmação'};

function renderIntegrationLists(){
  const deliveries=document.querySelector('#delivery-list');
  deliveries.innerHTML=integrationState.deliveries.length?integrationState.deliveries.slice(0,8).map(item=>`<div class="integration-row"><span>${esc(item.platform.toUpperCase())}</span><div><b>${esc(deliveryLabels[item.status]||item.status)}</b><small>${esc(item.job_id==='unselected'?'Nenhum pacote selecionado':item.job_id)}</small></div></div>`).join(''):'<div class="integration-empty">Execute um pré-teste para criar a primeira entrega segura.</div>';
  const audit=document.querySelector('#integration-audit');
  audit.innerHTML=integrationState.audit.length?integrationState.audit.slice(0,8).map(item=>`<div class="integration-row"><span>${esc(item.platform.toUpperCase())}</span><div><b>${esc(item.event.replaceAll('_',' '))}</b><small>${new Date(item.created_at).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'})}</small></div></div>`).join(''):'<div class="integration-empty">As verificações aparecerão aqui sem tokens ou segredos.</div>';
}

function renderConnections(readiness){
  document.querySelector('#connection-badge').textContent=`${readiness.connected}/${readiness.total}`;
  document.querySelector('#vault-status').textContent=readiness.vault.available?`${readiness.vault.provider} ativo`:'Cofre indisponível';
  document.querySelector('#backup-status').textContent=integrationState.backups.length?`${integrationState.backups.length} backup(s) íntegro(s) retido(s)`:'O backup diário será criado automaticamente';
  document.querySelector('#connection-grid').innerHTML=readiness.platforms.map(platform=>{
    const planned=platform.state==='planned';
    const connected=platform.authenticated;const configured=platform.connector_configured;
    const authAction=planned
      ?'<button class="secondary" disabled>Disponível em fase futura</button>'
      :connected
      ?`<button class="secondary" data-disconnect="${esc(platform.id)}">Desconectar conta</button>`
      :platform.oauth_supported
        ?`<button class="secondary" data-oauth="${esc(platform.id)}" ${configured?'':'disabled'}>${configured?'Abrir login oficial':'Configuração necessária'}</button>`
        :'<button class="secondary" disabled>Vinculação manual da conta</button>';
    return `<article class="connection-card ${planned?'planned':connected?'connected':configured?'configured':'waiting'}"><div class="connection-head"><div><span class="tag">${integrationLabels[platform.state]}</span><h3>${esc(platform.label)}</h3></div><span class="connection-state">${planned?'◷':connected?'✓':configured?'◇':'○'}</span></div><p>${esc(platform.output)}</p><dl><div><dt>Código</dt><dd>${platform.code_ready?'Pronto e testável':'Planejado'}</dd></div><div><dt>Pacote local</dt><dd>${platform.package_ready?'Pronto':'Em planejamento'}</dd></div><div><dt>Próxima etapa</dt><dd>${esc(platform.manual_step)}</dd></div></dl><div class="connection-actions"><button class="primary" data-preflight="${esc(platform.id)}" ${planned?'disabled':''}>${planned?'Ainda não iniciado':'Executar pré-teste'}</button>${authAction}</div><div class="preflight-result" data-result="${esc(platform.id)}"></div></article>`;
  }).join('');
  renderIntegrationLists();
}

async function loadConnections(){
  const root=document.querySelector('#connection-grid');root.setAttribute('aria-busy','true');
  try{
    const [readiness,backups,audit,deliveries]=await Promise.all([api('/api/platforms'),api('/api/system/backups'),api('/api/integrations/audit'),api('/api/integrations/deliveries')]);
    integrationState={platforms:readiness.platforms,backups,audit,deliveries};renderConnections(readiness);
  }catch(error){root.innerHTML='<div class="publish-empty"><b>Não foi possível verificar as conexões.</b><p>O restante do Studio continua disponível.</p></div>';toast(error.message,'error')}
  finally{root.removeAttribute('aria-busy')}
}

document.querySelector('#refresh-connections').onclick=loadConnections;
document.querySelector('#create-backup').onclick=async event=>{const button=event.currentTarget;button.disabled=true;try{const result=await api('/api/system/backup',{method:'POST',body:'{}'});toast(`Backup íntegro criado: ${result.file}`,'success');await loadConnections()}catch(error){toast(error.message,'error')}finally{button.disabled=false}};
document.querySelector('#connection-grid').addEventListener('click',async event=>{
  const preflight=event.target.closest('[data-preflight]');
  if(preflight){const platform=preflight.dataset.preflight;preflight.disabled=true;try{const result=await api(`/api/integrations/${encodeURIComponent(platform)}/preflight`,{method:'POST',body:'{}'});await loadConnections();const target=document.querySelector(`[data-result="${platform}"]`);target.innerHTML=`<b>${result.ready_after_manual_approval?'✓ Pronto após sua confirmação':'Pré-teste concluído'}</b><small>${result.blockers.map(esc).join(' · ')}</small>`;toast('Pré-teste concluído sem contatar a plataforma.','success')}catch(error){toast(error.message,'error')}finally{preflight.disabled=false}return}
  const oauth=event.target.closest('[data-oauth]');
  if(oauth){oauth.disabled=true;try{const result=await api(`/api/integrations/${encodeURIComponent(oauth.dataset.oauth)}/oauth-start`,{method:'POST',body:'{}'});location.assign(result.authorization_url)}catch(error){toast(error.message,'error');oauth.disabled=false}return}
  const disconnect=event.target.closest('[data-disconnect]');
  if(disconnect){disconnect.disabled=true;try{await api(`/api/integrations/${encodeURIComponent(disconnect.dataset.disconnect)}/disconnect`,{method:'POST',body:'{}'});toast('Conta removida do cofre local.','success');await loadConnections()}catch(error){toast(error.message,'error');disconnect.disabled=false}}
});

loadConnections();
