const state={jobs:[],summary:{},recommendations:[],profiles:{},operation:{},filter:'all'};
const $=selector=>document.querySelector(selector);
const esc=value=>{const node=document.createElement('div');node.textContent=value??'';return node.innerHTML};
const jobDetailExtensions=[];
const apiCache=new Map();
let toastTimer=0;
let loadSequence=0;
const statusLabels={queued:'Na fila',planning:'Planejamento',assets:'Assets',rendering:'Renderizando',reviewing:'Revisão dos agentes',awaiting_approval:'Sua revisão',approved:'Aprovado',rejected:'Ajustes pedidos',failed:'Falhou'};
const activeStatuses=new Set(['queued','planning','assets','rendering','reviewing']);
const toast=(message,tone='info')=>{const el=$('#toast');clearTimeout(toastTimer);el.textContent=message;el.dataset.tone=tone;el.classList.add('show');toastTimer=setTimeout(()=>el.classList.remove('show'),3200)};
const registerJobDetailExtension=extension=>{if(typeof extension==='function')jobDetailExtensions.push(extension)};
const hasRenderedArtifacts=job=>Boolean(job.metadata?.files?.video&&job.metadata?.files?.thumbnail);
const friendlyError=error=>{
  const message=String(error||'');
  if(message.includes('decodificar'))return 'O arquivo de vídeo ficou corrompido e foi bloqueado antes da publicação. Execute novamente para gerar uma cópia íntegra.';
  if(message.includes('FFmpeg falhou'))return 'A renderização foi interrompida. O trabalho pode ser executado novamente com segurança.';
  if(message.includes('Controle de qualidade'))return 'O controle de qualidade encontrou um problema. Revise os detalhes e execute novamente.';
  if(message.includes('acionamento involuntário'))return 'Esta produção foi interrompida durante uma auditoria e não gerou arquivos.';
  return message.split('\n')[0].slice(0,280)||'A produção não foi concluída.';
};
const errorPanel=error=>error?`<div class="agent-output error-summary"><h4>ATENÇÃO</h4><p>${esc(friendlyError(error))}</p><details><summary>Ver detalhes técnicos</summary><pre>${esc(error)}</pre></details></div>`:'';
const api=async(url,options={})=>{
  const {timeoutMs=30000,...fetchOptions}=options;
  const method=String(fetchOptions.method||'GET').toUpperCase();
  const cached=method==='GET'?apiCache.get(url):null;
  if(cached&&Date.now()-cached.at<1000)return cached.data;
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  const headers=new Headers(fetchOptions.headers||{});
  if(fetchOptions.body!=null&&!headers.has('Content-Type'))headers.set('Content-Type','application/json');
  try{
    const response=await fetch(url,{...fetchOptions,headers,signal:controller.signal});
    const text=await response.text();
    let data={};
    if(text){
      try{data=JSON.parse(text)}catch{throw new Error(response.ok?'O servidor retornou uma resposta inválida. Atualize o Studio.':'O serviço está temporariamente indisponível.')}
    }
    if(!response.ok){
      const error=new Error(data.error||'Não foi possível concluir a operação.');
      error.code=data.code||`HTTP_${response.status}`;error.requestId=data.request_id||response.headers.get('X-Request-ID');throw error;
    }
    if(method==='GET')apiCache.set(url,{at:Date.now(),data});else apiCache.clear();
    return data;
  }catch(error){
    if(error.name==='AbortError')throw new Error('A operação demorou mais que o esperado. Ela pode continuar em segundo plano; atualize em instantes.');
    throw error;
  }finally{clearTimeout(timer)}
};
const formatDuration=s=>s>=3600?`${Math.floor(s/3600)}h ${Math.round(s%3600/60)}min`:s>=60?`${Math.round(s/60)} min`:`${s}s`;

function renderStats(){const s=state.summary;const cards=[['◫','Produções',s.total??0,'histórico local'],['◌','Em andamento',s.in_progress??0,'fila automática'],['◆','Para revisar',s.awaiting_approval??0,'decisão humana'],['✦','Qualidade média',s.average_quality?`${s.average_quality}/100`:'—','score dos agentes']];$('#stats').innerHTML=cards.map(c=>`<article class="stat"><div class="stat-top"><span>${c[1]}</span><span class="stat-icon">${c[0]}</span></div><strong>${c[2]}</strong><small>${c[3]}</small></article>`).join('');$('#queue-badge').textContent=(s.in_progress??0)+(s.awaiting_approval??0)}

