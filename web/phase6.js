let autopilotState={enabled:false,series_ids:[],cadence:3,publish_hour:'19:00',duration:3600};

function renderAutopilotSeries(){
  const root=document.querySelector('#autopilot-series');
  root.innerHTML=phaseSeries.map(item=>`<label><input type="checkbox" name="series_ids" value="${esc(item.id)}"> <span>${esc(item.name)}</span></label>`).join('');
  root.querySelectorAll('[name=series_ids]').forEach(input=>input.checked=(autopilotState.series_ids||[]).includes(input.value));
}

async function loadAutopilot(){
  try{
    autopilotState=await phaseApi('/api/autopilot');
    const card=document.querySelector('#autopilot-card');
    card.classList.toggle('active',autopilotState.mode==='active');
    card.classList.toggle('paused',autopilotState.mode==='paused');
    document.querySelector('#autopilot-title').textContent=autopilotState.mode==='active'?'Automação editorial ativa':autopilotState.mode==='paused'?'Automação pausada com segurança':'Automação editorial desligada';
    document.querySelector('#autopilot-detail').textContent=autopilotState.blockers?.[0]||`${autopilotState.planned||0} na agenda · ${autopilotState.cadence||3} por semana · ${autopilotState.publish_hour||'19:00'}`;
    document.querySelector('#autopilot-toggle').textContent=autopilotState.mode==='active'?'Pausar':autopilotState.enabled?'Desativar':'Ativar';
  }catch(error){toast(error.message)}
}

function autopilotPayload(enabled){
  const data=new FormData(document.querySelector('#autopilot-form'));
  return {enabled,series_ids:data.getAll('series_ids'),cadence:Number(data.get('cadence')),publish_hour:data.get('publish_hour'),duration:Number(data.get('duration'))};
}

document.querySelector('#autopilot-configure').onclick=async()=>{
  if(!phaseSeries.length)await loadPhase2();
  const form=document.querySelector('#autopilot-form');
  form.querySelector('[name=cadence]').value=autopilotState.cadence||3;
  form.querySelector('[name=publish_hour]').value=autopilotState.publish_hour||'19:00';
  form.querySelector('[name=duration]').value=Number(autopilotState.duration)>=3600?'3600':'1800';
  renderAutopilotSeries();
  document.querySelector('#autopilot-dialog').showModal();
};
document.querySelector('#autopilot-toggle').onclick=async()=>{
  try{
    const body={...autopilotState,enabled:!autopilotState.enabled};
    await phaseApi('/api/autopilot',{method:'POST',body:JSON.stringify(body)});
    toast(body.enabled?'Automação ativada.':'Automação pausada.');
    await Promise.all([loadAutopilot(),loadPhase2()]);
  }catch(error){toast(error.message)}
};
document.querySelector('#autopilot-form').addEventListener('submit',async event=>{
  event.preventDefault();
  try{
    await phaseApi('/api/autopilot',{method:'POST',body:JSON.stringify(autopilotPayload(true))});
    document.querySelector('#autopilot-dialog').close();
    toast('Ritmo salvo e automação ativada.');
    await Promise.all([loadAutopilot(),loadPhase2()]);
  }catch(error){toast(error.message)}
});
document.querySelector('#autopilot-plan-now').onclick=async()=>{
  try{
    await phaseApi('/api/autopilot',{method:'POST',body:JSON.stringify(autopilotPayload(false))});
    const result=await phaseApi('/api/autopilot/plan',{method:'POST',body:'{}'});
    document.querySelector('#autopilot-dialog').close();
    toast(`${result.count} conteúdo(s) planejado(s).`);
    await Promise.all([loadAutopilot(),loadPhase2()]);
  }catch(error){toast(error.message)}
};
loadAutopilot();
