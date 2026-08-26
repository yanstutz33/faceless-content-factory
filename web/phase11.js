let nightState={enabled:false,start_hour:'22:00',end_hour:'07:00',batch_limit:2,mode:'off'};
async function loadNightShift(){
  try{
    nightState=await phaseApi('/api/night-shift');
    const card=document.querySelector('#night-card');card.classList.toggle('active',nightState.mode==='active');card.classList.toggle('blocked',nightState.mode==='blocked');
    const labels={off:'Turno noturno desligado',waiting:'Aguardando a janela noturna',active:'Turno noturno pronto',blocked:'Turno pausado com segurança'};
    document.querySelector('#night-title').textContent=labels[nightState.mode]||'Operação noturna';
    const last=nightState.last_summary||{};
    document.querySelector('#night-detail').textContent=nightState.blockers?.[0]||`${nightState.start_hour}–${nightState.end_hour} · até ${nightState.batch_limit} produção(ões) · ${last.created?.length||0} iniciada(s) no último turno`;
  }catch(error){toast(error.message)}
}
document.querySelector('#night-configure').onclick=()=>{const form=document.querySelector('#night-form');form.querySelector('[name=enabled]').checked=!!nightState.enabled;form.querySelector('[name=start_hour]').value=nightState.start_hour||'22:00';form.querySelector('[name=end_hour]').value=nightState.end_hour||'07:00';form.querySelector('[name=batch_limit]').value=String(nightState.batch_limit||2);document.querySelector('#night-dialog').showModal()};
document.querySelector('#night-form').addEventListener('submit',async event=>{event.preventDefault();const f=new FormData(event.currentTarget);try{await phaseApi('/api/night-shift',{method:'POST',body:JSON.stringify({enabled:!!f.get('enabled'),start_hour:f.get('start_hour'),end_hour:f.get('end_hour'),batch_limit:Number(f.get('batch_limit'))})});document.querySelector('#night-dialog').close();toast('Turno noturno salvo.');loadNightShift()}catch(error){toast(error.message)}});
document.querySelector('#night-run').onclick=async()=>{const button=document.querySelector('#night-run');button.disabled=true;try{const result=await phaseApi('/api/night-shift/run',{method:'POST',body:'{}'});toast(`${result.created?.length||0} produção(ões) iniciada(s); nenhum upload realizado.`);loadNightShift();loadPhase2();load()}catch(error){toast(error.message)}finally{button.disabled=false}};
loadNightShift();