function renderOperation(){const op=state.operation||{};const queue=op.queue||{};const ready=!!op.ok;$('#operation-title').textContent=ready?'Estúdio operacional':'Atenção necessária';$('#operation-status').textContent=ready?`${queue.active?.length||0} renderizando · ${op.free_gb??'—'} GB livres`:'Abra o diagnóstico para corrigir';$('#operation-pulse').classList.toggle('warning',!ready);$('#health-shield').textContent=ready?'✓':'!';$('#health-title').textContent=ready?'Renderização verificada e publicação protegida.':'O estúdio encontrou uma dependência indisponível.';$('#health-detail').textContent=ready?`Validação de mídia: ${op.validation_engine||'ativa'} · ${op.free_gb??'—'} GB livres · envio automático desativado.`:'Confira o FFmpeg e o espaço disponível antes de gerar novos pacotes.'}

function renderJobs(){
  let jobs=state.jobs;
  if(state.filter==='active')jobs=jobs.filter(job=>activeStatuses.has(job.status));
  if(state.filter==='review')jobs=jobs.filter(job=>['awaiting_approval','rejected','failed'].includes(job.status));
  const root=$('#jobs');
  if(!jobs.length){root.innerHTML='<div class="empty">Nenhuma produção neste filtro.</div>';return}
  root.innerHTML=jobs.map(job=>{
    const artwork=`/api/jobs/${encodeURIComponent(job.id)}/artifacts/thumbnail.jpg`;
    const thumbnail=hasRenderedArtifacts(job)?`<img class="thumb" src="${artwork}" alt="Capa de ${esc(job.topic)}" loading="lazy">`:'<div class="thumb thumb-placeholder" aria-hidden="true"></div>';
    return `<article class="production" data-job="${esc(job.id)}" tabindex="0">${thumbnail}<div><h3>${esc(job.topic)}</h3><div class="meta">${esc((state.profiles[job.profile]||{}).label||job.profile)} · ${formatDuration(job.duration)}</div></div><div class="stage">${esc(statusLabels[job.status]||job.status)}<div class="progress"><span style="width:${job.progress||0}%"></span></div></div><span class="status ${esc(job.status)}">${esc(statusLabels[job.status]||job.status)}</span><div class="score">${job.quality_score?`<b>${job.quality_score}</b>/100`:'—'}</div><button class="more" type="button" aria-label="Abrir detalhes">›</button></article>`;
  }).join('');
}

function renderAgents(agents){$('#agent-grid').innerHTML=agents.map((a,i)=>`<article class="agent" style="--agent:${a.color}"><div class="agent-icon">${['⌁','⌖','✎','◈','↗','✓','✦'][i]||'✦'}</div><h3>${esc(a.name)}</h3><p>${esc(a.role)}</p><small>ENTREGA · ${esc(a.output)}</small></article>`).join('')}
function renderRecommendations(){const recs=state.recommendations;$('#recommendations').innerHTML=recs.map(r=>`<article class="insight ${esc(r.tone)}"><h3>${esc(r.title)}</h3><p>${esc(r.body)}</p></article>`).join('');const first=recs[0];if(first){$('#next-title').textContent=first.title;$('#next-body').textContent=first.body}}
function renderProfiles(){const root=$('#profiles');root.innerHTML=Object.entries(state.profiles).map(([id,p],i)=>`<label class="profile-option"><input type="radio" name="profile" value="${id}" ${i===0?'checked':''}><span class="profile-card"><b>${esc(p.label)}</b><small>${p.width}×${p.height} · ${formatDuration(p.min_duration)} a ${formatDuration(p.max_duration)}</small></span></label>`).join('');root.querySelectorAll('input').forEach(input=>input.addEventListener('change',()=>{const profile=state.profiles[input.value];const duration=$('#generate-form [name=duration]');duration.min=profile.min_duration;duration.max=profile.max_duration;duration.value=profile.default_duration}))}

async function load(){const sequence=++loadSequence;$('#last-sync').setAttribute('aria-busy','true');try{const [dashboard,profiles]=await Promise.all([api('/api/dashboard'),Object.keys(state.profiles).length?Promise.resolve(state.profiles):api('/api/profiles')]);if(sequence!==loadSequence)return;state.jobs=dashboard.jobs;state.summary=dashboard.summary;state.recommendations=dashboard.recommendations;state.operation=dashboard.operation||{};state.profiles=profiles;renderStats();renderJobs();renderRecommendations();renderOperation();if(!$('#profiles').children.length)renderProfiles();$('#last-sync').textContent=`Atualizado às ${new Date().toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}`}catch(error){if(sequence===loadSequence){$('#last-sync').textContent='Falha ao sincronizar';toast(error.message,'error')}}finally{if(sequence===loadSequence)$('#last-sync').removeAttribute('aria-busy')}}

async function openJob(id){
  try{
    const job=await api(`/api/jobs/${encodeURIComponent(id)}`);
    const metadata=job.metadata||{};
    const agents=metadata.agents||{};
    const verificationData=metadata.verification||{};
    const ready=hasRenderedArtifacts(job)&&['awaiting_approval','approved','rejected'].includes(job.status);
    const video=ready?`<video class="preview" controls preload="metadata" poster="/api/jobs/${encodeURIComponent(job.id)}/artifacts/thumbnail.jpg"><source src="/api/jobs/${encodeURIComponent(job.id)}/artifacts/video.mp4" type="video/mp4"></video>`:'<div class="preview preview-placeholder"><span>Prévia indisponível</span></div>';
    const warnings=(metadata.quality?.warnings||[]).map(warning=>`<li>${esc(warning)}</li>`).join('');
    const events=job.events||[];
    const steps=['planning','assets','rendering','reviewing','awaiting_approval'];
    const done=Math.ceil((job.progress||0)/20);
    let actions='';
    if(job.status==='awaiting_approval')actions='<button class="primary" type="button" data-action="approve">Aprovar para envio manual</button><button class="secondary danger" type="button" data-action="reject">Pedir ajustes</button>';
    if(['failed','rejected'].includes(job.status))actions='<button class="primary" type="button" data-action="retry">Executar novamente</button>';
    const metrics=job.status==='approved'?`<form class="metric-form" id="metric-form"><h4>MÉTRICAS REAIS · ATIVAM O APRENDIZADO</h4><label>Plataforma<select name="platform"><option value="youtube">YouTube</option><option value="shorts">Shorts</option><option value="tiktok">TikTok</option><option value="reels">Reels</option><option value="shopee">Shopee</option><option value="bilibili">Bilibili</option><option value="pinterest">Pinterest</option></select></label><label>Visualizações<input name="views" type="number" min="0" value="0"></label><label>Curtidas<input name="likes" type="number" min="0" value="0"></label><label>Minutos assistidos<input name="watch_minutes" type="number" min="0" step="0.1" value="0"></label><label>Impressões<input name="impressions" type="number" min="0" value="0"></label><label>Cliques<input name="clicks" type="number" min="0" value="0"></label><label>Média assistida (s)<input name="average_view_seconds" type="number" min="0" step="0.1" value="0"></label><label>Thumbnail<select name="thumbnail_variant"><option value="a">A</option><option value="b">B</option></select></label><label>Conversões<input name="conversions" type="number" min="0" value="0"></label><label>Receita (R$)<input name="revenue" type="number" min="0" step="0.01" value="0"></label><button class="secondary" type="submit">Registrar snapshot</button></form>`:'';
    const verification=verificationData.passed&&ready?`<div class="verification"><span>✓ ARQUIVO VALIDADO</span><b>${verificationData.video?.width||'—'}×${verificationData.video?.height||'—'} · ${verificationData.video?.codec||'vídeo'} + ${verificationData.audio?.codec||'áudio'}</b><small>${formatDuration(Math.round(verificationData.duration_seconds||job.duration))} · ${(Number(verificationData.size_bytes||0)/1048576).toFixed(1)} MB · checksum SHA-256</small></div>`:'';
    const artifactLinks=ready?`<button class="secondary" type="button" data-artifact="metadata.json" data-artifact-job="${esc(job.id)}">Resumo do vídeo</button><button class="secondary" type="button" data-artifact="render-report.json" data-artifact-job="${esc(job.id)}">Relatório técnico</button><button class="secondary" type="button" data-artifact="artifact-manifest.json" data-artifact-job="${esc(job.id)}">Integridade dos arquivos</button>`:'';
    $('#job-detail').innerHTML=`<div class="dialog-head"><div><p class="kicker">${esc(statusLabels[job.status]||job.status)}</p><h2>${esc(job.topic)}</h2></div><button class="icon-button" type="button" data-close aria-label="Fechar">×</button></div><div class="detail-hero">${video}<div class="detail-title"><span class="tag">${esc((state.profiles[job.profile]||{}).label||job.profile)} · ${formatDuration(job.duration)}</span><h2>${esc(metadata.title||'Planejamento em andamento')}</h2><p>${esc(metadata.description||friendlyError(job.error)||'Os agentes estão preparando este pacote.')}</p>${job.quality_score?`<div class="score"><b>${job.quality_score}</b>/100 · qualidade estimada</div>`:''}</div></div>${verification}<div class="timeline">${steps.map((_,index)=>`<span class="${index<done?'done':''}"></span>`).join('')}</div>${agents.strategy?`<div class="agent-output"><h4>NORTE · ESTRATÉGIA</h4><p>${esc(agents.strategy.promise)}</p><p><b>Objetivo:</b> ${esc(agents.strategy.primary_goal)} · <b>Ritmo:</b> ${esc(agents.strategy.cadence)}</p></div>`:''}${agents.visual?`<div class="agent-output"><h4>DIREÇÃO · VISUAL E SOM</h4><p>${esc(agents.visual.asset_brief)}</p><p>${esc(agents.visual.sound)}</p></div>`:''}${warnings?`<div class="agent-output"><h4>CRÍTICA · RECOMENDAÇÕES</h4><ul>${warnings}</ul></div>`:''}${errorPanel(job.error)}<div class="detail-actions">${actions}${artifactLinks}</div>${metrics}<div class="agent-output"><h4>HISTÓRICO · ${events.length} EVENTOS</h4><p>${events.slice(-5).reverse().map(event=>`${esc(friendlyError(event.message))} · ${new Date(event.created_at).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'})}`).join('<br>')}</p></div>`;
    const dialog=$('#job-dialog');
    dialog.showModal();
    dialog.querySelector('[data-close]').onclick=()=>dialog.close();
    dialog.querySelector('[data-action="approve"]')?.addEventListener('click',()=>jobAction(id,'approve'));
    dialog.querySelector('[data-action="reject"]')?.addEventListener('click',()=>jobAction(id,'reject'));
    dialog.querySelector('[data-action="retry"]')?.addEventListener('click',()=>jobAction(id,'retry'));
    dialog.querySelector('#metric-form')?.addEventListener('submit',event=>saveMetrics(event,id));
  }catch(error){toast(error.message,'error')}
}

function requestRevisionReason(){
  return new Promise(resolve=>{
    const dialog=$('#revision-dialog');const form=$('#revision-form');const reason=form.elements.reason;
    reason.value='Revisar direção visual e primeiros 30 segundos.';
    const finish=value=>{dialog.removeEventListener('close',cancel);form.removeEventListener('submit',submit);resolve(value)};
    const cancel=()=>finish(null);
    const submit=event=>{event.preventDefault();const value=reason.value.trim();if(!value)return;dialog.close();finish(value)};
    dialog.querySelectorAll('[data-revision-close]').forEach(button=>button.onclick=()=>dialog.close());
    dialog.addEventListener('close',cancel,{once:true});form.addEventListener('submit',submit);dialog.showModal();reason.focus();reason.select();
  });
}

async function jobAction(id,action){let body={};if(action==='reject'){const reason=await requestRevisionReason();if(reason===null)return;body={reason}}try{await api(`/api/jobs/${encodeURIComponent(id)}/${action}`,{method:'POST',body:JSON.stringify(body)});$('#job-dialog').close();toast(action==='approve'?'Pacote aprovado para envio manual.':'Produção atualizada.','success');load()}catch(error){toast(error.message,'error')}}
async function saveMetrics(event,id){event.preventDefault();const f=new FormData(event.target);try{await api(`/api/jobs/${id}/metrics`,{method:'POST',body:JSON.stringify({platform:f.get('platform')||'youtube',views:Number(f.get('views')||0),likes:Number(f.get('likes')||0),watch_minutes:Number(f.get('watch_minutes')||0),impressions:Number(f.get('impressions')||0),clicks:Number(f.get('clicks')||0),average_view_seconds:Number(f.get('average_view_seconds')||0),thumbnail_variant:f.get('thumbnail_variant')||'a',conversions:Number(f.get('conversions')||0),revenue:Number(f.get('revenue')||0)})});toast('Snapshot registrado; o aprendizado criativo foi atualizado.','success');$('#job-dialog').close();load()}catch(error){toast(error.message,'error')}}

$('#new-production').onclick=()=>$('#create-dialog').showModal();$('#next-action').onclick=()=>location.hash='production';
$('#suggest-idea').onclick=async()=>{try{const ideas=await api('/api/ideas');const idea=ideas[Math.floor(Math.random()*ideas.length)];$('#generate-form [name=topic]').value=idea.topic;toast(`${idea.intent} · ${idea.why}`)}catch(error){toast(error.message)}};
$('#generate-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=event.currentTarget;
  const fields=new FormData(form);
  const button=$('#submit-production');
  const sourceAsset=String(fields.get('source_asset')||'').trim();
  if(sourceAsset&&!fields.get('source_asset_rights_confirmed')){
    $('#form-error').textContent='Confirme os direitos comerciais da imagem avulsa antes de iniciar.';
    return;
  }
  button.disabled=true;
  button.textContent='Adicionando à fila…';
  $('#form-error').textContent='';
  try{
    await api('/api/jobs',{method:'POST',body:JSON.stringify({
      topic:fields.get('topic'),duration:Number(fields.get('duration')),profile:fields.get('profile'),
      team_id:fields.get('team_id'),priority:Number(fields.get('priority')),
      subtitles:!!fields.get('subtitles'),narration:!!fields.get('narration'),source_asset:sourceAsset,
      source_asset_rights_confirmed:!!fields.get('source_asset_rights_confirmed'),
      asset_ids:fields.getAll('asset_ids').map(Number),
      music_asset_id:fields.get('music_asset_id')||null,
    })});
    $('#create-dialog').close();
    toast('Produção iniciada. Você pode continuar trabalhando.');
    location.hash='production';
    await load();
  }catch(error){$('#form-error').textContent=error.message}
  finally{button.disabled=false;button.innerHTML='Iniciar produção <span>→</span>'}
});
$('#jobs').addEventListener('click',event=>{const row=event.target.closest('[data-job]');if(row)openJob(row.dataset.job)});$('#jobs').addEventListener('keydown',event=>{if(event.key==='Enter'){const row=event.target.closest('[data-job]');if(row)openJob(row.dataset.job)}});
$('#filters').addEventListener('click',event=>{const button=event.target.closest('[data-filter]');if(!button)return;state.filter=button.dataset.filter;document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x===button));renderJobs()});
document.querySelectorAll('.nav-item').forEach(item=>item.onclick=()=>{document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('active'));item.classList.add('active')});
document.addEventListener('click',event=>{
  const closeButton=event.target.closest('[data-dialog-close]');
  if(closeButton)closeButton.closest('dialog')?.close();
});
document.addEventListener('submit',event=>{
  if(event.submitter?.value!=='cancel')return;
  event.preventDefault();
  event.stopImmediatePropagation();
  event.target.closest('dialog')?.close();
},true);

async function loadAssets(){
  const assets=await api('/api/assets');
  const grid=$('#asset-grid');
  const select=$('#production-assets');
  grid.innerHTML=assets.length?assets.map(asset=>`<article class="asset-card image-card">${asset.available?`<img class="asset-cover-preview" src="/api/assets/${Number(asset.id)}/preview" alt="Prévia de ${esc(asset.name)}" loading="lazy">`:'<div class="asset-cover-preview asset-unavailable">Imagem indisponível</div>'}<div class="asset-body"><span class="tag">${String(asset.notes||'').includes('nocturnal_rain_v1')?'PADRÃO OFICIAL':esc(asset.license_type)}</span><h3>${esc(asset.name)}</h3><p>${esc(String(asset.path).split(/[\\/]/).pop())}</p><small>${asset.available?(asset.approved?'✓ Direitos confirmados':'Bloqueado'):'! Arquivo precisa ser localizado'}</small></div></article>`).join(''):'<div class="empty">Nenhum asset registrado. Adicione imagens próprias ou licenciadas para ampliar as cenas.</div>';
  select.innerHTML=assets.filter(asset=>asset.approved&&asset.available&&!String(asset.notes||'').includes('nocturnal_rain_v1')).map(asset=>`<option value="${Number(asset.id)}">${esc(asset.name)} · ${esc(asset.license_type)}</option>`).join('');
}

async function loadMusicAssets(){
  const tracks=await api('/api/music-assets');
  const activeTracks=tracks.filter(track=>track.approved);const archivedTracks=tracks.filter(track=>!track.approved);
  const grid=$('#music-grid');const select=$('#production-music');
  const reviewedCount=activeTracks.filter(track=>track.human_review==='approved').length;
  $('#music-library-summary').textContent=activeTracks.length?`${activeTracks.length} ativas · ${reviewedCount} ouvidas · ${archivedTracks.length} arquivadas`:'Nenhuma faixa ativa';
  grid.innerHTML=activeTracks.length?activeTracks.map(track=>{const reviewed=track.human_review==='approved';return `<article class="asset-card music-card ${reviewed?'music-reviewed':''}"><span class="tag">${reviewed?'ESCUTA APROVADA':esc(track.license_type)}</span><h3>${esc(track.name)}</h3><p>${esc(String(track.path).split(/[\\/]/).pop())}</p><audio controls preload="none" aria-label="Ouvir ${esc(track.name)}"><source src="/api/music-assets/${Number(track.id)}/preview"></audio><small>Usada em ${Number(track.use_count||0)} vídeo(s) · ${reviewed?'✓ som aprovado':'escuta pendente'}</small><div class="music-review-actions"><button class="primary" type="button" data-music-review="approved" data-track-id="${Number(track.id)}" ${reviewed?'disabled':''}>${reviewed?'✓ Aprovada':'Aprovar faixa'}</button><button class="secondary danger" type="button" data-music-review="rejected" data-track-id="${Number(track.id)}">Reprovar</button></div></article>`}).join(''):'<div class="empty"><b>Sua biblioteca musical está vazia.</b><p>Clique em “Importar músicas” e informe uma pasta com suas faixas lo-fi licenciadas.</p></div>';
  select.innerHTML='<option value="">Automática · usar primeiro a menos repetida</option>'+activeTracks.map(track=>`<option value="${Number(track.id)}">${esc(track.name)} · usada ${Number(track.use_count||0)}x</option>`).join('');
  grid.onclick=async event=>{
    const button=event.target.closest('[data-music-review]');if(!button)return;
    const decision=button.dataset.musicReview;button.disabled=true;
    try{
      await api(`/api/music-assets/${Number(button.dataset.trackId)}/review`,{method:'POST',body:JSON.stringify({decision})});
      apiCache.clear();await Promise.all([loadMusicAssets(),loadCatalogReadiness()]);
      toast(decision==='approved'?'Faixa aprovada após a escuta.':'Faixa reprovada e retirada da rotação.',decision==='approved'?'success':'info');
    }catch(error){button.disabled=false;toast(error.message,'error')}
  };
}

async function loadCatalogReadiness(){
  const data=await api('/api/library/readiness');
  const panel=$('#catalog-readiness');
  panel.dataset.ready=String(!!data.ready);
  panel.innerHTML=`<div><p class="kicker">LOTE PILOTO · ${data.ready?'PRONTO':'PREPARAÇÃO'}</p><h3>${data.ready?'Catálogo com variedade mínima':'Complete o catálogo antes de renderizar em escala'}</h3><p>${esc(data.ready?data.policy:(data.blockers||[]).join(' '))}</p></div><div class="catalog-checks">${(data.checks||[]).map(check=>`<span class="${check.passed?'pass':'planned'}"><b>${check.passed?'✓':'!'}</b> ${esc(check.label)} · ${Number(check.value)}/${Number(check.target)}</span>`).join('')}</div>${data.music_tracks<12?'<button class="primary" id="bootstrap-music" type="button">Criar 12 músicas originais</button>':data.ready?'<span class="catalog-ready-badge">✓ rotação liberada</span>':'<span class="catalog-ready-badge pending">! escuta pendente</span>'}`;
  $('#bootstrap-music')?.addEventListener('click',bootstrapMusicCatalog);
}

async function bootstrapMusicCatalog(event){
  const button=event.currentTarget;button.disabled=true;button.textContent='Compondo catálogo…';
  try{
    const result=await api('/api/music-assets/bootstrap',{method:'POST',timeoutMs:600000,body:'{}'});
    apiCache.clear();await Promise.all([loadMusicAssets(),loadCatalogReadiness()]);
    toast(`${result.registered} músicas originais prontas para rotação.`,'success');
  }catch(error){toast(error.message,'error');button.disabled=false;button.textContent='Criar 12 músicas originais'}
}

async function loadFlowMusicGuide(){
  const root=$('#flow-music-guide');
  try{
    const data=await api('/api/music-sources/flow');
    const connected=!!data.api?.configured;
    root.dataset.connected=String(connected);
    root.innerHTML=`<div class="flow-guide-head"><div><p class="kicker">FLOW MUSIC BRIDGE · GOOGLE AI PLUS</p><h3>Seu produtor musical conectado à operação</h3><p>Use os créditos do plano Starter no Flow Music, baixe as faixas e traga o lote para a rotação da FFactory. O Google protege o login em uma aba própria; a API paga fica somente como alternativa.</p></div><div class="flow-actions"><a class="primary flow-launch" href="https://www.flowmusic.app/" target="_blank" rel="noopener noreferrer">▶ Abrir Flow Music ↗</a><button class="secondary" id="flow-import-music" type="button">＋ Importar downloads</button></div></div><div class="lyria-cost"><b>✓ Starter · uso comercial</b><span>3.000 créditos mensais do plano</span><span>Até 8 gerações simultâneas</span><span>Montagem final de 30/60 min continua local</span></div><ol>${(data.workflow||[]).map(step=>`<li>${esc(step)}</li>`).join('')}</ol><details><summary>Prompts e automação avançada</summary><div class="flow-prompt-grid">${(data.prompts||[]).map(item=>`<article><div><b>${esc(item.name)}</b><span><button class="secondary" type="button" data-copy-flow="${esc(item.prompt)}">Copiar</button>${connected?`<button class="primary" type="button" data-generate-flow="${esc(item.prompt)}" data-flow-name="${esc(item.name)}">Gerar via API</button>`:''}</span></div><p>${esc(item.prompt)}</p></article>`).join('')}</div><div class="api-alternative">${connected?`<b>Gemini API conectada.</b><button class="secondary" id="lyria-generate" type="button">Gerar via API</button>${data.api.key_source==='encrypted_vault'?'<button class="secondary" id="lyria-disconnect" type="button">Desconectar API</button>':''}`:'<b>Automação total opcional e cobrada separadamente.</b><button class="secondary" id="lyria-connect" type="button">Conectar Gemini API</button>'}</div></details>`;
    $('#flow-import-music').onclick=()=>$('#music-dialog').showModal();
    $('#lyria-connect')?.addEventListener('click',()=>$('#lyria-key-dialog').showModal());
    $('#lyria-generate')?.addEventListener('click',()=>openLyriaGeneration('', ''));
    $('#lyria-disconnect')?.addEventListener('click',async()=>{try{await api('/api/music-sources/lyria/disconnect',{method:'POST',body:'{}'});apiCache.clear();await loadFlowMusicGuide();toast('Chave removida do cofre local.','success')}catch(error){toast(error.message,'error')}});
    root.querySelectorAll('[data-generate-flow]').forEach(button=>button.addEventListener('click',()=>connected?openLyriaGeneration(button.dataset.flowName,button.dataset.generateFlow):$('#lyria-key-dialog').showModal()));
    root.querySelectorAll('[data-copy-flow]').forEach(button=>button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(button.dataset.copyFlow);toast('Prompt copiado.','success')}catch(_error){toast('Não foi possível copiar automaticamente.','error')}}));
  }catch(error){root.innerHTML=`<div class="empty"><b>Guia do Flow Music indisponível.</b><p>${esc(error.message)}</p></div>`}
}

function openLyriaGeneration(name,prompt){
  const form=$('#lyria-generate-form');
  form.elements.name.value=name||`Lyria ${new Date().toLocaleDateString('pt-BR')}`;
  form.elements.prompt.value=prompt||'Instrumental lo-fi chill, warm Rhodes piano, soft drums, rounded bass, rainy late-night mood, 72 BPM, 2 to 3 minutes, loop-friendly ending, no vocals, no samples, no artist imitation.';
  $('#lyria-generate-error').textContent='';
  $('#lyria-generate-dialog').showModal();
}

$('#lyria-key-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const fields=new FormData(form);const error=$('#lyria-key-error');const button=event.submitter;error.textContent='';button.disabled=true;button.textContent='Protegendo chave…';
  try{await api('/api/music-sources/lyria/configure',{method:'POST',body:JSON.stringify({api_key:fields.get('api_key')})});form.reset();$('#lyria-key-dialog').close();apiCache.clear();await loadFlowMusicGuide();toast('Lyria 3 conectado com chave criptografada.','success')}catch(problem){error.textContent=problem.message}finally{button.disabled=false;button.textContent='Salvar com segurança'}
});

$('#lyria-generate-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const fields=new FormData(form);const error=$('#lyria-generate-error');const button=event.submitter;error.textContent='';button.disabled=true;button.textContent='Gerando no Google…';
  try{const result=await api('/api/music-sources/lyria/generate',{method:'POST',timeoutMs:600000,body:JSON.stringify({name:fields.get('name'),prompt:fields.get('prompt'),model:fields.get('model'),rights_confirmed:!!fields.get('rights_confirmed')})});form.reset();$('#lyria-generate-dialog').close();apiCache.clear();await Promise.all([loadMusicAssets(),loadCatalogReadiness()]);toast(`${result.name} foi gerada, validada e adicionada à Biblioteca.`,'success')}catch(problem){error.textContent=problem.message}finally{button.disabled=false;button.textContent='Gerar e adicionar à Biblioteca'}
});

$('#new-music').onclick=()=>$('#music-dialog').showModal();
$('#migrate-covers').onclick=async event=>{const button=event.currentTarget;button.disabled=true;button.textContent='Atualizando capas…';try{const result=await api('/api/covers/migrate',{method:'POST',timeoutMs:180000,body:'{}'});apiCache.clear();await load();toast(result.count?`${result.count} produção(ões) atualizada(s); capas antigas preservadas em backup.`:'Todas as capas já usam o padrão atual.','success')}catch(error){toast(error.message,'error')}finally{button.disabled=false;button.textContent='↻ Atualizar capas antigas'}};
$('#music-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const fields=new FormData(form);const error=$('#music-form-error');error.textContent='';
  const button=event.submitter;button.disabled=true;button.textContent='Validando arquivos…';
  try{
    const result=await api('/api/music-assets',{method:'POST',timeoutMs:180000,body:JSON.stringify({name:fields.get('name'),path:fields.get('path'),license_type:fields.get('license_type'),source_url:fields.get('source_url'),notes:fields.get('notes'),rights_confirmed:!!fields.get('rights_confirmed'),replace_synthetic_catalog:!!fields.get('replace_synthetic_catalog')})});
    form.reset();$('#music-dialog').close();apiCache.clear();await Promise.all([loadMusicAssets(),loadCatalogReadiness()]);toast(`${result.count} música(s) validadas${result.archived?` · ${result.archived} antigas arquivadas`:''}.`,'success');
  }catch(problem){error.textContent=problem.message}finally{button.disabled=false;button.textContent='Validar e importar'}
});

function artifactRows(data,type){
  if(type==='metadata.json')return [
    ['Título',data.title||'—'],['Duração',formatDuration(Number(data.production?.duration_seconds||data.verification?.duration_seconds||0))],
    ['Música',data.music?.track_name||data.music?.arrangement||'Trilha original'],['Origem musical',data.music?.style==='licensed_music_library'?'Biblioteca licenciada':'Gerada localmente'],
    ['Ritmo',data.music?.rhythm_pattern||'Definido pela faixa'],['Cena',data.creative_dna?.scene||'—'],['Movimento',data.motion?.atmosphere||'—'],
    ['Câmera',data.motion?.camera_motion==='none'?'Fixa':'Revisar'],['Qualidade',`${Number(data.quality_gate?.score||0)}/100`]
  ];
  if(type==='render-report.json')return [
    ['Resultado',data.passed?'Arquivo validado':'Revisão necessária'],['Duração real',formatDuration(Math.round(Number(data.duration_seconds||0)))],
    ['Vídeo',`${data.video?.width||'—'}×${data.video?.height||'—'} · ${data.video?.codec||'—'}`],['Áudio',`${data.audio?.codec||'—'} · ${data.audio?.sample_rate||'—'} Hz`],
    ['Tamanho',`${(Number(data.size_bytes||0)/1048576).toFixed(1)} MB`],['Validação',data.validation_engine||'—']
  ];
  if(type==='quality-gate.json')return (data.checks||[]).map(check=>[check.passed?'✓ '+check.label:'! '+check.label,check.passed?'Aprovado':String(check.value||'Revisar')]);
  if(type==='artifact-manifest.json')return (data.files||[]).map(file=>[file.name,`${(Number(file.size_bytes||0)/1048576).toFixed(1)} MB · íntegro`]);
  return [];
}

async function openArtifact(jobId,type){
  const labels={'metadata.json':'Resumo do vídeo','render-report.json':'Relatório técnico','artifact-manifest.json':'Integridade dos arquivos','quality-gate.json':'Controle de qualidade'};
  try{
    const data=await api(`/api/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(type)}`);const rows=artifactRows(data,type);
    $('#artifact-detail').innerHTML=`<div class="dialog-head"><div><p class="kicker">LEITURA SIMPLIFICADA</p><h2>${esc(labels[type]||'Detalhes')}</h2></div><button class="icon-button" type="button" data-dialog-close aria-label="Fechar">×</button></div><div class="artifact-summary">${rows.map(([label,value])=>`<article><small>${esc(label)}</small><b>${esc(value)}</b></article>`).join('')}</div><div class="dialog-actions"><button class="primary" type="button" data-dialog-close>Entendi</button></div>`;
    $('#artifact-dialog').showModal();
  }catch(error){toast(error.message,'error')}
}

document.addEventListener('click',event=>{const button=event.target.closest('[data-artifact]');if(button){event.preventDefault();openArtifact(button.dataset.artifactJob,button.dataset.artifact)}});

$('#new-asset').onclick=()=>$('#asset-dialog').showModal();
$('#asset-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=event.currentTarget;
  const fields=new FormData(form);
  $('#asset-form-error').textContent='';
  try{
    await api('/api/assets',{method:'POST',body:JSON.stringify({
      name:fields.get('name'),path:fields.get('path'),license_type:fields.get('license_type'),
      source_url:fields.get('source_url'),notes:fields.get('notes'),rights_confirmed:!!fields.get('rights_confirmed'),
    })});
    form.reset();
    $('#asset-dialog').close();
    await loadAssets();
    toast('Asset registrado e liberado para produções.','success');
  }catch(error){$('#asset-form-error').textContent=error.message}
});

$('#create-dialog').addEventListener('click',event=>{if(event.target===$('#create-dialog'))$('#create-dialog').close()});
$('#job-dialog').addEventListener('click',event=>{if(event.target===$('#job-dialog'))$('#job-dialog').close()});
Promise.all([load(),loadAssets(),loadMusicAssets(),loadCatalogReadiness(),loadFlowMusicGuide(),api('/api/agents').then(renderAgents)]);setInterval(()=>{if(state.jobs.some(j=>activeStatuses.has(j.status)))load()},3000);
